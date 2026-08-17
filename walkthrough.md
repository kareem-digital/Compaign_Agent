# Planner / Orchestrator Agent Architecture & Implementation Walkthrough

We have implemented the central **Planner / Orchestrator Agent** according to `docs/Workflow.jpeg`, `M1_Planning.txt`, and the approved `implementation_plan.md`.

---

## Key Achievements

### 1. Central Planner / Orchestrator Node (`backend/app/agent/nodes/planner.py`)
- Acts as the central evaluation engine and controller for the multi-agent graph.
- Evaluates the shared `PlanningAgentState` across:
  - **Basics**: Markets, flight dates, durations, budget, currency, goal.
  - **Validation Blockers**: Severity errors from `validate_basics` (e.g. unsold market `CN`, past flight dates).
  - **Inventory & Rate Cards**: Selected deals / rate cards, dominant tier.
  - **Targeting**: Demographics, geo locations, dynamic budget splits.
  - **Audiences**: Suggested audience options and trader selection.
  - **Forecast & Delivery**: Reach and frequency forecast calculations.
- Determines the `next_agent` (`"emad_basics"`, `"vishal_inventory"`, `"kareem_targeting"`, `"audience_agent"`, `"forecast_agent"`, `"delivery_agent"`) and reasons for execution.

### 2. State Schema & Elicitation Protocol (`backend/app/agent/state.py` & `backend/app/api/sessions.py`)
- Added fields for interactive elicitation cycles matching the API contract (`API CONTRACT/*.json`):
  - `client_message_id`: Message deduplication.
  - `plan_version`: Monotonically increasing revision counter.
  - `active_elicitations` & `resolved_elicitations`: Structured multi-select / single-select interactive UI questions.
  - `resolved_blocks`: Block resolutions.
  - `inventory_type`: Fixed to `"RATE_CARD"` for M1.
  - `matched_rate_cards`: Duration-matched rate cards (10s, 15s, 20s, 30s) per provider.
  - `demographics` & `budget_split`: Age, HHI, and multi-channel budget allocations.

### 3. Dynamic Rate Card & CTV Inventory (`backend/app/agent/nodes/select_inventory.py`)
- Integrated duration-aware rate card lookups.
- Matches creative durations against rate cards from the snapshot (e.g. Prime Video 10s vs 20s vs 30s, Netflix, Disney+).
- Emits `inventory_type="RATE_CARD"` and populated `matched_rate_cards`.

### 4. Demographic & Budget-Split Targeting (`backend/app/agent/nodes/collect_targeting.py`)
- Grounds baseline demographic segments (age tiers, household income).
- Supports dynamic multi-channel budget splitting (e.g., 50/50 split across Prime Video and Netflix, or custom allocations).

### 5. API Response Contracts (`backend/app/api/sessions.py` & `presentation.py`)
- Emits `WireMessage` with `options` elicitation envelopes for unresolved fields.
- Default preselection reflects Amazon-owned inventory while enabling 3P CTV selection.

---

## Verification & Test Results

The entire backend test suite was executed:
- **Total Tests Passed**: **513 / 513**
- **Test Categories**:
  - `tests/unit/agent/`: Gates, brief parsing, flight dates, ask rendering, voice layer.
  - `tests/component/agent/`: Planning graph execution across all multi-turn scenarios.
  - `tests/integration/`: Golden Journey multi-turn dialogues (Cases A, B, C).
  - `tests/api/`: Session chat endpoints, health, presentation, validation details.
  - `tests/security/`: OIDC bearer token authentication, MCP token exchange.
  - `tests/contract/`: Registry contracts, targeting configuration schemas.
  - `tests/unit/governance/`: Policy enforcement, audit logging, kill switches.
