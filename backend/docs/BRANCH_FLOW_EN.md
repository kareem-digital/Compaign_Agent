# VOW Planning Agent — Backend Flow

**Branch:** `Future-PLN-KNW` (= `origin/feature_agent_planning` + 2 fixes)
**Date:** 2026-08-14 · **Tests:** 103 pass · **Model:** gpt-4o-mini

The *current* state of this branch's backend — what runs, how it runs, and where it is broken.
Written so the next change can be made with the whole picture in view.

---

## Contents

| | |
|---|---|
| 01 | [At a glance](#01--at-a-glance) |
| 02 | [One turn, end to end](#02--one-turn-end-to-end) |
| 03 | [graph.py — the wiring](#03--graphpy--the-wiring) |
| 04 | [state.py — every field](#04--statepy--every-field) |
| 05 | [gates.py — routing](#05--gatespy--routing) |
| 06 | [Six nodes, one by one](#06--six-nodes-one-by-one) |
| 07 | [The API response](#07--the-api-response) |
| 08 | [Governance (AGT)](#08--governance-agt) |
| 09 | [What the model costs](#09--what-the-model-costs) |
| 10 | [Reading the logs](#10--reading-the-logs) |
| 11 | [Open issues](#11--open-issues) |
| 12 | [What was fixed](#12--what-was-fixed) |

---

## 01 · At a glance

```
backend/app/
├── main.py                 FastAPI app, CORS, error handlers
├── config.py               Settings, read from env
├── api/
│   ├── routes.py           health + sessions routers
│   ├── health.py           /health/live, /health/ready
│   ├── sessions.py         POST /sessions/chat  ← the only real endpoint
│   ├── presentation.py     build_blocks() — structured reply for the UI
│   ├── errors.py           exception → HTTP status
│   └── validation_details.py
├── agent/
│   ├── graph.py            the LangGraph state machine (6 nodes)
│   ├── state.py            PlanningAgentState — 22 fields
│   ├── gates.py            routers + missing_basics
│   ├── llm.py              get_llm(), log_usage()
│   ├── checkpointer.py     in-memory or Postgres
│   └── nodes/              six node modules
├── governance/
│   ├── agt.py              policy engine + kill switch + audit
│   └── policies/vow_ctv.yaml   3 rules
├── knowledge/
│   ├── reference.py        provider → tier mapping
│   ├── reference_data.yaml
│   └── registry/           (empty — only __init__.py)
└── tools/
    ├── auth.py             VOWAuthProvider (StubAuth for now)
    ├── base.py
    └── mcp/
        ├── client.py       MCPClient + the governance wrapper
        ├── mock.py         MockMCPClient — canned VOW data
        └── mock_data.py
```

**The central design choice:** **one stage per turn.** The agent shows the trader something,
stops, and waits. It does not assemble the whole plan before it speaks.

**Two rules that hold across the graph:**
1. **The model never decides which tool is called** — the graph does.
2. **The model never calls a tool** — nodes do, and every call passes governance first.

---

## 02 · One turn, end to end

```
BROWSER
  │  POST http://localhost:8000/api/v1/sessions/chat
  │  { "message": "...", "session_id": "..." }
  │  headers: Content-Type, X-Request-ID, Vowmade-Advertiser-Id (optional)
  ▼
main.py  ── CORS middleware (allowed: localhost:3000, localhost:3001)
  ▼
api/sessions.py  chat()
  │  resolve advertiser_id (header, else DEV_ADVERTISER_ID)
  │  graph = build_graph(checkpointer, mcp)   ← per advertiser, cached
  │  load state from the checkpointer, keyed on session_id
  ▼
LangGraph: START → extract_fields
  │
  ├── extract_fields (runs every turn, without exception)
  │     ├─ _latest_human_text(state)
  │     ├─ LLM call #1  purpose="extract"   ~500 tokens in, ~1400ms
  │     │     (or the patterns, when no key is configured)
  │     ├─ _merge(state, found)             ← new over known
  │     ├─ _flight_already_over()           ← drop a finished flight  [NEW FIX]
  │     ├─ result["awaiting"] = missing_basics(result)
  │     └─ stage_cursor = None if market / duration / budget changed
  │
  ▼
route_one_stage(state)          ← the turn's only fork
  │
  ├─ awaiting non-empty?  ───────────────────────────► ask
  │                                                      └─ LLM call #2 purpose="ask" ~1100ms
  │
  └─ empty? → read stage_cursor:
       None / "basics" ─────► select_inventory   → 2 MCP calls
       "inventory"    ─────► suggest_audiences   → 1 MCP call
       "audiences"    ─────► predict_reach       → 1 MCP call
       "forecast"     ─────► plan_ready          → 0 calls
  │
  ▼
every stage node → END  (the turn ends; the graph waits for the next message)
  │
  ▼
api/sessions.py
  │  reply  = the last assistant message
  │  blocks = build_blocks(result)      ← api/presentation.py
  │  stage  = result["stage_cursor"] or current_stage
  ▼
{ session_id, reply, stage, blocks }  →  BROWSER
```

**A turn ends** either because `awaiting` filled up (routing to `ask`) or because a stage node
ran and reached `END`. Either way `stage_cursor` records how far the conversation has come.

---

## 03 · graph.py — the wiring

`app/agent/graph.py` is **107 lines**, and that is the whole state machine.

**Six registered nodes:**

| node | factory? | needs MCP? |
|---|---|---|
`extract_fields` | no, a plain function | no |
`select_inventory` | `make_select_inventory(mcp)` | yes |
`suggest_audiences` | `make_suggest_audiences(mcp)` | yes |
`predict_reach` | `make_predict_reach(mcp)` | yes |
`plan_ready` | no | no |
`ask` | no (`ask_for_missing`) | no |

**Edges:**

```python
graph.add_edge(START, "extract_fields")          # extraction always runs first

graph.add_conditional_edges(
    "extract_fields",
    route_one_stage,                              # a single fork
    {"ask": "ask", "select_inventory": ..., "suggest_audiences": ...,
     "predict_reach": ..., "plan_ready": ...},
)

for node in ("ask", "select_inventory", "suggest_audiences",
             "predict_reach", "plan_ready"):
    graph.add_edge(node, END)                     # every stage ends the turn
```

`build_graph()` **raises ValueError** when `mcp is None`, deliberately: a silently-mocked client
in staging would be worse than a startup failure.

**What is not there yet** (the graph's own docstring says so):
- **Plan approval** — an `interrupt()` after `predict_reach`
- **Repair loop** — an edge from `predict_reach` back to `suggest_audiences`. The node already
  detects a too-narrow reach; only the edge is missing.
- **Tier fork** — edges out of `select_inventory` for the curation-capture path

---

## 04 · state.py — every field

`PlanningAgentState` is a `TypedDict(total=False)`: nodes fill it progressively and each returns
only the keys it owns, for LangGraph to merge.

### Conversation
| field | notes |
|---|---|
`messages` | `Annotated[list, add_messages]` — LangGraph appends |

### Session
| field | notes |
|---|---|
`advertiser_id` | multi-tenancy |
`session_id` | conversation id |
`current_stage` | **reset every turn** — which node just ran |

### Basics (step 1)
| field | written by |
|---|---|
`strategy_name` | `extract_fields` — `"CTV GB 2026-10"`, provisional |
`flight_dates` | `{lower, upper, bounds:"[)"}` |
`markets` | ISO codes, a list |
`durations` | `["30"]` — seconds, as strings |
`primary_currency` | derived from the market, or from a symbol |
`goal` | always `"AWARENESS"` — fixed for CTV |
`kpi` | `"reach"` |
`market_budgets` | `[{market, budget, base_bid}]` |

### Inventory (step 2)
| field | written by |
|---|---|
`preferred_providers` | `extract_fields` — channels the trader named |
`inventory_tier` | `select_inventory` — the dominant tier |
`selected_deals` | `select_inventory` — matched deals |
`inventory_alternatives` | providers available but not chosen |

### Audience (step 4)
| field | written by |
|---|---|
`audience_options` | `suggest_audiences` — **always three**: narrow / balanced / wide |
`chosen_audience` | the trader's pick |

### Forecast (step 6)
| field | written by |
|---|---|
`forecast` | `predict_reach` — carries `is_available` for the honesty rule |

### Flow control — **the two that matter most**
| field | notes |
|---|---|
`stage_cursor` | **only moves forward.** Distinct from `current_stage`, which resets every turn. This is what makes one-stage-per-turn possible |
`awaiting` | what is missing, as human-readable labels. Non-empty means the graph stops and asks |
`validation_errors` | declared, but no node on this branch writes it |

**Who writes `stage_cursor`:**
```
select_inventory   → "inventory"
suggest_audiences  → "audiences"
predict_reach      → "forecast"
extract_fields     → None   (when market / duration / provider / budget changed)
```

---

## 05 · gates.py — routing

### `missing_basics(state)`
```python
BASICS = (
    ("markets",        "which country the campaign runs in"),
    ("flight_dates",   FLIGHT),                                    # "the start and end dates"
    ("durations",      "the creative durations - 10, 15, 20 or 30 seconds"),
    ("market_budgets", "the budget"),
)

def missing_basics(state):
    return [label for key, label in BASICS if not state.get(key)]
```

That is all of it: the label of every empty field. **Four basics.**

### `route_one_stage(state)` — the whole router
```python
_NEXT_STAGE = {
    None:         "select_inventory",
    "basics":     "select_inventory",
    "inventory":  "suggest_audiences",
    "audiences":  "predict_reach",
    "forecast":   "plan_ready",
}

def route_one_stage(state):
    if state.get("awaiting"):
        return "ask"                                    # something missing: stop
    return _NEXT_STAGE.get(state.get("stage_cursor"), "plan_ready")
```

**Two lines.** `awaiting` is checked first, because there is no point looking up inventory for a
market we do not have.

`gates.py` also defines `route_after_basics`, which the graph no longer uses —
`route_one_stage` replaced it.

---

## 06 · Six nodes, one by one

### 1. `extract_fields` — the entry node (~440 lines)

**Job:** read the message, merge into what is known, compute the gate.

```
_latest_human_text(state)
  │
  ├─ LLM configured? ──── yes ──► _extract_with_llm()
  │                                 ├─ _system_prompt()      ← carries TODAY IS  [FIX]
  │                                 ├─ _known_summary(state) ← labels, not values
  │                                 └─ structured output → BriefFields
  │                                    (falls back to patterns on failure)
  │
  └────────────────────── no ───► _extract_with_patterns()
                                     ├─ _markets()      regex
                                     ├─ _budget()       £/$/€ plus k/m
                                     ├─ _durations()    10/15/20/30
                                     └─ _flight_dates() month + optional year  [FIX]
  ▼
_merge(state, found)
  │  empty means "not mentioned this turn", never "clear it"
  │  providers: only those present in reference.providers()
  ▼
_flight_already_over(fields)          ← NEW CHECK  [FIX]
  │  flight already finished? → drop it, build the reason
  ▼
result = {**fields, current_stage, strategy_name, goal, kpi, messages}
result["awaiting"] = missing_basics(result)
  │  if the flight was dropped, swap the generic label for the reason  [FIX]
  ▼
stage_cursor = None when markets / durations / providers / budgets changed
```

**`BriefFields`** — the shape the model must return:
```python
markets: list[str]        flight_start: str | None    flight_end: str | None
durations: list[str]      budget_amount: str | None   currency: str | None
providers: list[str]
```

---

### 2. `ask_for_missing` (registered as `ask`)

**Job:** turn `awaiting` into one question, and end the turn.

```
missing = state["awaiting"]
  │
  ├─ stated     = computed labels, which carry a reason  [FIX]
  └─ rewordable = the gate's own fixed vocabulary
        │
        └─ LLM call #2  purpose="ask"  ← only this is sent  [FIX]

reply = [stated verbatim] + [the model's phrasing, or the template]
```

**`_FIXED_LABELS`** = the four `BASICS` labels plus `NO_INVENTORY` and `NO_AUDIENCE`. Anything
not in that set is said **verbatim** and never shown to the model.

---

### 3. `select_inventory` (~238 lines) — step 2

**Job:** fetch deals and classify them into the three tiers.

```
basics incomplete? → return awaiting and stop
  ▼
MCP: vow.list_deals { advertiser_id, market, durations, format }
  │  (governance checked first)
  ▼
MCP: vow.get_ctv_rate_card { advertiser_id, market }
  ▼
per deal: classify_tier(provider)     ← from reference.py
  │
  ├─ AMAZON_OWNED                Prime Video       → reach forecast AVAILABLE
  ├─ THIRD_PARTY_PRECURATED      Netflix           → NO forecast
  └─ THIRD_PARTY_NEEDS_CURATION  Disney+           → rate card only, no deal
  ▼
dominant_tier(deals)  ← the primary fork in the whole flow
  ▼
providers named? → keep only those
  ▼
{ selected_deals, inventory_tier, inventory_alternatives,
  stage_cursor: "inventory", awaiting: [] or [NO_INVENTORY] }
```

**The tier decides everything downstream** — whether reach can be forecast, whether Amazon
audiences apply, whether the deal is selectable at all.

---

### 4. `suggest_audiences` (~173 lines) — step 4

**Job:** offer three options, priced on **effective CPM**.

```
MCP: vow.suggest_audiences
  ▼
_cheapest_amazon_cpm(deals)   ← the base
  ▼
per option: effective_cpm = deal_cpm + vcpm_fee
  │
  ├─ NARROW    ~1.2M    18.22 + 3.50 = 21.72   dearest, smallest
  ├─ BALANCED  ~4.8M    18.22 + 2.00 = 20.22   the usual recommendation
  └─ WIDE      ~15.4M   18.22 + 0.85 = 19.07   cheapest, least precise
  ▼
{ audience_options, stage_cursor: "audiences", awaiting: [] or [NO_AUDIENCE] }
```

**The effective CPM is the real number.** Showing the deal price alone understates what
precision costs. And Amazon audiences apply **only to Amazon-owned inventory** — third-party
brings its own targeting at its own CPM, which is stated rather than quietly ignored.

---

### 5. `predict_reach` (~156 lines) — step 6

**Job:** forecast — and refuse plainly where a forecast is not possible.

```
MCP: vow.predict_reach
  ▼
tier is AMAZON_OWNED?
  │
  ├─ yes → reach + impressions + frequency
  └─ no  → impressions ONLY (budget ÷ CPM × 1000)
           plus a plain statement that reach cannot be forecast, and why
  ▼
{ forecast: {..., is_available}, stage_cursor: "forecast" }
```

**Two rules** (schema v2 §3 step 6):
1. **Never invent a reach number.** A plausible fabrication is worse than an admitted gap,
   because a trader will commit budget against it.
2. **Never sum reach across providers.** There is no cross-platform deduplication, so the
   figures are not additive.

---

### 6. `plan_ready`

**Job:** say the plan is assembled, and be honest that the flow stops here.

```
"The plan is complete - inventory, audience and forecast are all settled.
 Approval and creating it in VOW are the next steps, and are not built yet.
 Tell me if you'd like to change anything."
```

47 lines, no MCP call. Saying "the plan is complete" without the caveat would imply a campaign
exists. It does not.

---

## 07 · The API response

`POST /api/v1/sessions/chat` returns **four keys**:

```json
{
  "session_id": "747d5ce4-...",             // send back on the next message
  "reply": "Here is what I understood...",  // plain text for the chat bubble
  "stage": "inventory",                     // stage_cursor — drives the UI stepper
  "blocks": [ ... ]                         // the actual UI instructions
}
```

Response header: `X-Request-ID`, which ties the response to a log line.

### `blocks` — the Block contract

From `api/presentation.py`:

| field | meaning |
|---|---|
`text` | what a human reads |
`interaction` | **authoritative** — the frontend must honour it |
`layout` | **suggested** — the frontend may override |
`primary` | the main artifact of this step, rather than conversation |
`field` | which plan field the user's answer sets |
`data` | structured content |

**`Interaction` (7 values):**
```
none               read only
confirm            already decided — accept or amend
select_one         pick exactly one
select_many        pick any number
input_date_range   a start and an end
input_money        an amount in a currency
input_text         free text
```

**`Layout` (7 values):**
```
summary_list  table  cards  chips  metrics  date_range_picker  currency_input
```

### A real example (the inventory turn)

```json
{
  "text": "Got it - GB, 2026-10, 30s, 15000.00 GBP. Here's the CTV inventory available in GB.",
  "interaction": "select_many",
  "layout": "table",
  "primary": false,
  "field": "selected_deals",
  "data": {
    "columns": ["Provider", "Genre", "CPM", "Lengths", "Tier"],
    "rows": [
      { "value": "EXTQ5", "provider": "Prime Video", "cpm": "18.22",
        "tier": "Amazon-owned", "note": "Reach forecast available", "selected": true },
      { "value": "EXTNFLX0012", "provider": "Netflix", "cpm": "31.50",
        "tier": "Third-party, pre-curated", "note": "No reach forecast", "selected": true }
    ],
    "alternatives": ["Disney+", "Netflix", "Prime Video"],
    "confirming": []
  }
}
```

**This is the core idea:** the backend sends no HTML and the frontend holds no business logic.
The backend says *"this is a table, offer multi-select, put the answer in `selected_deals`"* and
the frontend renders it. A new control means one new enum value on each side.

`reply` and `blocks[0].text` are **two versions of the same thing** — one long, one short. The
frontend chooses which to show.

---

## 08 · Governance (AGT)

`app/governance/agt.py` — VA-174. Checked **before every MCP call**.

```
tools/mcp/client.py  call_tool()
  │
  ├─ governance.check   { tool, fields, advertiser }
  │     ▼
  │  agt.py → PolicyEngine (the agentmesh library)
  │     │  policy: app/governance/policies/vow_ctv.yaml — 3 rules
  │     │
  │     ├─ ALLOWED  → log "governance.allowed  rule=allow-planning-tools"
  │     └─ DENIED   → PolicyDeniedError → HTTP 403
  │
  ├─ kill switch: does the KILL_SWITCH file exist? → KillSwitchEngagedError → HTTP 503
  │
  └─ audit log: a record of every allow / deny
  ▼
the real MCP call
```

**Dependency:** `agent-governance-toolkit==4.1.0` and `-core==4.1.0`, pinned exactly per
ADR-001. Imported as `agentmesh.governance`.

**403 versus 503** (in `api/sessions.py`):
- `PolicyDeniedError` → **403**, logged at WARNING. A refusal is the system working, not
  failing. The client is told only that the action is not permitted; tool names, rule names and
  the engine's reasoning stay internal.
- `KillSwitchEngagedError` → **503**, logged at CRITICAL. It is temporary and deliberate, so the
  caller should understand it may work later — the opposite of a policy refusal.

**The kill switch is the file's existence:**
```
touch KILL_SWITCH   → agent halted
rm KILL_SWITCH      → agent resumes
```
Effective on the next call. No restart, no deploy. And there is **deliberately no on/off env
var** — a guardrail an env var can disable is not a guardrail.

---

## 09 · What the model costs

Read off the logs, not estimated. **39 calls across 27 turns.**

| purpose | calls | tokens in | tokens out | avg ms | cost |
|---|---|---|---|---|---|
`extract` | 26 | 13,003 | 1,106 | **1408** | $0.00261 |
`ask` | 12 | 1,339 | 374 | **1081** | $0.00043 |
| **TOTAL** | **39** | **16,476** | **1,585** | | **$0.00342** |

### Calls per turn
```
1 call:   15 turns
2 calls:  12 turns    ← extract + ask
```

### How much of each turn is spent waiting on the model

```
turn_ms   model_ms   model %   purposes
   4691       2773      59%    extract, ask
   4781       2649      55%    extract, ask
   4666       2716      58%    extract, ask
   4300       2447      57%    extract, ask
   2153       2143     100%    extract, ask
   1543       1518      98%    extract
   1223       1203      98%    extract
```

**Model latency is 55–100% of every turn.** Everything else — MCP calls, governance, tier
classification, block building — completes in **0 to 4 ms** (the mock MCP reports
`duration_ms=0`).

### Three places the spend is wasted

**1. Even a greeting costs two calls.** Type `"Hi"`:
```
extract call:  ~500 tokens in → returns nothing    ~1400ms
ask call:      ~110 tokens in → phrases a question ~1100ms
                                            TOTAL:  ~2500ms
```
Two and a half seconds to say "give me a market, a budget and some dates". Both calls are
avoidable: rules can recognise a greeting, and the question is **computed**, not generated.

**2. Eight of the 26 extract calls returned nothing** (≤34 output tokens). `"Hi"`, `"30s"`,
`"yes"` — each sends a ~500-token prompt and gets an empty answer back.

**3. The model writes the question's words.** `gate.blocked ... phrasing="llm"`. The *content*
is computed by `missing_basics`; a whole call goes on the phrasing. A deterministic template
already exists.

**The money is trivial** ($0.0034 for 39 calls) — **the latency is not.** And this is against a
mock MCP; with the real VOW server, MCP time will add on top of the model wait.

---

## 10 · Reading the logs

**File:** `backend/logs/vow-agent.log` — one JSON object per line. Console format is set by
`LOG_FORMAT` in `.env` (`text` or `json`).

### The events of one turn, in order

| event | logger | what it tells you |
|---|---|---|
`turn.start` | `api.sessions` | `message_chars` |
`turn.message` | `api.sessions` | **DEBUG** — the trader's actual text |
`llm.prompt` | `agent.nodes.extract_fields` | **DEBUG** — the full prompt |
`llm.call` | `agent.llm` | `purpose`, `model`, `tokens_in/out`, `duration_ms` |
`llm.parsed` | `agent.nodes.extract_fields` | **DEBUG** — what the model extracted |
`stage.basics` | `agent.nodes.extract_fields` | `method`, `fields_found=3/4`, `awaiting` |
`stage.basics.values` | | **DEBUG** — the merged values |
`flight.already_over` | | **WARNING** — a finished flight was dropped  [NEW] |
`governance.check` | `tools.mcp.client` | DEBUG — which tool, which fields |
`governance.allowed` | `governance.agt` | DEBUG — which rule allowed it |
`mcp.call` | `tools.mcp.client` | `tool`, `duration_ms`, `result_count` |
`mcp.response` | | **DEBUG** — the full body |
`stage.inventory` | `agent.nodes.select_inventory` | `deals`, `dominant_tier`, `tiers` |
`gate.blocked` | `agent.nodes.ask_for_missing` | `awaiting`, `phrasing` |
`turn.end` | `api.sessions` | `stage`, `duration_ms`, `nodes_run`, `blocked` |

### One real turn from the log
```
06:44:53  turn.start        message_chars=121
06:44:53  turn.message      text=We're launching a new running shoe line in the UK...
06:44:53  llm.prompt        purpose=extract
06:44:55  llm.call          purpose=extract tokens_in=543 tokens_out=47 duration_ms=1518
06:44:55  llm.parsed        flight_start=2026-10-01 flight_end=2026-10-31
06:44:55  stage.basics      method=llm fields_found=4/4 awaiting=
06:44:55  governance.check  tool=vow.list_deals
06:44:55  governance.allowed rule=allow-planning-tools
06:44:55  mcp.call          tool=vow.list_deals duration_ms=0 result_count=4
06:44:55  mcp.call          tool=vow.get_ctv_rate_card duration_ms=0 result_count=3
06:44:55  stage.inventory   deals=4 dominant_tier=AMAZON_OWNED
06:44:55  turn.end          stage=inventory duration_ms=1543 nodes_run=2 blocked=False
```

### Useful commands

```powershell
# the full trace of one session
Get-Content logs\vow-agent.log | ForEach-Object { $_ | ConvertFrom-Json } |
  Where-Object { $_.session_id -like '64abdae1*' }

# turn boundaries and cost only
Select-String logs\vow-agent.log -Pattern 'turn.end|llm.call'

# did a request arrive from the UI? (advertiser dev-advertiser-0001 = the browser)
Select-String logs\vow-agent.log -Pattern 'dev-advertiser-0001'
```

**One diagnostic worth keeping:** when CORS blocks a request, the request **still appears in the
log** — the server answered and the browser discarded the response afterwards. **Nothing in the
log at all** means the request never arrived: wrong port, wrong host, connection refused. Check
that first.

---

## 11 · Open issues

### 🔴 A. Two model calls per turn — ~2.5s of avoidable wait
`extract` then `ask`, on one message, including on a greeting. All twelve blocked turns made
both calls. Model latency is 55–100% of the turn.

**Where:** `extract_fields._extract_with_llm()` and `ask_for_missing`

### 🔴 B. There is no validation node
Six nodes, and **not one validates a value**. A past date, a duration the platform does not
sell, a budget beyond available credit — nothing is checked. The flight check now lives inside
`extract_fields`, which is a **stopgap**; the right home is a node of its own.

**Evidence:** `state.validation_errors` is declared and no node writes it.

### 🟠 C. `blocks` marks all four deals `selected: true`
Netflix (`No reach forecast`) and Disney+ (`Rate card only`) arrive pre-ticked, and
`confirming` is empty. The UI shows four ticked rows, two of which cannot be bought.

**Where:** `api/presentation.py`

### 🟠 D. Governance audit is in memory only
```
WARN governance.audit_in_memory
  note=decisions are NOT persisted and are lost on restart
  fix=set AUDIT_LOG_PATH and AUDIT_HMAC_KEY
```
Logged on every turn. Allow/deny decisions vanish on restart. For compliance this is meant to
be **evidence**, not logging — logs expire.

### 🟠 E. The model writes the question's words
`gate.blocked phrasing="llm"`. The content is computed and the phrasing generated — one call's
cost, and the model **also invented requirements** (audience, budget, channels) from a
one-item list. The reason-carrying half is fixed; the invention risk on plain lists remains.

### 🟡 F. `LOG_LEVEL=DEBUG` logs the entire OpenAI HTTP exchange
Response headers, `set-cookie`, the TLS handshake. It makes the real flow hard to find in a
181 kb file. `LOG_LEVEL=INFO` clears it.

### 🟡 G. `stage_cursor` invalidation is blunt
Any change to market / duration / provider / budget resets the cursor to `None`, re-walking the
whole flow. Changing only the budget re-fetches inventory and audiences. Their own comment
marks it `TMP-23`.

### 🟡 H. The flow stops at `plan_ready`
Approval and strategy creation are not built. The node is honest about it, but only 4–5 of the
flow chart's 13 stages exist.

### 🟡 I. The frontend panel shows placeholder data
`Mega Toothpaste`, `UK · USA · France`, `02.12.2025 – 20.11.2026` are the frontend's own
fixtures, not backend values. They should be replaced by real ones once a plan exists.

---

## 12 · What was fixed

### 1. Flight dates in the past 🔴 → ✅

**The bug:** *"October 1st to October 31st"* — no year — became `2023-10-01`. Today is 2026.
Inventory was then matched and priced for a flight that had finished three years earlier, and
**nothing objected.**

**Three causes:**
1. The prompt never said what day it was, so the model resolved the month against its training
   data
2. There is no validation node
3. `extract_fields` had **no tests at all**

**The fix, in three places:**

| where | what |
|---|---|
`_system_prompt()` | `_SYSTEM` became a **function**, carrying `TODAY IS 2026-08-14` and the rule *"a date with no year means the next time it occurs, never a past one"*. A function because building it at import would freeze the date on the morning the server started |
`_flight_dates()` | the pattern path read `date.today().year` flat, so "March" typed in August produced a date five months past. It now rolls to next year once the month has gone |
`_flight_already_over()` | **new check** — a finished flight never reaches the plan. It tests `upper`, not `lower`: a campaign that started last week and runs into next month is legitimately in flight |
`gates.FLIGHT` | the label got a name, so `extract_fields` can recognise and replace it |

**Verified through the real UI:**
```
"£15k from October 1 to 31"  →  flight_start=2026-10-01  flight_end=2026-10-31   ✅
"October 2023"               →  Flight: not stated
                                "I need a flight that has not already finished -
                                 2023-10-01 to 2023-10-31 is in the past, and
                                 today is 2026-08-14."                            ✅
```
A `WARNING flight.already_over` is logged with the dropped dates — it is not silent.

**18 tests** — `tests/unit/agent/test_flight_dates.py`

---

### 2. The model threw the reason away 🔴 → ✅

**The bug:** the reason reached `awaiting` correctly, and then `ask_for_missing` **handed it to
the model.** From a one-item list, gpt-4o-mini:
- dropped the reason entirely
- invented **three** requirements: audience, budget, channels
- asked for the budget, which was already on the card

The node's own docstring claims *"the LLM rewords a known list, it does not decide what is
missing"*. It decided.

**The fix:** `_FIXED_LABELS` — the gate's own vocabulary (four `BASICS` labels plus
`NO_INVENTORY` and `NO_AUDIENCE`) goes to the model. Any label **computed** from the trader's
own values is said **verbatim**. The correction comes first, the question second.

**12 tests** — `tests/unit/agent/test_ask_for_missing.py`

---

### 3. CORS blocked port 3001 🟠 → ✅

**The bug:** the `config.py` default allowed only `localhost:3000`. `npm run dev:remote` (the
Module Federation remote) runs on **3001**, and `npm run dev` also falls back to 3001 when 3000
is busy. In that case the backend returned **200 OK** but no `access-control-allow-origin`
header, so the browser discarded the response. DevTools showed `(failed)`, `0.0 kB`, and **no
status code at all**.

**The dangerous part:** this is **invisible from the server side.** The log records `turn.end`
and a successful turn, because from the backend's point of view nothing went wrong.

**The fix:** both ports in the default. `.env.example` already documented both and
`frontend/package.json` runs on both — so the default was wrong, not the configuration missing.

**6 tests** — `tests/unit/test_cors.py` (the setting, the actual header, **and the preflight** —
the chat call sends a custom header, so the browser sends OPTIONS first)

---

## Local setup

```powershell
# terminal 1 — backend
cd D:\vow-agent\backend
python -m uvicorn app.main:app --reload --port 8000

# terminal 2 — frontend
cd D:\vow-agent\frontend
npm run dev            # http://localhost:3000/agent/
```

**Port 8000**, because `frontend/.env` sets `VITE_API_BASE_URL=http://localhost:8000/api/v1`.
That file overrides `.env.example`, which says 4100. **Read `.env` before choosing a port.**

`--reload` picks up code changes automatically, but in-memory state is lost
(`USE_MEMORY_CHECKPOINTER=true`), so the conversation restarts.

---

**Tests:** 103 pass · **Lint:** ruff clean
