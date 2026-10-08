"""One bounded, lazy pool for a single-process local Django application.

Web entrypoints call initialize_runtime BEFORE creating their first run, then
schedule submit via transaction.on_commit. Imports, AppConfig and migrations
never recover runs or start workers. Management commands opt in explicitly.
"""

import atexit
import hashlib
import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from uuid import UUID

from django.conf import settings
from django.db import close_old_connections, connections
from django.utils import timezone

from analyses.models import AnalysisRun, RunState
from analyses.services.artifacts import FilesystemArtifactStore
from analyses.services.bert import record_bert_error, run_bert
from analyses.services.pipeline import DjangoAnalysisPipeline
from app.risk_analysis.base import RiskAnalyzer
from app.risk_analysis.bertimbau import BertimbauRiskAnalyzer, HuggingFaceBucketStore
from app.risk_analysis.disabled import DisabledRiskAnalyzer

_log = logging.getLogger(__name__)
_ACTIVE = (RunState.QUEUED, RunState.RUNNING)
_SUCCESS = (RunState.COMPLETED, RunState.COMPLETED_WITH_LIMITATIONS)
_runtime_lock = Lock()
_executor = None
_initialized = False


class ExecutorCapacityError(RuntimeError):
    """All workers and queue slots are occupied."""


class LocalAnalysisExecutor:
    def __init__(
        self,
        runner: Callable[[UUID], object],
        *,
        max_workers: int = 2,
        max_queued: int = 10,
        analyzer: RiskAnalyzer | None = None,
        artifact_store: FilesystemArtifactStore | None = None,
    ):
        if max_workers < 1 or max_queued < 0:
            raise ValueError("Invalid executor capacity")
        self._runner = runner
        self._analyzer = analyzer or DisabledRiskAnalyzer()
        # Bound pipeline methods carry the exact store/root used for input.txt.
        self._store = artifact_store or getattr(
            getattr(runner, "__self__", None), "artifact_store", None
        )
        if self._store is None:
            config = settings.APP_SETTINGS
            self._store = FilesystemArtifactStore(
                config.artifacts_dir, max_bytes=config.max_artifact_bytes_per_analysis
            )
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="verificaai")
        self._limit = max_workers + max_queued
        self._lock = Lock()
        self._closed = False
        self._futures: dict[UUID, Future] = {}

    def submit(self, run_id: UUID) -> None:
        run_id = UUID(str(run_id))
        with self._lock:
            if self._closed:
                raise RuntimeError("Executor is shut down")
            if run_id in self._futures:
                return
            if AnalysisRun.objects.get(pk=run_id).state != RunState.QUEUED:
                return
            if len(self._futures) >= self._limit:
                raise ExecutorCapacityError("A fila de análises atingiu sua capacidade")
            future = self._pool.submit(self._execute, run_id)
            self._futures[run_id] = future
        # Immediate callbacks and cancelled futures must not reacquire a held lock.
        future.add_done_callback(lambda done: self._release(run_id))

    def _release(self, run_id):
        with self._lock:
            self._futures.pop(run_id, None)

    def _execute(self, run_id):
        close_old_connections()
        try:
            try:
                self._runner(run_id)
                run = AnalysisRun.objects.get(pk=run_id)
                if run.state in _ACTIVE:
                    raise RuntimeError("Runner returned without terminal factual persistence")
            except Exception:
                now = timezone.now()
                AnalysisRun.objects.filter(pk=run_id, state__in=_ACTIVE).update(
                    state=RunState.FAILED,
                    error_code="EXECUTOR_ERROR",
                    error_message="Falha técnica ao executar a análise.",
                    finished_at=now,
                    updated_at=now,
                )
                return
            if run.state not in _SUCCESS:
                return
            try:
                text = self._input_text(run)
            except Exception:
                record_bert_error(run_id, "BERT_INPUT_ERROR")
                return
            run_bert(run_id, text, self._analyzer)
        except Exception:
            # A persistence outage cannot safely be rewritten into a BERT verdict.
            # Log identifiers only; providers/DB exceptions can contain private input.
            _log.error("Local worker persistence failure for run %s", run_id)
        finally:
            connections.close_all()

    def _input_text(self, run):
        ref = run.trace["input"]
        relative = Path(ref["relative_path"])
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or relative.parts != (str(run.pk), "input.txt")
        ):
            raise ValueError("Unsafe input artifact path")
        root = self._store.root
        path = root / relative
        if path.is_symlink() or path.parent.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("Input artifact escapes root")
        size = ref["size_bytes"]
        if type(size) is not int or not 0 <= size <= self._store.max_bytes:
            raise ValueError("Invalid input artifact size")
        with path.open("rb") as stream:
            content = stream.read(size + 1)
        if len(content) != size or hashlib.sha256(content).hexdigest() != ref["sha256"]:
            raise ValueError("Input artifact integrity mismatch")
        return content.decode("utf-8")

    def shutdown(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._pool.shutdown(wait=False, cancel_futures=True)


def recover_interrupted_runs() -> int:
    """Explicit startup recovery; never run while this process has active work."""
    now = timezone.now()
    return AnalysisRun.objects.filter(state__in=_ACTIVE).update(
        state=RunState.FAILED,
        error_code="PROCESS_INTERRUPTED",
        error_message="A execução foi interrompida. Solicite uma nova análise.",
        finished_at=now,
        updated_at=now,
    )


def _build_executor():
    config = settings.APP_SETTINGS
    providers = None
    if config.provider_mode == "fake":
        from app.services.demo import DemoServices

        providers = DemoServices()
    pipeline = DjangoAnalysisPipeline(
        claim_extractor=providers,
        query_generator=providers,
        search_provider=providers,
        judge=providers,
        document_loader=providers,
        settings=config,
    )
    analyzer = DisabledRiskAnalyzer()
    if config.risk_model_mode == "bertimbau":
        analyzer = BertimbauRiskAnalyzer(
            store=HuggingFaceBucketStore(
                cache_dir=config.bertimbau_cache_dir,
                token=config.hf_token.get_secret_value() if config.hf_token else None,
            ),
            max_length=config.bertimbau_max_input_tokens,
        )
    return LocalAnalysisExecutor(
        pipeline.run,
        max_workers=config.max_concurrent_analyses,
        max_queued=config.max_queued_jobs,
        analyzer=analyzer,
    )


def _get_executor_locked():
    global _executor
    if _executor is None:
        _executor = _build_executor()
    return _executor


def get_executor() -> LocalAnalysisExecutor:
    """Obtain the pool lazily, without database recovery or started threads."""
    with _runtime_lock:
        return _get_executor_locked()


def initialize_runtime() -> LocalAnalysisExecutor:
    """Recover exactly once BEFORE a web entrypoint creates new runs."""
    global _initialized
    with _runtime_lock:
        if not _initialized:
            recover_interrupted_runs()
            _initialized = True
        return _get_executor_locked()


def shutdown_executor() -> None:
    global _executor
    with _runtime_lock:
        if _executor is not None:
            _executor.shutdown()
            _executor = None


atexit.register(shutdown_executor)
