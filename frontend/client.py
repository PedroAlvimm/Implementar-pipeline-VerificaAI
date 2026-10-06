from __future__ import annotations

from typing import Any

import httpx


class ApiClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000", timeout: float = 10) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout)

    def submit(
        self,
        input_type: str,
        content: str,
        *,
        consent: bool = False,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        response = self._client.post(
            "/api/v1/analyses",
            json={
                "input_type": input_type,
                "content": content,
                "external_processing_consent": consent,
            },
            headers=headers,
        )
        response.raise_for_status()
        return response.json()

    def status(self, analysis_id: str) -> dict[str, Any]:
        response = self._client.get(f"/api/v1/analyses/{analysis_id}")
        response.raise_for_status()
        return response.json()

    def report(self, analysis_id: str) -> dict[str, Any]:
        response = self._client.get(f"/api/v1/analyses/{analysis_id}/report")
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        self._client.close()

