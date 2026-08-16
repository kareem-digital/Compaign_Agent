# Campaign Agent — Strategy Planning Discussion

A step-by-step plan to build a LangGraph-based conversational agent that collects campaign details from a user in a chatty, engaging way and produces a complete CTV strategy — using only grounded data from the registry, MCP server, and mock data.

---

## 1. Where We Are Today

### What already exists in VOW Agent

The current codebase has a solid foundation, but it is **not yet conversational**. Here is what is there:

| Layer | What exists | What it does well | What is missing |
|---|---|---|---|
| **LangGraph graph** | 4 nodes: `extract_fields → select_inventory → suggest_audiences → predict_reach` + `ask_for_missing` + `plan_ready` | Gated flow — won't skip ahead when basics are incomplete | No LLM-driven conversation. Nodes produce prose, not chat. Every turn re-runs all 4 nodes |
| **State** | `PlanningAgentState` with ~25 fields | Accumulates across turns, gates on `awaiting` | No location, no targeting detail, no approval flag, no strategy creation |
| **Registry** | `AdvertiserRegistry` → `GroundedRegistrySnapshot` with models, validators, normalizers | Zero-hallucination grounding against real/mock VOW data | All data comes from mock MCP — shapes are realistic, values are canned |
| **MCP Client** | `MockMCPClient` with tools: `list_deals`, `ctv_rate_card`, `suggest_audiences`, `reach_forecast`, `check_strategy_name` | Fail-closed policy, retry, governance checks | No real server. Tool names are guesses (TMP-05) |
| **Presentation** | `Block` model with `Interaction` and `Layout` enums | Backend decides interaction type (select_one, input_money, etc.) and suggests layout (cards, chips, table) | Frontend doesn't render blocks yet — everything arrives as plain text `reply` |
| **Frontend** | Vite + React + TypeScript with chat UI components | `MessageBubble`, `OptionsBlockCard`, `ChatInput`, `StartScreen` | Only renders text replies. `blocks[]` from the API is unused |
| **Test cases** | 84 test cases in the docs covering every conversation scenario | Covers vague intent, complete briefs, missing fields, unsupported inventory, audience, location, budget splits, approval, corrections | These are documentation — no automated tests implement them yet |

### The critical gap

The current agent is a **pipeline**, not a **conversationalist**. It:
- Dumps everything it knows in long paragraphs
- Doesn't engage the user — no follow-ups, no personality, no short chatty responses
- Re-runs the entire 4-node chain on every message
- Has no LLM generating the conversational responses — extraction uses LLM optionally, but the replies are template strings
- Cannot handle "Actually change X" without restarting the chain

---

## 2. What We Are Building — The Campaign Agent

A new LangGraph-based agent in the **Campaign_Agent** repo that:

1. **Chats naturally** — short, engaging messages like a real human conversation
2. **Collects campaign details progressively** — doesn't dump a form, asks one thing at a time
3. **Shows interactive UI elements** — radio buttons, cards, date pickers, budget inputs — based on what's being asked
4. **Grounds every value** — nothing from the LLM's imagination. Markets, deals, audiences, forecasts all come from the registry/MCP
5. **Manages state** — remembers everything across turns, never re-asks what was already given
6. **Handles corrections gracefully** — "Actually make it £20k" works without starting over

---

## 3. The Conversation Journey — Step by Step

Based on the test cases and flowchart, here is the full journey the agent must support:

```
┌─────────────────┐
│   User arrives   │
│  (vague or full) │
└────────┬────────┘
         │
         ▼
┌─────────────────────┐
│  PHASE 1: BASICS    │  Collect: market, product/context, budget,
│  (progressive chat) │  flight dates, creative duration, goal/KPI
└────────┬────────────┘
         │  all basics complete?
         ▼
┌─────────────────────┐
│  PHASE 2: INVENTORY │  Show available deals from MCP/registry
│  (cards/table)      │  Handle unsupported inventory gracefully
└────────┬────────────┘
         │  inventory selected?
         ▼
┌─────────────────────┐
│  PHASE 3: BUDGET    │  Only if multiple deals selected
│  SPLIT (table)      │  Propose split or let user set manually
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  PHASE 4: AUDIENCE  │  Three options: narrow/balanced/wide
│  (cards)            │  Optional: custom audience, geo targeting
└────────┬────────────┘
         │  audience chosen?
         ▼
┌─────────────────────┐
│  PHASE 5: LOCATION  │  Default to market-wide, allow refinement
│  (search/select)    │  Postcodes, city, radius — all optional
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  PHASE 6: FORECAST  │  Reach, impressions, frequency, CPM
│  (metrics + curve)  │  Honest: no reach for 3P inventory
└────────┬────────────┘
         │  reach acceptable?
         │  ┌─── NO ──→ Suggest widen audience → re-forecast
         ▼
┌─────────────────────┐
│  PHASE 7: PLAN      │  Show full summary with all details
│  REVIEW (summary)   │  Accept Plan / Edit Plan
└────────┬────────────┘
         │  approved?
         ▼
┌─────────────────────┐
│  PHASE 8: CREATE    │  Call strategy creation (future)
│  STRATEGY           │  Return strategy ID
└─────────────────────┘
```

> [!IMPORTANT]
> The user can arrive at ANY point in this journey. If they say "£15k, UK, Oct 1-31, 30s, awareness, Prime Video" — we skip straight to Phase 4. If they say "I want to run a campaign" — we start at Phase 1 and probe progressively.

---

## 4. Agent Architecture — How to Build It

### 4.1 The Core Idea: LLM as the Conversationalist, Tools for Data

```
┌───────────────────────────────────────────────────┐
│                   LangGraph Agent                  │
│                                                   │
│  ┌──────────┐    ┌────────────┐    ┌──────────┐  │
│  │  Router   │───▶│  LLM Node  │───▶│ Tool Node│  │
│  │ (decides  │    │ (chatty    │    │ (calls   │  │
│  │  what's   │    │  response  │    │ registry │  │
│  │  next)    │    │  + extract)│    │ & MCP)   │  │
│  └──────────┘    └────────────┘    └──────────┘  │
│        ▲                                  │       │
│        └──────────────────────────────────┘       │
│                                                   │
│  ┌────────────────────────────────────────────┐   │
│  │         PlanningState (TypedDict)          │   │
│  │  markets, budget, dates, deals, audience…  │   │
│  └────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────┘
```

The key architectural decision:

- **The LLM generates the chat response** — short, friendly, human-like. It reads the state and the user's message, and produces a chatty reply.
- **Tools provide the data** — the LLM calls tools to fetch inventory, audiences, forecasts. It NEVER makes up data.
- **The state machine controls the flow** — what phase we are in, what's collected, what's missing.

### 4.2 LangGraph Node Design

Here is the proposed node structure:

| Node | Trigger | What it does | Outputs |
|---|---|---|---|
| **`understand_message`** | Every turn | LLM extracts campaign fields from user message, merges with known state. Grounds against registry. | Updated state fields + what changed |
| **`decide_next_action`** | After understanding | Checks what's missing, what phase we are in. Decides: ask for more? show inventory? forecast? | Route to the right node |
| **`respond_to_user`** | When asking for info | LLM generates a SHORT, chatty response asking for missing info. Includes UI interaction blocks. | `reply` + `blocks[]` |
| **`fetch_inventory`** | When basics complete | Calls MCP `list_deals` + `ctv_rate_card`. Formats as cards/table. | Inventory data + blocks |
| **`fetch_audiences`** | After inventory | Calls MCP `suggest_audiences`. Shows 3 audience cards. | Audience options + blocks |
| **`run_forecast`** | After audience | Calls MCP `reach_forecast`. Shows metrics + curve. | Forecast data + blocks |
| **`present_plan`** | All settled | Shows final plan summary for approval. | Plan summary + approve/edit blocks |
| **`handle_correction`** | User changes a value | Updates state, invalidates dependent data, re-routes. | Updated state |

### 4.3 The Chatty Response Pattern

This is **THE** most important thing to get right. Based on the test cases:

**❌ What the current agent does (bad):**
```
Here is what I understood - correct anything that is wrong before I continue.

- Markets: GB
- Flight: 2026-10-01 to 2026-10-31
- Creative durations: 30
- Currency: GBP
- Budget: 15000.00 GBP (GB)
- Goal: Awareness, measured on reach (fixed for CTV)

CTV inventory available in GB:

- Prime Video - 18.22 CPM (15, 30s) - Amazon-owned (reach forecast available)
- Netflix - 31.50 CPM (30s) - third-party, pre-curated (no reach forecast)
...
```

**✅ What we want (good — from test cases):**
```
Great — I have the product, UK market and Prime Video.
I just need the campaign budget, dates, ad length and
campaign goal to build the initial plan.
```

Or even shorter:
```
Got it. What budget would you like to allocate to the campaign?
```

**The rules for chatty responses:**
1. **1-3 sentences max** for a regular turn
2. **Acknowledge what you understood** briefly — "Got it — £15k and October dates."
3. **Ask for ONE thing** (or a small batch if they are related)
4. **Use the user's language** — "ad length" not "creative duration"
5. **Never dump a paragraph** — if you need to show data, put it in blocks (cards, table), not in text
6. **Be warm but professional** — "Great", "Got it", "Sure", "No problem"
7. **Never repeat what was already said** — if they gave the market, don't ask for the market

### 4.4 UI Interaction Blocks

The presentation layer already defines the right primitives. The agent produces these alongside its chat message:

| When asking for... | Interaction type | Layout | Example |
|---|---|---|---|
| Market | `select_many` | `chips` | [UK] [USA] [France] [Germany] |
| Campaign goal | `select_one` | `chips` | ○ Awareness ○ Consideration |
| Creative duration | `select_many` | `chips` | [10s] [15s] [20s] [30s] |
| Budget | `input_money` | `currency_input` | £ [________] |
| Flight dates | `input_date_range` | `date_range_picker` | [Oct 1] — [Oct 31] |
| Inventory | `select_many` | `table` or `cards` | Deal cards with CPM, tier, lengths |
| Audience | `select_one` | `cards` | Narrow / Balanced / Wide with metrics |
| Budget split | `confirm` | `table` | Editable allocation table |
| Reach forecast | `none` | `metrics` | Reach: ~154k · Impressions: ~492k |
| Plan approval | `confirm` | `summary_list` | Accept Plan / Edit Plan |
| Unsupported inventory | `select_one` | `chips` | Show alternatives / Keep request |

---

## 5. Step-by-Step Build Plan

### Phase 1: Project Setup & Foundation
**Goal:** New repo, virtual environment, base project structure

1. Clone the new repo `https://github.com/kareem-digital/Compaign_Agent.git`
2. Set up Python virtual environment
3. Create the project folder structure:
   ```
   Compaign_Agent/
   ├── backend/
   │   ├── app/
   │   │   ├── agent/           # LangGraph graph, nodes, state
   │   │   ├── api/             # FastAPI endpoints
   │   │   ├── core/            # Config, exceptions, logging
   │   │   ├── knowledge/       # Registry, models, validators (from VOW Agent)
   │   │   ├── tools/           # MCP client, mock server (from VOW Agent)
   │   │   └── prompts/         # System prompts for the LLM
   │   ├── tests/
   │   ├── requirements.txt
   │   └── .env
   ├── docs/                    # Schema docs, test cases
   └── README.md
   ```
4. Install core dependencies:
   - `langgraph`, `langchain-core`, `langchain-openai`
   - `fastapi`, `uvicorn`, `pydantic`
   - `httpx` (for MCP)
5. Copy over the knowledge layer (registry, models, validators) — this is the grounding backbone
6. Copy over the MCP client + mock — this is our data source
7. Copy over governance layer — policies and guardrails

---

### Phase 2: State Design
**Goal:** Define the complete `PlanningState` that tracks the entire conversation

The state from VOW Agent is a good start. We expand it:

```python
class PlanningState(TypedDict, total=False):
    # --- Conversation ---
    messages: Annotated[list, add_messages]
    
    # --- Session ---
    advertiser_id: str
    session_id: str
    current_phase: str           # basics | inventory | budget_split | audience | location | forecast | review | approved
    
    # --- Basics ---
    product_context: str | None  # what they are promoting
    strategy_name: str | None
    markets: list[str]
    flight_dates: dict | None    # {lower, upper, bounds}
    durations: list[str]
    primary_currency: str
    budget_amount: str | None
    market_budgets: list[dict]
    goal: str
    kpi: str
    
    # --- Inventory ---
    preferred_providers: list[str]
    available_deals: list[dict]
    selected_deals: list[dict]
    inventory_tier: str | None
    inventory_alternatives: list[str]
    
    # --- Budget Split ---
    budget_split: list[dict] | None  # [{deal_id, provider, amount}]
    
    # --- Audience ---
    audience_options: list[dict]
    chosen_audience: dict | None
    audience_preference: str | None  # broad | narrow | custom
    custom_audience_desc: str | None
    
    # --- Location ---
    location_type: str | None     # market_wide | city | postcodes | radius
    locations: list[str]          # default [market ISO]
    postcodes: list[str]
    radius: dict | None           # {center, distance, unit}
    
    # --- Forecast ---
    forecast: dict | None
    forecast_acceptable: bool | None
    
    # --- Plan ---
    plan_approved: bool
    strategy_id: str | None
    
    # --- Flow control ---
    awaiting: list[str]           # what's still missing
    rejected_fields: list[str]    # values given but invalid
    last_user_intent: str | None  # what the user was trying to do
    
    # --- UI ---
    pending_blocks: list[dict]    # interactive blocks to show
```

> [!NOTE]
> The state accumulates — nothing is wiped between turns. When a user says "Actually £20k", only `budget_amount` and `market_budgets` are updated. Everything else is preserved. Downstream data that depends on changed values (forecast, reach) is invalidated.

---

### Phase 3: LLM Integration — The Brain
**Goal:** Wire the LLM to understand messages AND generate chatty responses

Two LLM calls per turn (both use the same model):

**Call 1 — Extract & Understand** (structured output)
- Takes: user message + known state
- Returns: structured `BriefFields` (markets, dates, budget, etc.)
- This is what `extract_fields` already does — we keep the same approach but extend it

**Call 2 — Generate Chat Response** (free-form text)
- Takes: user message + known state + what's missing + what was just understood
- Returns: SHORT chatty response (1-3 sentences)
- System prompt enforces the chatty style

The system prompt for the chat response will be something like:

```
You are VOW Agent, a friendly campaign planning assistant.

RULES:
- Be SHORT. 1-3 sentences. Never paragraphs.
- Acknowledge what you just learned: "Got it — UK market and £15k."
- Ask for what's missing naturally: "What dates should it run?"
- Use simple language. "ad length" not "creative duration".
- Never make up data. Never guess prices, reach, or deals.
- Be warm: "Great", "Got it", "Sure", "No problem".
- Don't repeat what the user already told you.

CURRENT STATE:
{state_summary}

WHAT'S MISSING:
{missing_fields}

Generate a 1-3 sentence reply.
```

> [!IMPORTANT]
> The LLM generates ONLY the chat text. The data (deals, audiences, forecasts) comes from tool calls. The UI interaction blocks (radio buttons, cards) are determined by code, not by the LLM.

---

### Phase 4: Tool Definitions
**Goal:** Define LangGraph tools the agent can call to fetch data from MCP/registry

```python
# Tool 1: Get available inventory
@tool
async def get_available_inventory(market: str, durations: list[str]) -> dict:
    """Fetch CTV deals available for a market. Returns deals with CPM, tier, ad lengths."""
    
# Tool 2: Get rate card
@tool
async def get_rate_card(market: str) -> dict:
    """Fetch the CTV rate card for a market."""

# Tool 3: Suggest audiences
@tool
async def suggest_audiences(market: str, goal: str, brief: str) -> dict:
    """Get 3 audience suggestions: narrow, balanced, wide. Each with VCPM fee."""

# Tool 4: Forecast reach
@tool
async def forecast_reach(inventory_tier: str, audience_set_id: str, budget: str, ...) -> dict:
    """Predict reach, impressions, frequency for the selected inventory and audience."""

# Tool 5: Validate market
@tool
async def validate_market(market_code: str) -> dict:
    """Check if a market is available on the platform. Returns valid/invalid with alternatives."""

# Tool 6: Validate provider
@tool
async def validate_provider(provider: str, market: str) -> dict:
    """Check if an inventory provider is available. Returns available/unavailable with alternatives."""

# Tool 7: Check strategy name
@tool
async def check_strategy_name(name: str) -> dict:
    """Check if a strategy name is unique in VOW."""
```

All tools wrap the existing MCP client + registry. No new data sources — everything comes from what's already there.

---

### Phase 5: The LangGraph Graph — Bringing It Together
**Goal:** Wire the conversation loop

```python
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode

def build_campaign_graph():
    graph = StateGraph(PlanningState)
    
    # Nodes
    graph.add_node("understand", understand_message)      # Extract fields from user msg
    graph.add_node("decide", decide_next_action)          # Router: what phase are we in?
    graph.add_node("respond", generate_response)          # LLM generates chatty reply
    graph.add_node("tools", ToolNode(tools))              # Execute tool calls
    graph.add_node("present_data", present_data_to_user)  # Format tool results as blocks
    
    # Edges
    graph.add_edge(START, "understand")
    graph.add_conditional_edges("understand", route_after_understanding)
    graph.add_edge("respond", END)                        # Chat reply → done
    graph.add_edge("tools", "present_data")               # Tool result → format → reply
    graph.add_edge("present_data", END)
    
    return graph.compile(checkpointer=MemorySaver())
```

The routing logic:

```
understand → (has missing basics?) → respond (ask for them)
          → (basics complete, no inventory?) → tools (fetch inventory)
          → (inventory done, no audience?) → tools (suggest audiences)
          → (audience chosen, no forecast?) → tools (run forecast)
          → (forecast done, not approved?) → respond (show plan, ask approval)
          → (approved?) → respond (create strategy)
          → (user changing a value?) → understand → invalidate → re-route
```

---

### Phase 6: Response Formatting & Blocks
**Goal:** Produce `blocks[]` that the frontend can render as interactive UI elements

Each turn produces:
1. **A `reply` string** — the chatty text message
2. **A `blocks[]` array** — structured UI elements

Example response for "What's the budget?":

```json
{
  "session_id": "abc-123",
  "reply": "Got it — UK market, October dates, and 30-second creative. What budget should I work with?",
  "stage": "basics",
  "blocks": [
    {
      "text": "What's the budget?",
      "interaction": "input_money",
      "layout": "currency_input",
      "field": "market_budgets",
      "data": { "currency": "GBP", "minimum": 1 }
    }
  ]
}
```

Example response for inventory selection:

```json
{
  "reply": "Great — here's what's available in the UK for your campaign.",
  "stage": "inventory",
  "blocks": [
    {
      "text": "CTV inventory available in GB",
      "interaction": "select_many",
      "layout": "cards",
      "field": "selected_deals",
      "data": {
        "options": [
          {
            "value": "EXTPRV0001",
            "label": "Prime Video",
            "sublabel": "Amazon-owned",
            "metrics": { "CPM": "18.22", "Lengths": "15s, 30s" },
            "badge": "Reach forecast available",
            "selected": true
          },
          {
            "value": "EXTNFLX0012",
            "label": "Netflix",
            "sublabel": "Third-party",
            "metrics": { "CPM": "31.50", "Lengths": "30s" },
            "badge": "No reach forecast"
          }
        ]
      }
    }
  ]
}
```

---

### Phase 7: Handling Edge Cases
**Goal:** Make the agent robust for every scenario in the test cases

| Scenario | How the agent handles it | Test case ref |
|---|---|---|
| User gives everything in one shot | Extract all, skip to inventory/audience/forecast | TC-005 |
| User says "I want to run a campaign" | Ask product + market | TC-001 |
| User gives invalid budget | "I couldn't read that. What budget?" | TC-069 |
| User gives past dates | "That's already passed — what dates?" | TC-070 |
| User asks for unsupported inventory | "Zee TV isn't available. Want to see alternatives?" | TC-014 |
| User changes a value mid-flow | Update state, invalidate downstream, re-route | TC-012 |
| User says "You decide" | Recommend, but still show for approval | TC-059 |
| User asks unrelated question | Redirect to campaign context | TC-067 |
| User wants to restart | Clear state, start fresh | TC-068 |
| Budget split needed | Only when multiple deals selected | TC-019 |
| Reach too narrow | Suggest broadening audience | TC-034 |

---

### Phase 8: API Endpoints
**Goal:** FastAPI endpoints that mirror the existing VOW Agent API

```python
# Chat endpoint — the main conversational turn
POST /api/v1/sessions/chat
{
    "message": "I want to run a campaign in the UK",
    "session_id": "optional-uuid"
}

# Response
{
    "session_id": "uuid",
    "reply": "Sure. What are you promoting?",
    "stage": "basics",
    "blocks": [...]
}

# Session state — for debugging/panel
GET /api/v1/sessions/{session_id}

# Health checks
GET /api/v1/health/live
GET /api/v1/health/ready
```

---

### Phase 9: Testing & Validation
**Goal:** Verify against the 84 test cases

1. **Unit tests** for each node — does `understand_message` extract correctly?
2. **Integration tests** for the graph — does a full conversation flow work?
3. **Golden path tests** — the 4 end-to-end scenarios from the test cases (Golden Cases A-D)
4. **Edge case tests** — unsupported inventory, invalid inputs, corrections

---

### Phase 10: Git Setup & Push
**Goal:** All code in the Campaign_Agent repo

```bash
git init
git remote add origin https://github.com/kareem-digital/Compaign_Agent.git
git add .
git commit -m "Initial commit: Campaign Agent with LangGraph"
git push -u origin main
```

---

## 6. Key Design Decisions

### Decision 1: LLM for conversation, code for data
The LLM generates the chatty replies. The registry/MCP provides the data. The presentation layer picks the UI format. None of these cross boundaries.

### Decision 2: One stage per turn
The agent shows ONE new thing per turn and waits. It doesn't dump inventory + audiences + forecast before the user says a word. This is the "chatty" requirement — the user is engaged at every step.

### Decision 3: Accumulate, never replace
State is additive. A new message adds or updates, never wipes. The user never has to repeat themselves.

### Decision 4: Blocks are code-determined, not LLM-determined
Which UI element to show (radio button vs card vs table) is decided by code based on the phase and the field being collected. The LLM doesn't choose layouts — that would be non-deterministic.

### Decision 5: Ground everything
Every market, deal, duration, audience, CPM, reach number comes from the registry or MCP. The LLM can say "Got it — UK market" but can never say "UK campaigns typically get 200k reach" unless the forecast tool said so.

---

## 7. What Gets Carried Over From VOW Agent

| Component | Action | Why |
|---|---|---|
| `knowledge/registry/` (models, validate, ingestion) | **Copy fully** | This is the grounding backbone — enums, normalizers, validators, snapshot |
| `tools/mcp/` (client, mock) | **Copy fully** | Data source — fail-closed policy, retry, mock responses |
| `governance/` | **Copy fully** | Policy engine — budget caps, market restrictions |
| `api/presentation.py` | **Adapt** | Block/Interaction/Layout model is solid. Builders need to work with new node structure |
| `agent/state.py` | **Extend** | Add location, budget_split, approval, product_context fields |
| `agent/gates.py` | **Refactor** | Keep the gating concept but make it work with LLM-driven routing |
| `agent/nodes/` | **Rebuild** | New nodes designed for chatty interaction. Keep the data-fetching logic, rebuild the response generation |
| `core/` | **Copy fully** | Config, exceptions, logging — infrastructure |

---

## Open Questions

> [!IMPORTANT]
> **Q1: Which LLM model should we use?**
> The existing code uses `gpt-4o-mini` via `langchain-openai`. Should we stick with that, or use a different model? The chatty response generation needs a model that's good at short, natural conversation.

> [!IMPORTANT]
> **Q2: Should the frontend be part of this new repo or separate?**
> The VOW Agent frontend already has chat components. Do we build a new frontend in the Campaign_Agent repo, or do we focus on the backend and let the existing frontend consume the API?

> [!WARNING]
> **Q3: Streaming vs Request/Response?**
> The current API is request/response — the user sends a message, waits a few seconds, gets the reply. For a chatty experience, streaming (SSE) would be much better — the user sees the response typing in real-time. Should we plan for streaming from the start?

> [!IMPORTANT]
> **Q4: The elicitation format**
> The `PFA_response_chat.json` shows an "options" content type with `select: "single"`, `allow_custom: true`, `status: "pending"`. Is this the format we should adopt for the `blocks[]`, or do we use the existing `Block` model from `presentation.py`?

---

## Summary

We are building a **chatty, conversational campaign planning agent** that:
1. Talks like a helpful colleague, not a form
2. Collects details progressively — one thing at a time
3. Shows interactive UI elements — buttons, cards, inputs
4. Never makes up data — everything comes from the registry and MCP
5. Handles any conversation path — vague start, complete brief, corrections, restarts
6. Uses LangGraph for the flow and an LLM for natural language — with tools for data

The foundation from VOW Agent is solid. We are adding the **conversational intelligence** layer on top.
