from __future__ import annotations

from datetime import UTC, datetime

from app.evidence.chunking import EvidenceDocument, chunk_document


def document(text: str) -> EvidenceDocument:
    return EvidenceDocument(
        id="doc_001",
        text=text,
        title="Contrato municipal",
        url="https://gov.example/contrato",
        domain="gov.example",
        published_at=datetime(2026, 1, 15, tzinfo=UTC),
        independence_group="grp_primary",
    )


def test_chunking_is_bounded_overlapping_and_preserves_metadata() -> None:
    text = (
        "O município não comprou 10 milhões de doses em janeiro de 2026. "
        "O contrato oficial prevê oito milhões de doses. "
        "A entrega ocorrerá em três etapas documentadas."
    )

    chunks = chunk_document(document(text), max_chars=90, overlap_chars=20)

    assert len(chunks) >= 2
    assert all(len(chunk.text) <= 90 for chunk in chunks)
    assert chunks[0].document_id == "doc_001"
    assert chunks[0].source_url == "https://gov.example/contrato"
    assert chunks[0].published_at.isoformat() == "2026-01-15T00:00:00+00:00"
    assert "não comprou 10 milhões" in chunks[0].text
    assert set(chunks[0].text[-20:].split()) & set(chunks[1].text[:30].split())


def test_chunk_ids_and_indexes_are_stable() -> None:
    source = document("Primeira frase verificável. Segunda frase verificável.")
    first = chunk_document(source, 35, 8)
    second = chunk_document(source, 35, 8)

    assert [chunk.evidence_id for chunk in first] == [chunk.evidence_id for chunk in second]
    assert [chunk.index for chunk in first] == list(range(len(first)))


def test_empty_document_produces_no_chunks() -> None:
    assert chunk_document(document("   "), 100, 10) == []
