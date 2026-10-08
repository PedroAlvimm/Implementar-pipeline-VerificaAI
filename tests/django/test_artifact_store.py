"""Artifacts are bounded, atomic and never escape the configured directory."""

from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest


def store(root, **kwargs):
    from analyses.services.artifacts import FilesystemArtifactStore

    return FilesystemArtifactStore(root, **kwargs)


def test_atomic_write_returns_only_relative_metadata(tmp_path, monkeypatch):
    run_id = uuid4()
    content = b"<html>document</html>"
    original_replace = Path.replace
    replaced = []

    def inspect_replace(source, target):
        assert source.read_bytes() == content
        assert not target.exists()
        replaced.append(target)
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", inspect_replace)
    ref = store(tmp_path).store(run_id, "page.html", content, "text/html")

    assert asdict(ref) == {
        "relative_path": f"{run_id}/page.html",
        "sha256": sha256(content).hexdigest(),
        "size_bytes": 21,
        "media_type": "text/html",
    }
    assert len(replaced) == 1
    assert (tmp_path / ref.relative_path).read_bytes() == content
    assert list((tmp_path / str(run_id)).iterdir()) == replaced


@pytest.mark.parametrize("name", ["../escape.html", "/tmp/escape", "x/../page", "..", ".", "x\\y"])
def test_unsafe_names_are_rejected(tmp_path, name):
    with pytest.raises(ValueError):
        store(tmp_path).store(uuid4(), name, b"data", "text/plain")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("symlink_target", ["directory", "file"])
def test_symlink_escape_is_rejected(tmp_path, symlink_target):
    root = tmp_path / "artifacts"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    run_id = uuid4()
    directory = root / str(run_id)
    if symlink_target == "directory":
        directory.symlink_to(outside, target_is_directory=True)
    else:
        directory.mkdir()
        (directory / "page.html").symlink_to(outside / "page.html")
    with pytest.raises(ValueError):
        store(root).store(run_id, "page.html", b"data", "text/html")
    assert not list(outside.iterdir())


def test_size_limit_and_cumulative_run_quota(tmp_path):
    artifacts = store(tmp_path, max_bytes=5)
    run_id = uuid4()
    with pytest.raises(ValueError):
        artifacts.store(run_id, "large.txt", b"123456", "text/plain")
    artifacts.store(run_id, "one.txt", b"123", "text/plain")
    with pytest.raises(ValueError):
        artifacts.store(run_id, "two.txt", b"456", "text/plain")
    assert not (tmp_path / str(run_id) / "two.txt").exists()


def test_failed_replace_cleans_temporary_file(tmp_path, monkeypatch):
    run_id = uuid4()

    def fail_replace(source, target):
        raise OSError("disk unavailable")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError):
        store(tmp_path).store(run_id, "page.html", b"data", "text/html")
    assert not list((tmp_path / str(run_id)).iterdir())
