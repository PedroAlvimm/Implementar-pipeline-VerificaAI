from __future__ import annotations

import gzip
import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.core.errors import CollectionError

_SAFE_ID = re.compile(r"^[A-Za-z0-9-]+$")


@dataclass(frozen=True)
class ArtifactMetadata:
    path: str
    sha256: str
    raw_size: int
    stored_size: int


class ArtifactStore:
    def __init__(self, root: Path, max_bytes_per_analysis: int = 25 * 1024 * 1024) -> None:
        self._root = root
        self._max_bytes = max_bytes_per_analysis

    def write_gzip(
        self, analysis_id: str, html: str, *, permitted: bool = True
    ) -> ArtifactMetadata:
        if not permitted:
            raise CollectionError("A persistência deste conteúdo não foi permitida")
        if not _SAFE_ID.fullmatch(analysis_id):
            raise CollectionError("O identificador da análise é inválido")
        raw = html.encode("utf-8")
        directory = self._root / analysis_id
        digest = hashlib.sha256(raw).hexdigest()
        destination = directory / f"{digest}.html.gz"
        if destination.is_file():
            return ArtifactMetadata(
                path=str(destination),
                sha256=digest,
                raw_size=len(raw),
                stored_size=destination.stat().st_size,
            )
        used = sum(
            len(gzip.decompress(path.read_bytes()))
            for path in directory.glob("*.html.gz")
            if path.is_file()
        )
        if used + len(raw) > self._max_bytes:
            raise CollectionError("A cota de artefatos da análise foi excedida")
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / f"{uuid4().hex}.tmp"
        compressed = gzip.compress(raw)
        temporary.write_bytes(compressed)
        os.replace(temporary, destination)
        return ArtifactMetadata(
            path=str(destination),
            sha256=digest,
            raw_size=len(raw),
            stored_size=len(compressed),
        )

    def cleanup_temporary_files(self) -> int:
        removed = 0
        if not self._root.exists():
            return removed
        for path in self._root.rglob("*.tmp"):
            if path.is_file():
                path.unlink()
                removed += 1
        return removed
