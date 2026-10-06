# VerificaAI Django Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the existing factual pipeline on immutable Django runs with complete versioning, observability, bounded retries, crash-recoverable local jobs, and a strictly auxiliary BERTimbau stage.

**Architecture:** Keep fact-checking domain objects independent from Django and adapt persistence through a Django store. Persist `FACTUAL_COMPLETED` before scheduling the typed BERT stage; persistent `Job` rows and leases are the source of truth while `ThreadPoolExecutor` is only an execution mechanism.

**Tech Stack:** Django 5.2 LTS, SQLite/WAL, Python `ThreadPoolExecutor`, contextvars, PyTorch, Transformers, Hugging Face Hub, pytest-django.

**Spec:** `docs/superpowers/specs/2026-10-06-verificaai-django-migration-design.md`

## Global Constraints

- Requires completion of `2026-10-06-verificaai-django-foundation.md`.
- Factual results must be committed before BERT download, load, or inference begins.
- BERTimbau never supplies retrieval, ranking, evidence, or factual aggregation signals.
- Each run stores app commit, dirty flag, prompt hashes, provider/model revisions, algorithm versions, limits, and relevant runtime versions.
- Logs and metrics carry correlation IDs but never raw input, HTML, full URLs, prompts, evidence, secrets, or unbounded labels.
- Retries are category-specific, deadline-aware, idempotent, and recorded as new attempts.
- One local application process owns one runtime; no pool starts at import or `AppConfig.ready()`.

## Review Focus

- Process death after factual commit but before BERT completion must leave the factual report retrievable; Task 5 adds the subprocess crash test.
- A runner that ignores cancellation and exceeds shutdown grace must not be reported as stopped; Task 4 adds the lifecycle test.
- Repeated SQLite lock errors must stop at the configured attempt/deadline budget without duplicate rows; Task 3 adds the test.
- A malformed risk result (`NaN`, unknown label, missing keys) must become `TECHNICAL_ERROR`; Task 6 adds the test.
- Extra files, symlinks, concurrent writers, or changed bucket metadata must never enter the model cache; Task 6 adds deterministic tests.

---

### Task 1: Django pipeline store and version manifest

**Files:**
- Create: `analyses/runtime/__init__.py`
- Create: `analyses/runtime/manifest.py`
- Create: `analyses/runtime/store.py`
- Modify: `app/services/pipeline.py`
- Test: `tests/django/test_pipeline_manifest.py`
- Test: `tests/django/test_pipeline_store.py`

**Interfaces:**
- Consumes: foundation models/state services and current `AnalysisPipeline` domain collaborators.
- Produces: `PipelineManifest.capture(*, settings, prompt_files: Sequence[Path]) -> dict[str, object]` and `DjangoPipelineStore` methods `load_run`, `save_clean_input`, `save_claims`, `save_queries`, `save_results`, `save_evidence`, `save_decisions`, `save_factual_report`, and `complete_run`.

- [ ] **Step 1: Write failing manifest and store tests**

Assert literal manifest keys/hashes, clean/dirty Git state representation, no secret values, atomic stage writes, same-run relationship enforcement, immutable earlier runs, and `FACTUAL_COMPLETED` immediately after report commit.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/pytest tests/django/test_pipeline_manifest.py tests/django/test_pipeline_store.py -v`  
Expected: FAIL because runtime modules do not exist.

- [ ] **Step 3: Implement manifest capture and store adapter**

Move persistence calls behind `DjangoPipelineStore`; keep domain schemas unchanged. Make prompt paths explicit inputs and hash bytes, not rendered sensitive prompts.

- [ ] **Step 4: Verify GREEN**

Run: `.venv/bin/pytest tests/django/test_pipeline_manifest.py tests/django/test_pipeline_store.py tests/integration/test_pipeline_text.py -v`  
Expected: new tests PASS and existing factual scenarios remain green.

- [ ] **Step 5: Commit**

```bash
git add analyses/runtime app/services/pipeline.py tests/django/test_pipeline_manifest.py tests/django/test_pipeline_store.py tests/integration/test_pipeline_text.py
git commit -m "feat: persist versioned django pipeline runs"
```

### Task 2: Correlation context and structured observability

**Files:**
- Create: `analyses/observability/__init__.py`
- Create: `analyses/observability/context.py`
- Create: `analyses/observability/logging.py`
- Create: `analyses/observability/metrics.py`
- Create: `analyses/middleware.py`
- Modify: `verificaai/settings/base.py`
- Test: `tests/django/test_correlation.py`
- Test: `tests/django/test_observability.py`

**Interfaces:**
- Consumes: `request_id`, `analysis_id`, `run_id`, and `job_id` UUIDs.
- Produces: `correlation_scope(**ids) -> ContextManager`, `current_correlation() -> CorrelationIds`, `record_metric(name: MetricName, value: float, labels: Mapping[str, str]) -> None`, and `RequestIdMiddleware` that returns `X-Request-ID`.

- [ ] **Step 1: Write failing propagation, redaction, and cardinality tests**

Assert validated incoming UUID or generated UUID, response header, context propagation into worker wrapper, JSON log fields, complete redaction, duration metrics, and rejection of URL/text/user-generated metric labels.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/pytest tests/django/test_correlation.py tests/django/test_observability.py -v`  
Expected: FAIL because middleware/context/metrics are missing.

- [ ] **Step 3: Implement contextvars, JSON formatter, and in-process metric registry**

Define a fixed `MetricName` enum and fixed label allowlists. Reset context tokens in `finally` so threads cannot leak correlation IDs between jobs.

- [ ] **Step 4: Verify GREEN**

Run: `.venv/bin/pytest tests/django/test_correlation.py tests/django/test_observability.py -v`  
Expected: all tests PASS with no sensitive fixture text in captured logs.

- [ ] **Step 5: Commit**

```bash
git add analyses/observability analyses/middleware.py verificaai/settings/base.py tests/django/test_correlation.py tests/django/test_observability.py
git commit -m "feat: add correlated django observability"
```

### Task 3: Typed retry and backoff policy

**Files:**
- Create: `analyses/runtime/errors.py`
- Create: `analyses/runtime/retry.py`
- Modify: `app/scraping/client.py`
- Modify: `app/claims/openai_provider.py`
- Modify: `app/search/brave.py`
- Test: `tests/django/test_retry_policy.py`

**Interfaces:**
- Consumes: typed operational errors from network, provider, model, validation, integrity, and SQLite boundaries.
- Produces: `RetryDecision(retry: bool, delay_seconds: float, category: ErrorCategory)`, `RetryPolicy.decide(error, attempt, remaining_seconds, retry_after=None)`, and `run_with_retry(operation, policy, clock, sleeper, jitter) -> T`.

- [ ] **Step 1: Write failing table-driven policy tests**

Use literal expected decisions for every row in spec section 8.1, including `429`, `5xx`, `4xx`, SSRF, robots denial, invalid schema/hash, SQLite locks, deadline exhaustion, deterministic jitter, and no duplicate confirmed side effects.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/pytest tests/django/test_retry_policy.py -v`  
Expected: FAIL because error categories and policy do not exist.

- [ ] **Step 3: Implement policy and adapt external boundaries**

Remove broad provider retry decisions from adapters; translate exceptions once, honor `Retry-After`, cap at two retries, and persist attempt metadata through the caller.

- [ ] **Step 4: Verify GREEN**

Run: `.venv/bin/pytest tests/django/test_retry_policy.py tests/integration/test_safe_collector.py tests/integration/test_openai_adapter.py tests/integration/test_brave_search_adapter.py -v`  
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add analyses/runtime/errors.py analyses/runtime/retry.py app/scraping/client.py app/claims/openai_provider.py app/search/brave.py tests/django/test_retry_policy.py
git commit -m "feat: enforce typed retry policies"
```

### Task 4: Persistent local job runtime lifecycle

**Files:**
- Create: `analyses/jobs/__init__.py`
- Create: `analyses/jobs/runtime.py`
- Create: `analyses/jobs/service.py`
- Create: `analyses/jobs/signals.py`
- Modify: `verificaai/settings/base.py`
- Test: `tests/django/test_job_runtime.py`
- Test: `tests/django/test_job_lifecycle.py`

**Interfaces:**
- Consumes: persistent `Job`, transition services, correlation scope, retry policy, `runner(run_id: UUID) -> None`.
- Produces: `LocalJobRuntime.start()`, `submit(run_id: UUID, request_id: UUID) -> Job`, `status(job_id: UUID) -> Job`, `shutdown(grace_seconds: float) -> ShutdownResult`; lifecycle `NEW|RUNNING|DRAINING|STOPPED`.

- [ ] **Step 1: Write failing capacity, lease, lifecycle, and connection tests**

Assert one pool per runtime, idempotent start/shutdown, exact worker/queue bounds, rejection during draining, queued rows retained when futures are cancelled, heartbeat renewal, context cleanup, `close_old_connections()` around work, and a non-cooperative runner returning `grace_expired=True` rather than a false success.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/pytest tests/django/test_job_runtime.py tests/django/test_job_lifecycle.py -v`  
Expected: FAIL because local runtime does not exist.

- [ ] **Step 3: Implement explicit runtime lifecycle**

Do not instantiate at import or `AppConfig.ready()`. Start lazily through the application service, install signal/atexit hooks only from the local entrypoint, use `shutdown(wait=False, cancel_futures=True)` after bounded waiting, and expose the inability to kill running threads in `ShutdownResult`.

- [ ] **Step 4: Verify GREEN and absence of leaked threads**

Run: `.venv/bin/pytest tests/django/test_job_runtime.py tests/django/test_job_lifecycle.py -v`  
Expected: all tests PASS and thread enumeration returns to baseline after cooperative cases.

- [ ] **Step 5: Commit**

```bash
git add analyses/jobs verificaai/settings/base.py tests/django/test_job_runtime.py tests/django/test_job_lifecycle.py
git commit -m "feat: add persistent local job runtime"
```

### Task 5: Lease reconciliation and real crash recovery

**Files:**
- Create: `analyses/jobs/recovery.py`
- Create: `analyses/management/commands/run_local_runtime.py`
- Create: `tests/helpers/crash_worker.py`
- Test: `tests/django/test_crash_recovery.py`
- Test: `tests/django/test_sqlite_contention.py`

**Interfaces:**
- Consumes: Task 4 runtime and Job rows with leases/checkpoints.
- Produces: `reconcile_expired_jobs(now: datetime) -> RecoverySummary` and local entrypoint with `SIGTERM`/`SIGINT`, no autoreload, one process.

- [ ] **Step 1: Write failing subprocess crash and SQLite contention tests**

Start a real child process against a temporary SQLite file, wait for a checkpoint marker, send `SIGKILL`, advance lease time, and start recovery. Cover crashes before and after `FACTUAL_COMPLETED`, retry eligibility, no duplicate report/claims, bounded lock retries, and exact `INTERRUPTED` audit records.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/pytest tests/django/test_crash_recovery.py tests/django/test_sqlite_contention.py -v`  
Expected: FAIL because recovery and entrypoint are absent.

- [ ] **Step 3: Implement lease reconciliation and local entrypoint**

Use database time where possible, conditional updates on current state/lease, new Job rows with `retry_of`, and checkpoints to resume only idempotent work. Configure WAL/busy timeout and reject multi-process local configuration.

- [ ] **Step 4: Verify GREEN**

Run: `.venv/bin/pytest tests/django/test_crash_recovery.py tests/django/test_sqlite_contention.py -v`  
Expected: all subprocess tests PASS without hanging or leaving child processes.

- [ ] **Step 5: Commit**

```bash
git add analyses/jobs/recovery.py analyses/management/commands/run_local_runtime.py tests/helpers/crash_worker.py tests/django/test_crash_recovery.py tests/django/test_sqlite_contention.py
git commit -m "feat: recover interrupted local jobs"
```

### Task 6: Factual-first BERTimbau stage and hardened cache

**Files:**
- Modify: `app/risk_analysis/base.py`
- Modify: `app/risk_analysis/bertimbau.py`
- Modify: `app/risk_analysis/disabled.py`
- Create: `analyses/runtime/risk.py`
- Modify: `app/services/pipeline.py`
- Test: `tests/django/test_risk_stage.py`
- Test: `tests/unit/test_risk_analysis.py`
- Test: `tests/integration/test_pipeline_text.py`

**Interfaces:**
- Consumes: a run already in `FACTUAL_COMPLETED`, verified model manifest, persistent `BERTAnalysis`.
- Produces: Pydantic `RiskAnalysisResult`, `run_bert_stage(run_id: UUID, timeout_seconds: float) -> BERTAnalysis`, exact four-file cache, and final run state independent from linguistic outcome.

- [ ] **Step 1: Write failing typed-result, ordering, cache, and separation tests**

Assert factual report visibility before BERT starts; timeout/crash/missing dependency/NaN/unknown label becomes terminal auxiliary error; disabled copy is accurate; extra file, symlink, wrong hash/Xet, and two concurrent cache writers fail safely; no BERT symbol or score is imported by search/evidence/ranking modules.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/pytest tests/django/test_risk_stage.py tests/unit/test_risk_analysis.py tests/integration/test_pipeline_text.py -v`  
Expected: FAIL for missing typed stage and hardened cache behavior.

- [ ] **Step 3: Implement factual-first stage and cache locking**

Validate result schema/ranges, use an inter-process file lock, exact allowlist without symlinks, recheck after lock, atomic promotion without deleting a valid target, and local-only safetensors loading. Keep `semantic_ranking` absent and do not expose a retrieval interface from this module.

- [ ] **Step 4: Verify complete runtime**

Run: `.venv/bin/pytest tests/django tests/unit/test_risk_analysis.py tests/integration/test_pipeline_text.py -q && .venv/bin/ruff check analyses app tests`  
Expected: all runtime and regression tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/risk_analysis app/services/pipeline.py analyses/runtime/risk.py tests/django/test_risk_stage.py tests/unit/test_risk_analysis.py tests/integration/test_pipeline_text.py
git commit -m "feat: isolate factual and bert analysis stages"
```
