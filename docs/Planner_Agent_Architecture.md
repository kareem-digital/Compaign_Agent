# Planner / Orchestrator Agent: Architecture & Execution Flow Documentation

## 1. Executive Summary & Workflow Alignment

The **Planner / Orchestrator Agent** is the central entry point and intelligence engine of the VOW Campaign Planning multi-agent system, designed in strict adherence to [`docs/Workflow.jpeg`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/docs/Workflow.jpeg) and [`M1_Planning.txt`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/M1_Planning.txt).

### Visual Architecture Flowchart

```mermaid
flowchart TD
    Start(["Customer Query / Inquiry"]) --> EntryPoint["1. PLANNER AGENT (Entry Point)<br/>• Understand query<br/>• Identify customer<br/>• Load customer state<br/>• Decide next step"]
    
    subgraph SharedStore ["SHARED STATE (Customer State Store)"]
        StateData[("• Customer Info<br/>• Basic Details: Market, Goal, Budget, Dates<br/>• CTV Inventory & Rate Cards<br/>• Demographics & Budget Split<br/>• Audiences & Forecast")]
    end

    EntryPoint <--> StateData

    EntryPoint --> CheckBasics{"Basic details<br/>complete?"}
    
    CheckBasics -- "No" --> Emad["2. EMAD AGENT (Basic Details Agent)<br/>• Collect basic customer info<br/>(market, goal, budget, duration)"]
    Emad --> UpdateBasics["Update State (Basic Details)"]
    UpdateBasics -.->|Always returns to Planner| EntryPoint
    
    CheckBasics -- "Yes" --> CheckInventory{"CTV inventory<br/>required?"}
    
    CheckInventory -- "Yes" --> Vishal["3. VISHAL AGENT (CTV Inventory Agent)<br/>• Duration Rate Cards (10s, 15s, 20s, 30s)<br/>• Prime Video, Netflix, Disney+"]
    Vishal --> UpdateInventory["Update State (CTV Inventory)"]
    UpdateInventory -.->|Always returns to Planner| EntryPoint
    
    CheckInventory -- "No" --> CheckTargeting{"Targeting<br/>needed?"}
    UpdateInventory --> CheckTargeting
    
    CheckTargeting -- "Yes" --> Kareem["4. KAREEM AGENT (Targeting Agent)<br/>• Demographics (Age, HHI)<br/>• Multi-channel budget split (e.g. 50/50)"]
    Kareem --> UpdateTargeting["Update State (Targeting)"]
    UpdateTargeting -.->|Always returns to Planner| EntryPoint
    
    CheckTargeting -- "No / Skip" --> CheckComplete{"All required<br/>information complete?"}
    UpdateTargeting --> CheckComplete
    
    CheckComplete -- "No" --> LoopDecision["Planner decides:<br/>• What is missing?<br/>• Which agent?<br/>• Ask more questions<br/>• Loop back"]
    LoopDecision -.-> EntryPoint
    
    CheckComplete -- "Yes" --> Execution["5. CAMPAIGN SETUP / EXECUTION AGENT<br/>• Create campaign<br/>• Call platform APIs (Amazon, Netflix, etc.)<br/>• Launch campaign"]
    Execution --> UpdateCampaign["Update State (Campaign Created)"]
    UpdateCampaign --> Monitoring["6. MONITORING AGENT<br/>• Monitor performance<br/>• Optimize<br/>• Report"]
    
    Monitoring --> NeedChanges{"Need<br/>changes?"}
    NeedChanges -- "Yes" -.->|Loop back on changes| EntryPoint
    NeedChanges -- "No" --> Finished(["END: Campaign Running Successfully"])
```

### Text Flowchart (Preview Backup)

```
[ START: Customer Query / Inquiry ]
                 │
                 ▼
 ┌─────────────────────────────────────────────────────────────┐
 │               1. PLANNER AGENT (Entry Point)                │
 │  • Understand query            • Identify customer          │
 │  • Load customer state         • Decide next step           │
 └──────────────────────────────┬──────────────────────────────┘
                                │
        ◄───────────────────────┴───────────────────────►
       ▲                                                 │
       │ Reads/Writes to:                                │
       │ [ SHARED STATE: Customer Info, Market, Dates,   │
       │   Durations, Budget, Rate Cards, Targeting ]    │
       │                                                 │
       │ (Loop back after every step)                    │
       │                                                 │
       ├── [Basic details complete?] ──(No)──► [2. EMAD AGENT (Basics)] ──► (Update State) ──┘
       │          │ (Yes)
       │          ▼
       ├── [CTV inventory required?] ──(Yes)─► [3. VISHAL AGENT (CTV)] ──► (Update State) ───┘
       │          │ (No / Done)
       │          ▼
       ├── [Targeting needed?] ────────(Yes)─► [4. KAREEM AGENT (Target)] ─► (Update State) ──┘
       │          │ (No / Skip)
       │          ▼
       ├── [All info complete?] ───────(No)──► [Planner Decision Loop] ──────────────────────┘
       │          │ (Yes)
       │          ▼
       └──► [5. CAMPAIGN SETUP / EXECUTION AGENT] ──► (Create & Launch)
                  │
                  ▼
            [6. MONITORING AGENT] ──(Need changes?)──► (Loop back to Planner)
                  │ (No)
                  ▼
            [ END: Campaign Running Successfully ]
```

---

## 2. 1:1 Mapping to `docs/Workflow.jpeg`

| Diagram Element (`Workflow.jpeg`) | Role in Architecture | Code Implementation |
|---|---|---|
| **START: Customer Query / Inquiry** | User message arrives via UI chat interface | `POST /api/v1/sessions/chat` in [`backend/app/api/sessions.py`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/app/api/sessions.py) |
| **1. PLANNER AGENT (Entry Point)**<br/>• Understand query<br/>• Identify customer<br/>• Load customer state<br/>• Decide next step | Evaluates query, authenticates tenant, loads thread state from checkpointer, determines dispatch | [`planner_node`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/app/agent/nodes/planner.py), [`evaluate_state_and_plan`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/app/agent/nodes/planner.py), and [`route_planner`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/app/agent/gates.py) |
| **SHARED STATE (Customer State Store)** | Single source of truth containing customer info, basics, market, goal, budget, durations, CTV inventory, targeting | `PlanningAgentState` TypedDict in [`backend/app/agent/state.py`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/app/agent/state.py) backed by checkpointer (`MemorySaver` / `AsyncPostgresSaver`) |
| **Decision: Basic details complete?** | Checks presence and validity of market, dates, duration, budget | `missing_basics(state)` and `blocking(state)` in [`backend/app/agent/gates.py`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/app/agent/gates.py) |
| **2. EMAD AGENT (Basic Details Agent)**<br/>• Collect basic customer info<br/>• Update State (Basic Details) | Extracts fields, validates against market snapshot, requests missing inputs | [`extract_fields.py`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/app/agent/nodes/extract_fields.py), [`validate_basics.py`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/app/agent/nodes/validate_basics.py), [`ask_for_missing.py`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/app/agent/nodes/ask_for_missing.py) |
| **Decision: CTV inventory required?** | Determines whether rate cards and CTV deals need to be matched | `evaluate_state_and_plan` checks `selected_deals` and `matched_rate_cards` |
| **3. VISHAL AGENT (CTV Inventory Agent)**<br/>• Platforms, Budget, Duration, Locations<br/>• Update State (CTV Inventory) | Queries registry for duration-matched rate cards (10s, 15s, 20s, 30s) across Prime Video, Netflix, Disney+ | [`select_inventory.py`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/app/agent/nodes/select_inventory.py) |
| **Decision: Targeting needed?** | Evaluates if demographic or geo targeting needs refinement | `evaluate_state_and_plan` checks `targeting_confirmed` |
| **4. KAREEM AGENT (Targeting Agent)**<br/>• Audience, Demographics, Interests, Locations<br/>• Update State (Targeting) | Refines demographic tiers (Age, HHI), applies baseline market geos, and computes multi-channel budget splits (e.g. 50/50) | [`collect_targeting.py`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/app/agent/nodes/collect_targeting.py) |
| **Decision: All required information complete?** | Verifies all basics, inventory, targeting, audiences, and forecast are computed | `evaluate_state_and_plan` returning `is_complete=True` |
| **Planner Decision Box**<br/>• What is missing?<br/>• Which agent?<br/>• Ask more questions<br/>• Loop back | Formulates exact interactive questions / elicitation envelopes and loops back | `evaluate_state_and_plan` emitting `missing_fields`, `conflicts`, and `next_agent` |
| **5. CAMPAIGN SETUP / EXECUTION AGENT**<br/>• Create campaign<br/>• Call platform APIs<br/>• Launch campaign | Formats complete plan ready for customer approval and platform API execution | [`deliver_plan.py`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/app/agent/nodes/deliver_plan.py) |
| **6. MONITORING AGENT**<br/>• Monitor performance, Optimize, Report<br/>• Loop back on changes | Inspects performance signals and loops back to Planner if budget, creative, or targeting adjustments are requested | Monitored state triggers loopback to `planner_node` |

---

## 3. Key Tenets Implemented in Codebase

1. **Planner is the Central Orchestrator**:
   - The Planner is evaluated on every customer turn (`START -> extract_fields -> planner`).
   - Rather than hardcoding static flows, the Planner checks the shared state and dispatches the exact specialized sub-agent needed.
2. **Loop-Back Control**:
   - All sub-agents (`validate_basics`, `select_inventory`, `collect_targeting`, `suggest_audiences`, `predict_reach`) read from and write to `PlanningAgentState`.
   - Control returns to the Planner to verify completeness.
3. **Zero Hallucination & Grounding**:
   - Every input is validated against the registry snapshot (`StepwiseCTVValidator` / `AdvertiserRegistry`).
   - Unsold markets (`CN`), past flight dates, or uncarried creative durations trigger validation errors that halt execution and prompt the trader for correction.
4. **Interactive Elicitation Protocol**:
   - Matches the API contract (`API CONTRACT/*.json`): emits single-select or multi-select option buttons, manages `plan_version`, and records `resolved_elicitations`.

---

## 4. Test Verification Matrix

- **Total Backend Tests**: **535 / 535 PASSED** (100% pass rate)
- Dedicated Planner tests in [`tests/unit/agent/test_planner_agent.py`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/tests/unit/agent/test_planner_agent.py): **22 / 22 PASSED**
- Router & Gate dispatch tests in [`tests/unit/agent/test_gates.py`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/tests/unit/agent/test_gates.py): **42 / 42 PASSED**
- Integration Golden Journey tests in [`tests/integration/test_golden_journeys.py`](file:///c:/Users/nedah/OneDrive/Desktop/VOW%20Agent/backend/tests/integration/test_golden_journeys.py): **3 / 3 PASSED**
