from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from app.api.dependencies import build_risk_analyzer
from app.core.config import Settings
from app.risk_analysis.bertimbau import (
    BertimbauPrediction,
    BertimbauRiskAnalyzer,
    BucketArtifact,
    BucketArtifactMismatchError,
    BucketModelSpec,
    HuggingFaceBucketStore,
    RemoteBucketArtifact,
)
from app.risk_analysis.disabled import DisabledRiskAnalyzer


@pytest.mark.parametrize(
    "change",
    [
        {"status": "unknown"},
        {"label": "FAKE"},
        {"score": float("nan")},
        {"score": float("inf")},
        {"score": -0.1},
        {"score": 1.1},
        {"score": "0.5"},
        {"extra": True},
        {"model_version": ""},
        {"status": "technical_error"},
    ],
)
def test_bert_result_rejects_invalid_provider_output(change):
    from pydantic import ValidationError

    from app.risk_analysis import base

    assert hasattr(base, "BERTResult"), "Strict BERT result is missing"
    payload = dict(
        status="available",
        label="FALSA",
        score=0.5,
        model_name="fixture",
        model_version="v1",
        message="Auxiliar",
    )
    with pytest.raises(ValidationError):
        base.BERTResult.model_validate(payload | change)


@pytest.mark.parametrize("tamper", ["extra", "hash", "symlink"])
def test_bucket_cache_revalidates_exact_snapshot_even_after_materializing(tmp_path, tamper):
    content = b"config"
    artifact = BucketArtifact("config.json", len(content), "xet", sha256(content).hexdigest())
    spec = BucketModelSpec("owner/bucket", "v1", (artifact,))
    target = tmp_path / "v1"
    target.mkdir()
    (target / "config.json").write_bytes(content)

    def remote(*args):
        raise BucketArtifactMismatchError("invalid local snapshot")

    store = HuggingFaceBucketStore(cache_dir=tmp_path, spec=spec, metadata_reader=remote)
    assert store.materialize() == target  # Valid pinned local data needs no bucket request.
    if tamper == "extra":
        (target / "untrusted.py").write_text("untrusted")
    elif tamper == "hash":
        (target / "config.json").write_bytes(b"tamper")
    else:
        outside = tmp_path / "outside.json"
        outside.write_bytes(content)
        (target / "config.json").unlink()
        (target / "config.json").symlink_to(outside)
    with pytest.raises(BucketArtifactMismatchError):
        store.materialize()


def test_disabled_risk_analyzer_never_returns_a_label_or_score() -> None:
    result = DisabledRiskAnalyzer().analyze("Uma afirmação qualquer.")

    assert result.model_dump() == {
        "status": "modelo_indisponivel",
        "label": None,
        "score": None,
        "model_name": None,
        "model_version": None,
        "message": "Análise linguística auxiliar indisponível; não altera o resultado factual.",
    }


class _Store:
    def __init__(self, model_dir: Path) -> None:
        self.model_dir = model_dir

    def materialize(self) -> Path:
        return self.model_dir


class _Backend:
    def __init__(self, prediction: BertimbauPrediction) -> None:
        self.prediction = prediction

    def predict(self, text: str, *, max_length: int) -> BertimbauPrediction:
        assert text == "Uma afirmação qualquer."
        assert max_length == 512
        return self.prediction


def test_bertimbau_returns_auxiliary_prediction_with_explicit_truncation(tmp_path: Path) -> None:
    prediction = BertimbauPrediction(label="FALSA", score=0.97, truncated=True)
    analyzer = BertimbauRiskAnalyzer(
        store=_Store(tmp_path),
        backend_factory=lambda model_dir: _Backend(prediction),
    )

    result = analyzer.analyze("Uma afirmação qualquer.")

    assert result.model_dump() == {
        "status": "available",
        "label": "FALSA",
        "score": 0.97,
        "model_name": "Alvinn007/bertimbau-fakenews-detector-v4-bucket",
        "model_version": "9fd0293af8b4e1b68d69d16911c7e5483394336ebeb11219c9246430e9cdc5fd",
        "message": (
            "Análise linguística auxiliar: FALSA (97,00%). O texto foi truncado para "
            "512 tokens. Este resultado não determina a veracidade factual."
        ),
    }


def test_bertimbau_failure_is_reported_without_inventing_a_prediction(tmp_path: Path) -> None:
    class FailingStore:
        def materialize(self) -> Path:
            raise OSError("offline")

    analyzer = BertimbauRiskAnalyzer(store=FailingStore())

    result = analyzer.analyze("Uma afirmação qualquer.")

    assert result["status"] == "technical_error"
    assert result["label"] is None
    assert result["score"] is None
    assert result["model_name"] == "Alvinn007/bertimbau-fakenews-detector-v4-bucket"
    assert "indisponível" in result["message"]
    assert "não altera" in result["message"]


def test_bucket_store_downloads_only_pinned_files_and_reuses_verified_cache(
    tmp_path: Path,
) -> None:
    contents = {"config.json": b"config", "model.safetensors": b"weights"}
    artifacts = tuple(
        BucketArtifact(
            path=path,
            size=len(content),
            xet_hash=f"xet-{path}",
            sha256=sha256(content).hexdigest(),
        )
        for path, content in contents.items()
    )
    spec = BucketModelSpec(
        bucket_id="owner/model-bucket",
        version="model-v1",
        artifacts=artifacts,
    )
    downloads = 0

    def metadata_reader(bucket_id: str, paths: tuple[str, ...], token: str | bool):
        assert bucket_id == "owner/model-bucket"
        assert paths == ("config.json", "model.safetensors")
        assert token is False
        return [
            RemoteBucketArtifact(path=item.path, size=item.size, xet_hash=item.xet_hash)
            for item in artifacts
        ]

    def downloader(
        bucket_id: str,
        files: tuple[tuple[str, Path], ...],
        token: str | bool,
    ) -> None:
        nonlocal downloads
        downloads += 1
        assert bucket_id == "owner/model-bucket"
        assert token is False
        for remote_path, local_path in files:
            local_path.write_bytes(contents[remote_path])

    store = HuggingFaceBucketStore(
        spec=spec,
        cache_dir=tmp_path,
        metadata_reader=metadata_reader,
        downloader=downloader,
    )

    first = store.materialize()
    second = store.materialize()

    assert first == second
    assert (first / "config.json").read_bytes() == b"config"
    assert (first / "model.safetensors").read_bytes() == b"weights"
    assert downloads == 1


def test_bucket_store_rejects_a_silently_replaced_remote_artifact(tmp_path: Path) -> None:
    content = b"config"
    artifact = BucketArtifact(
        path="config.json",
        size=len(content),
        xet_hash="expected-xet-hash",
        sha256=sha256(content).hexdigest(),
    )
    spec = BucketModelSpec(
        bucket_id="owner/model-bucket",
        version="model-v1",
        artifacts=(artifact,),
    )
    store = HuggingFaceBucketStore(
        spec=spec,
        cache_dir=tmp_path,
        metadata_reader=lambda bucket_id, paths, token: [
            RemoteBucketArtifact(
                path="config.json",
                size=len(content),
                xet_hash="replacement-xet-hash",
            )
        ],
        downloader=lambda bucket_id, files, token: pytest.fail("download must not start"),
    )

    with pytest.raises(BucketArtifactMismatchError, match=r"config\.json"):
        store.materialize()


def test_settings_enable_the_bucket_analyzer_without_loading_it(tmp_path: Path) -> None:
    analyzer = build_risk_analyzer(
        Settings(
            risk_model_mode="bertimbau",
            bertimbau_cache_dir=tmp_path,
            _env_file=None,
        )
    )

    assert isinstance(analyzer, BertimbauRiskAnalyzer)
