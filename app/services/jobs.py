from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from enum import StrEnum


class JobCapacityError(RuntimeError):
    pass


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class JobExecutor:
    def __init__(
        self,
        runner: Callable[[str], object],
        *,
        max_workers: int = 2,
        max_queued: int = 10,
    ) -> None:
        if max_workers < 1 or max_queued < 0:
            raise ValueError("Capacidade do executor inválida")
        self._runner = runner
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="verificaai")
        self._capacity = threading.BoundedSemaphore(max_workers + max_queued)
        self._lock = threading.Lock()
        self._statuses: dict[str, JobStatus] = {}
        self._errors: dict[str, str] = {}
        self._futures: dict[str, Future[None]] = {}

    def submit(self, analysis_id: str) -> JobStatus:
        with self._lock:
            existing = self._statuses.get(analysis_id)
            if existing is not None:
                return existing
            if not self._capacity.acquire(blocking=False):
                raise JobCapacityError("A fila de análises atingiu sua capacidade")
            self._statuses[analysis_id] = JobStatus.QUEUED
            self._futures[analysis_id] = self._pool.submit(self._execute, analysis_id)
            return JobStatus.QUEUED

    def _execute(self, analysis_id: str) -> None:
        with self._lock:
            self._statuses[analysis_id] = JobStatus.RUNNING
        try:
            self._runner(analysis_id)
        except Exception as exc:  # executor boundary must preserve worker availability
            with self._lock:
                self._statuses[analysis_id] = JobStatus.FAILED
                self._errors[analysis_id] = str(exc)
        else:
            with self._lock:
                self._statuses[analysis_id] = JobStatus.COMPLETED
        finally:
            self._capacity.release()

    def status(self, analysis_id: str) -> JobStatus:
        with self._lock:
            try:
                return self._statuses[analysis_id]
            except KeyError as exc:
                raise KeyError(analysis_id) from exc

    def error(self, analysis_id: str) -> str | None:
        with self._lock:
            return self._errors.get(analysis_id)

    def wait(self, analysis_id: str, timeout: float | None = None) -> JobStatus:
        with self._lock:
            future = self._futures.get(analysis_id)
        if future is None:
            raise KeyError(analysis_id)
        future.result(timeout=timeout)
        return self.status(analysis_id)

    def shutdown(self, wait: bool = True) -> None:
        self._pool.shutdown(wait=wait, cancel_futures=False)
