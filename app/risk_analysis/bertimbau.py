from __future__ import annotations

import shutil
import tempfile
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol

from app.risk_analysis.base import RiskAnalysisResult

BERTIMBAU_BUCKET_ID = "Alvinn007/bertimbau-fakenews-detector-v4-bucket"
BERTIMBAU_VERSION = "9fd0293af8b4e1b68d69d16911c7e5483394336ebeb11219c9246430e9cdc5fd"


@dataclass(frozen=True)
class BucketArtifact:
    path: str
    size: int
    xet_hash: str
    sha256: str


@dataclass(frozen=True)
class RemoteBucketArtifact:
    path: str
    size: int
    xet_hash: str


@dataclass(frozen=True)
class BucketModelSpec:
    bucket_id: str
    version: str
    artifacts: tuple[BucketArtifact, ...]


@dataclass(frozen=True)
class BertimbauPrediction:
    label: str
    score: float
    truncated: bool


BERTIMBAU_SPEC = BucketModelSpec(
    bucket_id=BERTIMBAU_BUCKET_ID,
    version=BERTIMBAU_VERSION,
    artifacts=(
        BucketArtifact(
            path="config.json",
            size=1_072,
            xet_hash="16480ba162b05f7c2976ea43b7fe3552ae91f0c944d57031e733d2844884ce91",
            sha256="44c2338d1d8d20d2eeaae22b95e004a9c1d4dc226ebff691bfa77533ada3b558",
        ),
        BucketArtifact(
            path="model.safetensors",
            size=435_722_224,
            xet_hash="9fd0293af8b4e1b68d69d16911c7e5483394336ebeb11219c9246430e9cdc5fd",
            sha256="61279dee660fb76950445330157f4bdc2ccde513eff896d7eb51c0f4393c6851",
        ),
        BucketArtifact(
            path="tokenizer.json",
            size=677_790,
            xet_hash="a555ffa5e5fe3f1047ccde359f6a20e586912be85ce5e529b1bf692feb6b6927",
            sha256="bcc8fe4209dffce14189a4319759f834e84c7df0a0bee8bfc6b576d4e2c6d387",
        ),
        BucketArtifact(
            path="tokenizer_config.json",
            size=380,
            xet_hash="6b322663b36113407e276c97c7bedb5c8827814a5d854d18488f8b12f24c93e2",
            sha256="4462f2399527c65c2eaaa75bf548f35fd0bf321f28c2d48e52b409767b6f4c86",
        ),
    ),
)


class BucketArtifactMismatchError(RuntimeError):
    """Raised when the mutable bucket no longer matches the pinned model."""


class ModelStore(Protocol):
    def materialize(self) -> Path: ...


class InferenceBackend(Protocol):
    def predict(self, text: str, *, max_length: int) -> BertimbauPrediction: ...


MetadataReader = Callable[[str, tuple[str, ...], str | bool], Iterable[RemoteBucketArtifact]]
BucketDownloader = Callable[[str, tuple[tuple[str, Path], ...], str | bool], None]


def _read_bucket_metadata(
    bucket_id: str,
    paths: tuple[str, ...],
    token: str | bool,
) -> Iterable[RemoteBucketArtifact]:
    from huggingface_hub import get_bucket_paths_info

    for item in get_bucket_paths_info(bucket_id, paths, token=token):
        yield RemoteBucketArtifact(path=item.path, size=item.size, xet_hash=item.xet_hash)


def _download_bucket_files(
    bucket_id: str,
    files: tuple[tuple[str, Path], ...],
    token: str | bool,
) -> None:
    from huggingface_hub import download_bucket_files

    download_bucket_files(
        bucket_id,
        list(files),
        raise_on_missing_files=True,
        token=token,
    )


class HuggingFaceBucketStore:
    """Materialize a pinned snapshot with an exact allowlist and verified hashes.

    A verified local snapshot stays valid without consulting the mutable bucket
    on each use. Local contents are verified again on every materialize call.
    """

    def __init__(
        self,
        *,
        cache_dir: Path,
        spec: BucketModelSpec = BERTIMBAU_SPEC,
        token: str | None = None,
        metadata_reader: MetadataReader = _read_bucket_metadata,
        downloader: BucketDownloader = _download_bucket_files,
    ) -> None:
        self.spec = spec
        self.cache_dir = cache_dir
        self.token: str | bool = token if token else False
        self.metadata_reader = metadata_reader
        self.downloader = downloader
        self._lock = threading.Lock()

    def materialize(self) -> Path:
        with self._lock:
            target = self.cache_dir / self.spec.version
            if self._is_valid_local_snapshot(target):
                return target
            self._validate_remote_snapshot()
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix=".download-", dir=self.cache_dir))
            try:
                files = tuple((item.path, staging / item.path) for item in self.spec.artifacts)
                self.downloader(self.spec.bucket_id, files, self.token)
                if not self._is_valid_local_snapshot(staging):
                    raise BucketArtifactMismatchError(
                        "Os arquivos baixados não correspondem ao snapshot fixado."
                    )
                if target.exists():
                    shutil.rmtree(target)
                staging.replace(target)
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
            return target

    def _validate_remote_snapshot(self) -> None:
        paths = tuple(item.path for item in self.spec.artifacts)
        remote = {
            item.path: item for item in self.metadata_reader(self.spec.bucket_id, paths, self.token)
        }
        for expected in self.spec.artifacts:
            actual = remote.get(expected.path)
            if (
                actual is None
                or actual.size != expected.size
                or actual.xet_hash != expected.xet_hash
            ):
                raise BucketArtifactMismatchError(
                    f"O artefato remoto {expected.path} não corresponde à versão fixada."
                )

    def _is_valid_local_snapshot(self, directory: Path) -> bool:
        if not directory.is_dir() or directory.is_symlink():
            return False
        # The pinned model has only top-level files; reject extras and symlinks.
        if {path.name for path in directory.iterdir()} != {
            artifact.path for artifact in self.spec.artifacts
        }:
            return False
        for artifact in self.spec.artifacts:
            path = directory / artifact.path
            if path.is_symlink() or not path.is_file() or path.stat().st_size != artifact.size:
                return False
            digest = sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() != artifact.sha256:
                return False
        return True


class TransformersBertimbauBackend:
    """Local-only Transformers inference over the verified safetensors snapshot."""

    def __init__(self, model_dir: Path) -> None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(
            model_dir,
            local_files_only=True,
            trust_remote_code=False,
        )
        self._model = AutoModelForSequenceClassification.from_pretrained(
            model_dir,
            local_files_only=True,
            trust_remote_code=False,
            use_safetensors=True,
        )
        labels = {int(index): label for index, label in self._model.config.id2label.items()}
        if labels != {0: "FALSA", 1: "VERDADEIRA"}:
            raise ValueError("O mapa de rótulos do BERTimbau é incompatível.")
        self._labels = labels
        self._model.eval()

    def predict(self, text: str, *, max_length: int) -> BertimbauPrediction:
        full_tokens = self._tokenizer(text, add_special_tokens=True, truncation=False)
        truncated = len(full_tokens["input_ids"]) > max_length
        encoded = self._tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=max_length,
        )
        with self._torch.inference_mode():
            output: Any = self._model(**encoded)
            probabilities = self._torch.softmax(output.logits, dim=-1)[0]
        index = int(self._torch.argmax(probabilities).item())
        return BertimbauPrediction(
            label=self._labels[index],
            score=float(probabilities[index].item()),
            truncated=truncated,
        )


class BertimbauRiskAnalyzer:
    """Auxiliary linguistic classifier that never determines a factual verdict."""

    def __init__(
        self,
        *,
        store: ModelStore,
        max_length: int = 512,
        backend_factory: Callable[[Path], InferenceBackend] = TransformersBertimbauBackend,
    ) -> None:
        self.store = store
        self.max_length = max_length
        self.backend_factory = backend_factory
        self._backend: InferenceBackend | None = None
        self._lock = threading.Lock()

    def analyze(self, text: str) -> RiskAnalysisResult:
        try:
            with self._lock:
                if self._backend is None:
                    self._backend = self.backend_factory(self.store.materialize())
                prediction = self._backend.predict(text, max_length=self.max_length)
            percentage = f"{prediction.score:.2%}".replace(".", ",")
            truncation = (
                f" O texto foi truncado para {self.max_length} tokens."
                if prediction.truncated
                else ""
            )
            return RiskAnalysisResult(
                status="available",
                label=prediction.label,
                score=prediction.score,
                model_name=BERTIMBAU_BUCKET_ID,
                model_version=BERTIMBAU_VERSION,
                message=(
                    f"Análise linguística auxiliar: {prediction.label} ({percentage})."
                    f"{truncation} Este resultado não determina a veracidade factual."
                ),
            )
        except Exception:
            return RiskAnalysisResult.model_validate(
                {
                    "status": "technical_error",
                    "label": None,
                    "score": None,
                    "model_name": BERTIMBAU_BUCKET_ID,
                    "model_version": BERTIMBAU_VERSION,
                    "message": (
                        "Análise linguística auxiliar indisponível por falha técnica; "
                        "isso não altera o resultado factual."
                    ),
                }
            )
