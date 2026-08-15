# Backend test layout

Authoritative source for tooling/taxonomy: `Calyxio_VOW_QA_Testing_Reporting_Strategy.pdf`.
Where it and `CLAUDE_QA_INSTRUCTIONS.md` disagree on a layer name, the PDF wins
(it's the client-facing QA strategy); `CLAUDE_QA_INSTRUCTIONS.md`'s general
engineering rules — mocking policy, fail-closed behaviour, idempotency,
traceability comments — still apply throughout.

```
tests/
    conftest.py       shared fixtures (currently: `client`, a fresh TestClient)
    fixtures/         static reference data shared across layers
    factories/        factory_boy-style factories for persistent domain objects (none yet — no ORM models exist)
    mocks/            fakes/stubs for external boundaries — the "fake/stub" tier of Amazon/VOW adapter testing
    helpers/          reusable assertion helpers / test utilities

    unit/             pure logic + transport-mocked adapters
        tools/        app.tools adapters (VOW API wrappers) - mocks httpx, the transport boundary
    component/        service / LangGraph-node orchestration - mocks collaborators, not transport
        agent/        app.agent graph/node logic (empty — only greet/echo stubs exist today)
    integration/       real Postgres/Redis/checkpointer; Amazon/VOW adapter at "fake/stub" level
    api/               FastAPI endpoint tests via TestClient/httpx - the AdCP/MCP/A2A surface
    contract/          ADCP/VOW protocol schema + task-lifecycle conformance
    workflow/          complete business workflows, API-driven, Allure step evidence (Golden Path)
    security/          auth, tenant/advertiser isolation, permission checks (pytest half of "Security" - ZAP is separate)
    evals/             AI/LLM evaluation - DeepEval/Ragas/custom, scored against fixed datasets/thresholds
    performance/       Locust/k6 locustfiles - NOT pytest, don't name test_*.py here
    resilience/        failure injection: timeouts, retries, restart recovery
    compliance/        financial-safety, audit, idempotency guarantees (release-gate-critical)
```

## The 10 QA layers, and which folder implements each

| PDF layer (§1)      | Primary tool(s)                          | Folder(s) here                  |
|---------------------|-------------------------------------------|----------------------------------|
| Unit                 | pytest                                    | `unit/`                          |
| Service / Component  | pytest + mocks                            | `component/`                     |
| API / Protocol       | pytest + HTTP/protocol client             | `api/`, `contract/`               |
| Integration          | pytest + test DB/mocks/Testcontainers     | `integration/`                   |
| Workflow             | pytest + Allure                           | `workflow/`                      |
| UI E2E               | Playwright                                | **`frontend/tests/e2e`** — not here |
| AI / LLM Evaluation  | DeepEval/custom; Promptfoo/Ragas          | `evals/`                         |
| Security             | OWASP ZAP + pytest security tests         | `security/` (pytest half only)    |
| Performance          | Locust or k6                              | `performance/`                   |
| Resilience           | pytest + fault injection                  | `resilience/`                    |

**Where does e2e live?** Frontend. The PDF names it "UI E2E" and its tool is
Playwright — a browser-driving tool, so it belongs in `frontend/tests/e2e`
(already scaffolded, see `frontend/tests/README.md`). This backend `tests/e2e/`
folder is retired in favour of `tests/workflow/`, which is the backend's
equivalent full-stack scope (the 21-step Golden Path) but driven through the
API/agent layer directly, with Allure evidence, rather than a browser.
`tests/e2e/__init__.py` is kept only as a pointer (empty package) since this
environment couldn't delete it — remove it once confirmed.

Most of these directories are intentionally empty right now — each carries a
docstring in its `__init__.py` explaining what belongs there and what
production code has to exist first. Don't force tests into a layer just to
fill it: today this repo is FastAPI + LangGraph talking only to VOW's own
platform REST API (`app/tools/`) — no Amazon Ads SDK, no ADCP/MCP/A2A surface,
no persistence beyond the LangGraph checkpointer, no auth, tenant model,
approval workflow, financial controls, or audit trail. `requirements.md` and
`docs/VOW_Strategy_Schema_v2.md` describe where those are headed.

## Coverage targets (PDF §7) and release gates (PDF §11)

| Area                        | Coverage target |
|------------------------------|------------------|
| Overall                       | >= 75%           |
| New code                      | >= 80%           |
| Critical business logic       | >= 90%           |
| Security / Authorization      | >= 90%           |
| Financial guardrails          | >= 95%           |
| Approval logic                | >= 95%           |
| Idempotency logic             | >= 95%           |
| Utility code                  | >= 70%           |

`pytest --cov=app --cov-report=term-missing --cov-report=xml` is already wired
in (see `pyproject.toml`); `coverage.xml` is what SonarQube ingests. Per-module
gates above need to be checked in SonarQube (not yet configured in this repo —
requires a SonarQube server/project + `SONAR_TOKEN`; out of scope for this
restructure).

Release is blocked unless the "Mandatory" gates in PDF §11 all pass: unit,
API, and integration tests (100% of critical tests), Golden Path
(`tests/workflow`), Financial Guardrails and Approval Workflow
(`tests/compliance`), Idempotency (`tests/compliance` + `tests/resilience`),
and Tenant Isolation (`tests/security`) — none of which exist as executable
tests yet because the underlying production code doesn't exist yet either.

## Cross-cutting exit criteria (Exit Criteria Traceability.xlsx)

Four of the exit criteria in the traceability matrix are explicitly
multi-layer, not owned by one folder:

| Exit criterion       | Spans layers                        | Marker (pyproject.toml) |
|-----------------------|--------------------------------------|---------------------------|
| Financial Guardrails   | Unit + API + Workflow + Security      | `financial_guardrails`    |
| Approval Workflow      | Unit + API + Workflow + Security      | `approval_workflow`       |
| Idempotency             | API + Workflow + Resilience           | `idempotency`             |
| Tenant Isolation        | API + Integration + Security          | `tenant_isolation`        |

Tag a test with both its layer marker and the matching exit-criterion
marker (e.g. `@pytest.mark.api` + `@pytest.mark.tenant_isolation`) so
`pytest -m tenant_isolation` collects the complete cross-cutting suite
for that release gate regardless of which directory the test lives in.
`tests/compliance/` holds only the holistic assertions that don't
belong to a single layer (see its `__init__.py`).

**Still pending client decision** (`Exit Criteria Traceability.xlsx`,
"Pending Decisions" sheet) — these gates can't be enforced numerically
until agreed: forecast-accuracy threshold/methodology, performance p95
SLA, and performance error-rate SLA. Everything else in the exit
criteria sheet is marked "Defined".

## Running tests

```bash
pytest                                    # everything except live_sandbox
pytest tests/unit tests/component         # fast layers only
pytest -m "not live_sandbox"              # explicit (also the pyproject.toml default)
pytest --cov=app --cov-report=term-missing --cov-report=xml
locust -f tests/performance/<file>.py     # performance - separate invocation, not `pytest`
```

## Conventions

- Plain `pytest` functions, not test classes (no Django TestCase — this isn't Django).
- `@pytest.mark.asyncio` on async tests (`asyncio_mode = "auto"` makes this mostly automatic).
- Mock the external boundary (VOW API transport, Amazon Ads, LLM), not the domain logic being tested.
- New markers must be registered in `pyproject.toml` (`--strict-markers` is on).
- Every test should be traceable to a requirement/Jira ID via a `# Requirement: ...` comment (`CLAUDE_QA_INSTRUCTIONS.md`) — cross-reference `Exit Criteria Traceability.xlsx` once its requirement IDs are mapped into this repo.
