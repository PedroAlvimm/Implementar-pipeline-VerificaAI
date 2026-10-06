from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_frontend_entrypoint_resolves_client_when_executed_as_a_file() -> None:
    root = Path(__file__).resolve().parents[2]

    result = subprocess.run(
        [sys.executable, "frontend/app.py"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "ModuleNotFoundError" not in result.stderr
