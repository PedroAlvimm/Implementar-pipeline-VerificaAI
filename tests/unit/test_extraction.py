from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import CollectionError
from app.scraping.block_detection import BlockDetector, BlockReason
from app.scraping.extraction import ArticleExtractor, CollectedPage

FIXTURES = Path(__file__).parents[1] / "fixtures" / "html"


def page(name: str) -> CollectedPage:
    return CollectedPage(
        requested_url="https://example.org/news",
        final_url="https://example.org/news",
        html=(FIXTURES / name).read_text(),
        content_type="text/html; charset=utf-8",
    )


def test_article_extraction_preserves_metadata_numbers_and_negation() -> None:
    article = ArticleExtractor().extract(page("article.html"))

    assert article.title == "Contrato municipal"
    assert article.subtitle == "Aquisição pública de vacinas"
    assert article.author == "Maria Silva"
    assert article.published_at.isoformat() == "2026-01-15T10:00:00-03:00"
    assert article.canonical_url == "https://example.org/contrato"
    assert article.language == "pt-BR"
    assert "não comprou 10 milhões" in article.clean_text
    assert "oito milhões" in article.clean_text
    assert article.extraction_method in {"trafilatura", "beautifulsoup"}


def test_jsonld_supplies_article_metadata() -> None:
    article = ArticleExtractor().extract(page("jsonld_article.html"))

    assert article.title == "Documento oficial"
    assert article.author == "Ana Lima"
    assert article.subtitle == "Resumo oficial"
    assert article.published_at.date().isoformat() == "2026-02-01"


def test_empty_page_is_not_treated_as_an_article() -> None:
    with pytest.raises(CollectionError, match="conteúdo jornalístico"):
        ArticleExtractor().extract(page("empty.html"))


def test_paywall_is_detected_before_extraction() -> None:
    assert BlockDetector().detect(page("paywall.html")) is BlockReason.PAYWALL
