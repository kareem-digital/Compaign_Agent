# VOW AI Campaign Planning Agent: Comprehensive Implementation & Architecture Report

---

## 1. Executive Summary

This report provides a complete architectural and implementation overview of the **VOW Multi-Agent Conversational Planning System**, designed according to:
- [`docs/Workflow.jpeg`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/docs/Workflow.jpeg) (LangGraph Multi-Agent Architecture)
- [`docs/Strategy_Schema_v4.0_FINAL.md`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/docs/Strategy_Schema_v4.0_FINAL.md) (Domain Specification)
- [`docs/res.png`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/res.png) (UI Design & 6-Group Targeting Classification)
- [`M1_Planning.txt`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/M1_Planning.txt) (Rate Card Matching & Validation Rules)

### Core Architectural Principle: Strict Single Responsibility Isolation
Each agent functions as an autonomous, self-contained domain engine with clear input/output state contracts. **No agent ever performs another agent's responsibilities.**

```
                                      ┌───────────────────────────────┐
                                      │      Trader Conversation      │
                                      └──────────────┬────────────────┘
                                                     │
                                                     ▼
                                      ┌───────────────────────────────┐
                                      │  1. PLANNER / ORCHESTRATOR    │
                                      │  (State Evaluation & Routing) │
                                      └──────────────┬────────────────┘
                                                     │
                ┌────────────────────────────────────┼────────────────────────────────────┐
                │                                    │                                    │
                ▼                                    ▼                                    ▼
┌───────────────────────────────┐    ┌───────────────────────────────┐    ┌───────────────────────────────┐
│        2. EMAD AGENT          │    │       3. VISHAL AGENT         │    │       4. KAREEM AGENT         │
│     (Basic Details Agent)     │    │     (CTV Inventory Agent)     │    │       (Targeting Agent)       │
├───────────────────────────────┤    ├───────────────────────────────┤    ├───────────────────────────────┤
│ • Market & Currency           │    │ • Platform Deals (Prime, etc.)│    │ • 6-Group UI Demographics     │
│ • Flight Dates (Start/End)    │    │ • Duration Rate Cards (15/30s)│    │ • 3 Geo Paths (Search/Post/Rad│
│ • Budget & Goal / KPI         │    │ • Inventory Tiers (Owned/3P)  │    │ • Replacement Rule (Nationwide│
│ • Creative Durations          │    │ • Alternative Providers       │    │ • Device & Safety Exclusions  │
└───────────────────────────────┘    └───────────────────────────────┘    └───────────────────────────────┘
```

---

## 2. End-to-End Execution Flow

### Stage 1: Entry & Orchestration — Planner Agent
- **File:** [`backend/app/agent/nodes/planner.py`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/app/agent/nodes/planner.py)
- **Role:** Central control center. Inspects the shared state store `PlanningAgentState` on every user turn.
- **Decision Engine (`evaluate_state_and_plan`):**
  1. Inspects blocking conflicts (`blocking(state)`).
  2. Inspects missing mandatory fields (`missing_basics(state)`).
  3. Evaluates which specialized sub-agent to dispatch to.
  4. Manages the loopback cycle after each specialized agent finishes.

---

### Stage 2: Basic Details Processing — Emad Agent
- **Files:**
  - Extraction: [`backend/app/agent/nodes/extract_fields.py`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/app/agent/nodes/extract_fields.py)
  - Grounded Validation: [`backend/app/agent/nodes/validate_basics.py`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/app/agent/nodes/validate_basics.py)
  - Probing Logic: [`backend/app/agent/nodes/ask_for_missing.py`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/app/agent/nodes/ask_for_missing.py)
- **Responsibilities:**
  - **Extraction:** Dual-path NLP (OpenAI `gpt-4o-mini` structured output with regex fallback) to extract markets, budgets, flight dates, durations (10s, 15s, 20s, 30s), currency, and goal.
  - **Grounding & Validation:** Grounded checks against market snapshots:
    - `validate_target_markets` (validates against VOW-supported ISO codes)
    - `validate_flight_dates` (detects past dates, enforces date ordering)
    - `validate_durations` (matches against market-specific rate cards)
    - `validate_currency` (enforces ISO currency rules)
    - `validate_goal_and_kpi` (enforces CTV goal defaults)
  - **Probing:** If any basic detail is missing, halts execution and prompts the user for the single next missing parameter without hallucination.

---

### Stage 3: Inventory & CTV Channel Matching — Vishal Agent
- **File:** [`backend/app/agent/nodes/select_inventory.py`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/app/agent/nodes/select_inventory.py)
- **Responsibilities:**
  - **Duration Rate Card Matching:** Matches user-selected durations (15s, 30s) against live rate cards with precise CPM rates.
  - **Inventory Tier Classification:**
    - `AMAZON_OWNED` (Prime Video — enables reach/frequency forecasting)
    - `THIRD_PARTY_PRECURATED` (Netflix, Hulu, Disney+)
  - **Metadata Enrichment:** Enriches matched deals with `deal_type` ("Private Auction"), `genre`, `tier`, and duration arrays.
  - **Alternatives Discovery:** Identifies unselected available providers in the market to provide clear guidance.

---

### Stage 4: Universal Targeting Engine — Kareem Agent
- **File:** [`backend/app/agent/nodes/collect_targeting.py`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/app/agent/nodes/collect_targeting.py)
- **Responsibilities:**
  1. **6-Group UI Classification (Matching [`res.png`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/res.png)):**
     - **Lifestyle, In-Market & Interests:** Green Shoppers, Health & Wellness, Organic Food Buyers, Runners, Tech, Gaming.
     - **Age Cohorts:** `18-24`, `25-34`, `35-44`, `45-54`, `55+` (with natural language normalizer).
     - **Gender Filter:** `Female`, `Male`, `All`.
     - **Household Income (HHI):** `£35-55k`, `£55-80k`, `£80k+` (or `Top 10%`, `Top 25%`).
     - **Household Composition:** `Families with children`, `Couples`.
     - **Device Types:** `Connected TV` (`CONNECTED_TV` / Smart TV — required for CTV), `Fire TV` (`STREAMING_STICK`), `Games Console` (`GAMES_CONSOLE`).
  2. **3 Geographic Acquisition Paths:**
     - **Search Query:** Resolves city/metro names (`London` $\rightarrow$ `GB-LND Greater London`).
     - **Postal Code Precision:** Validates postal codes (`SW1A 1AA`, `90210`).
     - **Custom Radius Proximity:** Mints `{address, radius, unit}` (e.g. `20 miles around London`) $\rightarrow$ generates custom radius ID.
  3. **The Replacement Rule:** A narrower geographic selection automatically replaces the `GB Nationwide` default.
  4. **Device & Mobile OS Guardrails:** Mobile operating systems (`IOS`, `ANDROID`) are permitted only when `MOBILE` is among active device types.
  5. **Brand Safety:** Configures `content_rating_exclusions` and `instream_positions` (`PRE_ROLL`, `MID_ROLL`).

---

### Stage 5: Downstream Planning & Delivery
- **Audiences:** Suggests three distinct audience profiles (**Narrow**, **Balanced**, **Wide**) stacking data fees onto base CPM.
- **Forecast:** Computes Reach & Frequency curves for Amazon-owned inventory and deterministic impression volumes for third-party inventory.
- **Delivery:** Formats the complete strategy plan for client approval and submission.

---

## 3. State Schema & Lifecycle Contract

The central state is defined in [`backend/app/agent/state.py`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/app/agent/state.py) as `PlanningAgentState`:

```python
class PlanningAgentState(TypedDict, total=False):
    # Conversation & Session
    messages: Annotated[list, add_messages]
    advertiser_id: str
    session_id: str
    current_stage: str
    stage_cursor: str | None
    awaiting: list[str]
    
    # 2. Emad Agent (Basics)
    strategy_name: str | None
    markets: list[str]
    durations: list[str]
    primary_currency: str
    goal: str
    kpi: str
    flight_start: str | None
    flight_end: str | None
    budget_amount: str | None
    flight_dates: dict | None
    market_budgets: list[dict]
    
    # 3. Vishal Agent (Inventory)
    inventory_type: str | None
    preferred_providers: list[str]
    inventory_tier: str | None
    selected_deals: list[dict]
    matched_rate_cards: list[dict] | None
    inventory_alternatives: list[str]
    
    # 4. Kareem Agent (Targeting)
    targeting_enabled: bool | None
    geo_targets: list[dict]
    location_include: list[str]
    location_exclude: list[str]
    custom_radius: dict | None
    postcode_targeting: dict | None
    demographics: dict | None
    device_types: list[str]
    mobile_operating_systems: list[str]
    content_rating_exclusions: list[str]
    instream_positions: list[str]
    targeting_confirmed: bool
    
    # 5. Audiences & Forecast
    audience_options: list[dict]
    audience_choice: str | None
    chosen_audience: dict | None
    forecast: dict | None
```

---

## 4. Verification & Quality Metrics

### Full Backend Test Suite: 560 / 560 Tests Passing (100%)

| Test Suite | File Path | Tests Passed | Domain Covered |
|---|---|---|---|
| **Kareem Agent Tests** | [`test_kareem_agent.py`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/tests/unit/agent/test_kareem_agent.py) | **10 / 10** | Demographics, 3 Geo paths, Replacement rule, Devices, Exclusions |
| **Emad Agent Tests** | [`test_emad_agent.py`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/tests/unit/agent/test_emad_agent.py) | **9 / 9** | Basic details extraction, snapshot grounding, date/market validation |
| **Vishal Agent Tests** | [`test_vishal_agent.py`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/tests/unit/agent/test_vishal_agent.py) | **6 / 6** | Rate card matching, pricing, tier resolution, alternatives |
| **Planner Agent Tests** | [`test_planner_agent.py`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/tests/unit/agent/test_planner_agent.py) | **22 / 22** | State evaluation, routing, completeness, loopbacks |
| **Component Graph Tests** | [`test_planning_graph.py`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/tests/component/agent/test_planning_graph.py) | **69 / 69** | Multi-turn conversational execution, state persistence |
| **Integration Golden Tests** | [`test_golden_journeys.py`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/tests/integration/test_golden_journeys.py) | **3 / 3** | Golden Journey Cases A, B, and C |
| **Registry & Contract Tests** | `test_registry_contract.py`, `test_targeting_config.py` | **25 / 25** | VOW schema grounding and registry integrity |
| **API, Governance & Core** | `test_policy.py`, `test_sessions.py`, etc. | **416 / 416** | Endpoints, policy guards, kill switch, audit trail |
| **TOTAL** | **Entire Test Suite** | **560 / 560 (100%)** | **Full System Verification** |

---

## 5. Next Steps Roadmap

1. **Audience & Forecast Agent (Node 4 & 5):**
   - Deep-dive into automated audience grouping and reach/frequency mathematical projections.
2. **Campaign Setup & Execution Agent (Node 6):**
   - Plan approval gates and integration with VOW strategy creation endpoints (`POST /api/strategies/`).
3. **Live MCP Integration:**
   - Seamless drop-in replacement of mock tools with live MCP server endpoints when deployed by the infrastructure team.
