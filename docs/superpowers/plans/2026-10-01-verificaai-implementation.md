# VerificaAI First Functional Version Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local, auditable Brazilian Portuguese fact-checking support application that accepts text or a public URL, retrieves evidence, produces deterministic claim verdicts, and explicitly leaves BERTimbau unavailable.

**Architecture:** Implement a synchronous domain pipeline inside a modular FastAPI monolith, with a bounded in-process executor for API jobs and a polling Streamlit client. Network, LLM, search, persistence, and risk analysis are accessed through typed interfaces so fakes can run the complete suite without internet and real providers can be swapped.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic 2, pydantic-settings, SQLAlchemy 2, SQLite, HTTPX, Trafilatura, BeautifulSoup 4, Streamlit, pytest, respx, Ruff.

**Spec:** `docs/superpowers/specs/2026-10-01-verificaai-design.md`

## Global Constraints

- Bind API and Streamlit instructions to `127.0.0.1` by default; this PoC is not internet-facing.
- Never execute or simulate BERTimbau; always show “Análise linguística: aguardando integração do BERTimbau.”
- Never use a fact-checking API or a fact-checking portal as evidence.
- Never turn a technical error, blocked collection, or absence of proof into `REFUTED`.
- Never allow an LLM to invent a URL, evidence ID, claim excerpt, or quotation.
- Real LLM uses the OpenAI Responses API through an adapter and requires both `OPENAI_API_KEY` and `OPENAI_MODEL`; there is no default model.
- Real search uses the Brave Web Search API and requires `BRAVE_SEARCH_API_KEY`.
- Provider SDKs do not enter domain code; both real adapters use HTTPX and validated JSON.
- Tests use fake providers and mocked HTTP/DNS only; the test suite never accesses the internet.
- Preserve original Portuguese text, numbers, dates, punctuation, accents, verbs, articles, and negations.
- Enforce the exact limits from specification section 5.1 and the retention rules from section 9.1.
- Default evidence chunks to 1,200 characters with 200-character overlap; preserve sentence boundaries when possible.
- Limit each external domain to one request per second and two concurrent requests; make at most two total attempts for transient provider errors.
- Persist all audit records except credentials, cookies, authentication headers, and full content in operational logs.
- Use TDD for each task and update `PROGRESS.md` after every completed task.

## Review Focus

- A hostname whose DNS answer changes after validation must still connect only to the pinned public IP; Task 3 adds `test_fetch_uses_validated_ip_not_second_dns_answer`.
- A partially successful analysis must become `COMPLETED_WITH_LIMITATIONS`, not a complete factual result; Task 9 adds `test_partial_pipeline_has_explicit_limitations`.
- Unicode-normalized text must never cause the report to display a quotation that was not copied from the original evidence; Task 8 adds `test_quote_mapping_returns_original_characters`.
- Reusing an idempotency key with a different payload must be rejected rather than return an unrelated analysis; Task 2 adds `test_idempotency_key_payload_mismatch_is_conflict`.
- A prompt-injection sentence inside evidence must remain data and must not add IDs or URLs to the judge output; Task 5 adds `test_untrusted_content_cannot_expand_allowed_identifiers`.

---

### Task 1: Project foundation, configuration, and disabled risk analysis

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `app/__init__.py`
- Create: `app/core/config.py`
- Create: `app/core/enums.py`
- Create: `app/core/outcomes.py`
- Create: `app/core/logging.py`
- Create: `app/risk_analysis/base.py`
- Create: `app/risk_analysis/disabled.py`
- Create: `app/risk_analysis/bertimbau.py`
- Create: `tests/unit/test_config.py`
- Create: `tests/unit/test_logging.py`
- Create: `tests/unit/test_risk_analysis.py`
- Create: `tests/conftest.py`
- Create: `PROGRESS.md`

**Interfaces:**
- Consumes: no application interfaces.
- Produces: `Settings`, `AnalysisStatus`, `OperationStatus`, `Verdict`, `ConfidenceLevel`, `OperationOutcome[T]`, redacting structured-log configuration, `RiskAnalyzer.analyze(text: str) -> RiskAnalysisResult`, `DisabledRiskAnalyzer`, and `BertimbauRiskAnalyzer`.

- [ ] **Step 1: Initialize local version control and the Python environment metadata**

Run `git init -b main` only because the inspected directory has no repository. Run `python3 -m venv .venv` and `.venv/bin/python -m pip install -e '.[dev]'`. Add Python 3.11 metadata, runtime/dev dependency groups, Ruff and pytest configuration to `pyproject.toml`, and local secrets/artifacts to `.gitignore`.

- [ ] **Step 2: Write failing configuration and risk-analysis tests**

Test exact default limits, `127.0.0.1` binding, rejection of fake providers outside test/demo mode, structured-log redaction of text/HTML/keys/cookies/authorization, the complete disabled-risk dictionary, and that `BertimbauRiskAnalyzer.analyze()` raises a documented unavailable error rather than returning a score. Add an autouse test guard that fails any unmocked network connection.

- [ ] **Step 3: Run tests to verify failure**

Run: `.venv/bin/pytest tests/unit/test_config.py tests/unit/test_logging.py tests/unit/test_risk_analysis.py -v`

Expected: FAIL because application modules do not exist.

- [ ] **Step 4: Implement the minimal typed foundation**

Implement `Settings` with all section 5.1 limits; define enums and generic operation outcomes; define risk result schema and the two analyzers. `.env.example` lists names only and contains no secrets.

- [ ] **Step 5: Verify Task 1 and record progress**

Run: `.venv/bin/pytest tests/unit/test_config.py tests/unit/test_logging.py tests/unit/test_risk_analysis.py -v && .venv/bin/ruff check app tests`

Expected: all tests pass and Ruff exits 0. Update `PROGRESS.md` with files, decisions, commands, and results.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore .env.example app tests PROGRESS.md
git commit -m "feat: establish verificaai foundation"
```

### Task 2: Persistence, state transitions, retention, and idempotency

**Files:**
- Create: `app/database/base.py`
- Create: `app/database/models.py`
- Create: `app/database/session.py`
- Create: `app/database/repositories.py`
- Create: `app/database/state_machine.py`
- Create: `app/database/retention.py`
- Create: `app/core/schemas.py`
- Create: `tests/unit/test_state_machine.py`
- Create: `tests/integration/test_analysis_repository.py`
- Create: `tests/integration/test_retention.py`
- Modify: `PROGRESS.md`

**Interfaces:**
- Consumes: `Settings`, `AnalysisStatus`, and `OperationStatus` from Task 1.
- Produces: SQLAlchemy `AnalysisRecord`, `ClaimRecord`, `QueryRecord`, `SearchResultRecord`, `DocumentRecord`, `EvidenceRecord`, `DecisionRecord`, `ReportRecord`, `AuditEvent`; `AnalysisRepository.create(request, idempotency_key)`, `transition(id, status)`, `fail(id, code, message)`, `complete_with_limitations(id, limitations)`, and `RetentionService.cleanup(now)`.

- [ ] **Step 1: Write failing repository, transition, and retention tests**

Cover valid/invalid state transitions, restart recovery, same-key replay, `test_idempotency_key_payload_mismatch_is_conflict`, WAL activation, 30-day analysis retention, 7-day raw-artifact retention, and preservation of audit hashes without preserved secret content.

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/pytest tests/unit/test_state_machine.py tests/integration/test_analysis_repository.py tests/integration/test_retention.py -v`

Expected: FAIL with missing database modules.

- [ ] **Step 3: Implement models and repository contracts**

Use UUID analysis IDs, timezone-aware UTC timestamps, short transactions, JSON columns for validated structured payloads, unique idempotency keys paired with payload hashes, and explicit conflict errors. Do not store HTML in SQLite.

- [ ] **Step 4: Verify Task 2 and record progress**

Run: `.venv/bin/pytest tests/unit/test_state_machine.py tests/integration/test_analysis_repository.py tests/integration/test_retention.py -v && .venv/bin/ruff check app tests`

Expected: PASS and Ruff exits 0. Update `PROGRESS.md`.

- [ ] **Step 5: Commit**

```bash
git add app/database app/core/schemas.py tests PROGRESS.md
git commit -m "feat: add auditable analysis persistence"
```

### Task 3: Input validation, SSRF defense, redirect policy, and robots.txt

**Files:**
- Create: `app/ingestion/validation.py`
- Create: `app/scraping/url_policy.py`
- Create: `app/scraping/dns.py`
- Create: `app/scraping/transport.py`
- Create: `app/scraping/robots.py`
- Create: `app/core/errors.py`
- Create: `tests/unit/test_input_validation.py`
- Create: `tests/unit/test_url_policy.py`
- Create: `tests/unit/test_robots.py`
- Create: `tests/integration/test_pinned_transport.py`
- Modify: `PROGRESS.md`

**Interfaces:**
- Consumes: limits from `Settings` and operation outcomes from Task 1.
- Produces: `validate_analysis_input(input_type, content) -> ValidatedInput`, `DnsResolver.resolve_public(hostname) -> tuple[IPAddress, ...]`, `UrlPolicy.validate(url) -> ValidatedTarget`, `PinnedHttpTransport.request(target, ...) -> httpx.Response`, and `RobotsPolicy.can_fetch(url, user_agent) -> RobotsDecision`.

- [ ] **Step 1: Write failing validation and SSRF tests**

Cover empty/oversized text, malformed URLs, credentials, non-HTTP schemes, ports, localhost, IPv4/IPv6 private/link-local/reserved/documentation/multicast/unspecified addresses, decimal/hex/octal IP tricks, mixed public/private DNS answers, redirect to private IP, credential stripping, maximum redirects, and `test_fetch_uses_validated_ip_not_second_dns_answer`.

- [ ] **Step 2: Write failing robots tests**

Cover allow/disallow rules for the configured User-Agent, `404` as absent/allowed, `401` and `403` as disallowed, timeout/DNS failure as `UNKNOWN`, fail-closed behavior, and cache expiry.

- [ ] **Step 3: Run tests to verify failure**

Run: `.venv/bin/pytest tests/unit/test_input_validation.py tests/unit/test_url_policy.py tests/unit/test_robots.py tests/integration/test_pinned_transport.py -v`

Expected: FAIL because the security modules do not exist.

- [ ] **Step 4: Implement validation and pinned transport**

Use `ipaddress` for classification, reject the entire hostname if any answer is non-public, disable inherited proxies, connect only to a validated IP while retaining hostname verification and SNI, and validate each redirect from scratch. Never forward authorization/cookie headers across origins.

- [ ] **Step 5: Verify Task 3 and record progress**

Run: `.venv/bin/pytest tests/unit/test_input_validation.py tests/unit/test_url_policy.py tests/unit/test_robots.py tests/integration/test_pinned_transport.py -v && .venv/bin/ruff check app tests`

Expected: PASS and Ruff exits 0. Update `PROGRESS.md` with the residual transport limitations.

- [ ] **Step 6: Commit**

```bash
git add app/ingestion app/scraping app/core/errors.py tests PROGRESS.md
git commit -m "feat: secure external URL collection"
```

### Task 4: Bounded page collection, article extraction, and artifact storage

**Files:**
- Create: `app/scraping/client.py`
- Create: `app/scraping/extraction.py`
- Create: `app/scraping/block_detection.py`
- Create: `app/database/artifacts.py`
- Create: `tests/fixtures/html/article.html`
- Create: `tests/fixtures/html/jsonld_article.html`
- Create: `tests/fixtures/html/paywall.html`
- Create: `tests/fixtures/html/empty.html`
- Create: `tests/unit/test_extraction.py`
- Create: `tests/integration/test_safe_collector.py`
- Create: `tests/integration/test_artifact_store.py`
- Modify: `PROGRESS.md`

**Interfaces:**
- Consumes: `ValidatedTarget`, `PinnedHttpTransport`, `RobotsPolicy`, `Settings`, and repository document records.
- Produces: `SafeCollector.collect(url) -> OperationOutcome[CollectedPage]`, `ArticleExtractor.extract(page) -> ExtractedArticle`, `BlockDetector.detect(page) -> BlockReason | None`, and `ArtifactStore.write_gzip(analysis_id, html) -> ArtifactMetadata`.

- [ ] **Step 1: Write failing collection and extraction tests**

Cover timeout, non-HTML content, 5 MiB streaming cutoff, one-request-per-second domain rate limit, two-request domain concurrency limit, bounded cache reuse, empty page, paywall/login/CAPTCHA detection, title/subtitle/author/date/canonical/language extraction, Trafilatura fallback behavior, preservation of numbers/negation/accents, and instruction to paste text when blocked.

- [ ] **Step 2: Write failing artifact tests**

Cover gzip round trip, SHA-256, atomic rename, 25 MiB per-analysis quota, path traversal rejection, forbidden-content non-persistence, and orphan temporary-file cleanup.

- [ ] **Step 3: Run tests to verify failure**

Run: `.venv/bin/pytest tests/unit/test_extraction.py tests/integration/test_safe_collector.py tests/integration/test_artifact_store.py -v`

Expected: FAIL with missing collector modules.

- [ ] **Step 4: Implement the bounded collector and extraction chain**

Stream responses through the pinned transport, require suitable content type, apply block detection before article analysis, extract with Trafilatura then BeautifulSoup/JSON-LD, and save allowed HTML through `ArtifactStore` only.

- [ ] **Step 5: Verify Task 4 and record progress**

Run: `.venv/bin/pytest tests/unit/test_extraction.py tests/integration/test_safe_collector.py tests/integration/test_artifact_store.py -v && .venv/bin/ruff check app tests`

Expected: PASS and Ruff exits 0. Update `PROGRESS.md`.

- [ ] **Step 6: Commit**

```bash
git add app/scraping app/database/artifacts.py tests PROGRESS.md
git commit -m "feat: extract and preserve public articles safely"
```

### Task 5: Structured LLM adapter, claim extraction, and query generation

**Files:**
- Create: `docs/decisions/0001-llm-provider.md`
- Create: `app/core/privacy.py`
- Create: `app/claims/contracts.py`
- Create: `app/claims/schemas.py`
- Create: `app/claims/openai_provider.py`
- Create: `app/claims/fake_provider.py`
- Create: `app/claims/validation.py`
- Create: `app/claims/service.py`
- Create: `tests/fixtures/llm/claims.json`
- Create: `tests/unit/test_claim_validation.py`
- Create: `tests/unit/test_query_generation.py`
- Create: `tests/unit/test_llm_output_validation.py`
- Create: `tests/integration/test_openai_adapter.py`
- Modify: `.env.example`
- Modify: `PROGRESS.md`

**Interfaces:**
- Consumes: validated input, `Settings`, privacy consent, audit repository, and HTTPX.
- Produces: `ClaimExtractor.extract(text) -> list[Claim]`, `QueryGenerator.generate(claim) -> QuerySet`, `OpenAIResponsesProvider.generate_json(schema, messages)`, `FakeLlmProvider`, `validate_claims(text, candidates)`, and `PrivacyConsent.require_external_processing()`.

- [ ] **Step 1: Document the provider decision and write failing tests**

Record why the first adapter is OpenAI Responses API via raw HTTPX, the required `OPENAI_API_KEY` and required `OPENAI_MODEL`, structured-output requirement, replaceability, data-consent boundary, and no default model. Test valid excerpt, invented excerpt rejection, three-claim cap, atomicity fields, names/numbers/dates/negation preservation, temporal fields, two-to-four queries, and an official-source query.

- [ ] **Step 2: Write failing adversarial-output tests**

Cover invalid JSON, unknown fields, wrong enum, timeout, 429, one repair attempt, token/call budget, no secret in logs, unknown evidence/URL rejection, and `test_untrusted_content_cannot_expand_allowed_identifiers`.

- [ ] **Step 3: Run tests to verify failure**

Run: `.venv/bin/pytest tests/unit/test_claim_validation.py tests/unit/test_query_generation.py tests/unit/test_llm_output_validation.py tests/integration/test_openai_adapter.py -v`

Expected: FAIL because LLM and claim modules do not exist.

- [ ] **Step 4: Implement contracts, fakes, and the OpenAI adapter**

Use the Responses API structured-output JSON schema, delimit untrusted content, validate with Pydantic, require consent in real mode, account for calls/tokens before retries, and persist provider/model/prompt version without request secrets.

- [ ] **Step 5: Verify Task 5 and record progress**

Run: `.venv/bin/pytest tests/unit/test_claim_validation.py tests/unit/test_query_generation.py tests/unit/test_llm_output_validation.py tests/integration/test_openai_adapter.py -v && .venv/bin/ruff check app tests`

Expected: PASS and Ruff exits 0. Update `PROGRESS.md`.

- [ ] **Step 6: Commit**

```bash
git add docs/decisions app/core/privacy.py app/claims tests .env.example PROGRESS.md
git commit -m "feat: add structured claim extraction adapters"
```

### Task 6: Search provider, fact-check exclusion, canonicalization, and source independence

**Files:**
- Create: `docs/decisions/0002-search-provider.md`
- Create: `app/search/contracts.py`
- Create: `app/search/brave.py`
- Create: `app/search/fake.py`
- Create: `app/search/filtering.py`
- Create: `app/search/canonical.py`
- Create: `app/search/deduplication.py`
- Create: `app/evidence/source_metadata.py`
- Create: `tests/fixtures/search/results.json`
- Create: `tests/unit/test_search_filtering.py`
- Create: `tests/unit/test_deduplication.py`
- Create: `tests/integration/test_brave_search_adapter.py`
- Modify: `.env.example`
- Modify: `PROGRESS.md`

**Interfaces:**
- Consumes: `QuerySet`, HTTPX, call budget, and stored search/audit records.
- Produces: `SearchProvider.search(query: str, limit: int = 10) -> list[SearchResult]`, `BraveSearchProvider`, `FakeSearchProvider`, `canonicalize_url(url)`, `deduplicate_results(results)`, `group_document_independence(documents)`, and `describe_source(document) -> SourceMetadata`.

- [ ] **Step 1: Document the search decision and write failing adapter/filter tests**

Record Brave Web Search endpoint, `X-Subscription-Token`, `BRAVE_SEARCH_API_KEY`, `country=BR`, `ui_lang=pt-BR`, omission of `search_lang` to avoid relying on an undocumented locale value, result mapping, 429/quota errors, and replaceability. Test no key, timeout, malformed response, rank/query preservation, same/canonical URL removal, and configurable exclusion of Lupa, Aos Fatos, Fato ou Fake, Comprova, AFP Checamos and configured additions.

- [ ] **Step 2: Write failing content-independence tests**

Cover exact hash duplicates, near duplicates, syndication/attribution clues, same domain without copied content, copied content on different domains, deterministic `independence_group`, and audit reasons for grouping.

- [ ] **Step 3: Run tests to verify failure**

Run: `.venv/bin/pytest tests/unit/test_search_filtering.py tests/unit/test_deduplication.py tests/integration/test_brave_search_adapter.py -v`

Expected: FAIL with missing search modules.

- [ ] **Step 4: Implement search and deduplication**

Use Brave only to discover result pages; do not use generated answers or provider verdicts. Normalize tracking parameters conservatively, combine canonical URL/SHA-256/SimHash/attribution signals, and never convert descriptive source metadata into a truth score.

- [ ] **Step 5: Verify Task 6 and record progress**

Run: `.venv/bin/pytest tests/unit/test_search_filtering.py tests/unit/test_deduplication.py tests/integration/test_brave_search_adapter.py -v && .venv/bin/ruff check app tests`

Expected: PASS and Ruff exits 0. Update `PROGRESS.md`.

- [ ] **Step 6: Commit**

```bash
git add docs/decisions app/search app/evidence/source_metadata.py tests .env.example PROGRESS.md
git commit -m "feat: add independent evidence discovery"
```

### Task 7: Evidence chunking and auditable ranking

**Files:**
- Create: `app/evidence/chunking.py`
- Create: `app/evidence/ranking.py`
- Create: `app/evidence/service.py`
- Create: `tests/unit/test_chunking.py`
- Create: `tests/unit/test_evidence_ranking.py`
- Modify: `PROGRESS.md`

**Interfaces:**
- Consumes: validated claims, extracted documents, `SourceMetadata`, and repository records.
- Produces: `chunk_document(document, max_chars, overlap_chars) -> list[EvidenceChunk]`, `EvidenceRanker.rank(claim, candidates, limit=5) -> list[RankedEvidence]`, and `EvidenceService.collect_for_claim(claim, search_results)`.

- [ ] **Step 1: Write failing chunking tests**

Cover bounded chunks, overlap, stable IDs/indexes, context preservation, sentence boundaries, metadata/URL propagation, empty documents, and preservation of numbers, dates and negation.

- [ ] **Step 2: Write failing ranking tests**

Cover BM25 term relevance, entity/date/number/title matches, temporal mismatch penalty, official-source boost only when the query or claim explicitly requests an official document, no source truth score, independence-group diversity, deterministic ties, and maximum five items.

- [ ] **Step 3: Run tests to verify failure**

Run: `.venv/bin/pytest tests/unit/test_chunking.py tests/unit/test_evidence_ranking.py -v`

Expected: FAIL with missing evidence modules.

- [ ] **Step 4: Implement pure-Python auditable ranking**

Implement BM25 and explicit additive feature contributions so every rank can expose its factors. Do not use a local BERT model or hidden probability.

- [ ] **Step 5: Verify Task 7 and record progress**

Run: `.venv/bin/pytest tests/unit/test_chunking.py tests/unit/test_evidence_ranking.py -v && .venv/bin/ruff check app tests`

Expected: PASS and Ruff exits 0. Update `PROGRESS.md`.

- [ ] **Step 6: Commit**

```bash
git add app/evidence tests PROGRESS.md
git commit -m "feat: rank auditable evidence chunks"
```

### Task 8: Evidence judgments, literal quotations, deterministic aggregation, and reports

**Files:**
- Create: `app/fact_checking/contracts.py`
- Create: `app/fact_checking/judgment.py`
- Create: `app/fact_checking/quotation.py`
- Create: `app/fact_checking/aggregation.py`
- Create: `app/reports/schemas.py`
- Create: `app/reports/builder.py`
- Create: `tests/unit/test_judgment_validation.py`
- Create: `tests/unit/test_aggregation.py`
- Create: `tests/unit/test_report_builder.py`
- Modify: `PROGRESS.md`

**Interfaces:**
- Consumes: `OpenAIResponsesProvider` or fake judge, stored claims/evidence/source metadata, operation outcomes, and disabled risk result.
- Produces: `EvidenceJudge.judge(claim, evidence) -> EvidenceDecision`, `validate_decision(decision, evidence)`, `map_quote_to_original(quote, evidence) -> OriginalQuote`, `aggregate_claim(claim, decisions, sources) -> ClaimResult`, `aggregate_analysis(results) -> OverallResult`, and `ReportBuilder.build(analysis) -> AnalysisReport`.

- [ ] **Step 1: Write failing judgment and quotation tests**

Cover exact quote, missing quote, quote from another evidence, unknown IDs, one repair, error exclusion, required evidence-only prompt, Unicode/whitespace normalization, and `test_quote_mapping_returns_original_characters`.

- [ ] **Step 2: Write failing deterministic aggregation tests**

Cover direct primary support/refutation, unrelated evidence as `NEI`, no evidence as `NEI`, independent disagreement as `CONFLICTING`, copied disagreement not independent, outdated evidence not deciding a current claim, technical error never refuting, and categorical confidence only.

- [ ] **Step 3: Write failing report tests**

Cover overall statuses, exact BERTimbau waiting copy, every factual conclusion citing stored evidence, no unknown URL/fact, partial-analysis limitations, source dates, retrieval time, and clickable URL serialization.

- [ ] **Step 4: Run tests to verify failure**

Run: `.venv/bin/pytest tests/unit/test_judgment_validation.py tests/unit/test_aggregation.py tests/unit/test_report_builder.py -v`

Expected: FAIL with missing fact-checking/report modules.

- [ ] **Step 5: Implement validators, aggregator, and report builder**

Keep all overall rules in Python. The LLM only judges supplied claim-evidence pairs and drafts explanations whose facts are checked against referenced evidence.

- [ ] **Step 6: Verify Task 8 and record progress**

Run: `.venv/bin/pytest tests/unit/test_judgment_validation.py tests/unit/test_aggregation.py tests/unit/test_report_builder.py -v && .venv/bin/ruff check app tests`

Expected: PASS and Ruff exits 0. Update `PROGRESS.md`.

- [ ] **Step 7: Commit**

```bash
git add app/fact_checking app/reports tests PROGRESS.md
git commit -m "feat: produce evidence-bound factual reports"
```

### Task 9: Pipeline orchestration, bounded jobs, and recovery

**Files:**
- Create: `app/services/pipeline.py`
- Create: `app/services/jobs.py`
- Create: `app/services/recovery.py`
- Create: `tests/fixtures/demo/supported.json`
- Create: `tests/fixtures/demo/refuted.json`
- Create: `tests/fixtures/demo/nei.json`
- Create: `tests/fixtures/demo/conflicting.json`
- Create: `tests/integration/test_pipeline_text.py`
- Create: `tests/integration/test_pipeline_url.py`
- Create: `tests/integration/test_job_executor.py`
- Modify: `PROGRESS.md`

**Interfaces:**
- Consumes: all service interfaces from Tasks 1–8 and repositories from Task 2.
- Produces: `AnalysisPipeline.run(analysis_id) -> AnalysisRecord`, `JobExecutor.submit(analysis_id)`, `JobExecutor.status(analysis_id)`, and `RecoveryService.fail_interrupted_analyses()`.

- [ ] **Step 1: Write failing end-to-end fake-pipeline tests**

Cover text and URL paths, preservation/audit of every stage, the four fictitious verdict cases, unavailable BERTimbau, provider-disabled error, retry without overwrite, five-minute budget, per-analysis call/token/storage budgets, and `test_partial_pipeline_has_explicit_limitations`.

- [ ] **Step 2: Write failing executor/recovery tests**

Cover two active jobs, ten queued jobs, capacity rejection, duplicate key replay without duplicate cost, worker exception, process-restart recovery, and explicit status progression.

- [ ] **Step 3: Run tests to verify failure**

Run: `.venv/bin/pytest tests/integration/test_pipeline_text.py tests/integration/test_pipeline_url.py tests/integration/test_job_executor.py -v`

Expected: FAIL with missing services.

- [ ] **Step 4: Implement the synchronous pipeline and bounded executor**

Persist before and after each stage, stop on terminal safety errors, continue independent claims when safe, distinguish partial completion, and submit only identifiers to the executor so workers reload persisted state.

- [ ] **Step 5: Verify Task 9 and record progress**

Run: `.venv/bin/pytest tests/integration/test_pipeline_text.py tests/integration/test_pipeline_url.py tests/integration/test_job_executor.py -v && .venv/bin/ruff check app tests`

Expected: PASS and Ruff exits 0. Update `PROGRESS.md`.

- [ ] **Step 6: Commit**

```bash
git add app/services tests PROGRESS.md
git commit -m "feat: orchestrate bounded verification jobs"
```

### Task 10: FastAPI endpoints and local Streamlit interface

**Files:**
- Create: `app/api/dependencies.py`
- Create: `app/api/schemas.py`
- Create: `app/api/routes.py`
- Create: `app/main.py`
- Create: `frontend/app.py`
- Create: `frontend/client.py`
- Create: `tests/integration/test_api.py`
- Create: `tests/unit/test_frontend_presenters.py`
- Modify: `PROGRESS.md`

**Interfaces:**
- Consumes: repository, `AnalysisPipeline`, `JobExecutor`, reports, `Settings`, and privacy consent.
- Produces: `create_app() -> FastAPI`, the four required `/api/v1/analyses` endpoints, `ApiClient`, and Portuguese Streamlit presenters.

- [ ] **Step 1: Write failing API tests**

Cover `POST` returning `202` and `Location`, text/URL validation, optional `Idempotency-Key`, conflicting payload response, queue capacity response, missing analysis `404`, claims/report retrieval, partial-result serialization, no raw HTML response, and CORS/local defaults.

- [ ] **Step 2: Write failing presentation tests**

Cover Portuguese labels, consent prompt in real LLM mode, progress/status mapping, explicit label plus color, clickable evidence URLs, limitations, technical errors distinct from `NEI`, and exact BERTimbau message.

- [ ] **Step 3: Run tests to verify failure**

Run: `.venv/bin/pytest tests/integration/test_api.py tests/unit/test_frontend_presenters.py -v`

Expected: FAIL with missing API/frontend modules.

- [ ] **Step 4: Implement the API and Streamlit client**

Keep processing out of route handlers, poll status without blocking Streamlit's entire session, escape displayed content, and bind documented launch commands to localhost.

- [ ] **Step 5: Verify Task 10 and record progress**

Run: `.venv/bin/pytest tests/integration/test_api.py tests/unit/test_frontend_presenters.py -v && .venv/bin/ruff check app frontend tests`

Expected: PASS and Ruff exits 0. Update `PROGRESS.md`.

- [ ] **Step 6: Commit**

```bash
git add app/api app/main.py frontend tests PROGRESS.md
git commit -m "feat: expose local api and investigation ui"
```

### Task 11: Evaluation corpus, documentation, and complete verification

**Files:**
- Create: `tests/evaluation/cases.json`
- Create: `scripts/run_evaluation.py`
- Create: `tests/integration/test_evaluation_corpus.py`
- Create: `README.md`
- Create: `docs/limitations.md`
- Create: `docs/bertimbau-integration.md`
- Create: `docs/security.md`
- Modify: `.env.example`
- Modify: `PROGRESS.md`

**Interfaces:**
- Consumes: public application interfaces and fake pipeline fixtures.
- Produces: `scripts/run_evaluation.py` JSON regression summary, complete run instructions, security/limitations documentation, and future BERTimbau adapter instructions.

- [ ] **Step 1: Write the evaluation corpus and failing corpus test**

Include negation, conflicting dates, different units, republications, stale sources, partial support, literal quote out of context, prompt injection, and mid-analysis technical failure. Assert expected verdict/status/limitations without claiming a truth probability.

- [ ] **Step 2: Run the corpus as an acceptance baseline**

Run: `.venv/bin/pytest tests/integration/test_evaluation_corpus.py -v`

Expected: PASS because Tasks 1–10 implement the specified behaviors. If a case fails, first add a focused failing regression test to the owning task's module, apply the minimal fix, and rerun both tests.

- [ ] **Step 3: Write user and operator documentation**

Document scraping versus fact-checking, architecture, local venv setup without administrator access, environment variables, OpenAI/Brave consent and cost caveats, API/Streamlit commands, tests, demo mode, retention, localhost restriction, limitations, audit behavior, and future BERTimbau integration.

- [ ] **Step 4: Run full verification**

Run: `.venv/bin/pytest -q`

Expected: all tests pass with no network access.

Run: `.venv/bin/ruff check app frontend tests scripts`

Expected: Ruff exits 0.

Run: `.venv/bin/ruff format --check app frontend tests scripts`

Expected: formatting check exits 0.

Run: `.venv/bin/python scripts/run_evaluation.py`

Expected: all versioned fictional cases match their expected statuses and the output contains no truth percentages.

- [ ] **Step 5: Perform a local smoke test**

Start API on `127.0.0.1`, run the explicit fictional demo through Streamlit, verify the four verdicts and BERTimbau waiting message, then stop both processes. Do not use real keys for the smoke test.

- [ ] **Step 6: Finalize progress and commit**

Record exact verification output, known limitations, and every created/modified file in `PROGRESS.md`.

```bash
git add README.md docs scripts tests .env.example PROGRESS.md
git commit -m "docs: complete verificaai poc guidance"
```
