"""Small, filesystem-only artifact store for local analysis runs."""

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from uuid import UUID

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}\Z")
_WRITE_LOCK = Lock()


class ArtifactLimitExceeded(ValueError):
    """The run's artifact quota would be exceeded."""


@dataclass(frozen=True)
class ArtifactRef:
    relative_path: str
    sha256: str
    size_bytes: int
    media_type: str


class FilesystemArtifactStore:
    def __init__(self, root: Path, *, max_bytes: int = 25 * 1024 * 1024) -> None:
        self.root = Path(root).resolve()
        self.max_bytes = max_bytes

    def store(self, run_id: UUID, name: str, content: bytes, media_type: str) -> ArtifactRef:
        run_key = str(UUID(str(run_id)))
        if not _NAME.fullmatch(name) or ".." in name:
            raise ValueError("Unsafe artifact name")
        if len(content) > self.max_bytes:
            raise ArtifactLimitExceeded("Artifact storage budget exceeded")
        directory = self.root / run_key
        destination = directory / name
        with _WRITE_LOCK:
            self._check_path(directory, destination)
            directory.mkdir(parents=True, exist_ok=True)
            self._check_path(directory, destination)
            used = sum(path.stat().st_size for path in directory.iterdir() if path.is_file())
            previous = destination.stat().st_size if destination.exists() else 0
            if used - previous + len(content) > self.max_bytes:
                raise ArtifactLimitExceeded("Artifact storage budget exceeded")
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    dir=directory, prefix=".artifact-", delete=False
                ) as f:
                    temporary = Path(f.name)
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())
                self._check_path(directory, destination)
                temporary.replace(destination)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        return ArtifactRef(
            relative_path=f"{run_key}/{name}",
            sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
            media_type=media_type,
        )

    def _check_path(self, directory: Path, destination: Path) -> None:
        if directory.is_symlink() or destination.is_symlink():
            raise ValueError("Artifact symlinks are not allowed")
        if not directory.resolve().is_relative_to(self.root):
            raise ValueError("Artifact directory escapes root")
        if not destination.resolve().is_relative_to(self.root):
            raise ValueError("Artifact destination escapes root")
