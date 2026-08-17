# VOW AGENT — M1 CONTINUATION & IMPLEMENTATION PROMPT
## Current State Audit → Fix Existing Flow → Complete M1 Strategy Planning

Act as a Senior AI Engineer and Senior Agentic AI Architect working on the VOW Agent.

We are implementing Milestone 1 (M1) of the VOW Agentic Media Planning platform.

The goal of M1 is:

User natural-language prompt
        ↓
Understand campaign intent
        ↓
Collect/verify missing campaign information
        ↓
Match available CTV inventory
        ↓
Apply targeting
        ↓
Predict reach / impressions / frequency where supported
        ↓
Repair plan if reach is insufficient
        ↓
Present final Strategy Plan
        ↓
User finalises the plan
        ↓
M1 ends

DO NOT jump directly to strategy creation or execution.

============================================================
1. FIRST: AUDIT THE CURRENT IMPLEMENTATION
============================================================

Before writing or modifying code, inspect the COMPLETE existing repository.

Do NOT assume anything is missing.

Check:

- backend architecture
- LangGraph workflow
- planner/orchestrator
- specialised agents
- state schema
- Pydantic models
- API/MCP tools
- registry
- prompts
- validators
- frontend chat components
- interactive response components
- strategy sidebar
- network/API calls
- existing tests
- logs
- error handling
- existing mock MCP responses
- existing fixtures
- existing database/state persistence

Run the application.

Test the existing flow end-to-end.

Use browser/network inspection where possible.

Check:

1. What happens when a user starts with a vague prompt?
2. What happens when product + market are provided?
3. What happens when inventory is provided?
4. What happens when unsupported inventory is provided?
5. What happens when the user accepts alternatives?
6. What happens when the user rejects alternatives?
7. What happens when inventory is selected?
8. What happens when dates are missing?
9. What happens when creative duration is missing?
10. What happens when budget is missing?
11. What happens when goal/KPI is missing?
12. What happens when user provides all information in one prompt?
13. What happens when user changes an earlier decision?
14. What happens when invalid data is supplied?
15. What happens when inventory has no forecast?
16. What happens when targeting is requested?
17. What happens when the user says "keep it broad"?
18. What happens when user asks for London/postcodes/radius?
19. What happens when user asks for audience targeting?
20. What happens when multiple deals are selected?
21. What happens when budget split is required?
22. What happens when reach is too narrow?
23. What happens when user wants more reach?
24. What happens when user rejects the recommendation?
25. What happens when final strategy plan should be shown?

Do not implement anything until this audit is complete.

Create a short internal implementation report:

CURRENTLY WORKING
PARTIALLY WORKING
BROKEN
MISSING
DUPLICATED
NOT NEEDED
NEXT TO IMPLEMENT

Do not rebuild functionality that already works.

============================================================
2. IMPORTANT: CURRENT IMPLEMENTED FLOW
============================================================

The current implementation already demonstrates the following:

A. User can start with:

"We're launching a new running shoe line, want to run something on Zee TV in the UK."

B. Agent understands:

- product = running shoes
- market = UK
- requested inventory = Zee TV

C. Agent correctly checks inventory availability.

If Zee TV is not available, the agent responds approximately:

"Zee TV isn't currently available as inventory on this platform, so I can't plan the campaign on it. We hope to support it in the future. Would you like to use an available inventory instead?"

Then the UI should provide:

[Show available inventory]

[No, I'll plan this later]

IMPORTANT:

Do NOT show:

[Keep Zee TV]

because the platform already confirmed that Zee TV is unavailable.

Never give the user an option to select an inventory that the system has already determined cannot be used.

If user chooses "No, I'll plan this later":

Respond politely and end the planning conversation.

Example:

"No problem. I won't create a plan for Zee TV on this platform. If it becomes available later, you can come back and continue the campaign."

Do not continue asking questions.

============================================================
3. AVAILABLE INVENTORY FLOW
============================================================

If user chooses:

"Show available inventory"

DO NOT dump the entire market by default.

Return a small relevant set of available inventory options.

Use interactive UI components.

For example:

Prime Video
Netflix
Disney+
Hulu

Each option can show only verified information such as:

- channel/inventory
- available duration
- CPM/rate if verified
- deal/tier if available
- reach forecast availability
- relevant capability

Use:

- single-select radio/card when user should select ONE inventory
- multi-select cards only when multiple inventory choices are actually allowed
- table when comparing several inventory options

If user explicitly says:

"Show me everything"
"Show all available options"
"Show the rest of the market"

then show the complete relevant inventory table.

Never show static/mock inventory if real registry/API data exists.

============================================================
4. IMPORTANT ZERO-HALLUCINATION RULE
============================================================

The agent must follow these three rules:

1. NEVER INVENT
2. ALWAYS VERIFY
3. NEVER SILENTLY FIX

Example:

User:
"Run it on Netflix."

The agent must NOT simply put Netflix into state.

It must verify:

- Netflix exists
- Netflix is available in selected market
- Netflix supports selected duration
- matching deal exists
- CPM/rate exists
- targeting capability
- reach forecast capability

Only then can Netflix enter the strategy state.

If verification fails:

Explain exactly what failed.

Do not silently replace Netflix with Prime Video.

Do not silently modify the user's value.

Instead ask the user for a decision.

============================================================
5. CHAT-FIRST PROGRESSIVE FLOW
============================================================

The agent must NOT behave like a large questionnaire.

It must behave like a smart trader assistant.

Always:

1. Parse the user's latest message.
2. Extract all information.
3. Merge it into existing state.
4. Validate every supplied value.
5. Identify what is still missing.
6. Decide the NEXT meaningful decision.
7. Ask only for that decision.
8. Continue from existing state.

Never ask:

"What is your budget?"

if the user already said:

"I have £15k."

Never ask for dates again if they were already provided.

Never reset the conversation when one field changes.

============================================================
6. CURRENT M1 ORDER
============================================================

Follow this logical order:

STEP 1 — BASIC DETAILS
    ↓
STEP 2 — CTV INVENTORY
    ↓
STEP 2A — OPTIONAL BUDGET SPLIT
    ↓
STEP 3/4 — AUDIENCE + TARGETING
    ↓
STEP 5 — PREDICT REACH
    ↓
STEP 6 — REPAIR IF NECESSARY
    ↓
STEP 7 — FINALISE PLAN
    ↓
M1 COMPLETE

Do not jump from inventory directly to audience.

Before targeting, verify that the core campaign brief is complete.

============================================================
7. BASIC DETAILS
============================================================

The agent should collect/infer/derive:

- strategy name
- market
- flight dates
- primary currency
- creative duration
- goal
- KPI
- KPI target when applicable
- budget
- impression target if applicable
- advertiser defaults
- product category
- format

Important:

Not every field needs to be explicitly asked from the user.

Use source classification:

ASKED
INFERRED
DERIVED
GENERATED
ADVERTISER
FIXED
API
MATCHED
LATER

Example:

Strategy name:
GENERATED

Market:
INFERRED from user brief

Currency:
ADVERTISER/default

Format:
CTV / streaming_tv

Goal:
DEFAULTED to Awareness for CTV, but NOT LOCKED

KPI:
derived/validated based on selected goal

Budget:
ASKED only if missing

Flight:
ASKED only if missing

Creative duration:
ASKED only if missing

============================================================
8. GOAL BEHAVIOUR
============================================================

For CTV:

Awareness should be the DEFAULT.

But Awareness is NOT FIXED.

User must be allowed to change it.

If user selects another goal:

Do NOT block.

Instead explain briefly:

"Awareness is generally recommended for CTV because lower-funnel tracking can be less reliable on streaming inventory, but you can choose another goal if that's what you need."

Then continue.

Never silently change the user's selected goal back to Awareness.

============================================================
9. KPI BEHAVIOUR
============================================================

Goal and KPI are different fields.

Goal answers:

"What are we trying to achieve?"

KPI answers:

"How are we measuring success?"

For example:

Goal:
Awareness

KPI:
Reach

If goal changes, available KPI options must be retrieved/validated from the actual platform/API.

Do NOT hard-code KPI lists if an API/registry exists.

If KPI requires a target value, collect it conditionally.

Example:

KPI = FREQUENCY

Ask for target frequency only if required.

Do not ask for a frequency target when KPI = REACH unless the schema/API requires it.

============================================================
10. BUDGET
============================================================

If budget is provided:

Do not ask again.

Example:

User:
"I have £15,000."

Agent:

"Got it — £15,000 campaign budget."

If budget is missing:

Ask:

"What budget would you like to allocate to the campaign?"

UI:

Currency input

Optional action:

[Recommend a budget]

If user says:

"You decide"

the agent can recommend only using verified inventory/rate information.

Do NOT invent a minimum budget.

============================================================
11. CREATIVE DURATION
============================================================

If user says:

"45 seconds"

check whether that duration is supported.

If unsupported:

Do NOT silently change it.

Respond:

"We don't currently support 45-second CTV spots for this inventory. Available durations are 10s, 15s, 20s and 30s. Which would you like?"

UI:

10s
15s
20s
30s

Use actual API/registry-supported durations.

============================================================
12. DATE VALIDATION
============================================================

Dates must be validated.

Rules:

- start date must not be in the past
- end date must be after start date
- invalid date format must be rejected
- past campaign dates should not be silently accepted
- if user wants historical campaign analysis, that's a different intent and should not be treated as a live campaign

Example:

User:
"Run it March 1 to March 31 2020."

Agent:

"I see those dates are in the past. Should I update the campaign to upcoming dates, or are you trying to review a past campaign?"

Do not create a live campaign plan with past dates.

============================================================
13. CTV INVENTORY
============================================================

After basic details are sufficient:

Match inventory using real API/registry data.

Do not expose raw deal IDs unless specifically required.

User chooses meaningful inventory/channel.

The agent internally matches the appropriate deal.

The agent should surface:

- channel
- CPM/rate
- duration
- tier/capability
- forecast availability
- relevant commercial information

Do not make the user choose between opaque internal deal IDs.

============================================================
14. SINGLE VS MULTIPLE INVENTORY
============================================================

If one inventory:

Do NOT ask for budget split.

Continue to targeting.

If multiple inventories:

Show budget split.

Example:

Prime Video — £10,000
Sky — £5,000
Total — £15,000

UI:

[Use suggested split]

[Edit split]

If user provides manual split:

Validate total.

Example:

Budget = £15,000

User:

"£10k Prime and £10k Sky."

Agent:

"That split totals £20,000, but your campaign budget is £15,000. Please adjust the allocation."

Use editable allocation table.

Never allow invalid totals.

============================================================
15. TARGETING
============================================================

IMPORTANT:

Targeting should NOT behave like a mandatory questionnaire.

The targeting baseline should already exist.

For example:

Market = GB

Default location = GB

Default device = advertiser configuration / Connected TV requirement

Then ask:

"Your core campaign details are complete. Would you like to keep the default targeting or refine the audience/location?"

UI options:

[Keep default targeting]

[Add audience targeting]

[Refine location]

[Both]

If user says:

"Keep it broad."

Respond:

"Sounds good. I'll keep the default targeting and move on to the reach check."

Do NOT continue asking:

age?
gender?
interest?
postcode?
device?

============================================================
16. AUDIENCE TARGETING
============================================================

Audience targeting is OPTIONAL.

If user says:

"Target runners."

Do not invent an audience ID.

Use the audience suggestion API/tool.

Find relevant verified audience segments.

Present options.

Example:

"Narrow"
"Balanced"
"Wide"

These are presentation strategies created from verified audience data.

Do not pretend they are directly returned by the API if they are not.

User can:

- choose one
- modify
- decline audience targeting

If user says:

"No audience targeting."

Accept it.

Do not force audience selection.

============================================================
17. GEO / LOCATION TARGETING
============================================================

Location is separate from market.

Market:

GB

Location:

GB-wide

User may refine:

London

Manchester

Birmingham

specific postcodes

radius around an address

If user says:

"London only."

Agent must resolve London through the location API.

Do not invent a location ID.

If user says:

"SW1A 1AA, W1A 1AA"

validate those postcodes.

If some are invalid:

Tell the user which ones failed.

Do not silently remove them.

If user says:

"Within 10 miles of London"

use the custom-radius location flow.

UI:

Location/address
Radius number
Unit:

miles
km

Important:

A narrower location REPLACES the broad market location.

Do not create:

GB + London

when the intention is London-only.

It should become:

GB market
London location targeting

============================================================
18. EXTRA TARGETING
============================================================

Extra targeting is optional.

Possible refinements:

- audience
- age
- interests
- locations
- postcodes
- radius
- device types
- mobile OS when applicable
- instream position
- content-rating exclusions

But only offer targeting types that are actually supported by the platform/API.

Never show:

Tablet

if Tablet is not a valid targeting value.

Never invent targeting capabilities.

The targeting configuration should be extensible/config-driven because targeting types can change.

============================================================
19. DEVICE TARGETING
============================================================

For streaming_tv:

CONNECTED_TV is required.

DESKTOP and MOBILE may be optional depending on advertiser settings.

If MOBILE is selected:

mobile operating system can be:

IOS
ANDROID

Do not invent other values.

Advertiser defaults must be respected.

If a device policy is locked:

the agent must not offer the user an option to override it.

============================================================
20. REACH FORECAST
============================================================

Only forecast after:

- basic details are complete
- inventory is matched
- budget is known
- creative duration is known
- targeting is settled

Then:

"I'm checking the available reach and forecast for your selected inventory and targeting."

Show:

- estimated unique reach
- estimated impressions
- average frequency
- indicative CPM
- reach curve where supported

All numbers must come from the actual forecast/API.

Never invent a forecast.

============================================================
21. THIRD-PARTY INVENTORY FORECAST RULE
============================================================

If inventory does not support unique reach forecasting:

DO NOT fabricate reach.

Say:

"A unique reach forecast isn't available for this inventory. I can still show the available CPM and estimated impressions and continue with the plan."

Clearly label estimates.

Never present estimated impressions as guaranteed delivery.

============================================================
22. REACH REPAIR LOOP
============================================================

If reach is insufficient:

Do not silently change the plan.

Explain:

"The current targeting is too narrow for the available budget. I can try to improve reach without changing the core campaign."

Possible actions:

1. Raise bid for floor-rate inventory, where supported
2. Widen audience
3. Relax targeting
4. Widen inventory
5. Increase budget

The agent should choose the least disruptive valid option first.

Ask the user before materially changing the plan.

UI:

[Broaden audience]

[Increase budget]

[Change inventory]

[Show recommendation]

If user says:

"You decide."

Agent can recommend based on verified forecast data.

============================================================
23. USER CHANGES AN EARLIER DECISION
============================================================

The conversation must be stateful.

Example:

User:
"Actually make the budget £20k."

Agent:

"Sure — I've updated the campaign budget to £20,000. I'll recalculate the forecast using the new budget."

Do not restart.

If user changes inventory:

"Actually use Sky instead of Prime Video."

Then:

- update state
- revalidate Sky
- rematch deals
- recalculate budget split if needed
- re-run targeting compatibility if needed
- re-run forecast

============================================================
24. RESPONSE FORMAT DECISION
============================================================

The backend response must tell the frontend what interaction is expected.

The agent should not return arbitrary UI instructions.

Use structured response semantics.

Examples:

SINGLE SELECTION:

{
  "type": "single_select",
  "message": "...",
  "options": [...]
}

MULTI SELECTION:

{
  "type": "multi_select",
  "message": "...",
  "options": [...]
}

TABLE:

{
  "type": "table",
  "message": "...",
  "columns": [...],
  "rows": [...]
}

CARDS:

{
  "type": "cards",
  "message": "...",
  "options": [...]
}

DATE:

{
  "type": "date_range",
  "message": "..."
}

CURRENCY:

{
  "type": "currency_input",
  "message": "..."
}

CONFIRMATION:

{
  "type": "confirmation",
  "message": "...",
  "actions": [...]
}

SKIP:

{
  "type": "confirmation",
  "message": "...",
  "actions": [
      {"label": "Continue", "value": "continue"},
      {"label": "Refine targeting", "value": "refine"}
  ]
}

IMPORTANT:

The backend should determine the semantic interaction required.

The frontend should render the corresponding component.

Do not hard-code business decisions into the frontend.

============================================================
25. RESPONSE FORMAT RULE
============================================================

Use:

Radio/single-select:
when exactly ONE choice must be selected.

Checkbox/multi-select:
when multiple choices can be selected.

Table:
when comparing multiple inventory/deal options.

Cards:
when choices need richer information.

Date picker:
for flight dates.

Currency input:
for budget.

Editable allocation table:
for budget split.

Search:
for locations.

Multi-value input:
for postcodes.

Radius input:
for custom radius.

Confirmation:
when the user must approve a meaningful business decision.

Simple chat response:
when no decision is required.

============================================================
26. IMPORTANT: NO UNNECESSARY DATA DUMP
============================================================

Do not return:

"Here are all 369 deals..."

when the user asked:

"Show me an available option."

Return a small relevant set.

Only return the full inventory when the user explicitly asks for it.

============================================================
27. FINAL STRATEGY PLAN
============================================================

Once:

- basic details complete
- inventory matched
- budget settled
- targeting settled
- forecast generated
- any repair decisions resolved

present a compact Strategy Plan.

Sidebar should dynamically reflect actual backend state.

Sections:

BASIC DETAILS

- Campaign
- Market
- Dates
- Currency
- Creative duration
- Goal
- KPI
- Budget

CTV INVENTORY

- Selected inventory
- Matched deals
- CPM
- Budget allocation
- Budget split if applicable

TARGETING

- Audience
- Location
- Postcodes
- Device
- Optional targeting refinements

REACH CURVE

- Unique reach
- Reach %
- Impressions
- Frequency
- CPM
- Reach curve where supported

DECISION

[Edit Plan]

[Finalise Plan]

Do not show fake/static values.

Everything in the sidebar must come from current backend state.

============================================================
28. FINALISE PLAN
============================================================

Do not treat "finalise" as manager approval.

For current M1:

DRAFT → FINALISED

The trader/user finalises the plan.

After finalisation, M1 strategy planning is complete.

Do not automatically activate/spend money.

Do not jump into M2 execution.

============================================================
29. CRITICAL BUGS TO PREVENT
============================================================

Test and prevent all of these:

1. Unsupported inventory treated as available.
2. User allowed to select unavailable inventory.
3. Agent asking for information already provided.
4. Agent jumping to audience before basic details are complete.
5. Agent asking targeting questions when user said keep broad.
6. Agent inventing audience IDs.
7. Agent inventing location IDs.
8. Agent accepting invalid postcodes.
9. Agent accepting unsupported durations.
10. Agent accepting past flight dates.
11. Agent inventing CPM.
12. Agent inventing reach.
13. Agent showing reach for inventory that cannot forecast reach.
14. Agent asking budget split when only one deal exists.
15. Agent allowing split greater than total budget.
16. Agent silently changing user's choice.
17. Agent resetting state after user changes one field.
18. Agent dumping entire inventory without request.
19. Agent treating Goal and KPI as the same field.
20. Agent treating Awareness as locked.
21. Agent forcing Awareness when user selected another valid goal.
22. Agent hard-coding inventory.
23. Agent hard-coding targeting.
24. Agent hard-coding CPM.
25. Agent hard-coding audience IDs.
26. Agent hard-coding market availability.
27. Agent showing static strategy sidebar data.
28. Agent creating strategy before required planning decisions are complete.
29. Agent creating/activating campaign without finalisation.
30. Agent using stale state after a user change.

============================================================
30. TESTING REQUIREMENT
============================================================

Before considering M1 complete, create/run tests for at least:

A. Vague campaign
B. Product + market
C. Product + market + inventory
D. Complete brief
E. Missing budget
F. Missing dates
G. Missing duration
H. Missing goal
I. Unsupported inventory
J. User says yes to alternatives
K. User says no to alternatives
L. User asks "show everything"
M. One inventory
N. Multiple inventories
O. Budget split
P. Invalid budget split
Q. Keep broad
R. Audience targeting
S. Age targeting
T. Interest targeting
U. City targeting
V. Postcode targeting
W. Invalid postcode
X. Radius targeting
Y. Device targeting
Z. Mobile OS targeting
AA. Reach available
AB. Reach unavailable
AC. Reach too narrow
AD. User wants more reach
AE. User rejects recommendation
AF. User says "you decide"
AG. User changes budget
AH. User changes inventory
AI. User changes dates
AJ. User changes duration
AK. User changes goal
AL. User changes KPI
AM. Final strategy plan
AN. Finalise plan

Also test combinations:

- all information in one message
- information spread over multiple messages
- information provided in random order
- conflicting information
- invalid information
- unsupported information
- user changing previous decisions
- user saying "yes"
- user saying "no"
- user saying "skip"
- user saying "show me more"
- user saying "other options"
- user saying "you decide"
- user saying "whatever you recommend"

============================================================
31. FRONTEND / BACKEND CONTRACT
============================================================

Inspect the existing frontend components provided by the UI team.

Do NOT create a second incompatible response format.

Reuse the existing component contract for:

- single selection
- multi selection
- table
- cards
- list
- confirmation
- date picker
- currency input
- editable table
- search
- radius
- final plan

Backend must provide enough structured information for the frontend component to render the correct interaction.

The LLM should decide the business meaning.

The deterministic backend/state layer should validate and execute it.

The frontend should render it.

============================================================
32. NETWORK / LOGGING VALIDATION
============================================================

For every implemented step:

Check browser Network tab.

Verify:

- request payload
- response payload
- HTTP status
- state updates
- error handling
- frontend rendering

Check backend logs.

Verify:

- correct graph node executed
- correct agent/tool executed
- correct MCP/API endpoint called
- state persisted
- no duplicate tool calls
- no unexpected fallback
- no hallucinated values

============================================================
33. DO NOT USE STATIC BUSINESS DATA
============================================================

Never hard-code:

- inventory
- CPM
- deal IDs
- audience IDs
- location IDs
- market availability
- targeting options
- reach
- impressions
- currency rates
- durations
- KPI options

If mock MCP exists:

Use it only where it is explicitly intended as the current development source.

Do not create fake fallback data just to make the UI look complete.

If mock MCP is the current source of truth for development, clearly keep the integration behind the same interface that real MCP/API will use later.

============================================================
34. IMPORTANT ARCHITECTURAL PRINCIPLE
============================================================

LLM:

- understands intent
- extracts information
- decides next conversational action
- explains decisions
- recommends options

Deterministic tools/backend:

- validate
- query registry
- query MCP
- match deals
- calculate
- persist state
- forecast
- enforce business rules

Frontend:

- renders structured interaction
- collects user selection
- sends selection back to backend

Never allow the LLM to directly invent a value that should come from a tool.

============================================================
35. YOUR TASK NOW
============================================================

Do NOT immediately start coding.

First:

1. Audit the current repository.
2. Run the existing application.
3. Test the currently implemented flow.
4. Identify exactly how far the agentic flow currently works.
5. Compare it against the M1 requirements above.
6. Identify the smallest next implementation unit.
7. Tell me:

   CURRENT FLOW:
   what already works

   NEXT FLOW:
   what should be implemented next

   BACKEND:
   what needs changing

   FRONTEND:
   what needs changing

   STATE:
   what fields are missing

   API/MCP:
   which tools/endpoints are required

   TESTS:
   which tests should be added

8. Only after this audit, implement the next missing M1 capability.

Do not rewrite working code.

Do not create duplicate agents.

Do not create duplicate state models.

Do not create duplicate API clients.

Follow the existing project architecture.

============================================================
36. DEFINITION OF DONE FOR THIS ITERATION
============================================================

The implementation is NOT done merely because the UI renders.

It is done only when:

- backend flow works
- frontend flow works
- state persists correctly
- API/MCP calls are correct
- registry verification works
- no hallucinated values occur
- invalid inputs are handled
- user changes are handled
- UI components receive correct structured responses
- network responses are correct
- logs are clean
- tests pass
- existing functionality remains working
- strategy sidebar reflects real state
- no static business data is used
- agent does not jump ahead to the next stage
- M1 flow remains conversational and progressive

Most importantly:

DO NOT make the agent behave like a form.

The user should feel like they are talking to a smart media trader assistant that understands what they have already told it and only asks for the next decision that actually matters.