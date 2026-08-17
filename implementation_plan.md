# M1 Strategy Plan — Planner / Orchestrator Agent Architecture & Implementation Plan

> **Scope**: Planner/Orchestrator-centered multi-agent LangGraph architecture, domain rules (Rate Cards, R&F, Budget Splitting, Targeting), and API contract elicitation protocol.  
> **Reference Assets**: `docs/Workflow.jpeg`, `M1_Planning.txt`, `backend/API CONTRACT/*.json`, `docs/AGENT_API_FOR_UI.md`.

---

## 1. Executive Summary & Orchestrator Core Concept

Following the blueprint in [Workflow.jpeg](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/docs/Workflow.jpeg) and the requirements in [M1_Planning.txt](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/M1_Planning.txt), the system is structured around the **Planner / Orchestrator Agent** as the central intelligence and control center.

```
                              ┌─────────────────────────────────────────┐
                              │       START: Customer Query / Turn      │
                              └────────────────────┬────────────────────┘
                                                   │
                                                   ▼
                              ┌─────────────────────────────────────────┐
                              │        1. PLANNER / ORCHESTRATOR        │
                              │  - Understand query & extraction        │
                              │  - Load / identify customer state       │
                              │  - Gap & conflict analysis              │
                              │  - Dynamic routing & dispatch           │
                              └─────────┬───────────────────▲───────────┘
                                        │                   │ (Always returns
                                        │                   │  to Planner)
        ┌───────────────────────────────┼───────────────────┴──────────────────────────┐
        │                               │                                              │
        ▼ (Basics incomplete)           ▼ (Inventory stage)                            ▼ (Targeting stage)
┌───────────────────────┐       ┌───────────────────────┐                      ┌───────────────────────┐
│ 2. EMAD AGENT         │       │ 3. VISHAL AGENT       │                      │ 4. KAREEM AGENT       │
│ (Basic Details)       │       │ (CTV Inventory)       │                      │ (Targeting & Split)   │
│ - Market, Goals, Dates│       │ - Platforms (Prime,   │                      │ - Demographics (Age,  │
│ - Budget, Durations   │       │   Netflix, Disney+)   │                      │   HHI, Geos)          │
│ - Rate card matching  │       │ - Rate Cards vs Deals │                      │ - Dynamic Budget Split│
│ - Update Shared State │       │ - Update Shared State │                      │ - Reach & Freq Calc   │
└───────────┬───────────┘       └───────────┬───────────┘                      └───────────┬───────────┘
            │                               │                                              │
            └───────────────────────────────┴──────────────────────────────────────────────┘
                                                    │
                                                    ▼ (All required info complete)
                                        ┌───────────────────────┐
                                        │ 5. CAMPAIGN SETUP /   │
                                        │    EXECUTION AGENT    │
                                        │ - Final Plan Summary  │
                                        │ - Human Approval Gate │
                                        │ - Platform Execution  │
                                        └───────────┬───────────┘
                                                    │
                                                    ▼
                                        ┌───────────────────────┐
                                        │ 6. MONITORING AGENT   │
                                        │ - Performance / Report│
                                        │ - Loop back on changes│
                                        └───────────────────────┘
```

### Key Architectural Tenets:
1. **Planner is the Sole Decision Maker**:
   - Evaluates what information is present, what is missing, what is invalid, and which specialized agent to dispatch.
   - Generates interactive UI elicitation blocks (single/multi-select chips, date range pickers, currency inputs) when user input is needed.
2. **Shared State Store (`PlanningAgentState`)**:
   - All specialized agents read from and write back to the centralized shared state.
   - Persistence and idempotency across turns are keyed by `session_id` and `client_message_id`.
3. **Hub-and-Spoke Loop-Back**:
   - After any specialized sub-agent updates the shared state, control **always returns to the Planner** to re-evaluate completion before advancing.

---

## 2. Shared State Schema & Multi-Agent State Definition

### State Schema Extensions (`backend/app/agent/state.py`):

```python
class PlanningAgentState(TypedDict, total=False):
    # Session & Tracing
    session_id: str
    client_message_id: str | None
    advertiser_id: str
    plan_version: int
    current_stage: str                  # Currently executing sub-agent
    stage_cursor: str | None            # Furthest validated milestone reached
    
    # Conversation & Elicitation Protocol
    messages: Annotated[list, add_messages]
    active_elicitations: list[dict]     # Unresolved interactive UI components
    resolved_elicitations: list[dict]   # Completed interactive UI history
    resolved_blocks: list[dict]
    awaiting: list[str]                 # Missing field descriptors
    
    # 1. Basic Details (Emad Agent)
    strategy_name: str | None
    markets: list[str]                  # e.g., ["GB", "US"]
    flight_start: str | None            # ISO YYYY-MM-DD
    flight_end: str | None              # ISO YYYY-MM-DD
    flight_dates: dict | None           # Normalized date range
    durations: list[str]                # ["10", "15", "20", "30"]
    primary_currency: str               # GBP, USD, EUR
    goal: str                           # "AWARENESS" (CTV standard)
    kpi: str                            # "reach"
    total_budget: float | None          # e.g., 50000.00
    
    # 2. CTV Inventory & Rate Card (Vishal Agent)
    inventory_type: str                 # "RATE_CARD" (M1 default) | "DEALS"
    preferred_providers: list[str]      # ["Prime Video", "Netflix", "Disney+"]
    matched_rate_cards: list[dict]      # Duration-matched rate card entries
    selected_deals: list[dict]
    inventory_tier: str                 # AMAZON_OWNED / THIRD_PARTY
    inventory_alternatives: list[str]
    
    # 3. Targeting & Budget Splitting (Kareem Agent)
    demographics: dict                  # {"age_groups": [...], "hhi": [...], "gender": [...]}
    geo_targets: list[dict]             # Targetable locations / regions
    budget_split: dict                  # {"Prime Video": 0.50, "Netflix": 0.50} or custom amounts
    audience_options: list[dict]        # NARROW / BALANCED / WIDE profiles
    chosen_audience: str | None
    forecast: dict | None               # Impressions, unique reach, average frequency
    
    # Validation & Auditing
    validation_errors: list[dict]
    validation_checks: list[dict]
    registry_provenance: str
    audited: bool
```

---

## 3. Specialized Sub-Agent Breakdown & Responsibilities

### 3.1 Planner / Orchestrator Agent (`planner_node` & `gates.py`)
- **Extraction & Normalization**: Dual-path (LLM + deterministic pattern fallback). Ingests user free text + structured elicitation responses.
- **State Evaluation**:
  - Checks missing basic fields: `markets`, `flight_dates`, `durations`, `total_budget`.
  - Checks if Rate Cards / Inventory need user selection or confirmation.
  - Checks if Demographic Targeting & Budget Splitting need configuration.
- **Decision Engine**:
  - If missing basic fields → calls **Emad Agent**.
  - If inventory unselected → calls **Vishal Agent**.
  - If targeting / budget split incomplete → calls **Kareem Agent**.
  - If user input required → prepares structured UI blocks (options, date picker, budget) and pauses turn.
  - If all data complete → advances to **Campaign Setup / Approval Gate**.

### 3.2 Emad Agent — Basic Details (`validate_basics.py` & `extract_fields.py`)
- **Focus**: Validates core campaign parameters against Grounded Registry.
- **Validation**:
  - `markets`: Checks against supported ISO country codes.
  - `flight_dates`: Checks against past dates and minimum flight durations.
  - `durations`: Restricts to supported creative lengths (10s, 15s, 20s, 30s).
  - `budget_amount` & `primary_currency`: Normalizes £/$/€ and shorthand (e.g. £50k → 50,000.00 GBP).
- **Output**: Writes verified parameters to Shared State and loops back to Planner.

### 3.3 Vishal Agent — CTV Inventory & Dynamic Rate Cards (`select_inventory.py`)
- **Domain Rule**: *Deals are disabled in M1 — use Rate Cards.*
- **Dynamic Duration Rate Card Matching**:
  - If user selects **10s** duration on **Prime Video** → fetch 10s Rate Card (cheaper CPM, e.g. 18.22).
  - If user selects **20s** duration on **Prime Video** → fetch 20s Rate Card (e.g. 25.00).
  - If user selects **Netflix** or **Disney+** → fetch provider-specific CTV rate cards.
- **Surface for Confirmation**: Emits table/chips block for trader confirmation.
- **Output**: Writes `matched_rate_cards` and `inventory_tier` to Shared State and loops back to Planner.

### 3.4 Kareem Agent — Targeting, Budget Splitting & R&F Forecasting (`collect_targeting.py` & `predict_reach.py`)
- **Demographic Targeting**:
  - Age groups (e.g., 18-34, 25-54), Household Income tiers (HHI), and Geographic regions.
- **Dynamic Budget Splitting**:
  - Proactively guides the trader on multi-channel allocation (e.g., 50/50 Prime Video / Netflix split, 70/30, or custom).
- **Reach & Frequency Calculations**:
  - Computes projected impressions: $\text{Impressions} = \frac{\text{Budget}}{\text{CPM}} \times 1000$.
  - Computes unique reach and frequency based on audience width and provider curve for Amazon-owned inventory.
  - Honest reporting for 3P inventory (impressions only, plain refusal for non-deduped 3P reach).
- **Output**: Writes targeting parameters, split allocation, and forecast metrics to Shared State and loops back to Planner.

### 3.5 Campaign Setup & Execution Agent (`deliver_plan.py`)
- **Consolidation**: Generates single comprehensive plan summary card.
- **Approval Gate**: Emits `interrupt()` for trader sign-off before any execution or API creation calls.
- **Suggestions**: Emits post-plan action chips (e.g., "Adjust budget", "Export plan", "Launch campaign").

---

## 4. API Contract & Interactive UI Component Mapping

Strict alignment with `backend/API CONTRACT/*.json` guarantees that the UI renders rich interactive widgets:

| JSON Contract | Interaction Mode | UI Component | Usage in Planner Flow |
|---|---|---|---|
| `Response_options.json` | `select: "multi"` | `OptionsBlockCard` (Checkboxes + Badges) | Market selection, duration selection, geo regions |
| `Response_options_single.json` | `select: "single"` | `OptionsBlockCard` (Radio cards) | Audience profile selection (Narrow/Balanced/Wide), rate card confirmation |
| `DateRangePicker` | `input_date_range` | `DateRangePickerCard` | Campaign flight start and end date selection |
| `CurrencyInput` | `input_money` | `CurrencyInputBlock` | Budget entry with currency symbol |
| `Response_suggestions.json` | `suggestions` | Suggestion Chips | Post-delivery quick-action shortcuts |

### Elicitation Protocol Envelope:
```json
{
  "session_id": "8230152f-c8fe-4999-afad-b9377d819759",
  "client_message_id": "3f8de983-25f4-4d5d-9194-7fe885637cc6",
  "stage": "basics",
  "reply": "Which creative duration would you like to use for Prime Video?",
  "message": {
    "id": "msg_1cc00d5d-8ae2-428b-a2fa-8431d9668579",
    "role": "assistant",
    "content": [
      { "type": "text", "text": "Which creative duration would you like to use for Prime Video?" },
      {
        "type": "options",
        "id": "elc_creative_length.ec6111f7",
        "prompt": "How long is the creative?",
        "select": "single",
        "allow_custom": true,
        "allow_skip": false,
        "status": "pending",
        "options": [
          { "id": "opt_10s", "label": "10 seconds", "description": "Rate Card: £18.22 CPM — highest impression volume", "badge": "Suggested" },
          { "id": "opt_20s", "label": "20 seconds", "description": "Rate Card: £25.00 CPM — balanced storytelling", "badge": null }
        ],
        "answer": null
      }
    ]
  },
  "resolved_elicitations": [],
  "resolved_blocks": [],
  "plan_version": 1
}
```

---

## 5. Phased Implementation Roadmap

### Phase 1: Planner/Orchestrator Core & Hub-and-Spoke Graph
- [ ] Refactor `graph.py` to establish the `planner_node` central hub.
- [ ] Implement loop-back conditional edges ensuring all sub-agent executions route back through Planner.
- [ ] Extend `state.py` with `client_message_id`, `plan_version`, `budget_split`, `demographics`, `matched_rate_cards`.

### Phase 2: Dynamic Rate Cards & CTV Inventory (Vishal Agent)
- [ ] Update `select_inventory.py` to prioritize Rate Cards over Deals for M1.
- [ ] Implement duration-specific rate card lookup (10s vs 20s vs 30s) and dynamic provider matching (Prime Video, Netflix, Disney+).

### Phase 3: Targeting, Budget Splitting & Reach Forecasting (Kareem Agent)
- [ ] Implement `collect_targeting.py` for demographic targeting (Age, HHI, Geos).
- [ ] Implement dynamic budget allocation helper (50/50 split and custom multi-channel splits).
- [ ] Integrate Reach & Frequency calculations based on selected duration rate card CPM and total budget.

### Phase 4: API Elicitation Contract & Frontend Integration
- [ ] Update `sessions.py` and `presentation.py` to output the full `message.content[]` elicitation envelope matching `backend/API CONTRACT/*.json`.
- [ ] Connect `http-agent-client.ts` in frontend to talk directly to `/api/v1/sessions/chat`.

### Phase 5: Verification & End-to-End Test Suite
- [ ] Unit tests for Planner routing and loop-back logic.
- [ ] Unit tests for Rate Card CPM matching across durations.
- [ ] Contract tests verifying JSON schema parity with `API CONTRACT/*.json`.
- [ ] End-to-end multi-turn conversation test simulating full M1 workflow.

---

## 6. Verification Plan

### Automated Test Commands:
```powershell
# Run all backend unit and agent tests
pytest backend/tests/ -v

# Run targeted orchestrator & rate card tests
pytest backend/tests/unit/agent/ -k "test_planner or test_rate_card or test_targeting" -v

# Run contract parity tests against API CONTRACT/*.json
pytest backend/tests/contract/ -v
```

### Manual Verification:
1. Start backend: `cd backend; uvicorn app.main:app --reload`
2. Test one-shot turn: `"Plan a UK CTV campaign with Prime Video 10s, budget £50,000, August 2026"` → Verify Planner extracts parameters, fetches 10s Rate Card, computes R&F, and surfaces plan.
3. Test multi-turn conversational probing: Send `"I want to plan a campaign"` → Verify Planner asks for market with interactive multi-select chips.
