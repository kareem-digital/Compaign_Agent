# Provisional decisions

Things we have deliberately done the temporary way, and what has to change
before they stop being acceptable.

This is not a bug list. Everything here was a conscious choice made to keep
moving while something external was missing - a client answer, a real server,
an infrastructure decision. The risk is not that these choices were wrong; it
is that they get forgotten and quietly ship as if they were permanent.

**How to use it.** Add a row when you take a shortcut. Reference the ID in the
code comment where the shortcut lives (`# TMP-04`) so the two stay connected.
Delete the row when it is genuinely resolved - a register nobody prunes stops
being read.

**Review it at every gate.** Anything still open at G0 or G1 either gets fixed
or gets stated openly to the client. Neither is a problem; discovering it late
is.

---

## Register

| ID | What we are doing now | Why it is temporary | Unblocked by | What must change |
|---|---|---|---|---|
| **TMP-01** | Audit trail written to a **local file** (`FileAuditSink`), or memory when unconfigured | A file inside a container is lost on every deploy; memory is lost on restart | Postgres access (raised with David) | Write a Postgres audit sink. This is what "the audit trail exists" actually means for PLT-21 |
| **TMP-02** | An audit write failure **does not block** the action | Today every action is read-only, so losing the record of a price lookup is not a compliance problem | `create_strategy` / `activate_strategy` existing | Refuse the action if it cannot be recorded - but only for the two consequential ones. Never spend money you cannot account for |
| **TMP-03** | Guardrail values are **placeholders**: £100,000 cap, markets `GB/US/FR/DE` | Real figures never supplied | **A3** (David) | Replace in `policies/vow_ctv.yaml`. PLT-22's DoD says placeholders are not acceptable at the gate |
| **TMP-04** | **Mock MCP server** returns canned VOW data | The real MCP server does not exist yet | Client delivering MCP | Swap in a real transport behind `MCPClient`. Shapes are realistic; values are invented |
| **TMP-05** | VOW tool names in `VowTools` are **guesses** mapped from REST endpoints | No real server to check against | Client delivering MCP | Run `list_tools()` against the real server and reconcile. This is the main integration risk of the MCP move |
| **TMP-06** | Provider-to-tier mapping is **hardcoded** in `select_inventory.py` | The mock does not return a tier | Real MCP | If the server returns the tier, delete `_TIER_BY_PROVIDER` and trust it |
| **TMP-07** | No authentication to VOW - `mcp_auth_token` is empty | Client has not confirmed the method | **A1** (David) | Implement the real auth. Blocks PLT-05 and any use of staging |
| **TMP-08** | `dev_advertiser_id` fallback when the header is absent | Lets the chat endpoint work before the UI sends the header | UI sending `Vowmade-Advertiser-Id` | Nothing - it is already restricted to `ENVIRONMENT=local` and fails closed elsewhere. Remove once the UI is wired |
| **TMP-09** | Legacy `vow_api_*` settings retained | `app/tools/base.py` still reads them | Retiring the REST wrappers | Delete both together, deliberately. Removing the settings alone breaks `base.py` at runtime, not at import |
| **TMP-10** | `MIN_VIABLE_REACH = 100_000` in `predict_reach.py` | Invented threshold | **A3** (David) | Replace with the real viability floor |
| **TMP-11** | Mock returns **no Prime Video for France** | Otherwise the third-party "cannot forecast reach" path is unreachable in a demo | Real MCP | Delete the lever. It is a demo scaffold, **not** a statement about real market availability |
| **TMP-12** | No LLM when `OPENAI_API_KEY` is unset - falls back to pattern matching | Keeps tests and CI free of secrets | — | Nothing. This is a deliberate permanent design, listed so nobody "fixes" it |
| **TMP-13** | Kill switch is **hand-rolled**, not AGT's `agent_sre` | `agent_sre` lives in a fifth distribution we left out, and a kill switch is a boolean | — | Decide whether AGT's version adds anything (circuit breakers, SLO monitoring). If not, correct ADR-001 AD-7, which credits AGT with providing it |
| **TMP-19** | The kill switch is a **file on disk** - presence halts all VOW calls | Per-container, and needs shell access to the box. See TMP-21: with more than one replica it stops only the pod you touched | Postgres (a shared flag) or auth (an admin endpoint, A1) | **This is the "lever" decision to revisit.** Options: a database flag visible to every instance, or an authenticated endpoint someone can hit from a phone |
| **TMP-20** | **Conversation state is in memory.** `USE_MEMORY_CHECKPOINTER=true`, hard-coded in `helm/templates/backend.yaml` | LangGraph's `MemorySaver` holds every session's transcript and plan-in-progress in the process. A restart or a rolling deploy loses all of it - a trader mid-plan gets a 404 on their session | Postgres access (raised with David) | Switch to `AsyncPostgresSaver`. The code path already exists in `app/agent/checkpointer.py`, but **the dependencies are not installed** - `langgraph-checkpoint-postgres` and `psycopg` are missing from `requirements.txt`, so setting the flag to `false` today raises at startup. This matters more once plan approval lands: an `interrupt()` can pause a conversation for hours, and in memory that pause does not survive a deploy |
| **TMP-14** | Every turn re-runs all four nodes; a follow-up that omits a field re-asks for it | Conversational refinement of a single field is not built | Kareem's M1 work | Real traders refine one field at a time |
| **TMP-15** | `create_strategy` and `activate_strategy` **do not exist** | Not yet built | M1 | Until they do, the policies that matter guard nothing, and *"an over-budget plan is blocked"* cannot be demonstrated end to end |
| **TMP-16** | mypy runs with `continue-on-error` and reports 11 errors | Inherited from staging's CI config | — | Either fix the errors and remove the flag, or accept that the tick means nothing. A check that always passes is not a check |
| **TMP-17** | Backend tests not committed with their features | Excluded from the PLT-27 and VA-174 PRs | — | Land them. Two PRs running with "tests" unticked is a pattern reviewers will notice |
| **TMP-18** | Test suite calls the **real OpenAI API** when a key is present | `conftest.py` does not isolate the LLM | — | Autouse fixture forcing the pattern path, plus separate opt-in LLM tests. Currently non-deterministic, slow, and costs money per run |

---

## TMP-21 · The service cannot be scaled past one replica

Listed separately because it is a different kind of risk from the rest. The
others degrade honestly. This one makes a **safety mechanism fail quietly.**

`helm/values.yaml` sets `backend.replicas: 1`. That value is load-bearing and
nothing in the file says so. Raise it and three things break with no error:

| Raising replicas | Consequence |
|---|---|
| **Conversations** | Each pod has its own memory, so whether a session is found depends on which pod the load balancer picks. Intermittent 404s that look like a bug in the UI |
| **Audit trail** | Each pod holds a partial record. Neither is complete, and nothing indicates that |
| **Kill switch** | It is a file on one container's filesystem. Touch it in one pod and the others keep calling VOW - **an emergency stop that half works**, which is worse than one that visibly does not |

All three share one cause: **this service keeps its state in memory.** It cannot
be scaled until that state moves to Postgres - see TMP-01, TMP-19 and TMP-20,
which are the same underlying fact seen from three angles.

**Until then:** `replicas: 1`, and a comment in `helm/values.yaml` explaining
why, so nobody scales it up for load and silently defeats the kill switch.

**Owner:** Tarun, since it is his file and his deployment.

---

## Needs someone else to act

Not ours to fix, but they block or mislead us.

| ID | Issue | Owner |
|---|---|---|
| **EXT-01** | **DEV-12 describes AGT as a containerised sidecar.** It is a pip library - there is nothing for the app container to "reach" | Tarun |
| **EXT-07** | **`helm/values.yaml` needs a comment on `replicas: 1`.** Scaling up silently breaks sessions, splits the audit trail and defeats the kill switch. See TMP-21 | Tarun |
| **EXT-02** | `frontend/Dockerfile` runs `USER appuser`, a user that does not exist in `nginx:alpine`. The container will not start | Basil |
| **EXT-03** | The Dockerfile declares `VITE_IS_MOCK` but the app reads `VITE_USE_MOCK_AGENT`, so a built frontend **always uses the mock** | Basil |
| **EXT-04** | Dockerfile runs `npm run build`, which only produces `dist/agent`. `/mfe/` is never built, so nginx 403s | Basil |
| **EXT-05** | `nginx.conf` predates Module Federation - it expects one SPA at the root, but the build now emits `/agent/` and `/mfe/` | Basil |
| **EXT-06** | ADR-001 AD-7 says AGT has "native LangGraph integration". It is an adapter, and policies are YAML, not Rego | Delivery Lead |

---

## Open questions these depend on

| | Question | Blocks |
|---|---|---|
| **A1** | How does the agent authenticate to VOW? | TMP-07, PLT-05 |
| **A3** | Real guardrail and credit values | TMP-03, TMP-10, PLT-22 DoD |
| **A4** | SME/trader time for a manual baseline | G1's ">=70% faster" criterion |
| **new** | How long must audit records be kept? | TMP-01 - drives the storage choice |
| **new** | Who may read the audit trail? | TMP-01 - usually tighter access than app logs |

---

*Last reviewed: 11 August 2026*
