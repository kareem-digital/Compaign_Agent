# VOW Agent --- Strategy Planning Conversation & Test Case Matrix

## 1. Purpose

This document defines the expected **chat-first Strategy Planning
journey** for the VOW Agent.

The goal is to cover how a user can arrive with: - a vague campaign
request, - a partially completed brief, - a complete brief, - a specific
inventory request, - an unsupported inventory request, - a
budget/date/creative/goal constraint, - an audience or location
request, - or a combination of all of these,

and how the agent should collect the missing decisions **without making
the conversation feel like a long form**.

The flow is based on the provided CTV journey flowchart and VOW UI
design. The uploaded slides describe the UI as a sequential VOW agentic
workflow and explicitly say the slides focus on page design/rendering
rather than the example rendered data. fileciteturn17file0L2-L5

------------------------------------------------------------------------

# 2. Core Principle

## Chat should be progressive, not a questionnaire

The agent should:

1.  Understand what the user already said.
2.  Extract all known campaign information.
3.  Check inventory availability.
4.  If inventory is unavailable, explain it briefly and offer available
    alternatives.
5.  Collect only the **missing information needed for the next planning
    decision**.
6.  Use sensible defaults only when the flowchart/schema allows it.
7.  Ask for user confirmation when a business decision materially
    changes the plan.
8.  Apply baseline targeting automatically.
9.  Offer optional audience/geo refinement.
10. Check reach availability.
11. Predict reach/impressions/frequency where supported.
12. If reach is too narrow, propose extending the audience and
    re-predict.
13. Present the plan for approval.
14. After approval, create the strategy.
15. Stop the strategy-planning conversation at the strategy creation
    boundary.

------------------------------------------------------------------------

# 3. Strategy Planning State

The agent should internally maintain a campaign state similar to:

  -----------------------------------------------------------------------
  Field                   Example                 Status
  ----------------------- ----------------------- -----------------------
  Campaign name           Running Shoe UK         Derived/optional

  Product/context         New running shoe line   Known

  Market                  UK                      Known

  Location                UK-wide / postcodes /   Default or user-defined
                          radius                  

  Inventory               Prime Video             Known after selection

  Budget                  £15,000                 Required

  Flight start            1 Oct 2026              Required

  Flight end              31 Oct 2026             Required

  Creative duration       30s                     Required for deal
                                                  matching

  Goal                    Awareness               Required

  KPI                     Reach / impressions     Derived/goal dependent
                          etc.                    

  Audience                Broad / lifestyle /     Baseline + optional
                          custom                  refinement

  Geo targeting           UK-wide / postcode /    Optional refinement
                          radius                  

  Selected deals          1+ deals                Derived from inventory
                                                  selection

  Budget split            £x / £y                 Only when multiple
                                                  deals selected

  Reach forecast          \~154k                  Derived

  Impressions             \~492k                  Derived

  Frequency               3.2                     Derived

  CPM                     £30.51                  Derived

  Plan approval           Pending/Approved        User decision

  Strategy ID             Generated after         System
                          creation                
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 4. Important Flow Rules

## Rule A --- Never ask for information the user already provided

User: \> I have £15k, UK, October 1 to 31, 30 seconds, awareness.

Agent should not ask: \> What is your budget?

It should recognise all four fields.

------------------------------------------------------------------------

## Rule B --- Do not jump to Audience too early

After inventory selection, the agent should first verify that the
**basic campaign brief** is complete.

Minimum planning information normally includes: - market/location, -
inventory, - budget, - flight dates, - creative duration, - campaign
goal/KPI.

Audience is then handled through the targeting stage.

------------------------------------------------------------------------

## Rule C --- Unsupported inventory must not be treated as available

Example:

> "I want to run something on Zee TV in the UK."

If Zee TV is not in the platform inventory, the agent must not continue
as though Zee TV exists.

Correct:

> "Zee TV isn't currently available as inventory on this platform, so I
> can't plan the campaign on it. We hope to support it in the future.
> Would you like to use an available inventory instead?"

If the user says **No**, conclude politely.

If the user says **Yes**, present available alternatives or let the user
select an alternative.

------------------------------------------------------------------------

## Rule D --- Do not dump the entire market unless requested

Default response should offer a **small relevant set of available
alternatives**.

Recommended UI: - inventory cards, - radio buttons, - selectable deal
cards.

Example:

> "Zee TV isn't currently available. I can plan this campaign on an
> available UK CTV inventory instead. Would you like to see suitable
> alternatives?"

Buttons: - `Show alternatives` - `No, keep Zee TV`

If the user asks: \> "Show me everything."

Then show the complete available inventory table.

------------------------------------------------------------------------

## Rule E --- Budget split is conditional

`budget_split` is needed when:

`selected_deals > 1`

Example:

> Total budget: £15,000\
> Prime Video: £10,000\
> Sky: £5,000

If only one deal is selected, do not ask about budget split.

------------------------------------------------------------------------

## Rule F --- Reach prediction comes after targeting/inventory information

The flowchart shows: - reach availability, - prediction for supported
inventory, - reach acceptability, - audience extension if reach is too
narrow, - approval.

The agent should not claim a reach forecast before the required
inventory/targeting inputs are settled.

------------------------------------------------------------------------

# 5. Recommended UI Interaction Types

  Information             Recommended UI
  ----------------------- ---------------------------------------
  Campaign goal           Radio buttons
  Budget                  Currency input
  Start/end dates         Date picker
  Creative length         Radio buttons / selectable cards
  Inventory               Cards/table + radio/select
  Multiple deals          Checkbox/select cards
  Budget split            Editable allocation table
  Audience                Radio buttons + optional custom input
  Location                Search/select input
  Postcodes               Multi-value input
  Radius                  Address + radius + unit
  Reach results           Result card + reach curve
  Narrow reach            `Extend audience` button
  Approval                `Accept Plan` / `Edit Plan`
  Unsupported inventory   `Choose alternative` / `Keep request`
  User rejection          End/close conversation

------------------------------------------------------------------------

# 6. Test Case Matrix

## A. Starting a Campaign --- Vague User Intent

### TC-001 --- User only says "I want to run a campaign"

**User** \> I want to run a campaign.

**Agent** \> Absolutely. I can help plan it. What are you promoting, and
which market would you like to run it in?

**UI** - Free-text chat. - No unnecessary form.

**Expected** - Do not ask ten questions at once. - Start with the
highest-value missing information.

------------------------------------------------------------------------

### TC-002 --- User says campaign + market

**User** \> I want to run a campaign in the UK.

**Agent** \> Sure. What are you promoting? If you already know the
channel or inventory you'd like, you can tell me that too.

------------------------------------------------------------------------

### TC-003 --- User gives product + market

**User** \> I want to promote a new running shoe in the UK.

**Agent** \> Great. What inventory would you like to use, or would you
like me to suggest suitable UK CTV options?

**UI** - `Suggest inventory` - Optional inventory search.

------------------------------------------------------------------------

### TC-004 --- User gives product + inventory + market

**User** \> We're launching a new running shoe line and want Prime Video
in the UK.

**Agent** \> Great --- I have the product, UK market and Prime Video. I
just need the campaign budget, dates, ad length and campaign goal to
build the initial plan.

**UI** Show quick choices: - Budget input - Date picker - Creative
duration - Goal radio buttons

------------------------------------------------------------------------

# 7. Complete Brief in One Message

### TC-005 --- User provides everything

**User** \> We're launching a new running shoe line in the UK. We have
£15k from October 1 to 31 and want 30-second ads for awareness on Prime
Video.

**Agent** \> Perfect. I have the core campaign brief: \> - UK \> - Prime
Video \> - £15,000 \> - 1--31 October \> - 30s \> - Awareness \> \> I'll
use the default UK-wide targeting unless you'd like to refine the
audience or location.

**Next** - Baseline targeting. - Then optional audience/geo refinement.

**Expected** - No repeated questions.

------------------------------------------------------------------------

# 8. Missing Budget

### TC-006

**User** \> New running shoe campaign in the UK, October 1--31, 30
seconds on Prime Video.

**Agent** \> Got it. What budget would you like to allocate to the
campaign?

**UI** Currency input.

Optional: - `I need a recommendation`

------------------------------------------------------------------------

# 9. Missing Dates

### TC-007

**User** \> I have £15k for a 30-second running shoe awareness campaign
on Prime Video in the UK.

**Agent** \> Great. What are the campaign start and end dates?

**UI** Date range picker.

------------------------------------------------------------------------

# 10. Missing Creative Duration

### TC-008

**User** \> £15k, UK, October 1--31, awareness campaign for our new
running shoes on Prime Video.

**Agent** \> Got it. What ad length would you like?

**UI** Radio buttons: - 10s - 15s - 20s - 30s - 40s - Other

------------------------------------------------------------------------

# 11. Missing Goal

### TC-009

**User** \> £15k, UK, October 1--31, 30-second running shoe ads on Prime
Video.

**Agent** \> What is the main campaign goal?

**UI** Radio buttons: - Awareness - Reach - Consideration - Other/Custom

------------------------------------------------------------------------

# 12. User Gives Multiple Missing Fields

### TC-010

**User** \> £15k and October 1 to 31.

**Agent** \> Thanks --- I have the £15k budget and dates. What are you
promoting, and what inventory would you like to use?

**Expected** - Preserve known fields. - Ask only for remaining
high-level fields.

------------------------------------------------------------------------

# 13. User Gives Information in Different Order

### TC-011

**User** \> 30 seconds. Awareness. £15k. Running shoes. UK.

**Agent** \> Perfect --- I have the product, UK market, £15k budget, 30s
creative and awareness goal. What dates would you like to run the
campaign?

------------------------------------------------------------------------

# 14. User Changes a Previously Given Value

### TC-012

**User** \> Actually, make the budget £20k instead of £15k.

**Agent** \> Sure --- I've updated the campaign budget to £20,000. I'll
use that for the forecast.

**Expected** - Update state. - Recalculate affected forecast later. - Do
not restart the conversation.

------------------------------------------------------------------------

# 15. User Changes Inventory

### TC-013

**User** \> Actually use Sky instead of Prime Video.

**Agent** \> No problem. I'll switch the inventory to Sky and update the
available deals and forecast.

**Expected** - Re-check deal availability. - Re-check reach. - Re-check
budget split if multiple deals are involved.

------------------------------------------------------------------------

# 16. Unsupported Inventory

## TC-014 --- Zee TV is not available

**User** \> We're launching a new running shoe line, want to run
something on Zee TV in the UK.

**Agent** \> Zee TV isn't currently available as inventory on this
platform, so I can't plan the campaign on it. We hope to support it in
the future. Would you like to use an available UK inventory instead?

**UI** - `Show available alternatives` - `Keep Zee TV`

**Expected** - Never pretend Zee TV is available. - Do not ask for
dates/budget for Zee TV before resolving inventory.

------------------------------------------------------------------------

## TC-015 --- User says Yes to alternatives

**User** \> Yes.

**Agent** \> Sure. I can help you choose an available UK inventory. Here
are the most relevant options.

**UI** Inventory cards/table with: - Inventory - Creative length
availability - Deal/tier - CPM if available - Reach forecast
availability

User selects one or more.

------------------------------------------------------------------------

## TC-016 --- User says No to alternatives

**User** \> No.

**Agent** \> No problem. I won't create a plan for Zee TV on this
platform. If Zee TV becomes available later, you can use the campaign
brief again.

**Expected** - Conversation can end cleanly. - No forced inventory
list. - No more questions.

------------------------------------------------------------------------

## TC-017 --- User asks "Why isn't Zee TV available?"

**User** \> Why can't I use Zee TV?

**Agent** \> Zee TV isn't currently available in the inventory supported
by this platform, so I can't create a strategy for it right now.

Do not invent a reason such as: - technical outage, - commercial
restriction, - provider issue, unless the system actually knows it.

------------------------------------------------------------------------

# 17. Available Inventory Selection

## TC-018 --- One inventory selected

**User** \> Prime Video.

**Agent** \> Great --- Prime Video selected. I have the inventory. I
still need any missing campaign details before I build the plan.

Then ask only missing fields.

------------------------------------------------------------------------

## TC-019 --- User selects multiple deals

**User** \> I'll use Prime Video and Sky.

**Agent** \> Great. You've selected two deals. How would you like to
allocate the campaign budget between them?

**UI** Budget split table.

Example:

  Deal                 Budget
  ------------- -------------
  Prime Video         £10,000
  Sky                  £5,000
  **Total**       **£15,000**

Buttons: - `Use suggested split` - `Edit split`

------------------------------------------------------------------------

## TC-020 --- Agent proposes budget split

**Agent** \> Based on the available deals, I suggest: \> - Prime Video:
£10,000 \> - Sky: £5,000 \> \> Would you like to use this split?

**UI** - `Use this split` - `Edit`

------------------------------------------------------------------------

## TC-021 --- User changes budget split

**User** \> Give Sky £7k and the rest to Prime Video.

**Agent** \> Done. The proposed split is now: \> - Sky: £7,000 \> -
Prime Video: £8,000 \> \> Total: £15,000.

------------------------------------------------------------------------

# 18. "Show Me Everything" Inventory Request

## TC-022

**User** \> Show me all available options.

**Agent** \> Sure. Here are all available UK inventory options for the
campaign.

**UI** Use a table/card list.

Recommended columns: - Inventory - Creative length - Deal/tier - CPM -
Reach forecast availability - Selection control

**Expected** - Only show all inventory when explicitly requested. -
Otherwise prefer a short relevant list.

------------------------------------------------------------------------

# 19. Audience / Targeting

## TC-023 --- Keep broad

**Agent** \> Your core campaign details are complete. For targeting,
would you like to keep the audience broad or add audience/geo targeting?

**UI** Radio: - Broad/default - Add audience targeting - Add location
targeting - Both

------------------------------------------------------------------------

## TC-024 --- User asks for runners

**User** \> Target runners.

**Agent** \> Sure. I'll use a running/fitness-relevant audience where
available. Would you like to keep the UK-wide location?

**UI** - `UK-wide` - `Refine location`

------------------------------------------------------------------------

## TC-025 --- User specifies age

**User** \> Target people aged 25--44.

**Agent** \> Got it. I'll target the 25--44 audience and keep the UK
location unless you'd like to refine it.

------------------------------------------------------------------------

## TC-026 --- User gives audience + geo

**User** \> Target fitness enthusiasts aged 25--44 in London.

**Agent** \> Got it --- fitness enthusiasts aged 25--44 in London. I'll
use that as the targeting refinement and check the resulting reach.

------------------------------------------------------------------------

# 20. Location Handling

The Strategy Schema documentation describes `location` as a list of
strings, auto-defaulting to the target market ISO (for example `["GB"]`)
and allowing refinement to postcodes.

The document comments also raise: - user searching for locations, -
validating a provided list of postcodes to get location IDs, - creating
a custom-radius location from an address plus numeric radius and unit.

Therefore location should support several user patterns.

## TC-027 --- Default UK-wide

**User** \> UK campaign.

**Agent** \> I'll use UK-wide targeting by default. You can refine it to
specific locations if you want.

------------------------------------------------------------------------

## TC-028 --- City

**User** \> London only.

**Agent** \> Got it. I'll refine the location to London and update the
reach forecast.

------------------------------------------------------------------------

## TC-029 --- Postcodes

**User** \> Target these postcodes: SW1A 1AA, W1A 1AA.

**Agent** \> Sure. I'll validate those postcodes and use the matching
location areas for targeting.

**Expected** - Validate postcodes. - Do not blindly accept invalid
postcodes.

------------------------------------------------------------------------

## TC-030 --- Radius

**User** \> Target people within 10 miles of London.

**Agent** \> Sure. I can use a 10-mile radius around London. I'll update
the targeting and forecast.

**UI** Radius: - Address/location - Number - Unit: miles/km

------------------------------------------------------------------------

# 21. Extra Targeting Is Optional

The flowchart identifies **Extra targeting** as optional.

Therefore:

If the user says:

> Keep it broad.

Agent should not keep asking for: - age, - interests, - postcode, -
device, - etc.

**Agent** \> Sounds good. I'll keep the default targeting and move on to
the reach check.

------------------------------------------------------------------------

# 22. Reach Availability

## TC-031 --- Reach forecast available

After targeting is settled:

**Agent** \> Your targeting is set. I'm checking the available reach and
forecast for the selected inventory.

Then show:

-   Estimated reach
-   Impressions
-   Frequency
-   CPM
-   Reach curve where supported

------------------------------------------------------------------------

## TC-032 --- No reach curve available

For inventory where the flowchart indicates no reach curve is available:

**Agent** \> A reach curve isn't available for this inventory. I can
still provide the available impression/CPM estimate and continue with
the plan.

**Expected** - Do not fabricate a reach curve.

------------------------------------------------------------------------

# 23. Reach Acceptability

## TC-033 --- Reach acceptable

**Agent** \> The forecasted reach looks acceptable for the current
targeting. Would you like to approve this plan?

**UI** - `Approve plan` - `Edit targeting`

------------------------------------------------------------------------

## TC-034 --- Reach too narrow

**Agent** \> The current audience is too narrow for the available
budget. I recommend widening the audience and re-running the forecast.
Would you like me to broaden it?

**UI** - `Extend audience` - `Keep current targeting`

------------------------------------------------------------------------

## TC-035 --- User accepts audience extension

**User** \> Yes, broaden it.

**Agent** \> I'll broaden the audience while keeping the campaign
objective and core market unchanged, then re-check the forecast.

------------------------------------------------------------------------

## TC-036 --- User rejects audience extension

**User** \> No.

**Agent** \> Understood. I'll keep the current targeting. The forecast
remains based on the narrower audience.

Then offer: - `Approve plan` - `Edit targeting`

Do not silently broaden targeting.

------------------------------------------------------------------------

# 24. Budget vs Reach Trade-off

## TC-037 --- User asks for more reach

**User** \> I need more reach.

**Agent** \> I can try to improve reach by broadening the audience,
increasing the budget, or changing the inventory mix. Which would you
prefer?

**UI** Radio: - Broaden audience - Increase budget - Change inventory -
Show recommendation

------------------------------------------------------------------------

# 25. User Has No Preference

## TC-038

**User** \> I don't know. You decide.

**Agent** \> I can recommend the option that gives the best balance
between reach and your current budget. Would you like me to optimise for
reach?

**UI** - `Optimise for reach` - `Keep current plan`

------------------------------------------------------------------------

# 26. Budget Too Low / Plan Not Practical

## TC-039

**Agent** \> With the current budget and targeting, the forecast is too
limited to make the plan efficient. I can broaden the audience or
suggest a different inventory mix.

**UI** - `Broaden audience` - `Change inventory` - `Keep current plan`

Do not invent a guaranteed minimum budget unless the platform has a real
business rule for it.

------------------------------------------------------------------------

# 27. User Wants to Spend Less

## TC-040

**User** \> Can I do this with £5k instead?

**Agent** \> Yes, I can re-plan it at £5,000 and update the forecast.
Would you like me to apply the new budget?

**UI** - `Apply £5k` - `Keep £15k`

------------------------------------------------------------------------

# 28. User Wants to Change Dates After Forecast

## TC-041

**User** \> Change October 1--31 to October 15--31.

**Agent** \> Sure. I'll update the flight dates to 15--31 October and
regenerate the forecast.

------------------------------------------------------------------------

# 29. User Wants to Change Creative Length After Deal Selection

## TC-042

**User** \> Actually, make it 15 seconds instead of 30.

**Agent** \> No problem. I'll switch the creative length to 15 seconds
and re-check the matching inventory/deals.

Expected: - Revalidate inventory. - Recalculate affected
pricing/forecast. - Preserve unrelated campaign fields.

------------------------------------------------------------------------

# 30. User Gives Ambiguous Date

## TC-043

**User** \> Run it next month.

**Agent** \> Sure. What exact start and end dates would you like for the
campaign?

Do not guess dates when exact flight dates are needed.

------------------------------------------------------------------------

# 31. User Gives Ambiguous Budget

## TC-044

**User** \> Around 15k.

**Agent** \> Got it --- should I use £15,000 as the campaign budget?

**UI** - `Use £15,000` - `Change`

------------------------------------------------------------------------

# 32. User Gives Currency Ambiguously

## TC-045

**User** \> Budget is 15k.

If market/currency is clear:

**Agent** \> I'll use £15,000 for the UK campaign. Is that correct?

If currency is not clear:

**Agent** \> What currency should I use for the £15k-equivalent budget?

Do not silently convert without knowing the intended currency.

------------------------------------------------------------------------

# 33. Currency Mismatch

If inventory/deals are priced in GBP while the campaign budget is in
another currency:

**Agent** \> The selected deal is priced in GBP while your campaign
budget is in another currency. I'll keep the calculations in one
currency and show the currency used in the plan.

The agent should not mix currencies in arithmetic.

------------------------------------------------------------------------

# 34. User Selects a Deal but Deal Does Not Match Creative Length

## TC-046

**User** \> I want the 30-second Prime Video deal.

If no matching deal exists:

**Agent** \> I couldn't find a matching 30-second Prime Video deal for
the current campaign setup. I can show the closest available options.

**UI** - Matching alternatives - `Show all`

------------------------------------------------------------------------

# 35. User Asks "What do you recommend?"

## TC-047

**User** \> What do you recommend for a new running shoe?

**Agent** \> For a new product launch, I'd start with an
awareness-focused plan and a broad UK audience, then refine targeting
only if the reach forecast is too broad or inefficient. Would you like
me to build that plan?

Do not pretend this is a guaranteed business rule; present it as a
recommendation.

------------------------------------------------------------------------

# 36. User Asks for a Campaign but Provides No Inventory

## TC-048

**User** \> I have £15k for a running shoe campaign in the UK from
October 1 to 31, 30 seconds, awareness.

**Agent** \> Great --- I have the core campaign brief. Would you like me
to recommend available UK CTV inventory, or do you already have an
inventory in mind?

**UI** - `Recommend inventory` - `I have an inventory`

------------------------------------------------------------------------

# 37. User Asks for Specific Inventory but Gives No Budget

## TC-049

**User** \> I want Prime Video in the UK for a running shoe campaign.

**Agent** \> Prime Video is available. To build the plan, I need your
budget, campaign dates, creative length and campaign goal.

------------------------------------------------------------------------

# 38. User Starts With Audience

## TC-050

**User** \> I want to reach fitness enthusiasts aged 25--44.

**Agent** \> Sure. What are you promoting and which market would you
like to target?

Preserve the audience information and continue collecting the campaign
brief.

------------------------------------------------------------------------

# 39. User Starts With Location

## TC-051

**User** \> I want to advertise only in London.

**Agent** \> Sure. What are you promoting, and what type of CTV
inventory would you like to use?

Preserve London as the location.

------------------------------------------------------------------------

# 40. User Starts With Inventory

## TC-052

**User** \> Prime Video.

**Agent** \> Prime Video can be used for the plan. What are you
promoting, which market are you targeting, and what budget/dates do you
have?

------------------------------------------------------------------------

# 41. User Provides Everything Plus Extra Information

## TC-053

**User** \> We're launching running shoes in the UK, £15k, Oct 1--31, 30
seconds, awareness, Prime Video, fitness enthusiasts aged 25--44,
London.

**Agent** \> Perfect. I have the complete campaign brief and targeting.
I'll check the available Prime Video deals and forecast the reach for
this audience.

Expected: - Do not ask audience again. - Do not ask location again. - Do
not ask for basic details again.

------------------------------------------------------------------------

# 42. User Wants Broad Audience After Giving Specific Audience

## TC-054

**User** \> Actually, don't target fitness enthusiasts. Keep it broad.

**Agent** \> Sure. I'll remove the audience refinement and use the
default UK targeting.

------------------------------------------------------------------------

# 43. User Wants to Add Audience After Baseline

## TC-055

**User** \> Add runners.

**Agent** \> Sure. I'll add the relevant running audience and update the
reach forecast.

------------------------------------------------------------------------

# 44. User Wants to Remove Location

## TC-056

**User** \> Remove London. Make it UK-wide.

**Agent** \> Done. I'll switch the location back to UK-wide and update
the forecast.

------------------------------------------------------------------------

# 45. User Asks What Is Missing

## TC-057

**User** \> What do you still need from me?

**Agent** \> I have the UK market and running shoe campaign. I still
need: \> - Budget \> - Campaign dates \> - Creative length \> - Campaign
goal \> \> You can send them all together or one at a time.

------------------------------------------------------------------------

# 46. User Says "Use Defaults"

## TC-058

**User** \> Just use the defaults.

**Agent** \> Sure. I'll use the platform defaults for the fields that
can safely be defaulted and only ask you for decisions that are required
to build the plan.

Expected: - Never default a materially important field if the system
requires user confirmation. - Explain only the remaining required
decisions.

------------------------------------------------------------------------

# 47. User Wants the Agent to Choose Everything

## TC-059

**User** \> You decide everything.

**Agent** \> I can recommend the setup. I'll optimise for a practical
awareness plan based on your market, budget and available inventory, and
I'll show you the proposed plan before creating it.

Expected: - Agent may recommend. - User still gets approval before
strategy creation.

------------------------------------------------------------------------

# 48. User Asks for a Summary Before Approval

## TC-060

**User** \> Show me the plan before creating it.

**Agent** \> Of course. I'll show the complete strategy summary and
forecast first. You can approve it or make changes.

------------------------------------------------------------------------

# 49. Strategy Plan Summary

Once stages 1--6 are settled, the agent should show a concise plan
summary.

Example:

> **Strategy plan ready**
>
> **Campaign:** UK Running Shoe Launch\
> **Market:** UK\
> **Dates:** 1--31 October 2026\
> **Budget:** £15,000\
> **Goal:** Awareness\
> **Creative:** 30s\
> **Inventory:** Prime Video\
> **Audience:** Broad UK audience
>
> **Forecast** - Reach: \~154k - Impressions: \~492k - Frequency: 3.2 -
> CPM: £30.51
>
> Would you like to approve this plan?

**UI** - Expandable `Basic details` - Expandable `CTV inventory` -
Expandable `Targeting` - Reach curve - `Accept Plan` - `Edit Plan`

The provided UI design shows a draft Strategy Plan with Basic Details,
CTV Inventory, Targeting, Reach Curve and an `Accept Plan` action.
fileciteturn17file0L2-L5

------------------------------------------------------------------------

# 50. Approval

## TC-061 --- User approves

**User** \> Yes, approve it.

**Agent** \> Great. The plan is approved. I'll create the strategy from
this approved plan.

Then: - Create strategy. - Return strategy ID/status. - Do not continue
asking strategy-planning questions.

------------------------------------------------------------------------

# 51. User Rejects Plan

## TC-062

**User** \> No, I want to change the audience.

**Agent** \> Sure. What would you like to change about the audience?

Then return to the relevant planning step.

------------------------------------------------------------------------

# 52. User Wants to Edit Budget From Plan

## TC-063

**User** \> Change the budget to £20k.

**Agent** \> Sure. I'll update the budget to £20,000 and regenerate the
forecast.

Then return to forecast/approval.

------------------------------------------------------------------------

# 53. User Says "Create It"

## TC-064

**User** \> Yes, create it.

If all required information is complete:

**Agent** \> Great. I'll create the strategy using the approved plan.

Expected: - Create strategy. - Return strategy ID. - Status should
reflect that the strategy has been created/not yet running where
applicable.

------------------------------------------------------------------------

# 54. User Tries to Create Before Required Fields Are Complete

## TC-065

**User** \> Create it.

But budget/dates/goal are missing.

**Agent** \> I can create it once the core campaign details are
complete. I still need: \> - Budget \> - Dates \> - Goal

Do not create an incomplete strategy.

------------------------------------------------------------------------

# 55. User Sends Multiple Corrections in One Message

## TC-066

**User** \> Actually £20k, October 5--31, 15 seconds, target runners
aged 25--44 in London.

**Agent** \> Got it. I've updated: \> - Budget: £20,000 \> - Dates:
5--31 October \> - Creative: 15s \> - Audience: runners 25--44 \> -
Location: London \> \> I'll re-check the matching inventory and
forecast.

Expected: - Apply all valid updates together. - Revalidate dependent
fields.

------------------------------------------------------------------------

# 56. User Asks Unrelated Question During Planning

## TC-067

**User** \> By the way, what's the weather in London?

**Agent** \> I can help with the campaign plan here. For the campaign,
we still need \[missing field\].

Expected: - Keep campaign context. - Do not lose campaign state.

------------------------------------------------------------------------

# 57. User Restarts Campaign Mid-Conversation

## TC-068

**User** \> Forget this. I want to plan a completely different campaign.

**Agent** \> Sure. Let's start a new campaign. What are you promoting
and which market would you like to target?

Expected: - Clear previous campaign state or create a new campaign
context. - Do not mix the two campaigns.

------------------------------------------------------------------------

# 58. User Gives Invalid Budget

## TC-069

**User** \> Budget: abc.

**Agent** \> I couldn't read a valid budget from that. What campaign
budget would you like to use?

------------------------------------------------------------------------

# 59. Invalid Date Range

## TC-070

**User** \> Start October 31 and end October 1.

**Agent** \> The end date is earlier than the start date. What date
range should I use?

------------------------------------------------------------------------

# 60. Invalid Creative Length

## TC-071

**User** \> Make it 37 seconds.

If 37s is unsupported:

**Agent** \> I don't currently have a matching 37-second deal. I can
show the closest supported creative lengths.

------------------------------------------------------------------------

# 61. Unsupported Location

## TC-072

**User** \> Target people in ABC123.

**Agent** \> I couldn't validate that location. Could you provide a
valid postcode, city, or address/radius?

------------------------------------------------------------------------

# 62. Reach Changes After Targeting

## TC-073

User changes: \> Add London.

Agent:

> Adding London changes the targetable audience. I'll update the
> forecast before we continue.

Expected: - Never keep stale reach results after a material targeting
change.

------------------------------------------------------------------------

# 63. Reach Changes After Budget

## TC-074

User: \> Increase budget to £25k.

Agent:

> Updated to £25,000. I'll regenerate the reach curve and forecast.

------------------------------------------------------------------------

# 64. User Wants Only the Forecast

## TC-075

**User** \> Just tell me how much reach I can get.

**Agent** \> I can do that. I need the campaign market, inventory,
budget, dates, creative length and targeting needed for the forecast.

If enough information is already present, calculate/display forecast
without forcing full strategy creation.

------------------------------------------------------------------------

# 65. User Wants a Plan but No Audience Preference

## TC-076

**User** \> I don't care about the audience.

**Agent** \> No problem. I'll use the default broad targeting and check
whether the resulting reach is acceptable.

------------------------------------------------------------------------

# 66. User Wants Maximum Reach

## TC-077

**User** \> I want maximum possible reach.

**Agent** \> Got it. I'll optimise the plan for reach within your budget
and campaign constraints.

Expected: - Audience/inventory recommendations should support reach. -
Still show the final plan before creation.

------------------------------------------------------------------------

# 67. User Wants Lowest CPM

## TC-078

**User** \> I want the cheapest CPM.

**Agent** \> I can optimise the available inventory selection for lower
CPM, while keeping your campaign constraints. I'll show the recommended
option before creating the strategy.

------------------------------------------------------------------------

# 68. User Wants Multiple Objectives

## TC-079

**User** \> I want awareness but also conversions.

**Agent** \> We can plan around the primary objective first. Which
should be the main objective: Awareness or Conversions?

**UI** Radio buttons: - Awareness - Conversions

Expected: - Do not silently choose one.

------------------------------------------------------------------------

# 69. User Asks to Split Budget by Deal

## TC-080

**User** \> Split the £15k between Prime Video and Sky.

**Agent** \> Sure. I can propose a split based on the available deals,
or you can set the amounts yourself.

**UI** - `Recommend split` - `Set manually`

------------------------------------------------------------------------

# 70. User Provides Manual Split

## TC-081

**User** \> £9k Prime Video and £6k Sky.

**Agent** \> Got it: \> - Prime Video: £9,000 \> - Sky: £6,000 \> -
Total: £15,000 \> \> I'll use this split for the forecast.

------------------------------------------------------------------------

# 71. User Gives Split That Exceeds Total Budget

## TC-082

**User** \> £10k Prime Video and £10k Sky.

If total budget is £15k:

**Agent** \> The split totals £20,000, but your campaign budget is
£15,000. Please adjust the allocation.

**UI** Editable split table with validation.

------------------------------------------------------------------------

# 72. User Says "Whatever You Recommend" for Split

## TC-083

**Agent** \> I'll recommend a split based on the available deals and
expected reach, then show it to you for approval.

------------------------------------------------------------------------

# 73. Strategy Plan Should Not Be Created Too Early

## TC-084

The agent must not create the final strategy merely because: - product
is known, - market is known, - inventory is selected.

It should first settle the required campaign details and
targeting/forecast path.

------------------------------------------------------------------------

# 74. Strategy Plan Final UI State

The final strategy-plan UI should present the user with a compact
decision surface.

Recommended sections:

### Basic Details

-   Campaign
-   Dates
-   Markets
-   Currency
-   Goal/KPI
-   Budget

### CTV Inventory

-   Selected inventory
-   Selected deals
-   Deal allocation
-   Budget split if multiple deals

### Targeting

-   Audience
-   Locations
-   Postcodes
-   Device type
-   Optional targeting refinements

### Reach Curve

-   Unique reach
-   Reached %
-   Frequency
-   Impressions
-   CPM
-   Reach curve where supported

### Decision

-   `Edit Plan`
-   `Accept Plan`

The supplied UI examples show this structure, including Basic Details,
CTV Inventory, Targeting, Reach Curve and the final `Accept Plan`
action. fileciteturn17file0L2-L5

------------------------------------------------------------------------

# 75. End-to-End Golden Test Cases

## Golden Case A --- Minimal user

**User** \> I want to run a campaign.

**Agent** \> What are you promoting and which market would you like to
target?

↓

**User** \> New running shoes in the UK.

**Agent** \> Great. Would you like me to recommend available UK CTV
inventory?

↓

**User** \> Yes.

↓

**Agent** \> \[Inventory options\]

↓

**User** \> Prime Video.

↓

**Agent** \> Great. I need your budget, campaign dates, creative length
and campaign goal.

↓

**User** \> £15k, Oct 1--31, 30s, awareness.

↓

**Agent** \> Core brief complete. Would you like to keep the audience
broad or add targeting?

↓

**User** \> Keep it broad.

↓

**Agent** \> \[Forecast\]

↓

**Agent** \> The reach looks acceptable. Would you like to approve the
plan?

↓

**User** \> Yes.

↓

**Agent** \> Great. I'll create the strategy.

------------------------------------------------------------------------

# 76. Golden Case B --- Complete User in One Message

**User** \> We're launching a new running shoe line in the UK. We have
£15k from October 1 to 31 and want 30-second ads for awareness on Prime
Video.

**Agent** \> Perfect. I have the core brief. I'll use UK-wide default
targeting unless you'd like to refine the audience or location.

↓

**User** \> Keep it broad.

↓

**Agent** \> \[Reach forecast\]

↓

**Agent** \> The forecasted reach is acceptable. Would you like to
approve the plan?

↓

**User** \> Yes, create it.

↓

**Agent** \> Strategy created successfully.

------------------------------------------------------------------------

# 77. Golden Case C --- Unsupported Inventory

**User** \> We're launching a new running shoe line, want to run
something on Zee TV in the UK.

**Agent** \> Zee TV isn't currently available as inventory on this
platform, so I can't plan the campaign on it. We hope to support it in
the future. Would you like to use an available UK inventory instead?

### If YES

**Agent** \> Sure. I can show suitable available UK options.

↓

User selects Prime Video.

↓

Continue with missing campaign details.

### If NO

**Agent** \> No problem. I won't create a plan for Zee TV on this
platform. You can return when the inventory is available.

------------------------------------------------------------------------

# 78. Golden Case D --- Unsupported Inventory + Complete Brief

**User** \> We're launching a new running shoe line on Zee TV in the UK.
We have £15k from Oct 1--31, 30 seconds, awareness.

**Agent** \> Zee TV isn't currently available on this platform, so I
can't plan the campaign on it. We hope to support it in the future.
Would you like to use an available UK inventory instead?

If user says yes:

**Agent** \> Great. I'll use your existing £15k, Oct 1--31, 30s and
awareness brief. Which available inventory would you like to use?

This is important: **do not ask again for budget/dates/creative/goal
because they were already provided.**

------------------------------------------------------------------------

# 79. Golden Case E --- Multiple Deals

**User** \> I want Prime Video and Sky.

**Agent** \> Great. You've selected two deals. I can recommend a budget
split or you can set it yourself.

↓

User: \> Recommend it.

↓

Agent: \> Suggested split: \> - Prime Video: £10k \> - Sky: £5k \> \>
Use this split?

↓

User: \> Yes.

↓

Agent: \> Great. I'll use this split for the reach forecast.

------------------------------------------------------------------------

# 80. Golden Case F --- Narrow Reach

**User** \> Target only SW1A.

↓

Agent: \> This audience is very narrow for the current budget. Would you
like me to broaden the audience and re-run the forecast?

### Yes

> I'll broaden it and re-check the forecast.

### No

> Understood. I'll keep SW1A as the targeting and show the forecast
> based on that audience.

------------------------------------------------------------------------

# 81. Golden Case G --- User Changes Mind

**User** \> Prime Video, £15k, Oct 1--31, 30s, awareness.

↓

Agent: \> \[Targeting/forecast\]

↓

User: \> Actually make it £20k and target London.

↓

Agent: \> Got it. I've updated the budget to £20,000 and location to
London. I'll regenerate the forecast.

Expected: - Recalculate. - Do not restart campaign. - Do not ask
unrelated fields again.

------------------------------------------------------------------------

# 82. Conversation Quality Rules

The agent should always:

### Do

-   Be concise.
-   Ask one logical decision at a time.
-   Preserve previously supplied information.
-   Use selectable UI where choices are finite.
-   Use tables/cards when comparing inventory/deals.
-   Show forecasts only when supported.
-   Explain unavailable inventory honestly.
-   Let the user reject recommendations.
-   Allow users to change previous decisions.
-   Ask for approval before final strategy creation.

### Don't

-   Ask for fields already provided.
-   Dump the entire inventory list unless requested.
-   Jump directly to audience after inventory selection if core fields
    are missing.
-   Pretend unsupported inventory exists.
-   Fabricate reach curves.
-   Automatically broaden targeting without user agreement.
-   Automatically split a budget without showing the proposed
    allocation.
-   Create a strategy with missing required campaign information.
-   Force the user through a fixed questionnaire when their message
    already contains multiple answers.

------------------------------------------------------------------------

# 83. Recommended Conversation State Machine

``` text
START
  |
  v
Understand user intent
  |
  v
Extract known campaign fields
  |
  v
Inventory specified?
  |----------------------|
 No                     Yes
  |                      |
  v                      v
Recommend/search       Check inventory
inventory                |
                          v
                 Inventory available?
                    |            |
                   No           Yes
                    |            |
                    v            v
             Explain + offer   Continue
             alternatives        |
                    |             |
                    v             v
              User chooses   Check missing
              alternative       core fields
                    |             |
                    v             v
                  Continue   Budget / dates /
                             creative / goal
                                  |
                                  v
                         Unified baseline targeting
                                  |
                                  v
                         Optional targeting/geo
                                  |
                                  v
                        Reach available?
                         |             |
                        No            Yes
                         |             |
                         v             v
                    CPM/impressions  Predict reach
                    where supported       |
                                         v
                                  Reach acceptable?
                                    |        |
                                   No       Yes
                                    |        |
                                    v        v
                              Extend audience
                              + re-predict
                                         |
                                         v
                                  Approve plan
                                    |       |
                                  Edit     Approve
                                    |       |
                                    v       v
                                Re-plan   Create
                                          strategy
```

------------------------------------------------------------------------

# 84. Final Acceptance Criteria

The implementation is considered correct when:

-   A vague user can start naturally.
-   A complete user can skip unnecessary questions.
-   Missing fields are collected progressively.
-   Inventory availability is checked before planning against that
    inventory.
-   Unsupported inventory is handled gracefully.
-   Alternatives are offered without overwhelming the user.
-   Audience is not requested prematurely.
-   Location defaults to the target market where appropriate.
-   Location can be refined through supported methods.
-   `budget_split` appears only when multiple deals are selected.
-   Reach prediction occurs only after the relevant inputs are settled.
-   Unsupported reach curves are not fabricated.
-   Narrow reach triggers an optional audience-extension path.
-   User can accept/reject/edit recommendations.
-   Final plan is shown before strategy creation.
-   Strategy creation happens only after approval/required confirmation.
-   The chat remains conversational rather than behaving like a long
    form.
-   The user can change earlier decisions without restarting the whole
    journey.

------------------------------------------------------------------------

# 85. One-Line Product Rule

> **The VOW Agent should collect only what is missing, make only
> safe/defaultable decisions automatically, ask the user for material
> campaign decisions, validate inventory before planning, forecast only
> when supported, and never create the final strategy until the plan is
> complete and approved.**
