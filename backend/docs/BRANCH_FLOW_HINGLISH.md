# VOW Planning Agent — Backend Ka Poora Flow

**Branch:** `Future-PLN-KNW` (= `origin/feature_agent_planning` + 2 fixes)
**Date:** 2026-08-14 · **Tests:** 103 pass · **Model:** gpt-4o-mini

Ye document is branch ke backend ka *current* state hai — kya chal raha hai, kaise chal raha
hai, kahan toota hua hai. Taaki agla implementation step-by-step samajh kar ho.

---

## Contents

| | |
|---|---|
| 01 | [Ek nazar me](#01--ek-nazar-me) |
| 02 | [Ek turn ka poora safar](#02--ek-turn-ka-poora-safar) |
| 03 | [graph.py — wiring](#03--graphpy--wiring) |
| 04 | [state.py — har field](#04--statepy--har-field) |
| 05 | [gates.py — routing](#05--gatespy--routing) |
| 06 | [Chhe nodes, ek-ek](#06--chhe-nodes-ek-ek) |
| 07 | [API response — network tab](#07--api-response--network-tab) |
| 08 | [Governance (AGT)](#08--governance-agt) |
| 09 | [LLM ka kharcha — asli numbers](#09--llm-ka-kharcha--asli-numbers) |
| 10 | [Logs kaise padhein](#10--logs-kaise-padhein) |
| 11 | [Abhi ke issues](#11--abhi-ke-issues) |
| 12 | [Kya fix hua](#12--kya-fix-hua) |

---

## 01 · Ek nazar me

```
backend/app/
├── main.py                 FastAPI app, CORS, error handlers
├── config.py               Settings (env se)
├── api/
│   ├── routes.py           health + sessions router
│   ├── health.py           /health/live, /health/ready
│   ├── sessions.py         POST /sessions/chat  ← ek hi asli endpoint
│   ├── presentation.py     build_blocks() — UI ke liye structured reply
│   ├── errors.py           exception → HTTP status
│   └── validation_details.py
├── agent/
│   ├── graph.py            LangGraph state machine (6 nodes)
│   ├── state.py            PlanningAgentState — 22 fields
│   ├── gates.py            routers + missing_basics
│   ├── llm.py              get_llm(), log_usage()
│   ├── checkpointer.py     in-memory ya Postgres
│   └── nodes/              6 node files
├── governance/
│   ├── agt.py              policy engine + kill switch + audit
│   └── policies/vow_ctv.yaml   3 rules
├── knowledge/
│   ├── reference.py        provider → tier mapping
│   ├── reference_data.yaml
│   └── registry/           (khali — sirf __init__.py)
└── tools/
    ├── auth.py             VOWAuthProvider (StubAuth abhi)
    ├── base.py
    └── mcp/
        ├── client.py       MCPClient + governance wrapper
        ├── mock.py         MockMCPClient — canned VOW data
        └── mock_data.py
```

**Design ka core:** ek turn me **ek hi stage** chalti hai. Agent kuch dikhata hai, rukta hai,
user jawab deta hai, phir agla stage. Poora plan ek saath nahi banata.

**Do rules jo poore graph par lagte hain:**
1. **Model kabhi decide nahi karta ki kaunsa tool call hoga** — wo graph ka kaam hai.
2. **Model kabhi tool call nahi karta** — nodes karte hain, aur har call se pehle governance
   check hoti hai.

---

## 02 · Ek turn ka poora safar

```
BROWSER
  │  POST http://localhost:8000/api/v1/sessions/chat
  │  { "message": "...", "session_id": "..." }
  │  headers: Content-Type, X-Request-ID, Vowmade-Advertiser-Id (optional)
  ▼
main.py  ── CORS middleware (allowed: localhost:3000, localhost:3001)
  ▼
api/sessions.py  chat()
  │  advertiser_id nikalo (header ya DEV_ADVERTISER_ID)
  │  graph = build_graph(checkpointer, mcp)   ← per advertiser, cached
  │  state = checkpointer se load (session_id ke against)
  ▼
LangGraph: START → extract_fields
  │
  ├── extract_fields (hamesha chalta hai)
  │     ├─ _latest_human_text(state)
  │     ├─ LLM call #1  purpose="extract"   ~500 tokens in, ~1400ms
  │     │     (ya patterns, agar LLM key nahi)
  │     ├─ _merge(state, found)             ← naya + purana
  │     ├─ _flight_already_over()           ← past flight drop  [NAYA FIX]
  │     ├─ result["awaiting"] = missing_basics(result)
  │     └─ stage_cursor = None (agar market/duration/budget badla)
  │
  ▼
route_one_stage(state)          ← turn ka EK HI fork
  │
  ├─ awaiting khali nahi?  ──────────────────────────► ask
  │                                                      └─ LLM call #2 purpose="ask" ~1100ms
  │
  └─ khali hai? → stage_cursor dekho:
       None / "basics" ─────► select_inventory   → 2 MCP calls
       "inventory"    ─────► suggest_audiences   → 1 MCP call
       "audiences"    ─────► predict_reach       → 1 MCP call
       "forecast"     ─────► plan_ready          → 0 calls
  │
  ▼
har stage node → END  (turn khatam, agla message ka intezaar)
  │
  ▼
api/sessions.py
  │  reply = aakhri assistant message
  │  blocks = build_blocks(result)      ← api/presentation.py
  │  stage = result["stage_cursor"] ya current_stage
  ▼
{ session_id, reply, stage, blocks }  →  BROWSER
```

**Turn khatam kab hota hai:** jab `awaiting` bhar jaye (ask), ya jab koi stage node chal kar
`END` par pahunch jaye. Dono case me `stage_cursor` batata hai kahan tak pahunche.

---

## 03 · graph.py — wiring

`app/agent/graph.py` — sirf **107 lines**, aur wahi poora state machine hai.

**6 nodes register hote hain:**

| node | factory? | MCP chahiye? |
|---|---|---|
`extract_fields` | nahi, plain function | nahi |
`select_inventory` | `make_select_inventory(mcp)` | haan |
`suggest_audiences` | `make_suggest_audiences(mcp)` | haan |
`predict_reach` | `make_predict_reach(mcp)` | haan |
`plan_ready` | nahi | nahi |
`ask` | nahi (`ask_for_missing`) | nahi |

**Edges:**

```python
graph.add_edge(START, "extract_fields")          # hamesha pehle extraction

graph.add_conditional_edges(
    "extract_fields",
    route_one_stage,                              # EK hi fork
    {"ask": "ask", "select_inventory": ..., "suggest_audiences": ...,
     "predict_reach": ..., "plan_ready": ...},
)

for node in ("ask", "select_inventory", "suggest_audiences",
             "predict_reach", "plan_ready"):
    graph.add_edge(node, END)                     # sab turn khatam karte hain
```

`build_graph()` me `mcp=None` ho to **ValueError raise hota hai** — jaan-boojh kar. Staging me
chup-chaap mock client chalne se startup fail hona behtar hai.

**Jo abhi nahi hai** (graph ke docstring me khud likha hai):
- **Plan approval** — `predict_reach` ke baad `interrupt()`
- **Repair loop** — `predict_reach` se wapas `suggest_audiences` (detect hota hai, edge nahi hai)
- **Tier fork** — `select_inventory` se curation path

---

## 04 · state.py — har field

`PlanningAgentState` ek `TypedDict(total=False)` hai — nodes progressively bharte hain, har node
sirf apni keys return karta hai aur LangGraph merge karta hai.

### Conversation
| field | kya |
|---|---|
`messages` | `Annotated[list, add_messages]` — LangGraph khud append karta hai |

### Session
| field | kya |
|---|---|
`advertiser_id` | multi-tenancy |
`session_id` | conversation ID |
`current_stage` | **har turn reset hota hai** — abhi kaunsa node chala |

### Basics (Step 1)
| field | kaun likhta hai |
|---|---|
`strategy_name` | `extract_fields` — `"CTV GB 2026-10"` (provisional) |
`flight_dates` | `{lower, upper, bounds:"[)"}` |
`markets` | ISO codes, list |
`durations` | `["30"]` — seconds, string |
`primary_currency` | market se derive ya symbol se |
`goal` | hamesha `"AWARENESS"` (CTV ke liye fixed) |
`kpi` | `"reach"` |
`market_budgets` | `[{market, budget, base_bid}]` |

### Inventory (Step 2)
| field | kaun likhta hai |
|---|---|
`preferred_providers` | `extract_fields` — user ne jo channel naam liye |
`inventory_tier` | `select_inventory` — dominant tier |
`selected_deals` | `select_inventory` — matched deals |
`inventory_alternatives` | jo providers available hain par choose nahi kiye |

### Audience (Step 4)
| field | kaun likhta hai |
|---|---|
`audience_options` | `suggest_audiences` — **hamesha 3**: narrow/balanced/wide |
`chosen_audience` | user ki pick |

### Forecast (Step 6)
| field | kaun likhta hai |
|---|---|
`forecast` | `predict_reach` — `is_available` flag carry karta hai (honesty rule) |

### Flow control — **ye do sabse important hain**
| field | kya |
|---|---|
`stage_cursor` | **sirf aage badhta hai.** `current_stage` se alag: wo har turn reset hota hai, ye nahi. Yahi "ek stage per turn" ko possible banata hai |
`awaiting` | kya missing hai, human-readable labels ki list. Non-empty = graph rukta hai aur poochta hai |
`validation_errors` | (declared hai, is branch me koi node bharta nahi) |

**`stage_cursor` kaun likhta hai:**
```
select_inventory   → "inventory"
suggest_audiences  → "audiences"
predict_reach      → "forecast"
extract_fields     → None   (jab market/duration/provider/budget badla — invalidation)
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

Bas itna — jo field khali hai, uska label return. **4 basics** hain.

### `route_one_stage(state)` — poora router
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
        return "ask"                                    # missing hai to rukо
    return _NEXT_STAGE.get(state.get("stage_cursor"), "plan_ready")
```

**Do line ka router.** Pehle `awaiting` check — market na ho to inventory dhoondhne ka koi
matlab nahi. Phir cursor se agla stage.

`gates.py` me `route_after_basics` bhi hai par graph use nahi karta — `route_one_stage` ne
replace kar diya.

---

## 06 · Chhe nodes, ek-ek

### 1. `extract_fields` — entry node (~440 lines)

**Kaam:** message samjho, purane plan me merge karo, gate compute karo.

```
_latest_human_text(state)
  │
  ├─ LLM configured? ──── haan ──► _extract_with_llm()
  │                                  ├─ _system_prompt()      ← TODAY IS date  [FIX]
  │                                  ├─ _known_summary(state) ← labels, values nahi
  │                                  └─ structured output → BriefFields
  │                                     (fail ho to patterns par gir jao)
  │
  └─────────────────────── nahi ──► _extract_with_patterns()
                                       ├─ _markets()      regex
                                       ├─ _budget()       £/$/€ + k/m
                                       ├─ _durations()    10/15/20/30
                                       └─ _flight_dates() month + optional year  [FIX]
  ▼
_merge(state, found)
  │  khali = "is turn mention nahi hua", kabhi "clear karo" nahi
  │  providers: sirf wo jo reference.providers() me hain
  ▼
_flight_already_over(fields)          ← NAYA CHECK  [FIX]
  │  flight khatam ho chuki? → drop karo + reason banao
  ▼
result = {**fields, current_stage, strategy_name, goal, kpi, messages}
result["awaiting"] = missing_basics(result)
  │  flight drop hui to generic label ko reason se replace karo  [FIX]
  ▼
stage_cursor = None  agar markets/durations/providers/budgets badla
```

**`BriefFields`** — model ko yahi shape return karna hai:
```python
markets: list[str]        flight_start: str | None    flight_end: str | None
durations: list[str]      budget_amount: str | None   currency: str | None
providers: list[str]
```

---

### 2. `ask_for_missing` (node name: `ask`)

**Kaam:** `awaiting` ko ek sawal me badlo aur turn khatam karo.

```
missing = state["awaiting"]
  │
  ├─ stated     = jo labels compute hue (reason carry karte hain)  [FIX]
  └─ rewordable = jo gate ki fixed vocabulary hai
        │
        └─ LLM call #2  purpose="ask"  ← sirf ye jaata hai  [FIX]

reply = [stated verbatim] + [model ka phrasing ya template]
```

**`_FIXED_LABELS`** = `BASICS` ke 4 labels + `NO_INVENTORY` + `NO_AUDIENCE`. Isme jo nahi hai
wo **verbatim** bolta hai, model ko dikhta hi nahi.

---

### 3. `select_inventory` (~238 lines) — Step 2

**Kaam:** deals fetch karo, teen tiers me baanto.

```
basics adhoore? → awaiting return karke ruk jao
  ▼
MCP: vow.list_deals { advertiser_id, market, durations, format }
  │  (governance check pehle)
  ▼
MCP: vow.get_ctv_rate_card { advertiser_id, market }
  ▼
har deal ke liye: classify_tier(provider)     ← reference.py se
  │
  ├─ AMAZON_OWNED                Prime Video       → reach forecast MILEGA
  ├─ THIRD_PARTY_PRECURATED      Netflix           → forecast NAHI
  └─ THIRD_PARTY_NEEDS_CURATION  Disney+           → rate card only, deal nahi
  ▼
dominant_tier(deals)  ← poore flow ka primary fork
  ▼
preferred_providers diye the? → sirf wahi rakho
  ▼
{ selected_deals, inventory_tier, inventory_alternatives,
  stage_cursor: "inventory", awaiting: [] ya [NO_INVENTORY] }
```

**Tier hi sab decide karta hai** — reach forecast possible hai ya nahi, Amazon audience lagegi
ya nahi, deal selectable hai ya nahi.

---

### 4. `suggest_audiences` (~173 lines) — Step 4

**Kaam:** teen options do, **effective CPM** ke saath.

```
MCP: vow.suggest_audiences
  ▼
_cheapest_amazon_cpm(deals)   ← base CPM
  ▼
har option: effective_cpm = deal_cpm + vcpm_fee
  │
  ├─ NARROW    ~1.2M    18.22 + 3.50 = 21.72   sabse mehnga, sabse chhota
  ├─ BALANCED  ~4.8M    18.22 + 2.00 = 20.22   usual recommendation
  └─ WIDE      ~15.4M   18.22 + 0.85 = 19.07   sabse sasta, least precision
  ▼
{ audience_options, stage_cursor: "audiences", awaiting: [] ya [NO_AUDIENCE] }
```

**Effective CPM hi asli number hai.** Sirf deal CPM dikhana precision ki keemat chhupa deta
hai. Aur Amazon audience **sirf Amazon inventory** par lagti hai — third-party ka apna
targeting hai jo apna CPM jodta hai. Ye bola jaata hai, chupaya nahi.

---

### 5. `predict_reach` (~156 lines) — Step 6

**Kaam:** forecast — aur jahan possible nahi wahan **saaf mana karo**.

```
MCP: vow.predict_reach
  ▼
tier AMAZON_OWNED?
  │
  ├─ haan → reach + impressions + frequency
  └─ nahi → impressions ONLY (budget ÷ CPM × 1000)
            + saaf bolo ki reach forecast nahi mil sakta aur kyun
  ▼
{ forecast: {..., is_available}, stage_cursor: "forecast" }
```

**Do rules** (schema v2 §3 step 6):
1. **Reach number kabhi invent na karo** — ek believable jhoothi figure, admitted gap se
   zyada bura hai, kyunki trader uspar budget commit karega.
2. **Reach ko providers ke across add na karo** — cross-platform dedup nahi hai, numbers
   additive nahi hain.

---

### 6. `plan_ready`

**Kaam:** bolo ki plan ban gaya, aur **imaandari se bolo ki flow yahin rukta hai**.

```
"The plan is complete - inventory, audience and forecast are all settled.
 Approval and creating it in VOW are the next steps, and are not built yet.
 Tell me if you'd like to change anything."
```

47 lines, koi MCP call nahi. "Plan complete" bina caveat ke bolna implied karta ki campaign
exist karta hai — wo nahi karta.

---

## 07 · API response — network tab

`POST /api/v1/sessions/chat` → **4 keys**:

```json
{
  "session_id": "747d5ce4-...",         // agle message me wapas bhejo
  "reply": "Here is what I understood...",  // plain text, chat bubble
  "stage": "inventory",                  // stage_cursor — UI stepper
  "blocks": [ ... ]                      // asli UI instructions
}
```

Response header: `X-Request-ID` — log se match karne ke liye.

### `blocks` — Block contract

`api/presentation.py` me `Block` model:

| field | kya |
|---|---|
`text` | jo insaan padhta hai |
`interaction` | **authoritative** — frontend ko maanna hi hai |
`layout` | **suggested** — frontend override kar sakta hai |
`primary` | ye step ka main artifact hai ya sirf baatcheet |
`field` | user ki pick kis state field me jaayegi |
`data` | structured content |

**`Interaction` enum (7):**
```
none               read only
confirm            already decided — accept ya amend
select_one         ek hi chuno
select_many        kitne bhi chuno
input_date_range   start + end
input_money        amount + currency
input_text         free text
```

**`Layout` enum (7):**
```
summary_list  table  cards  chips  metrics  date_range_picker  currency_input
```

### Asli example (inventory turn)

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

**Ye design ka core idea hai:** backend HTML nahi bhejta, frontend business logic nahi rakhta.
Backend kehta hai *"table hai, multi-select karao, jawab `selected_deals` me daalo"* — frontend
sirf render karta hai. Naya control chahiye to dono side ek nayi enum value.

`reply` aur `blocks[0].text` **do alag versions** hain — ek lamba, ek chhota. Frontend chunta
hai kaunsa dikhaye.

---

## 08 · Governance (AGT)

`app/governance/agt.py` — VA-174. **Har MCP call se pehle** check hoti hai.

```
tools/mcp/client.py  call_tool()
  │
  ├─ governance.check   { tool, fields, advertiser }
  │     ▼
  │  agt.py → PolicyEngine (agentmesh library)
  │     │  policy: app/governance/policies/vow_ctv.yaml  — 3 rules
  │     │
  │     ├─ ALLOWED  → log "governance.allowed  rule=allow-planning-tools"
  │     └─ DENIED   → PolicyDeniedError → HTTP 403
  │
  ├─ kill switch: KILL_SWITCH file maujood?  → KillSwitchEngagedError → HTTP 503
  │
  └─ audit log: har allow/deny ka record
  ▼
asli MCP call
```

**Dependency:** `agent-governance-toolkit==4.1.0` + `-core==4.1.0` (exact pins, ADR-001).
Import `agentmesh.governance` se hota hai.

**403 vs 503 ka farq** (`api/sessions.py` me):
- `PolicyDeniedError` → **403**, WARNING log. Refusal system ka kaam karna hai, fail hona nahi.
  Client ko sirf "not permitted" milta hai — tool ka naam, rule ka naam, engine ki reasoning
  sab internal rehti hai, log me.
- `KillSwitchEngagedError` → **503**, CRITICAL log. Temporary hai, to caller ko samajhna
  chahiye ki baad me chal sakta hai — policy refusal ka ulta.

**Kill switch:** file ki **maujoodgi** hi switch hai.
```
touch KILL_SWITCH   → agent halted
rm KILL_SWITCH      → agent resumes
```
Agli call par asar. Koi restart nahi, koi deploy nahi. Aur **on/off env var jaan-boojh kar nahi
hai** — jo guardrail env var se band ho sake wo guardrail nahi hai.

---

## 09 · LLM ka kharcha — asli numbers

Ye logs se nikale gaye hain, estimate nahi. **39 calls, 27 turns.**

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

### Turn ka kitna hissa model ka intezaar hai

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

**Model latency har turn ka 55–100% hai.** Baaki poora backend — MCP calls, governance,
tier classification, block building — **0 se 4 ms** me ho jaata hai (mock MCP `duration_ms=0`
deta hai).

### Bekar ka kharcha — teen jagah

**1. Greeting par bhi do model calls.** `"Hi"` type karo:
```
extract call:  ~500 tokens in → kuch nahi nikalta   ~1400ms
ask call:      ~110 tokens in → sawal ke shabd      ~1100ms
                                            TOTAL:  ~2500ms
```
2.5 second, sirf ye kehne ke liye ki "market, budget aur dates do". Dono call bachayi ja sakti
hain — rules greeting pehchaan sakte hain, aur sawal **compute** hota hai, generate nahi.

**2. 26 extract calls me se 8 ne kuch bhi return nahi kiya** (≤34 output tokens). `"Hi"`,
`"30s"`, `"yes"` — in par 500 tokens ka prompt jaata hai aur khali jawab aata hai.

**3. Sawal ke shabd model banata hai.** `gate.blocked ... phrasing="llm"`. Content compute hota
hai (`missing_basics`), par phrasing ke liye ek poori call jaati hai. Template already maujood
hai aur deterministic hai.

**Paisa chhota hai** ($0.0034 / 39 calls) — **latency badi hai.** Aur ye mock MCP par hai; asli
VOW server ke saath MCP calls bhi time lenge, to model latency ke upar wo add hoga.

---

## 10 · Logs kaise padhein

**File:** `backend/logs/vow-agent.log` — ek line ek JSON object. Console format `.env` ke
`LOG_FORMAT` se (`text` ya `json`).

### Ek turn ke events, order me

| event | logger | kya batata hai |
|---|---|---|
`turn.start` | `api.sessions` | `message_chars` |
`turn.message` | `api.sessions` | **DEBUG** — user ka asli text |
`llm.prompt` | `agent.nodes.extract_fields` | **DEBUG** — poora prompt |
`llm.call` | `agent.llm` | `purpose`, `model`, `tokens_in/out`, `duration_ms` |
`llm.parsed` | `agent.nodes.extract_fields` | **DEBUG** — model ne kya nikala |
`stage.basics` | `agent.nodes.extract_fields` | `method`, `fields_found=3/4`, `awaiting` |
`stage.basics.values` | | **DEBUG** — merge ke baad ki values |
`flight.already_over` | | **WARNING** — past flight drop hui  [NAYA] |
`governance.check` | `tools.mcp.client` | DEBUG — kaunsa tool, kaunse fields |
`governance.allowed` | `governance.agt` | DEBUG — kis rule se pass hua |
`mcp.call` | `tools.mcp.client` | `tool`, `duration_ms`, `result_count` |
`mcp.response` | | **DEBUG** — poora body |
`stage.inventory` | `agent.nodes.select_inventory` | `deals`, `dominant_tier`, `tiers` |
`gate.blocked` | `agent.nodes.ask_for_missing` | `awaiting`, `phrasing` |
`turn.end` | `api.sessions` | `stage`, `duration_ms`, `nodes_run`, `blocked` |

### Ek turn ki misaal (asli log se)
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

### Kaam ke commands

```powershell
# ek session ka poora trace
Get-Content logs\vow-agent.log | ForEach-Object { $_ | ConvertFrom-Json } |
  Where-Object { $_.session_id -like '64abdae1*' }

# sirf turn boundaries aur cost
Select-String logs\vow-agent.log -Pattern 'turn.end|llm.call'

# UI se request aayi ya nahi (advertiser dev-advertiser-0001 = browser)
Select-String logs\vow-agent.log -Pattern 'dev-advertiser-0001'
```

**Ek trick jo ek issue ne sikhayi:** CORS block hone par request **log me aati hai** (server
jawab deta hai, browser baad me phenkta hai). Log me **kuch bhi nahi** = request pahunchi hi
nahi = connection-level problem (galat port, galat host). Ye pehla check hona chahiye.

---

## 11 · Abhi ke issues

### 🔴 A. Ek turn me do model calls — 2.5s bekar
`extract` + `ask`, ek hi message par. Greeting par bhi. 12 me se 12 blocked turns me dono
chalti hain. Model latency turn ka 55–100%.

**Kahan:** `extract_fields._extract_with_llm()` + `ask_for_missing`

### 🔴 B. Koi validation node nahi hai
6 nodes hain, **ek bhi value validate nahi karta**. Past date, aisi duration jo platform bechta
nahi, budget jo credit se zyada — koi check nahi. Maine flight check `extract_fields` ke andar
daala, par wo **stopgap hai** — asli jagah ek node hai.

**Saboot:** `state.validation_errors` declared hai, koi node bharta nahi.

### 🟠 C. `blocks` me chaaron deals `selected: true`
Netflix (`No reach forecast`) aur Disney+ (`Rate card only`) bhi pre-ticked aate hain, aur
`confirming: []` khali hai. UI par chaar rows tick lage dikhenge, jinme do khareedi nahi ja
sakti.

**Kahan:** `api/presentation.py`

### 🟠 D. Governance audit kahin save nahi ho raha
```
WARN governance.audit_in_memory
  note=decisions are NOT persisted and are lost on restart
  fix=set AUDIT_LOG_PATH and AUDIT_HMAC_KEY
```
Har turn par ye warning. Allow/deny decisions restart par gayab. Compliance ke liye ye
**evidence** hona chahiye, log nahi (log expire hote hain).

### 🟠 E. Sawal ke shabd model banata hai
`gate.blocked phrasing="llm"`. Content compute hota hai, phrasing generate. Ek call ka kharcha,
aur model ne **requirements invent bhi ki thi** (audience, budget, channels — ek item ki list
se). Reason wala hissa maine fix kiya; plain list par invention ka risk bacha hai.

### 🟡 F. `LOG_LEVEL=DEBUG` par OpenAI ka poora HTTP handshake log hota hai
Response headers, `set-cookie`, TLS handshake — sab. 181 kb ki file me asli flow dhoondhna
mushkil. `LOG_LEVEL=INFO` se saaf ho jaata hai.

### 🟡 G. `stage_cursor` invalidation blunt hai
Kuch bhi badla (market/duration/provider/budget) to cursor `None` — poora flow se dobara.
Sirf budget badalne par bhi inventory aur audiences dobara. Unke apne comment me `TMP-23`
likha hai.

### 🟡 H. `plan_ready` par flow rukta hai
Approval aur strategy creation nahi bane. Node imaandari se bolta hai, par flow chart ke 13
stages me se sirf 4-5 hue hain.

### 🟡 I. Frontend panel me placeholder data
`Mega Toothpaste`, `UK · USA · France`, `02.12.2025 – 20.11.2026` — ye frontend ka apna fixture
data hai, backend se nahi aata. Chat chalne ke baad asli values se replace hona chahiye.

---

## 12 · Kya fix hua

### 1. Past flight dates 🔴 → ✅

**Problem:** *"October 1st to October 31st"* (saal nahi bola) → model ne `2023-10-01` diya. Aaj
2026 hai. Inventory bhi usi 3-saal purani flight ke liye match hui. **Kisi ne check nahi kiya.**

**Teen wajah:**
1. Prompt me aaj ki tareekh hi nahi thi — model ne apni training data se resolve kiya
2. Koi validation node nahi hai
3. `extract_fields` ka **ek bhi test nahi tha**

**Fix — teen jagah:**

| kahan | kya |
|---|---|
`_system_prompt()` | `_SYSTEM` constant se **function** bana. Prompt me `TODAY IS 2026-08-14` + rule *"saal na ho to aage wali date, kabhi peechhe nahi"*. Function hai kyunki import par banata to server jis subah start hua wahi tareekh freeze ho jaati |
`_flight_dates()` | pattern path bhi `date.today().year` flat padh raha tha — August me "March" likhne par 5 mahine purani date. Ab mahina nikal gaya to agla saal |
`_flight_already_over()` | **naya check** — khatam ho chuki flight plan me jaane hi nahi deta. `upper` dekhta hai `lower` nahi: pichhle hafte shuru hua aur agle mahine tak chalega wo valid hai |
`gates.FLIGHT` | label ko naam diya, taaki `extract_fields` pehchaan kar badal sake |

**Verify (asli UI se):**
```
"£15k from October 1 to 31"  →  flight_start=2026-10-01  flight_end=2026-10-31   ✅
"October 2023"               →  Flight: not stated
                                "I need a flight that has not already finished -
                                 2023-10-01 to 2023-10-31 is in the past, and
                                 today is 2026-08-14."                            ✅
```
Log me `WARNING flight.already_over` bhi aata hai — silent nahi.

**18 tests** — `tests/unit/agent/test_flight_dates.py`

---

### 2. Reason model ne gira diya 🔴 → ✅

**Problem:** Mera reason `awaiting` tak theek pahuncha, phir `ask_for_missing` ne **model ko de
diya**. Ek item ki list se gpt-4o-mini ne:
- reason poora gira diya
- **teen** requirements invent ki: audience, budget, channels
- budget maanga jo card par already tha

Node ki apni docstring kehti hai *"the LLM rewords a known list, it does not decide what is
missing"* — model ne decide kar liya.

**Fix:** `_FIXED_LABELS` — gate ki apni vocabulary (4 BASICS labels + NO_INVENTORY +
NO_AUDIENCE) model ko jaati hai. Jo label trader ki apni values se **compute** hua ho, wo
**verbatim** bolta hai. Correction pehle, sawal baad me.

**12 tests** — `tests/unit/agent/test_ask_for_missing.py`

---

### 3. CORS — 3001 blocked 🟠 → ✅

**Problem:** `config.py` ka default sirf `localhost:3000` allow karta tha. `npm run dev:remote`
(Module Federation remote) **3001** par chalta hai, aur `npm run dev` bhi 3001 par gir jaata hai
jab 3000 busy ho. Us case me backend **200 OK** deta tha par `access-control-allow-origin`
header nahi — browser response phenk deta tha. DevTools me `(failed)`, `0.0 kB`, **status code
bhi nahi**.

**Sabse khatarnak baat:** ye server side se **invisible** hai. Log me `turn.end` normally aata
hai, sab successful — kyunki backend ke hisaab se kuch galat nahi hua.

**Fix:** default me dono port. `.env.example` pehle se dono likhta tha, `frontend/package.json`
dono par chalta hai — to default hi galat tha, config missing nahi thi.

**6 tests** — `tests/unit/test_cors.py` (setting, actual header, **aur preflight** — chat call
custom header bhejta hai to browser pehle OPTIONS maarta hai)

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

**Port 8000** — kyunki `frontend/.env` me `VITE_API_BASE_URL=http://localhost:8000/api/v1` hai.
Ye file `.env.example` (jo 4100 kehta hai) ko override karti hai. **Pehle `.env` padho, phir
port chuno.**

`--reload` se code change apne aap uthta hai — par in-memory state chala jaata hai
(`USE_MEMORY_CHECKPOINTER=true`), to conversation naya shuru hoga.

---

**Tests:** 103 pass · **Lint:** ruff clean
