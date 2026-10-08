from __future__ import annotations

from ipaddress import ip_address

import httpx
import pytest

from app.core.enums import OperationStatus
from app.core.outcomes import OperationOutcome
from app.ingestion.url_loader import LoadedUrl, UrlInputFailure, UrlInputLoader
from app.scraping.client import SafeCollector
from app.scraping.extraction import ArticleExtractor, CollectedPage
from app.scraping.robots import RobotsPolicy, RobotsResponse
from app.scraping.transport import PinnedHttpTransport
from app.scraping.url_policy import UrlPolicy


class PublicResolver:
    def resolve_public(self, hostname: str):
        del hostname
        return (ip_address("93.184.216.34"),)


def test_url_input_loader_collects_and_extracts_public_html() -> None:
    policy = UrlPolicy(PublicResolver())

    def connector(target, address, method, headers, content):
        del address, method, headers, content
        html = """
        <html lang="pt-BR"><head><title>Notícia de teste</title></head>
        <body><article><h1>Notícia de teste</h1>
        <p>O município publicou um documento oficial com dez itens nesta semana.</p>
        </article></body></html>
        """
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=html,
            request=httpx.Request("GET", target.url),
        )

    transport = PinnedHttpTransport(policy, connector=connector)
    robots = RobotsPolicy(lambda url: RobotsResponse(404, ""))
    collector = SafeCollector(policy, transport, robots)
    loader = UrlInputLoader(collector, ArticleExtractor())

    loaded = loader("https://public.example/noticia")

    assert loaded == LoadedUrl(
        text=(
            "Notícia de teste\nO município publicou um documento oficial "
            "com dez itens nesta semana."
        ),
        title="Notícia de teste",
        canonical_url="https://public.example/noticia",
        final_url="https://public.example/noticia",
    )


@pytest.mark.parametrize(
    "outcome,expected_code,expected_message",
    [
        (
            OperationOutcome(
                status=OperationStatus.BLOCKED,
                error_code="ROBOTS_UNKNOWN",
                error_message="A coleta não foi permitida; cole o texto para continuar.",
            ),
            "ROBOTS_UNKNOWN",
            "A coleta não foi permitida; cole o texto para continuar.",
        ),
        (
            OperationOutcome(
                status=OperationStatus.BLOCKED,
                error_code="PAYWALL",
                error_message="O conteúdo está bloqueado; cole o texto para continuar.",
            ),
            "PAYWALL",
            "O conteúdo está bloqueado; cole o texto para continuar.",
        ),
        (
            OperationOutcome(
                status=OperationStatus.TECHNICAL_ERROR,
                error_code="COLLECTION_TIMEOUT",
                error_message="A página não respondeu no tempo permitido.",
            ),
            "COLLECTION_TIMEOUT",
            "A página não respondeu no tempo permitido.",
        ),
    ],
)
def test_url_input_loader_preserves_collection_failure(
    outcome: OperationOutcome,
    expected_code: str,
    expected_message: str,
) -> None:
    class Collector:
        def collect(self, url: str):
            del url
            return outcome

    loader = UrlInputLoader(Collector(), ArticleExtractor())

    with pytest.raises(UrlInputFailure) as captured:
        loader("https://public.example/noticia")

    assert captured.value.code == expected_code
    assert str(captured.value) == expected_message


def test_url_input_loader_maps_extraction_failure() -> None:
    class Collector:
        def collect(self, url: str):
            return OperationOutcome(
                status=OperationStatus.SUCCESS,
                data=CollectedPage(
                    requested_url=url,
                    final_url=url,
                    html="<html><body>curto</body></html>",
                    content_type="text/html",
                ),
            )

    loader = UrlInputLoader(Collector(), ArticleExtractor())

    with pytest.raises(UrlInputFailure) as captured:
        loader("https://public.example/vazia")

    assert captured.value.code == "EXTRACTION_FAILED"
    assert "conteúdo jornalístico" in str(captured.value)


@pytest.mark.parametrize(
    "declared,expected",
    [
        ("https://saude.gov.br/fonte", "https://publisher.example/final/news"),
        ("//saude.gov.br/fonte", "https://publisher.example/final/news"),
        ("javascript:alert(1)", "https://publisher.example/final/news"),
        ("https://user:password@publisher.example/story", "https://publisher.example/final/news"),
        ("http://publisher.example/story", "https://publisher.example/final/news"),
        ("https://publisher.example:444/story", "https://publisher.example/final/news"),
        ("https://publisher.example:0/story", "https://publisher.example/final/news"),
        ("https://publisher.example:broken/story", "https://publisher.example/final/news"),
        ("../story?utm_source=feed", "https://publisher.example/story"),
        ("https://PUBLISHER.example:443/story", "https://publisher.example/story"),
    ],
)
def test_declared_canonical_identity_is_confined_to_verified_final_origin(declared, expected):
    class Collector:
        def collect(self, url):
            return OperationOutcome(
                status=OperationStatus.SUCCESS,
                data=CollectedPage(
                    requested_url=url,
                    final_url="https://publisher.example/final/news",
                    content_type="text/html",
                    html=(
                        f'<html><head><link rel="canonical" href="{declared}"></head>'
                        "<body><article>O município publicou um documento oficial com dez itens."
                        "</article></body></html>"
                    ),
                ),
            )

    loaded = UrlInputLoader(Collector(), ArticleExtractor())("https://redirect.example/start")
    assert loaded.canonical_url == expected
    assert loaded.final_url == "https://publisher.example/final/news"
