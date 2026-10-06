from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from app.core.errors import CollectionError
from app.database.artifacts import ArtifactStore


def test_artifact_store_writes_gzip_atomically_with_sha256(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path, max_bytes_per_analysis=1_000)

    metadata = store.write_gzip("analysis-123", "<html>ação</html>")

    assert Path(metadata.path).suffix == ".gz"
    assert gzip.decompress(Path(metadata.path).read_bytes()).decode() == "<html>ação</html>"
    assert len(metadata.sha256) == 64
    assert not list(tmp_path.rglob("*.tmp"))


def test_artifact_store_rejects_quota_path_traversal_and_forbidden_content(
    tmp_path: Path,
) -> None:
    store = ArtifactStore(tmp_path, max_bytes_per_analysis=10)

    with pytest.raises(CollectionError, match="cota"):
        store.write_gzip("analysis", "x" * 11)
    with pytest.raises(CollectionError, match="identificador"):
        store.write_gzip("../escape", "ok")
    with pytest.raises(CollectionError, match="permitida"):
        store.write_gzip("analysis", "ok", permitted=False)
    assert not list(tmp_path.rglob("*.gz"))


def test_artifact_store_removes_orphan_temporary_files(tmp_path: Path) -> None:
    orphan = tmp_path / "analysis" / "orphan.tmp"
    orphan.parent.mkdir()
    orphan.write_bytes(b"partial")

    removed = ArtifactStore(tmp_path).cleanup_temporary_files()

    assert removed == 1
    assert not orphan.exists()


def test_artifact_quota_counts_previously_stored_raw_content(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path, max_bytes_per_analysis=10)
    store.write_gzip("analysis", "123456")

    with pytest.raises(CollectionError, match="cota"):
        store.write_gzip("analysis", "abcdef")
