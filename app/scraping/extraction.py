from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

import trafilatura
from bs4 import BeautifulSoup

from app.core.errors import CollectionError
from app.search.canonical import canonicalize_url


@dataclass(frozen=True)
class CollectedPage:
    requested_url: str
    final_url: str
    html: str
    content_type: str


@dataclass(frozen=True)
class ExtractedArticle:
    title: str | None
    subtitle: str | None
    author: str | None
    published_at: datetime | None
    domain: str
    canonical_url: str
    language: str | None
    original_html: str
    clean_text: str
    extraction_method: str
    extracted_at: datetime


def _jsonld_article(soup: BeautifulSoup) -> dict[str, object]:
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(node.get_text(strip=True))
        except (json.JSONDecodeError, TypeError):
            continue
        candidates = payload if isinstance(payload, list) else [payload]
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate.get("@type") in {
                "Article",
                "NewsArticle",
                "Report",
            }:
                return candidate
    return {}


def _parse_date(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def source_identity_url(final_url: str, declared: str | None) -> str:
    """Constrain HTML's canonical hint to the origin actually collected.

    final_url is supplied by the safe transport, never by HTML. This does not
    fetch the canonical target: it is only a same-origin identity hint.
    """

    def origin(url):
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("Invalid source identity URL")
        return (
            parsed.scheme,
            parsed.hostname.casefold().rstrip("."),
            parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80),
        )

    verified_origin = origin(final_url)
    fallback = canonicalize_url(final_url)
    if not declared or any(ord(char) < 32 for char in declared):
        return fallback
    try:
        candidate = urljoin(final_url, declared.strip())
        if origin(candidate) == verified_origin:
            return canonicalize_url(candidate)
    except ValueError:
        pass
    return fallback


class ArticleExtractor:
    def extract(self, page: CollectedPage) -> ExtractedArticle:
        soup = BeautifulSoup(page.html, "html.parser")
        jsonld = _jsonld_article(soup)
        text = trafilatura.extract(
            page.html,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
        method = "trafilatura"
        if not text:
            container = soup.find("article") or soup.find("main")
            text = container.get_text("\n", strip=True) if container else ""
            method = "beautifulsoup"
        if len(text.split()) < 5:
            raise CollectionError("A página não contém conteúdo jornalístico disponível")

        title_node = soup.find("title") or soup.find("h1")
        title = str(jsonld.get("headline") or "").strip() or (
            title_node.get_text(" ", strip=True) if title_node else None
        )
        description = soup.find("meta", attrs={"name": "description"})
        subtitle = str(jsonld.get("description") or "").strip() or (
            description.get("content") if description else None
        )
        author_node = soup.find("meta", attrs={"name": "author"})
        author_value = jsonld.get("author")
        if isinstance(author_value, dict):
            author_value = author_value.get("name")
        author = str(author_value or "").strip() or (
            author_node.get("content") if author_node else None
        )
        date_node = soup.find("meta", attrs={"property": "article:published_time"})
        published_at = _parse_date(
            jsonld.get("datePublished") or (date_node.get("content") if date_node else None)
        )
        canonical_node = soup.find("link", rel="canonical")
        canonical_url = source_identity_url(
            page.final_url,
            str(canonical_node.get("href") or "") if canonical_node else None,
        )
        language = soup.html.get("lang") if soup.html else None
        return ExtractedArticle(
            title=title,
            subtitle=str(subtitle) if subtitle else None,
            author=str(author) if author else None,
            published_at=published_at,
            domain=urlsplit(canonical_url).hostname or "",
            canonical_url=canonical_url,
            language=str(language) if language else None,
            original_html=page.html,
            clean_text=text,
            extraction_method=method,
            extracted_at=datetime.now(UTC),
        )
