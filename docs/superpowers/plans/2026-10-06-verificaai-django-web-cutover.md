# VerificaAI Django Web Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the Django REST API and server-rendered interface, rehearse legacy migration, remove the old web/persistence stack, and verify the complete local application.

**Architecture:** DRF and Django templates call the same application services and persistent local runtime. The cutover is last: FastAPI, Streamlit, and SQLAlchemy remain until API contracts, UI, migration reconciliation, and end-to-end behavior are proven.

**Tech Stack:** Django 5.2 LTS, Django REST Framework 3.16+, Django templates, small vanilla JavaScript polling, SQLite, pytest-django.

**Spec:** `docs/superpowers/specs/2026-10-06-verificaai-django-migration-design.md`

## Global Constraints

- Requires completion of both Django foundation and runtime plans.
- Preserve current `/api/v1/analyses` behavior, status codes, `Idempotency-Key`, `Location`, and consent checks.
- Add run-history/reexecution endpoints without changing earlier immutable reports.
- Templates escape all untrusted content; links accept only validated HTTP(S) URLs.
- JavaScript enhances polling but manual reload remains usable.
- Execute legacy import dry-run and reconciliation before any cutover; never delete the source database.
- Final repository must contain no FastAPI, Streamlit, or SQLAlchemy imports/dependencies.
- Document that this is local architecture, not production-public deployment.

## Review Focus

- Concurrent identical POSTs with one idempotency key must return one analysis; Task 1 adds the API concurrency test.
- Polling an older completed run while a new run is active must return the selected immutable report, not latest-run data; Task 1 adds the test.
- Script tags, malicious titles, and `javascript:` evidence URLs must render inert; Task 2 adds the security test.
- With JavaScript disabled, submit/status/history/report must remain reachable through normal forms and links; Task 2 adds the test.
- A migrated artifact path that is missing or outside the allowed root must be reported without reading arbitrary files; Task 3 adds the rehearsal test.

---

### Task 1: Compatible DRF API and run endpoints

**Files:**
- Create: `analyses/api/__init__.py`
- Create: `analyses/api/serializers.py`
- Create: `analyses/api/views.py`
- Create: `analyses/api/urls.py`
- Modify: `verificaai/urls.py`
- Test: `tests/django/test_api_contract.py`
- Test: `tests/django/test_run_api.py`

**Interfaces:**
- Consumes: foundation creation services, runtime `LocalJobRuntime`, Django pipeline store.
- Produces: preserved analysis endpoints plus `GET/POST /api/v1/analyses/{analysis_id}/runs` and `GET /api/v1/analyses/{analysis_id}/runs/{run_id}/report`.

- [ ] **Step 1: Write failing API contract, concurrency, and selected-run tests**

Port current API literals for payloads/status codes/headers. Add concurrent idempotent POST, mismatch `409`, capacity `429`, consent `403`, request ID response, reexecution, run history, old-run report while latest is running, and no stack trace/sensitive text on errors.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/pytest tests/django/test_api_contract.py tests/django/test_run_api.py -v`  
Expected: FAIL because DRF routes are missing.

- [ ] **Step 3: Implement serializers and views over application services**

Do not duplicate domain validation in views. Use transactions for create+run intent, return typed errors, and serialize stored report payloads without recomputation.

- [ ] **Step 4: Verify GREEN**

Run: `.venv/bin/pytest tests/django/test_api_contract.py tests/django/test_run_api.py -v`  
Expected: all API tests PASS.

- [ ] **Step 5: Commit**

```bash
git add analyses/api verificaai/urls.py tests/django/test_api_contract.py tests/django/test_run_api.py
git commit -m "feat: expose django analysis api"
```

### Task 2: Django templates, polling, and accessible fallback

**Files:**
- Create: `analyses/forms.py`
- Create: `analyses/views.py`
- Create: `analyses/urls.py`
- Create: `analyses/templates/analyses/base.html`
- Create: `analyses/templates/analyses/index.html`
- Create: `analyses/templates/analyses/detail.html`
- Create: `analyses/templates/analyses/history.html`
- Create: `analyses/static/analyses/app.js`
- Create: `analyses/static/analyses/app.css`
- Modify: `verificaai/urls.py`
- Test: `tests/django/test_web_views.py`
- Test: `tests/django/test_template_security.py`

**Interfaces:**
- Consumes: Task 1 API contracts and application services.
- Produces: `/`, `/analyses/`, `/analyses/{analysis_id}/`, POST form submission, reexecute action, progressive status/report rendering.

- [ ] **Step 1: Write failing page, no-JS, accessibility, and injection tests**

Assert Portuguese labels, form errors, CSRF, manual redirect flow, history links, textual status in addition to color, polling data attributes, escaped script payloads, blocked unsafe URLs, literal citations, distinct `NEI`/technical error, and independent BERT panel.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/pytest tests/django/test_web_views.py tests/django/test_template_security.py -v`  
Expected: FAIL because templates/views do not exist.

- [ ] **Step 3: Implement server-rendered pages and minimal polling JavaScript**

Use Django forms and URL reversing. JavaScript reads endpoint URLs from data attributes, applies text with DOM-safe APIs, stops on terminal state, and never injects HTML from API values.

- [ ] **Step 4: Verify GREEN**

Run: `.venv/bin/pytest tests/django/test_web_views.py tests/django/test_template_security.py -v`  
Expected: all page and security tests PASS.

- [ ] **Step 5: Commit**

```bash
git add analyses/forms.py analyses/views.py analyses/urls.py analyses/templates analyses/static verificaai/urls.py tests/django/test_web_views.py tests/django/test_template_security.py
git commit -m "feat: add django investigation interface"
```

### Task 3: Migration rehearsal, retention, and operational Admin

**Files:**
- Modify: `analyses/legacy/importer.py`
- Create: `analyses/management/commands/reconcile_legacy_data.py`
- Create: `analyses/services/retention.py`
- Modify: `analyses/admin.py`
- Test: `tests/django/test_migration_rehearsal.py`
- Test: `tests/django/test_django_retention.py`
- Test: `tests/django/test_admin_observability.py`

**Interfaces:**
- Consumes: imported legacy data, Artifact allowlist root, metrics snapshot.
- Produces: `reconcile_legacy_data --source PATH --report PATH`, `RetentionService.cleanup(now) -> RetentionSummary`, read-only operational summaries in Admin.

- [ ] **Step 1: Write failing rehearsal, path-boundary, retention, and Admin tests**

Assert source/destination counts and hashes, missing artifact limitation, traversal/outside-root rejection, archive-before-purge behavior, preserved audit tombstones, operational metrics without sensitive fields, and unchanged source DB hash before/after.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/pytest tests/django/test_migration_rehearsal.py tests/django/test_django_retention.py tests/django/test_admin_observability.py -v`  
Expected: FAIL because reconciliation/retention views are missing.

- [ ] **Step 3: Implement reconciliation and safe retention**

Never follow symlinks or absolute paths. Purge artifact bytes separately from immutable report metadata and preserve hash/tombstone audit events.

- [ ] **Step 4: Verify GREEN**

Run: `.venv/bin/pytest tests/django/test_migration_rehearsal.py tests/django/test_django_retention.py tests/django/test_admin_observability.py -v`  
Expected: all tests PASS and legacy source SHA-256 is unchanged.

- [ ] **Step 5: Commit**

```bash
git add analyses/legacy/importer.py analyses/management/commands/reconcile_legacy_data.py analyses/services/retention.py analyses/admin.py tests/django/test_migration_rehearsal.py tests/django/test_django_retention.py tests/django/test_admin_observability.py
git commit -m "feat: reconcile migrated django data"
```

### Task 4: Remove old web and SQLAlchemy stack

**Files:**
- Delete: `frontend/`
- Delete: `app/api/`
- Delete: `app/database/`
- Delete: `app/main.py`
- Delete: obsolete FastAPI/Streamlit/SQLAlchemy tests after equivalent Django tests exist
- Modify: `pyproject.toml`
- Modify: `.env.example`
- Modify: `scripts/run_evaluation.py`
- Test: `tests/django/test_cutover.py`

**Interfaces:**
- Consumes: complete Django API/UI/runtime and migrated persistence.
- Produces: repository with no FastAPI, Streamlit, or SQLAlchemy runtime dependency/import; Django-only entrypoints.

- [ ] **Step 1: Write the failing cutover guard**

Assert forbidden packages are absent from declared dependencies, `rg`-equivalent AST scan finds no imports, old entrypoints are absent, Django URLs own all user-visible routes, and evaluation reads Django-backed fixtures/services.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/pytest tests/django/test_cutover.py -v`  
Expected: FAIL while old stack remains.

- [ ] **Step 3: Remove only superseded files and dependencies**

Before each deletion, map its tests to passing Django equivalents. Preserve framework-independent `app` domain modules and all security/evaluation fixtures.

- [ ] **Step 4: Verify GREEN and search the repository**

Run: `.venv/bin/pytest tests/django/test_cutover.py -v && ! rg -n 'fastapi|streamlit|sqlalchemy' --glob '*.py' --glob 'pyproject.toml' app analyses verificaai tests pyproject.toml`  
Expected: test PASS and `rg` finds no forbidden runtime reference.

- [ ] **Step 5: Commit**

```bash
git add -A frontend app/api app/database app/main.py tests pyproject.toml .env.example scripts/run_evaluation.py
git commit -m "refactor: complete django web cutover"
```

### Task 5: Documentation and full local acceptance

**Files:**
- Modify: `README.md`
- Modify: `docs/security.md`
- Modify: `docs/limitations.md`
- Modify: `docs/bertimbau-integration.md`
- Create: `docs/operations.md`
- Create: `scripts/smoke_django.py`
- Test: `tests/django/test_documented_commands.py`

**Interfaces:**
- Consumes: final Django commands, migration/reconciliation commands, local runtime, API, UI, and BERT cache.
- Produces: clean-machine install/run/migrate/recover instructions and automated local smoke path.

- [ ] **Step 1: Write failing documented-command and smoke tests**

Execute documented Django checks/migrations against temporary paths, run one fictional factual scenario through the API/runtime, verify old/new run history, factual-before-BERT behavior, correlation IDs, and explicit local-not-production warnings.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/pytest tests/django/test_documented_commands.py -v`  
Expected: FAIL until commands/docs/smoke script agree.

- [ ] **Step 3: Update documentation and implement smoke script**

Document `pip install -e '.[dev,bertimbau]'`, Django migrations, legacy dry-run/import/reconcile, the no-autoreload local entrypoint, graceful/forced shutdown, BERT cache, SQLite/thread limitations, and the future PostgreSQL/Celery production boundary.

- [ ] **Step 4: Run final acceptance suite**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check app analyses verificaai tests scripts && .venv/bin/ruff format --check app analyses verificaai tests scripts && .venv/bin/python scripts/run_evaluation.py && .venv/bin/python scripts/smoke_django.py`  
Expected: all tests PASS, lint/format clean, evaluation reports every case passed, and smoke exits 0.

- [ ] **Step 5: Commit**

```bash
git add README.md docs .env.example scripts/smoke_django.py tests/django/test_documented_commands.py
git commit -m "docs: complete django local operations"
```
