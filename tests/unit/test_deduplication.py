from __future__ import annotations

from app.search.deduplication import DocumentCandidate, group_document_independence


def document(identifier: str, url: str, text: str, original_source: str | None = None):
    return DocumentCandidate(
        id=identifier,
        url=url,
        title=f"Documento {identifier}",
        text=text,
        original_source=original_source,
    )


def test_exact_copies_across_domains_share_one_independence_group() -> None:
    text = "O contrato prevê a aquisição de oito milhões de doses pelo município."
    grouped = group_document_independence(
        [
            document("doc_1", "https://a.example/news", text),
            document("doc_2", "https://b.example/copy", text),
        ]
    )

    assert grouped.documents[0].independence_group == grouped.documents[1].independence_group
    assert grouped.reasons["doc_2"] == "exact_content_hash"


def test_near_copies_and_declared_syndication_are_grouped() -> None:
    original = "O contrato prevê a aquisição de oito milhões de doses pelo município em janeiro."
    near_copy = original + " Documento publicado nesta segunda-feira."
    grouped = group_document_independence(
        [
            document("doc_1", "https://agencia.example/original", original),
            document("doc_2", "https://portal.example/copy", near_copy),
            document(
                "doc_3",
                "https://outro.example/reprint",
                "Texto resumido diferente.",
                original_source="https://agencia.example/original",
            ),
        ]
    )

    group = grouped.documents[0].independence_group
    assert {item.independence_group for item in grouped.documents} == {group}
    assert grouped.reasons["doc_2"] == "near_duplicate_content"
    assert grouped.reasons["doc_3"] == "declared_original_source"


def test_distinct_articles_on_same_domain_remain_independent() -> None:
    grouped = group_document_independence(
        [
            document("doc_1", "https://news.example/a", "Contrato municipal de oito milhões."),
            document("doc_2", "https://news.example/b", "Pesquisa científica sobre vacinação."),
        ]
    )

    assert grouped.documents[0].independence_group != grouped.documents[1].independence_group


def test_group_identifiers_are_deterministic() -> None:
    documents = [document("doc_1", "https://a.example/x", "Mesmo conteúdo extenso e verificável.")]

    first = group_document_independence(documents)
    second = group_document_independence(documents)

    assert first.documents[0].independence_group == second.documents[0].independence_group


def test_same_canonical_url_cannot_split_an_existing_copy_group():
    grouped = group_document_independence(
        [
            document("a", "https://a.example/x", "Primeiro conteúdo municipal."),
            document("b", "https://b.example/y", "Primeiro conteúdo municipal."),
            document(
                "c",
                "https://b.example/y?utm_source=news",
                "Artigo atualizado totalmente diferente.",
            ),
        ]
    )
    assert len({item.independence_group for item in grouped.documents}) == 1


def test_declared_origin_groups_copies_even_when_original_comes_last():
    grouped = group_document_independence(
        [
            document(
                "copy", "https://copy.example/x", "Resumo local.", "https://origin.example/news"
            ),
            document(
                "origin",
                "https://origin.example/news",
                "Relatório integral com informações distintas.",
            ),
        ]
    )
    assert grouped.documents[0].independence_group == grouped.documents[1].independence_group
