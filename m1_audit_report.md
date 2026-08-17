# M1 Audit Report — VOW Agent
## Complete Code-Level Audit Against M1_Strategy_Plan.md

---

## CURRENT FLOW — What Already Works ✅

### 1. Basic Details Collection (Emad Agent / `extract_fields`)
- ✅ Market detection (GB, US, FR, DE, CN) via regex + LLM fallback
- ✅ Flight start/end dates (raw slots: `flight_start`, `flight_end` → derived `flight_dates`)
- ✅ Creative durations (registry-grounded: only 10/15/20/30s accepted)
- ✅ Budget parsing (£/$/€ + `50k`, `budget of...` patterns)
- ✅ Preferred providers extracted (Prime Video, Netflix, Disney+, Hulu)
- ✅ Audience profile extraction (NARROW / BALANCED / WIDE from text)
- ✅ Accumulation semantics — never overwrites known fields, only fills gaps
- ✅ Currency derived from market (GBP→GB, USD→US, EUR→FR/DE)
- ✅ Goal/KPI defaulted to Awareness/Reach for CTV (not locked — can be overridden)
- ✅ Strategy name auto-generated
- ✅ `_confirmation` message tells trader what was understood this turn

### 2. Basic Validation (Vishal Agent / `validate_basics`)
- ✅ Flight dates validated against VOW rate card (past dates blocked)
- ✅ Durations grounded against registry — unsupported values rejected with real options
- ✅ Budget minimum check
- ✅ Market validated against what VOW carries
- ✅ Warning on non-GBP billing
- ✅ Validation outcomes replace per stage (never accumulate stale errors)

### 3. CTV Inventory Selection (Vishal Agent / `select_inventory`)
- ✅ Registry-grounded deal lookup (by market + durations)
- ✅ Preferred provider filtering (named provider → confirms; unnamed → shows options)
- ✅ Dead-end messages (no inventory in market, unsupported duration)
- ✅ Alternative markets/durations suggested when dead end
- ✅ `inventory_alternatives` tracked for "no visible way out" prevention
- ✅ `selected_deals` carries deal_id, provider, CPM, tier, ad_lengths
- ✅ Tier classification: AMAZON_OWNED / THIRD_PARTY_PRECURATED / THIRD_PARTY_NEEDS_CURATION
- ✅ Dominant tier computed and stored in `inventory_tier`

### 4. Targeting Collection (Kareem Agent / `collect_targeting`)
- ✅ All 6 targeting groups from res.png: Lifestyle/Interest, Age, Gender, HHI, Household, Device
- ✅ Geographic parsing: city metros, postcodes, custom radius
- ✅ Replacement Rule: specific location replaces broad market default (not "GB + London")
- ✅ Device types: CONNECTED_TV required, STREAMING_STICK, GAMES_CONSOLE, DESKTOP, MOBILE
- ✅ Mobile OS guardrail: IOS/ANDROID only valid when MOBILE in device_types
- ✅ Brand safety exclusions: NEWS_POLITICS, SENSITIVE, VIOLENCE, GAMBLING
- ✅ Instream positions: PRE_ROLL / MID_ROLL (configurable)
- ✅ Default fallback: market nationwide when no location given
- ✅ `targeting_confirmed = True` written on completion

### 5. Audience Suggestion (Vishal Agent / `suggest_audiences`)
- ✅ Always three options: NARROW / BALANCED / WIDE
- ✅ Effective CPM calculation per option (deal CPM + vcpm_fee)
- ✅ Amazon audience applicability note for third-party inventory
- ✅ Real wait-for-user step: `awaiting = [NO_AUDIENCE_CHOICE]`
- ✅ `say()` suppression prevents repeated options block on follow-up messages
- ✅ `_RE_ASK` short form on second ask

### 6. Reach Forecast (Vishal Agent / `predict_reach`)
- ✅ MCP `REACH_FORECAST` tool call (real or mock)
- ✅ Amazon reach: unique reach, impressions, frequency, CPM
- ✅ Third-party: impressions only, reach = unavailable (honesty rule)
- ✅ `is_available` flag separates the two cases
- ✅ MIN_VIABLE_REACH threshold defined (100k) — repair loop seam marked

### 7. Plan Delivery (`deliver_plan`)
- ✅ Consolidated plan summary (market, flight, durations, budget, inventory, audience, forecast)
- ✅ "Say the word to create strategy or tell me what to change"
- ✅ STANDING_BY repeat suppression
- ✅ Outstanding validation warnings repeated in plan summary
- ✅ `current_stage = "delivered"`

### 8. Orchestration / Flow
- ✅ Planner node evaluates state and decides next agent
- ✅ Gated routing: each stage checks its gate before proceeding
- ✅ `gates.say()` prevents stage repetition on every turn
- ✅ `awaiting` tracks what's outstanding; `blocking` tracks what failed validation
- ✅ `stage_cursor` moves forward only, rewinds when upstream changes
- ✅ One question per turn via `ask_for_missing`

### 9. API / Wire Format
- ✅ `ChatResponse` → `message.content[]` with text + options blocks
- ✅ `plan_state` dict feeds the StrategyPanel sidebar
- ✅ `validation` field exposes grounding detail
- ✅ `resolved_elicitations` returned for UI state cleanup
- ✅ `build_blocks()` correctly dispatches by stage (inventory/audiences/forecast/delivered)
- ✅ Wire options format matches `OptionsBlock` in `wire.ts`

---

## PARTIALLY WORKING ⚠️

### 1. Targeting — Conversational Gate (CRITICAL GAP)
**Problem**: Kareem Agent currently always runs automatically. It parses the full conversation text and applies targeting, then immediately sets `targeting_confirmed = True` — even when the user said nothing about targeting.

**M1 Requirement** (Section 15):
> "Your core campaign details are complete. Would you like to keep the default targeting or refine the audience/location?"
> Options: [Keep default] [Add audience targeting] [Refine location] [Both]

**Current behavior**: User never gets a choice. Targeting runs silently in the background.

**Fix needed**: Add a `targeting_confirmed` gate check. If the user hasn't explicitly signaled targeting intent, present the targeting decision prompt first. Only parse demographics/geo if user chooses to refine.

### 2. Budget Split for Multiple Inventory
**Problem**: When multiple deals are selected, `_build_plan_state()` and `deliver_plan` show only `market_budgets[0]`. No budget split UI is triggered.

**M1 Requirement** (Section 14):
> "If multiple inventories → Show budget split."
> Prime Video — £10,000 / Sky — £5,000 / Total — £15,000

**Missing**: 
- Budget split state field (`budget_splits: list[dict]`)
- Budget split validation (sum must equal total)
- Budget split UI block (editable allocation table type)

### 3. Targeting — "Keep broad" handling
**Problem**: If user says "keep it broad", the regex parser in `collect_targeting._parse_demographics()` still assigns defaults (ages: `["25-54", "All Adults"]`, income: `["£55-80k", "£80k+"]`). These are not "broad" — they're specific targeting values incorrectly applied.

**M1 Requirement** (Section 15):
> "If user says 'Keep it broad.'" → "Sounds good. I'll keep the default targeting and move on."
> Do NOT continue asking age? gender? interest?

**Fix**: Detect "keep broad/default" intent and skip all demographic parsing. Set targeting to market-baseline only.

### 4. Targeting — UI structured response
**Problem**: `collect_targeting` currently uses `say()` to output a plain text message, not a structured block. The presentation layer (`build_blocks`) has no targeting stage handler — `_STAGE_BLOCKS` only contains `inventory`, `audiences`, `forecast`, and `delivered`.

**Result**: The targeting stage produces a text message but no structured options block (no "Keep default / Refine location / Both" chips). The frontend renders raw text, not interactive components.

### 5. `planner_node` is registered but bypassed
**Problem**: `graph.py` does NOT route through `planner_node`. The graph goes:
`START → extract_fields → validate_basics → select_inventory → collect_targeting → suggest_audiences → predict_reach → deliver_plan`

The `planner_node` is added to the graph but no edges actually route through it. It logs a decision but has no effect on execution. The `route_planner` function in `gates.py` exists but is never used as a conditional edge.

**This is not a bug** — the gated flow achieves the same result. But the planner node is dead code right now.

### 6. Sidebar `plan_state` — Targeting fields missing
**Problem**: `_build_plan_state()` in `sessions.py` (line 541-545) only exposes `targeting = geo_targets names`. It doesn't include:
- Demographics (age, gender, interests, HHI, household type)
- Device types
- Custom radius or postcodes
- Brand safety exclusions

The Strategy Sidebar shows only geo targeting in the Targeting section.

---

## BROKEN ❌

### 1. Graph topology: `planner` node has no incoming/outgoing real edges
The `add_node("planner", planner_node)` at line 122 of `graph.py` adds the node, but there are no `add_edge` or `add_conditional_edges` calls that route any turn through `planner`. The node is registered but completely unreachable. The `route_planner` function in `gates.py` is also unreachable.

### 2. `deliver_plan` hardcodes "Goal: Awareness, measured on reach (fixed for CTV)"
Line 126 of `deliver_plan.py`: `"- Goal: Awareness, measured on reach (fixed for CTV)"` — this is hardcoded even when the user has changed the goal. M1 plan says goal is not locked. The `state.get("goal")` field exists but isn't used here.

### 3. No reach repair loop
`predict_reach.py` defines `MIN_VIABLE_REACH = 100_000` and the docstring says "repair loop attaches here — not built yet; seam is marked". The graph has no edge from `predict_reach` back to `suggest_audiences`. M1 sections 22 and 23 require this.

---

## MISSING ❌

### 1. Targeting Decision Gate (HIGHEST PRIORITY)
No structured interaction for the targeting entry question:
- "Would you like to keep default targeting or refine?"
- `presentation.py` has no `targeting_block()` builder
- `_STAGE_BLOCKS` has no `"targeting"` key
- `route_after_targeting` in `gates.py` handles `NO_TARGETING_DECISION` but nothing ever sets `awaiting = [NO_TARGETING_DECISION]`

### 2. Budget Split Feature
- No `budget_splits` state field
- No budget split validation (sum ≠ total budget → block)
- No editable allocation table interaction type in `presentation.py`
- No budget split in `plan_state` or sidebar

### 3. Reach Repair Loop
- No graph edge: `predict_reach → suggest_audiences` when reach < MIN_VIABLE_REACH
- No user-facing repair options: [Broaden audience] [Increase budget] [Change inventory]
- No structured repair block in `presentation.py`

### 4. Plan Finalise Step
- No `plan_ready.py` node creates a strategy or transitions to FINALISED state
- The node file exists (`plan_ready.py`) but checking its contents:

### 5. Targeting Interaction Types Missing from `presentation.py`
The following interaction types referenced in M1_Strategy_Plan.md are not in `Interaction` enum or `build_blocks`:
- `INPUT_TEXT_SEARCH` (location search)
- `INPUT_POSTCODE` (multi postcode entry)  
- `INPUT_RADIUS` (address + radius + unit)
- `EDITABLE_TABLE` (budget split)
- `CONFIRM_WITH_ACTIONS` (targeting decision: keep/refine/both)

### 6. Goal/KPI Not Asked
M1 says goal defaults to Awareness but is not locked, and KPI is a separate field. Currently:
- `goal` and `kpi` are set in `extract_fields` as defaults but never offered as interactive choices
- No goal/KPI block in `presentation.py`
- No goal validation against registry (M1 sec 9: "retrieve/validate from actual platform")

---

## DUPLICATED ⚠️

### 1. Planner logic is duplicated
`planner.py::evaluate_state_and_plan()` implements the same routing logic as `gates.route_after_basics`, `route_after_validation`, `route_after_inventory`, `route_after_targeting`, `route_after_audiences`. Both exist, both are correct, but only the gates functions actually run (planner is dead code).

---

## NOT NEEDED (Can be deferred)

1. `plan_ready.py` — creates strategy in VOW (M2 scope, correctly deferred)
2. Curation requirements capture for Disney+ (marked in `select_inventory.py` docstring)
3. Tier fork for `THIRD_PARTY_NEEDS_CURATION` (marked in `graph.py` docstring)
4. Reach curve visualization (requires `reach_curve` data from forecast)

---

## NEXT TO IMPLEMENT (Prioritized)

### Priority 1 — Targeting Decision Gate (Blocks correct flow)
**What**: Present a choice: "Keep default targeting / Add audience targeting / Refine location / Both"
**Files**: `presentation.py`, `collect_targeting.py`, `gates.py`
**Approach**:
1. Add `targeting_decision_requested` to state
2. Add `"targeting"` to `_STAGE_BLOCKS` in `presentation.py` 
3. `collect_targeting` checks: if no user targeting intent → set `awaiting = [NO_TARGETING_DECISION]` and emit a structured options block
4. If user says "keep broad/default" → `targeting_confirmed = True`, skip all parsing
5. If user chooses to refine → proceed with current parsing logic

### Priority 2 — Fix "keep broad" detection
**What**: Detect "broad/default/skip targeting" intent and bypass all demographic parsing
**File**: `collect_targeting.py`

### Priority 3 — Fix deliver_plan hardcoded goal
**What**: Use `state.get("goal")` and `state.get("kpi")` dynamically
**File**: `deliver_plan.py`

### Priority 4 — Targeting in plan_state/sidebar
**What**: Add demographics, device_types, postcodes to `_build_plan_state()` 
**File**: `sessions.py`

### Priority 5 — Budget Split for multiple deals
**What**: After inventory selection with multiple deals, compute suggested split and offer editable allocation
**Files**: `presentation.py`, state schema, sessions.py

### Priority 6 — Reach Repair Loop
**What**: If `estimated_unique_reach < MIN_VIABLE_REACH`, route back to options: broaden audience, increase budget, change inventory
**Files**: `graph.py` (new edge), `predict_reach.py`, `presentation.py`

---

## SUMMARY TABLE

| Feature | Status |
|---|---|
| Market/Date/Duration/Budget collection | ✅ Working |
| Registry grounding & validation | ✅ Working |
| CTV inventory selection | ✅ Working |
| Dead-end inventory handling | ✅ Working |
| Targeting (all 6 groups parsed) | ⚠️ Works but no conversational gate |
| Targeting decision prompt | ❌ Missing |
| "Keep broad" intent handling | ❌ Missing |
| Targeting sidebar fields | ❌ Missing |
| Audience suggestion (3 options) | ✅ Working |
| Audience choice wait | ✅ Working |
| Reach forecast (Amazon) | ✅ Working |
| Reach unavailable honesty (3P) | ✅ Working |
| Plan delivery (consolidated) | ✅ Working |
| Budget split (multiple deals) | ❌ Missing |
| Reach repair loop | ❌ Missing |
| Goal/KPI not locked | ⚠️ Partial (defaults set, hardcoded in deliver_plan) |
| Wire format / UI contract | ✅ Working |
| StrategyPanel sidebar | ⚠️ Partial (targeting fields absent) |
| Plan finalise step | ❌ Missing (deferred to M2) |
| Planner node actually routing | ❌ Dead code (gated flow works without it) |
