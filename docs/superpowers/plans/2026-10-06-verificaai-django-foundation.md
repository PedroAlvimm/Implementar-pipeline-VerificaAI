# VerificaAI Django Foundation Implementation Plan

> **Substituído:** para a entrega 1.0, use `2026-10-06-verificaai-1-0.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an executable Django foundation, constrained audit models, formal state machines, and a safe legacy SQLite importer while leaving the existing application runnable.

**Architecture:** Introduce a `verificaai` Django project and an `analyses` Django app beside the current code. Django owns new persistence; existing domain modules remain framework-independent until the runtime plan migrates their storage adapters.

**Tech Stack:** Python 3.11+, Django 5.2 LTS, Django REST Framework 3.16+, SQLite, pytest, pytest-django.

**Spec:** `docs/superpowers/specs/2026-10-06-verificaai-django-migration-design.md`

## Global Constraints

- Preserve the legacy SQLite file as read-only; never migrate in place or delete it.
- Use Django database constraints for invariants expressible by SQLite; document service-enforced cross-table invariants.
- UUIDs and timestamps are immutable/UTC; audit rows use `PROTECT`, not cascading deletion.
- Every analysis execution is a new immutable `AnalysisRun`; old results are never overwritten.
- SQLite is local-only; configure WAL, short transactions, one application process, and low concurrency.
- Keep the existing FastAPI/Streamlit/SQLAlchemy stack runnable until the final cutover plan.
- Existing uncommitted BERTimbau work is user-owned source material; do not discard or reset it.

## Review Focus

- Two concurrent requests for a new run on one analysis must produce one active run and no duplicate ordinal; Task 3 adds the concurrency test.
- Reusing an idempotency key with different content must return a conflict without a second analysis; Task 3 adds the test.
- A legacy database with missing parents or malformed JSON must fail dry-run without destination writes; Task 4 adds the test.
- Direct ORM writes with invalid state, score, ordinal, or duplicate report must fail at the database boundary; Task 2 adds the tests.
- Naive timestamps and malformed UUIDs in legacy rows must be rejected and reported, not silently normalized; Task 4 adds the test.

---

### Task 1: Django project bootstrap

**Files:**
- Create: `manage.py`
- Create: `verificaai/__init__.py`
- Create: `verificaai/settings/__init__.py`
- Create: `verificaai/settings/base.py`
- Create: `verificaai/settings/local.py`
- Create: `verificaai/settings/test.py`
- Create: `verificaai/urls.py`
- Create: `verificaai/asgi.py`
- Create: `verificaai/wsgi.py`
- Create: `analyses/__init__.py`
- Create: `analyses/apps.py`
- Modify: `pyproject.toml`
- Modify: `tests/conftest.py`
- Test: `tests/django/test_django_bootstrap.py`

**Interfaces:**
- Consumes: environment values already represented by `app.core.config.Settings`.
- Produces: `DJANGO_SETTINGS_MODULE=verificaai.settings.test`, Django app label `analyses`, SQLite connection initialization with WAL and busy timeout.

- [ ] **Step 1: Write the failing bootstrap tests**

Add `test_django_boots_with_localhost_defaults`, `test_test_database_enables_foreign_keys_and_wal`, and `test_secret_key_has_no_production_default`. Assert installed app names, `ALLOWED_HOSTS`, SQLite pragmas, timezone UTC, and safe production validation.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/pytest tests/django/test_django_bootstrap.py -v`  
Expected: FAIL because the Django project and dependency do not exist.

- [ ] **Step 3: Implement the minimal Django project**

Add `django>=5.2,<5.3`, `djangorestframework>=3.16,<4`, and `pytest-django>=4.11,<5`. Keep settings split by environment, preserve localhost defaults, configure UTC and SQLite connection setup without starting threads.

- [ ] **Step 4: Verify GREEN**

Run: `.venv/bin/pytest tests/django/test_django_bootstrap.py -v && .venv/bin/python manage.py check --settings=verificaai.settings.test`  
Expected: all tests PASS and Django reports no system-check issues.

- [ ] **Step 5: Commit**

```bash
git add manage.py verificaai analyses pyproject.toml tests/conftest.py tests/django/test_django_bootstrap.py
git commit -m "feat: bootstrap django application"
```

### Task 2: Audit models, constraints, and indexes

**Files:**
- Create: `analyses/models/__init__.py`
- Create: `analyses/models/analysis.py`
- Create: `analyses/models/job.py`
- Create: `analyses/models/content.py`
- Create: `analyses/models/risk.py`
- Create: `analyses/migrations/0001_initial.py`
- Test: `tests/django/test_model_constraints.py`
- Test: `tests/django/test_model_indexes.py`

**Interfaces:**
- Consumes: Django app and database settings from Task 1.
- Produces: `Analysis`, `AnalysisRun`, `Job`, `BERTAnalysis`, `Claim`, `Query`, `SearchResult`, `Evidence`, `Decision`, `Report`, `Artifact`, `AuditEvent`; text-choice enums for all states.

- [ ] **Step 1: Write failing constraint and index tests**

Add literal cases for every constraint in spec sections 4.1–4.2. Use `transaction.atomic()` and assert `IntegrityError` for invalid direct writes. Inspect `connection.introspection.get_constraints()` and `EXPLAIN QUERY PLAN` for `job_queue_idx`, `job_lease_idx`, run history, evidence rank, and artifact retention.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/pytest tests/django/test_model_constraints.py tests/django/test_model_indexes.py -v`  
Expected: FAIL because the models and migrations do not exist.

- [ ] **Step 3: Implement models and initial migration**

Use focused model modules and exact constraint/index names from the spec. Use `PROTECT` for audit relationships, conditional unique constraints for one active run/job, one-to-one `Report.run`, and database checks for enum values, score range, timestamps, and positive ordinals.

- [ ] **Step 4: Verify GREEN and migration stability**

Run: `.venv/bin/pytest tests/django/test_model_constraints.py tests/django/test_model_indexes.py -v && .venv/bin/python manage.py makemigrations --check --dry-run --settings=verificaai.settings.test`  
Expected: tests PASS and `No changes detected`.

- [ ] **Step 5: Commit**

```bash
git add analyses/models analyses/migrations tests/django/test_model_constraints.py tests/django/test_model_indexes.py
git commit -m "feat: model auditable django analyses"
```

### Task 3: State machines and run creation services

**Files:**
- Create: `analyses/services/__init__.py`
- Create: `analyses/services/transitions.py`
- Create: `analyses/services/creation.py`
- Test: `tests/django/test_state_machines.py`
- Test: `tests/django/test_analysis_runs.py`

**Interfaces:**
- Consumes: model enums and constraints from Task 2.
- Produces: `transition_analysis(analysis_id: UUID, target: AnalysisState) -> Analysis`, `transition_run(run_id: UUID, target: RunState) -> AnalysisRun`, `transition_job(job_id: UUID, target: JobState) -> Job`, `transition_bert(bert_id: UUID, target: BERTState) -> BERTAnalysis`, `create_analysis(input_type: str, content: str, idempotency_key: str | None) -> tuple[Analysis, bool]`, and `create_run(analysis_id: UUID, request_id: UUID, manifest: dict[str, object]) -> AnalysisRun`.

- [ ] **Step 1: Write failing transition, idempotency, and concurrent-run tests**

Assert every allowed transition from spec section 4.5, representative forbidden transitions, idempotent replay, mismatch conflict, immutable terminal runs, and two concurrent `create_run` calls yielding one active run with unique ordinals.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/pytest tests/django/test_state_machines.py tests/django/test_analysis_runs.py -v`  
Expected: FAIL because service functions are missing.

- [ ] **Step 3: Implement transactional services**

Use `transaction.atomic()`, `select_for_update()`, explicit transition maps, and `F()`/aggregate logic for ordinals. Map database contention or uniqueness races to typed `IdempotencyConflict`, `ActiveRunConflict`, and `InvalidTransition` errors.

- [ ] **Step 4: Verify GREEN**

Run: `.venv/bin/pytest tests/django/test_state_machines.py tests/django/test_analysis_runs.py -v`  
Expected: all tests PASS repeatedly with `--count=5` when pytest-repeat is available.

- [ ] **Step 5: Commit**

```bash
git add analyses/services tests/django/test_state_machines.py tests/django/test_analysis_runs.py
git commit -m "feat: enforce django analysis state machines"
```

### Task 4: Idempotent legacy SQLite importer

**Files:**
- Create: `analyses/legacy/__init__.py`
- Create: `analyses/legacy/reader.py`
- Create: `analyses/legacy/importer.py`
- Create: `analyses/management/commands/migrate_legacy_data.py`
- Test: `tests/django/test_legacy_import.py`
- Test: `tests/fixtures/legacy/build_legacy_db.py`

**Interfaces:**
- Consumes: all Task 2 models and Task 3 creation services.
- Produces: `LegacyImportService(source: Path)`, `plan() -> ImportSummary`, `execute() -> ImportSummary`, and command `manage.py migrate_legacy_data --source PATH [--dry-run] [--report PATH]`.

- [ ] **Step 1: Write failing dry-run, import, idempotency, rollback, and malformed-source tests**

Build the legacy fixture from literal SQL matching current SQLAlchemy tables. Assert one `AnalysisRun(ordinal=1)` per legacy analysis, preserved IDs/timestamps/payloads, zero writes in dry-run, identical counts after rerun, JSON audit report, and total rollback for orphan, naive timestamp, malformed UUID, or invalid JSON rows.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/pytest tests/django/test_legacy_import.py -v`  
Expected: FAIL because importer and command are missing.

- [ ] **Step 3: Implement read-only validation and transactional import**

Open the source with SQLite read-only URI mode, validate its schema before destination writes, map each legacy analysis to run ordinal 1, preserve raw payload JSON, and reconcile counts/relationships/hashes in `ImportSummary`.

- [ ] **Step 4: Verify GREEN**

Run: `.venv/bin/pytest tests/django/test_legacy_import.py -v`  
Expected: all tests PASS; malformed fixtures leave destination counts at zero.

- [ ] **Step 5: Commit**

```bash
git add analyses/legacy analyses/management tests/django/test_legacy_import.py tests/fixtures/legacy
git commit -m "feat: import legacy analyses into django"
```

### Task 5: Safe Django Admin and foundation verification

**Files:**
- Create: `analyses/admin.py`
- Test: `tests/django/test_admin_safety.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 2 models and immutable-service rules.
- Produces: read-oriented Admin registrations that expose IDs, states, timings, and hashes but not secrets, raw HTML, full input, or mutation of protected state.

- [ ] **Step 1: Write failing Admin safety tests**

Assert sensitive fields are excluded, state fields are readonly, protected model deletion is unavailable, list pages use indexed filters, and no job runtime starts while loading Admin or running `manage.py check`.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/pytest tests/django/test_admin_safety.py -v`  
Expected: FAIL because Admin registrations are missing.

- [ ] **Step 3: Implement Admin and foundation run instructions**

Register focused `ModelAdmin` classes and document migrations plus legacy `--dry-run`; do not add runtime threads.

- [ ] **Step 4: Verify the complete foundation**

Run: `.venv/bin/pytest tests/django -q && .venv/bin/python manage.py check --settings=verificaai.settings.test && .venv/bin/ruff check analyses verificaai tests/django`  
Expected: all tests and checks PASS.

- [ ] **Step 5: Commit**

```bash
git add analyses/admin.py tests/django/test_admin_safety.py README.md
git commit -m "feat: expose safe django audit admin"
```
