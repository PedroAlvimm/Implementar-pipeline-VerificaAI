"""The factual adapter persists real domain output using offline providers."""

import json
import unicodedata
from dataclasses import asdict
from hashlib import sha256
from uuid import uuid4

import pytest

from analyses.models import Claim, Evidence, RunState
from analyses.services.runs import create_analysis, create_rerun, transition_run
from app.claims.schemas import Claim as DomainClaim
from app.claims.schemas import ClaimValidationResult, QuerySet
from app.core.config import Settings
from app.core.enums import Verdict
from app.evidence.chunking import EvidenceDocument
from app.fact_checking.judgment import EvidenceDecision
from app.ingestion.url_loader import LoadedUrl, UrlInputFailure
from app.search.contracts import SearchResult

pytestmark = pytest.mark.django_db

TEXT = "O município comprou 10 ambulâncias."
EXCERPT = "O contrato confirma a compra de 10 ambulâncias pelo município."


class Providers:
    version = "fixture-1"

    def __init__(self, *, mode="supported", quote=None):
        self.mode = mode
        self.quote = quote
        self.loaded = []

    def extract(self, text):
        claim = DomainClaim(
            id="claim_1",
            text=TEXT,
            original_excerpt=text,
            claim_type="quantitative",
            checkable=True,
            priority="high",
            entities=["município"],
        )
        return ClaimValidationResult(accepted=[claim], rejected=[])

    def generate(self, claim):
        return QuerySet(claim_id=claim.id, queries=["contrato ambulâncias", "compra ambulâncias"])

    def search(self, query, limit):
        if self.mode == "search_error":
            raise TimeoutError("SECRET-DO-NOT-PERSIST")
        if self.mode == "empty":
            return []
        urls = ["https://source.example/contract"]
        if self.mode == "copies":
            urls += ["https://source.example/contract?utm_source=test", "https://copy.example/news"]
        return [
            SearchResult(
                title="Contrato",
                url=url,
                snippet="Resumo",
                domain=url.split("/")[2],
                published_at=None,
                query=query,
                rank=index,
            )
            for index, url in enumerate(urls, 1)
        ][:limit]

    def load(self, result):
        if self.mode == "collection_error":
            raise TimeoutError("SECRET-DO-NOT-PERSIST")
        self.loaded.append(result.url)
        text = unicodedata.normalize("NFD", EXCERPT.replace("compra de", "compra\n de"))
        return EvidenceDocument(
            id=result.domain,
            text=text,
            title=result.title,
            url=result.url,
            domain=result.domain,
            published_at=None,
            independence_group="untrusted-provider-group",
        )

    def judge(self, claim_id, claim_text, evidence):
        if self.mode == "invalid_llm":
            return {"label": "FAKE", "secret": "SECRET-DO-NOT-PERSIST"}
        return EvidenceDecision(
            claim_id=claim_id,
            evidence_id=evidence.evidence_id,
            label="SUPPORTED",
            reason="O contrato documenta a compra.",
            quoted_excerpt=self.quote if self.quote is not None else evidence.text,
            limitations=[],
        )


def make_pipeline(tmp_path, providers=None, **kwargs):
    from analyses.services.artifacts import FilesystemArtifactStore
    from analyses.services.pipeline import DjangoAnalysisPipeline

    providers = providers or Providers()
    return DjangoAnalysisPipeline(
        claim_extractor=providers,
        query_generator=providers,
        search_provider=providers,
        document_loader=providers,
        judge=providers,
        artifact_store=FilesystemArtifactStore(tmp_path),
        **kwargs,
    )


def create_run(input_type="text", content=TEXT):
    return create_analysis(input_type, content, None, uuid4())[1]


def test_complete_pipeline_persists_claim_evidence_report_and_artifact_metadata(tmp_path):
    run = create_run()
    completed = make_pipeline(tmp_path).run(run.pk)
    assert completed.state == RunState.COMPLETED
    assert completed.finished_at >= completed.started_at
    claim = Claim.objects.get(run=run)
    evidence = Evidence.objects.get(run=run, claim=claim)
    assert (claim.verdict, claim.priority, claim.position) == ("SUPPORTED", 3, 1)
    assert evidence.quotation == evidence.excerpt == EXCERPT
    assert evidence.bm25_score > 0 and evidence.rank == 1
    assert completed.report["claims"][0]["verdict"] == "SUPPORTED"
    assert completed.report["overall_result"] == "MAIN_CLAIMS_SUPPORTED"
    assert completed.trace["queries"][0]["claim_id"] == "claim_1"
    assert completed.provider_versions["judge"]["version"] == "fixture-1"
    assert set(completed.trace["input"]) == {"relative_path", "sha256", "size_bytes", "media_type"}
    assert (tmp_path / completed.trace["input"]["relative_path"]).read_text() == TEXT
    assert EXCERPT not in json.dumps(completed.trace, ensure_ascii=False)
    assert "risk_status" not in completed.report


@pytest.mark.parametrize(
    "mode,limitation",
    [
        ("search_error", "claim_1:search_unavailable"),
        ("collection_error", "claim_1:document_unavailable"),
    ],
)
def test_technical_failure_is_explicit_not_genuine_absence(tmp_path, mode, limitation):
    run = make_pipeline(tmp_path, Providers(mode=mode)).run(create_run().pk)
    assert run.state == RunState.COMPLETED_WITH_LIMITATIONS
    assert limitation in run.limitations
    assert limitation in run.report["limitations"]
    assert run.report["claims"][0]["verdict"] == "NEI"
    assert "SECRET-DO-NOT-PERSIST" not in json.dumps(run.report)


def test_successful_search_with_no_evidence_is_completed_nei(tmp_path):
    run = make_pipeline(tmp_path, Providers(mode="empty")).run(create_run().pk)
    assert run.state == RunState.COMPLETED
    assert run.limitations == []
    assert run.report["overall_result"] == "INSUFFICIENT_EVIDENCE"
    assert not Evidence.objects.filter(run=run).exists()


def test_canonical_results_are_collected_once_and_copies_count_as_one_source(tmp_path):
    providers = Providers(mode="copies")
    run = make_pipeline(tmp_path, providers).run(create_run().pk)
    assert len(providers.loaded) == 2
    documents = run.trace["documents"]
    assert len(documents) == 2
    assert len({item["independence_group"] for item in documents}) == 1
    assert Evidence.objects.filter(run=run).count() == 1
    assert run.report["claims"][0]["confidence_level"] == "LOW"


def test_redirected_canonical_duplicates_cannot_overwrite_recorded_artifacts(tmp_path):
    class Redirects(Providers):
        def load(self, result):
            document = super().load(result)
            return document.model_copy(
                update={
                    "url": "https://origin.example/article",
                    "text": EXCERPT if len(self.loaded) == 1 else EXCERPT + " Texto atualizado.",
                }
            )

    run = make_pipeline(tmp_path, Redirects(mode="copies")).run(create_run().pk)
    assert run.state == RunState.COMPLETED
    documents = run.trace["documents"]
    assert len(documents) == 1
    for doc in documents:
        ref = doc["artifact"]
        assert sha256((tmp_path / ref["relative_path"]).read_bytes()).hexdigest() == ref["sha256"]


@pytest.mark.parametrize(
    "quote",
    [
        EXCERPT.replace("10", "20"),
        EXCERPT.replace("confirma", "CONFIRMA"),
        EXCERPT.replace("município", "municipio"),
        EXCERPT.replace(".", "!"),
    ],
)
def test_quote_differences_remaining_after_normalization_fail_run(tmp_path, quote):
    run = make_pipeline(tmp_path, Providers(quote=quote)).run(create_run().pk)
    assert run.state == RunState.FAILED
    assert run.error_code == "INVALID_LLM_OUTPUT"
    assert not Evidence.objects.filter(run=run).exists()


def test_invalid_llm_schema_fails_explicitly_without_leaking_output(tmp_path):
    run = make_pipeline(tmp_path, Providers(mode="invalid_llm")).run(create_run().pk)
    assert run.state == RunState.FAILED
    assert run.error_code == "INVALID_LLM_OUTPUT"
    assert "SECRET-DO-NOT-PERSIST" not in run.error_message
    assert run.report == {}


def test_terminal_replay_and_rerun_preserve_previous_results(tmp_path):
    pipeline = make_pipeline(tmp_path)
    first = pipeline.run(create_run().pk)
    before = first.report
    pipeline.run(first.pk)
    second = create_rerun(first.analysis_id, uuid4())
    pipeline.run(second.pk)
    first.refresh_from_db()
    assert first.report == before
    assert (
        Claim.objects.filter(run=first).count() == Evidence.objects.filter(run=first).count() == 1
    )
    assert Claim.objects.filter(run=second).count() == 1


def test_running_run_is_not_adopted_by_another_pipeline_call(tmp_path):
    from analyses.services.runs import RunConflictError

    run = create_run()
    transition_run(run.pk, RunState.RUNNING)
    with pytest.raises(RunConflictError, match="worker"):
        make_pipeline(tmp_path).run(run.pk)
    assert not Claim.objects.filter(run=run).exists()


@pytest.mark.parametrize("verdict", ["REFUTED", "NEI", "CONFLICTING"])
def test_other_factual_verdicts_reuse_domain_aggregation(tmp_path, verdict):
    class Scenario(Providers):
        def search(self, query, limit):
            results = super().search(query, limit)
            if verdict == "CONFLICTING":
                results.append(
                    results[0].model_copy(
                        update={
                            "url": "https://other.example/news",
                            "domain": "other.example",
                        }
                    )
                )
            return results

        def load(self, result):
            document = super().load(result)
            if result.domain == "other.example":
                return document.model_copy(
                    update={"text": "A frota anunciada possui somente 8 veículos."}
                )
            return document

        def judge(self, claim_id, claim_text, evidence):
            decision = super().judge(claim_id, claim_text, evidence)
            label = verdict
            if verdict == "CONFLICTING":
                label = "REFUTED" if evidence.source_domain == "other.example" else "SUPPORTED"
            return decision.model_copy(
                update={
                    "label": Verdict(label),
                    "quoted_excerpt": "" if label == "NEI" else evidence.text,
                }
            )

    run = make_pipeline(tmp_path, Scenario()).run(create_run().pk)
    assert run.state == RunState.COMPLETED
    assert Claim.objects.get(run=run).verdict == verdict
    assert run.report["claims"][0]["verdict"] == verdict


def test_shared_evidence_for_multiple_claims_has_distinct_persisted_keys(tmp_path):
    class Multiple(Providers):
        def extract(self, text):
            batch = super().extract(text)
            return batch.model_copy(
                update={
                    "accepted": [
                        batch.accepted[0],
                        batch.accepted[0].model_copy(update={"id": "claim_2"}),
                    ]
                }
            )

    run = make_pipeline(tmp_path, Multiple()).run(create_run().pk)
    assert run.state == RunState.COMPLETED
    rows = list(Evidence.objects.filter(run=run))
    assert len(rows) == 2
    assert rows[0].evidence_key != rows[1].evidence_key
    assert rows[0].claim_id != rows[1].claim_id


def test_independence_groups_are_consistent_across_claims_in_the_run(tmp_path):
    class DifferentSearches(Providers):
        def extract(self, text):
            batch = super().extract(text)
            return batch.model_copy(
                update={
                    "accepted": [
                        batch.accepted[0],
                        batch.accepted[0].model_copy(update={"id": "claim_2"}),
                    ]
                }
            )

        def generate(self, claim):
            return QuerySet(claim_id=claim.id, queries=[f"{claim.id} first", f"{claim.id} second"])

        def search(self, query, limit):
            result = super().search(query, limit)[0]
            source = result.model_copy(
                update={"url": "https://z.example/source", "domain": "z.example"}
            )
            if query.startswith("claim_2"):
                return [source]
            return [
                result.model_copy(update={"url": "https://a.example/copy", "domain": "a.example"}),
                source,
            ]

    run = make_pipeline(tmp_path, DifferentSearches()).run(create_run().pk)
    assert run.state == RunState.COMPLETED
    assert (
        len(set(Evidence.objects.filter(run=run).values_list("independence_group", flat=True))) == 1
    )


@pytest.mark.parametrize("stage", ["extract", "generate"])
def test_invalid_claim_or_query_contract_fails_without_inventing_result(tmp_path, stage):
    provider = Providers()
    setattr(provider, stage, lambda value: {"unknown": "not a structured response"})
    run = make_pipeline(tmp_path, provider).run(create_run().pk)
    assert run.state == RunState.FAILED and run.error_code == "INVALID_LLM_OUTPUT"
    assert run.report == {}


def test_wrong_query_claim_reference_fails_explicitly(tmp_path):
    provider = Providers()
    provider.generate = lambda claim: QuerySet(claim_id="claim_unknown", queries=["one", "two"])
    run = make_pipeline(tmp_path, provider).run(create_run().pk)
    assert run.state == RunState.FAILED and run.error_code == "INVALID_LLM_OUTPUT"


def test_deadline_is_checked_after_last_provider_returns(tmp_path):
    moments = iter([0, 0, 0, 0, 0, 0, 0, 0, 301])
    pipeline = make_pipeline(tmp_path, clock=lambda: next(moments, 301))
    run = pipeline.run(create_run().pk)
    assert run.state == RunState.FAILED and run.error_code == "RESOURCE_BUDGET_EXCEEDED"


@pytest.mark.django_db(transaction=True)
def test_external_work_never_holds_database_transaction(tmp_path):
    from django.db import connection

    provider = Providers()
    for name in ("extract", "generate", "search", "load", "judge"):
        original = getattr(provider, name)

        def outside_transaction(*args, _method=original):
            assert not connection.in_atomic_block
            return _method(*args)

        setattr(provider, name, outside_transaction)
    run = make_pipeline(tmp_path, provider).run(create_run().pk)
    assert run.state == RunState.COMPLETED


def test_factual_persistence_rejects_cross_run_evidence_and_nonliteral_quote(tmp_path):
    from analyses.services.pipeline import persist_evidence

    first, second = create_run(), create_run()
    transition_run(first.pk, RunState.RUNNING)
    transition_run(second.pk, RunState.RUNNING)
    claim = Claim.objects.create(run=first, claim_key="claim_1", text=TEXT, position=1)
    foreign = Evidence(
        run=second,
        claim=claim,
        evidence_key="ev_1",
        canonical_url="https://a.example/",
        domain="a.example",
        excerpt=EXCERPT,
        quotation=EXCERPT,
    )
    with pytest.raises(ValueError, match="run"):
        persist_evidence(second.pk, [foreign])
    invalid = Evidence(
        run=first,
        claim=claim,
        evidence_key="ev_2",
        canonical_url="https://a.example/",
        domain="a.example",
        excerpt=EXCERPT,
        quotation="20 ambulâncias",
    )
    with pytest.raises(ValueError, match=r"[Cc]ita|quotation"):
        persist_evidence(first.pk, [invalid])
    assert Evidence.objects.count() == 0


def test_factual_persistence_normalizes_before_storing_literal_quote(tmp_path):
    from analyses.services.pipeline import persist_evidence

    run = create_run()
    transition_run(run.pk, RunState.RUNNING)
    claim = Claim.objects.create(run=run, claim_key="claim_1", text=TEXT, position=1)
    row = Evidence(
        run=run,
        claim=claim,
        evidence_key="ev_1",
        canonical_url="https://a.example/",
        domain="a.example",
        excerpt=unicodedata.normalize("NFD", EXCERPT),
        quotation="10   ambulâncias",
    )
    persist_evidence(run.pk, [row])
    row.refresh_from_db()
    assert row.excerpt == EXCERPT and row.quotation == "10 ambulâncias"
    assert row.quotation in row.excerpt


def test_url_input_is_loaded_by_injected_safe_boundary_and_stored_on_disk(tmp_path):
    def load(url):
        assert url == "https://input.example/news"
        return LoadedUrl(text=TEXT, title="Entrada", canonical_url=url, final_url=url)

    run = create_run("url", "https://input.example/news")
    completed = make_pipeline(tmp_path, url_loader=load).run(run.pk)
    assert completed.state == RunState.COMPLETED
    assert completed.report["title"] == "Entrada"
    assert (tmp_path / completed.trace["input"]["relative_path"]).read_text() == TEXT


def test_unsafe_url_error_is_preserved_without_raw_details(tmp_path):
    def load(url):
        raise UrlInputFailure("UNSAFE_URL", "SECRET-DO-NOT-PERSIST")

    run = make_pipeline(tmp_path, url_loader=load).run(create_run("url", "http://127.0.0.1/").pk)
    assert run.state == RunState.FAILED and run.error_code == "UNSAFE_URL"
    assert "SECRET-DO-NOT-PERSIST" not in run.error_message


def test_default_url_loader_blocks_loopback_before_network(tmp_path):
    run = make_pipeline(tmp_path).run(create_run("url", "http://127.0.0.1/").pk)
    assert run.state == RunState.FAILED and run.error_code == "UNSAFE_URL"


def test_default_document_loader_uses_safe_input_loader(tmp_path):
    from analyses.services.artifacts import FilesystemArtifactStore
    from analyses.services.pipeline import DjangoAnalysisPipeline
    from app.core.enums import OperationStatus
    from app.core.outcomes import OperationOutcome
    from app.ingestion.url_loader import UrlInputLoader
    from app.scraping.extraction import ArticleExtractor, CollectedPage

    class Collector:
        def collect(self, url):
            return OperationOutcome(
                status=OperationStatus.SUCCESS,
                data=CollectedPage(
                    requested_url=url,
                    final_url=url,
                    content_type="text/html",
                    html=f"<html><head><title>Contrato</title></head><body><article><p>{EXCERPT}</p></article></body></html>",
                ),
            )

    provider = Providers()
    pipeline = DjangoAnalysisPipeline(
        claim_extractor=provider,
        query_generator=provider,
        search_provider=provider,
        judge=provider,
        url_loader=UrlInputLoader(Collector(), ArticleExtractor()),
        artifact_store=FilesystemArtifactStore(tmp_path),
    )
    run = pipeline.run(create_run().pk)
    assert run.state == RunState.COMPLETED
    assert Evidence.objects.get(run=run).excerpt == EXCERPT


def test_html_canonical_cannot_promote_third_party_to_official_source(tmp_path):
    from analyses.services.pipeline import SafeEvidenceDocumentLoader
    from app.core.enums import OperationStatus
    from app.core.outcomes import OperationOutcome
    from app.ingestion.url_loader import UrlInputLoader
    from app.scraping.extraction import ArticleExtractor, CollectedPage

    class Collector:
        def collect(self, url):
            return OperationOutcome(
                status=OperationStatus.SUCCESS,
                data=CollectedPage(
                    requested_url=url,
                    final_url="https://thirdparty.example/article",
                    content_type="text/html",
                    html=(
                        '<html><head><link rel="canonical" href="https://saude.gov.br/official">'
                        f"</head><body><article>{EXCERPT}</article></body></html>"
                    ),
                ),
            )

    pipeline = make_pipeline(tmp_path)
    pipeline.document_loader = SafeEvidenceDocumentLoader(
        UrlInputLoader(Collector(), ArticleExtractor())
    )
    run = pipeline.run(create_run().pk)
    assert run.state == RunState.COMPLETED
    row = Evidence.objects.get(run=run)
    assert row.canonical_url == "https://thirdparty.example/article"
    assert row.domain == "thirdparty.example"
    assert run.report["claims"][0]["confidence_level"] == "LOW"


def test_document_loader_checks_provenance_even_for_an_alternate_input_loader():
    from analyses.services.pipeline import SafeEvidenceDocumentLoader

    loaded = LoadedUrl(
        text=EXCERPT,
        title="Fonte",
        final_url="https://thirdparty.example/final",
        canonical_url="https://saude.gov.br/forged",
    )
    result = Providers().search("query", 1)[0]
    document = SafeEvidenceDocumentLoader(lambda url: loaded).load(result)
    assert document.url == "https://thirdparty.example/final"
    assert document.domain == "thirdparty.example"


@pytest.mark.parametrize(
    "queries,settings",
    [
        (["x" * 513, "valid query"], Settings()),
        (["query one", "query two", "query three"], Settings(max_queries_per_claim=2)),
        (["🚑" * 512] * 4, Settings()),
    ],
)
def test_oversized_queries_fail_before_search_or_trace_write(tmp_path, queries, settings):
    provider = Providers()
    provider.generate = lambda claim: QuerySet.model_construct(claim_id=claim.id, queries=queries)
    searched = []
    provider.search = lambda query, limit: searched.append(query) or []
    run = make_pipeline(tmp_path, provider, settings=settings).run(create_run().pk)
    assert run.state == RunState.FAILED and run.error_code == "INVALID_LLM_OUTPUT"
    assert searched == []
    assert run.trace["queries"] == []
    assert len(json.dumps(run.trace).encode()) < 1024
    assert run.report == {}


@pytest.mark.parametrize(
    "changes",
    [
        {"text": "x" * 4097},
        {"id": "claim_" + "x" * 128},
        {"original_excerpt": "x" * 8193},
        {"entities": ["x" * 257]},
        {"entities": ["entity"] * 21},
        {"temporal_scope": "x" * 513},
    ],
)
def test_oversized_claim_fields_are_rejected_before_any_claim_write(tmp_path, changes):
    provider = Providers()
    extract = provider.extract

    def oversized(text):
        batch = extract(text)
        batch.accepted[0] = batch.accepted[0].model_copy(update=changes)
        return batch

    provider.extract = oversized
    run = make_pipeline(tmp_path, provider).run(create_run().pk)
    assert run.state == RunState.FAILED and run.error_code == "INVALID_LLM_OUTPUT"
    assert not Claim.objects.filter(run=run).exists()
    assert len(json.dumps(run.trace).encode()) < 1024
    assert run.limitations == [] and run.report == {}


@pytest.mark.parametrize(
    "changes",
    [
        {"reason": "x" * 2049},
        {"quoted_excerpt": "x" * 4097},
        {"limitations": ["x" * 513]},
        {"limitations": ["reason"] * 17},
    ],
)
def test_oversized_judgment_fields_fail_without_persisting_decision(tmp_path, changes):
    provider = Providers()
    judge = provider.judge
    provider.judge = lambda *args: judge(*args).model_copy(update=changes)
    run = make_pipeline(tmp_path, provider).run(create_run().pk)
    assert run.state == RunState.FAILED and run.error_code == "INVALID_LLM_OUTPUT"
    assert not Evidence.objects.filter(run=run).exists()
    assert Claim.objects.get(run=run).verdict == ""
    assert run.report == {} and run.limitations == []


def test_rejection_text_and_aggregate_claim_payload_are_bounded(tmp_path):
    from app.claims.schemas import RejectedClaim

    provider = Providers()
    extract = provider.extract

    def oversized(text):
        batch = extract(text)
        batch.rejected = [RejectedClaim.model_construct(claim_id="claim_2", reason="x" * 513)]
        return batch

    provider.extract = oversized
    run = make_pipeline(tmp_path, provider).run(create_run().pk)
    assert run.state == RunState.FAILED and run.error_code == "INVALID_LLM_OUTPUT"
    assert not Claim.objects.filter(run=run).exists()
    assert run.limitations == []


def test_schema_valid_claim_batch_exceeding_json_budget_is_rejected_as_a_whole(tmp_path):
    provider = Providers()
    extract = provider.extract

    def oversized(text):
        batch = extract(text)
        claim = batch.accepted[0].model_copy(update={"text": "🚑" * 4096})
        return batch.model_copy(
            update={
                "accepted": [
                    claim.model_copy(update={"id": f"claim_{index}"}) for index in range(3)
                ]
            }
        )

    provider.extract = oversized
    run = make_pipeline(tmp_path, provider).run(create_run().pk)
    assert run.state == RunState.FAILED and run.error_code == "INVALID_LLM_OUTPUT"
    assert not Claim.objects.filter(run=run).exists()
    assert run.limitations == [] and run.report == {}


def test_trace_budget_rejects_entire_update_without_replacing_previous_trace(tmp_path):
    from analyses.services.pipeline import DjangoAnalysisPipeline
    from app.fact_checking.judgment import JudgmentValidationError

    run = create_run()
    transition_run(run.pk, RunState.RUNNING)
    run.trace = {"queries": []}
    run.save(update_fields=["trace"])
    with pytest.raises(JudgmentValidationError):
        DjangoAnalysisPipeline._update(run.pk, trace={"large": "x" * 65536}, limitations=["new"])
    run.refresh_from_db()
    assert run.trace == {"queries": []} and run.limitations == []


def test_artifact_batch_rejection_does_not_persist_valid_prefix(tmp_path):
    from analyses.services.pipeline import persist_evidence

    run, foreign_run = create_run(), create_run()
    transition_run(run.pk, RunState.RUNNING)
    claim = Claim.objects.create(run=run, claim_key="claim_1", text=TEXT, position=1)
    rows = [
        Evidence(
            run=run,
            claim=claim,
            evidence_key="ev_good",
            canonical_url="https://a.example/",
            domain="a.example",
            excerpt=EXCERPT,
            quotation=EXCERPT,
        ),
        Evidence(
            run=foreign_run,
            claim=claim,
            evidence_key="ev_bad",
            canonical_url="https://b.example/",
            domain="b.example",
            excerpt=EXCERPT,
            quotation=EXCERPT,
        ),
    ]
    with pytest.raises(ValueError, match="run"):
        persist_evidence(run.pk, rows)
    assert not Evidence.objects.exists()


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_llm_calls": 0},
        {"max_llm_tokens": 1},
        {"max_artifact_bytes_per_analysis": 1},
    ],
)
def test_resource_limits_fail_closed(tmp_path, overrides):
    run = make_pipeline(tmp_path, settings=Settings(**overrides)).run(create_run().pk)
    assert run.state == RunState.FAILED and run.error_code == "RESOURCE_BUDGET_EXCEEDED"


def test_html_artifact_reference_in_sqlite_never_contains_html(tmp_path):
    from analyses.services.artifacts import FilesystemArtifactStore

    run = create_run()
    ref = FilesystemArtifactStore(tmp_path).store(
        run.pk, "page.html", b"<html>large</html>", "text/html"
    )
    run.trace = {"artifacts": [asdict(ref)]}
    run.save(update_fields=["trace"])
    run.refresh_from_db()
    assert "<html>" not in json.dumps(run.trace)
    assert (
        tmp_path / run.trace["artifacts"][0]["relative_path"]
    ).read_bytes() == b"<html>large</html>"
