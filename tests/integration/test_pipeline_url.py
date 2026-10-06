from __future__ import annotations

import json
from pathlib import Path

from app.core.enums import AnalysisStatus
from app.core.schemas import AnalysisCreate
from app.services.pipeline import LoadedInput
from tests.integration.test_pipeline_text import pipeline_factory as _pipeline_factory

PIPELINE_FIXTURE = _pipeline_factory


def test_url_pipeline_uses_loader_and_preserves_source_metadata(PIPELINE_FIXTURE) -> None:
    scenario = json.loads(Path("tests/fixtures/demo/supported.json").read_text())
    pipeline, repository, sessions = PIPELINE_FIXTURE(scenario)
    pipeline.url_loader = lambda url: LoadedInput(
        text=scenario["text"], title="Documento de entrada", canonical_url=url
    )
    created = repository.create(
        AnalysisCreate(input_type="url", content="https://entrada.example/noticia")
    )

    result = pipeline.run(created.id)

    assert result.status == AnalysisStatus.COMPLETED
    assert result.clean_text == scenario["text"]
    with sessions() as session:
        stored = session.get(type(result), created.id)
        assert stored.original_input == "https://entrada.example/noticia"


def test_url_collection_error_does_not_become_absence_of_evidence(PIPELINE_FIXTURE) -> None:
    scenario = json.loads(Path("tests/fixtures/demo/supported.json").read_text())
    pipeline, repository, _ = PIPELINE_FIXTURE(scenario)
    pipeline.url_loader = lambda url: (_ for _ in ()).throw(TimeoutError(url))
    created = repository.create(
        AnalysisCreate(input_type="url", content="https://entrada.example/noticia")
    )

    result = pipeline.run(created.id)

    assert result.status == AnalysisStatus.FAILED
    assert result.error_code == "COLLECTION_TECHNICAL_ERROR"
