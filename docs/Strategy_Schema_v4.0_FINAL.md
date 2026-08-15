# VOW Platform — Strategy Schema

## Final Specification, version 4.0

| | |
|---|---|
| **Version** | 4.0 |
| **Supersedes** | 1.1.0, 2.0.0, 3.0.0 |
| **Status** | For client sign-off. Implementation-ready except where marked **Open**. |
| **Scope** | Connected TV (`streaming_tv`) only. Display and online video are future scope. |
| **Verified against** | `staging.vowmade.dev`, 4 August 2026. Test strategy `VMA2026368`. |
| **Purpose** | Single reference for building the CTV planning agent. Replaces all earlier revisions. |
| **Contains no code** | Deliberately. This is the specification the implementation is written from, not the implementation. |

---

# 0. How to read this document

## 0.1 Why this version exists

Three revisions preceded this one, and each was reviewed.

**Version 1.1.0** described the six-step UI wizard as it exists in the platform today, covering display, online video and CTV.

**Version 2.0.0** reordered that into an agent-first flow scoped to CTV. It received **28 review comments**.

**Version 3.0.0** restructured the flow again and received **nine further review comments** across four threads. Seven are new positions; two are answers to questions raised in reply.

Separately, a full walkthrough of the live Strategy module was carried out — all nine screens, every field, and all seventeen API calls with their payloads and responses. That produced 177 recorded findings, and a number of them contradict positions held in all three earlier revisions.

This version does four things:

1. Carries forward everything correct from 1.1.0, 2.0.0 and 3.0.0
2. Applies all 37 review resolutions
3. Corrects the specification against what the platform actually does
4. Adds the material that was missing entirely — the domain model, the currency model, the validation rules, and the data contracts

**Section 1 is a full traceability index**, so any earlier comment can be traced to where its resolution now lives.

## 0.2 Evidence markers

Every non-obvious claim carries one of these:

| Marker | Meaning |
|---|---|
| **Verified** | Observed in an API request or response on staging |
| **Observed** | Seen on screen; not confirmed in the API |
| **Inferred** | Reasoned from evidence; not confirmed |
| **Open** | Needs a client answer before it can be built |
| **Contested** | A review position that the platform appears to contradict; evidence stated inline |

Anything unmarked is a design decision recorded here, or a statement carried unchanged from an earlier revision.

## 0.3 How to review this document

- **Section 1** shows what changed and why. Start here if you reviewed an earlier version.
- **Section 11** lists every open decision, ranked. Six of them block implementation.
- **Section 12** lists four data quality issues that cannot be resolved on our side.

Where a position is contested, the evidence for it is stated inline, so the disagreement can be settled on facts rather than on reading.

---

# 1. What changed and where

## 1.1 Review comments on version 2.0 — resolution index

All 28, with the text each was made on and where the resolution now lives.

| # | Comment anchor | Resolution | Section |
|---|---|---|---|
| 1 | "Their own targeting (adds CPM)" | Third-party targeting comes from Amazon DSP **or** the inventory source. A per-deal choice, not a property of the tier. Known only after matching. | 4.3, 4.4 |
| 2 | "added fee consequence" | Fee is driven by the data provider, not the profile. No compounding within a provider; stacking across providers. | 4.4.4 |
| 3 | "Budget split NEW" | Optional. Moved **after** creation — the platform allocates budget itself and exposes it for editing. | 6.11 |
| 4 | "mandatory" (audiences) | Audiences are optional. Declining all three is a valid plan and incurs no data fee. | 6.6 |
| 5 | "Targeting NEW" | Audiences are one kind of targeting. Targeting arrives pre-filled. Geography can substitute for audiences. Partially split by an API constraint — see 5.1. | 6.6, 6.10 |
| 6 | The two v1.1.0 field lists | **Source** column introduced. Requirement and Source are separate questions. The trader is asked for three things. | 5.3 |
| 7 | "Required" (Strategy name) | Generated from the brief. Requirement Optional, Source GENERATED. | 6.4 |
| 8 | "Multi-select" (Target markets) | One market per strategy in M1; the field stays a list. Per-market versus campaign-level split documented. | 3.2, 6.4 |
| 9 | "Required" (Primary currency) | Not asked. **Corrected:** it comes from the advertiser, not derived from the market. | 4.5 |
| 10 | "KPI" | Target value added. **Corrected:** range is 2–5, and it is held per format. | 6.4 |
| 11 | "Table" (Market budgets) | The Type column holds data types throughout. Widgets removed from the whole column. | 6.4, 7 |
| 12 | "Required" (Base bids) | Not asked. **Contested:** floor-rate deals do require a bid, and almost all VOW inventory is floor-rate. | 4.2, 6.4, 11 |
| 13 | "Optional" (Frequency cap) | Advertiser profile defaults introduced as a concept, with a locked flag for brand policies. | 3.5 |
| 14 | "Required" (Formats) | Format is a constant; Prime Video is a channel. **Corrected:** the forecast endpoint treats `prime_video` as a separate supply line. | 4.6, 6.7 |
| 15 | "Required for video" (Product categories) | From the advertiser, else implied from the brief. The "for video" qualifier is dropped. | 6.4 |
| 16 | "Required" (Selling location) | Removed from basics; belongs with tracking. Comes from the advertiser. | 6.14 |
| 17 | "Conditional" (Product ASINs) | Removed from basics. Sent empty at creation, attached later. | 6.14 |
| 18 | "Checkbox table" (Selected deals) | Deals are matched, not selected. Channel and CPM surface, plus tier capability and commercial commitment. **Blocked:** the matching inputs are not available as fields. | 6.5, 11, 12 |
| 19 | "Netflix/Disney" | Same correction as comment 1, second occurrence. | 4.4.6 |
| 20 | "bundles.narrow/balanced/broad" | Does not exist. The agent groups a flat list itself. **New finding:** the suggest flow is already in production use. | 4.4.3, 6.6 |
| 21 | "Optional" (Location) | Defaults to the market's country. `markets` and `location` distinguished. | 6.10 |
| 22 | "Optional" (Device type) | From the advertiser, possibly locked. Format and device type separated. | 3.5, 4.6, 6.10 |
| 23 | "Plan Approval" heading | Reduced to a status change. Manager routing, rejection and the interrupt removed. | 6.8 |
| 24 | "api/strategies" | **Contested and partly reintroduced in 3.0** — see 1.3. Fourteen endpoint corrections applied. | 9, 11 |
| 25 | "Required" (Click-through URL) | Optional. Confirmed on the platform — approved Streaming TV creatives exist with a null URL. | 6.12 |
| 26 | Three approval rows | One status per channel, keyed by data. **Blocked:** platform granularity is creative × market. | 6.13, 11 |
| 27 | "Tracking Setup" heading | No order between the post-creation branches. Activation becomes a join node with an explicit checklist. | 5.1, 6.16 |
| 28 | "Confirm with client" | A strategy can be updated after creation. Guardrails added for fields that carry money. | 6.17 |

## 1.2 Review comments on version 3.0 — resolution index

Nine comments across four threads, received after 3.0 was published. Seven are new positions; two are answers to questions raised in reply.

| # | Comment anchor | What the comment said | Resolution | Section |
|---|---|---|---|---|
| 29 | `FIXED` on the `goal` row | "Defaulted for CTV" | Goal is a **default**, not a constant. Requirement Optional, Source DEFAULTED. The trader can change it. | 4.8, 6.4 |
| 30 | Follow-up on the KPI question | "we would then support those based on the goal. For CTV we don't advise to do non awareness but we should not stop the user selecting an alternative." | KPI options follow the goal. The four non-Awareness KPIs return. **A new behaviour category — advise, do not block.** | 4.8, 6.4 |
| 31 | `List[str]` on the `location` row | "can the user search for locations? we will need to validate a user provided list of postcodes to get location ids. There is also a custom radius location you can create in Amazon from a given address + a numeric value and unit (km / miles) to get a new location id." | Locations are identifiers obtained from a lookup, not free text. Three acquisition paths. | 6.10 |
| 32 | Same row | "there is a list of inclusions and exclusions" | Location holds two lists — include and exclude. | 6.10 |
| 33 | Same row | "this would replace the GB default" | A specified location **replaces** the market-country default rather than adding to it. | 6.10 |
| 34 | Answer to the radius question | "GET /strategies/locations/{market}/ is for searching location and POST /strategies/locations/{market}/ is for creating a new radius location" | Same path, two methods. All three location paths now have endpoints. | 6.10, 9 |
| 35 | `List[str]` on the `device_types` row | "DESKTOP, MOBILE (optional) CONNECTED_TV (required) for streaming_tv" | Three values, uppercase enum form. `CONNECTED_TV` is **required** whenever the format is `streaming_tv`. No `TABLET` value. | 4.6, 6.10 |
| 36 | Same row | "by default either ALL or just CONNECTED_TV (CTV)" | The default is one of two states, set per advertiser — not an arbitrary combination. | 3.5, 6.10 |
| 37 | `Enum` on the `mobile_environment` row | "IOS or ANDROID only relevant if MOBILE device is selected" | The values are operating systems, not app-versus-browser. The field is renamed accordingly. | 6.10 |

## 1.3 Corrections from platform verification

Positions held in earlier revisions that the live platform contradicts. Each is the reason a section here differs from an earlier version.

| Held in an earlier revision | What the platform does | Evidence | Section |
|---|---|---|---|
| Targeting is a pre-creation step | Every targeting endpoint is nested under a strategy identifier, so targeting cannot precede creation. The wizard has no targeting step; it appears under Locations afterwards. | **Verified** | 5.1, 6.10 |
| Budget split is the agent's job, before creation | The platform splits the market budget evenly per format at creation and exposes it for editing in the Planner. | **Verified** — one submitted budget of £10,000 became two allocations of EUR 5,454.55 | 6.11 |
| Currency is derived from the market ISO | Currency is an advertiser default. It is pre-filled before a market is chosen and does not change when one is selected. | **Verified** — a strategy exists with primary currency `NOK` and market `US` | 4.5 |
| Format as the constant `["streaming_tv"]` is sufficient everywhere | The forecast endpoint returns a separate `DSP_PRIME_VIDEO` supply line. Omitting `prime_video` loses it. | **Verified** — 71,120 reach and 212,860 impressions absent without it | 4.6, 6.7 |
| The forecast depends on audiences and targeting | The forecast payload contains four inputs only: flight dates, formats, goal, market budgets. | **Verified** | 6.7 |
| The repair loop widens the audience and re-forecasts | Audience-aware forecast endpoints exist but nothing in the product calls them. | **Verified** | 6.7, 11 |
| A deal carries an inventory tier and a channel | Neither field exists on a deal. Both would require parsing the deal name. | **Verified** | 6.5, 12 |
| Creative approval is per channel | A creative carries market and approval status, with no channel dimension. | **Verified** | 6.13 |
| Audiences are campaign-level | Audiences are nested per market inside the market info array. | **Verified** | 3.2 |
| One flight date range per strategy | Multiple flight ranges are supported, each with its own per-market, per-format budget. | **Verified** — dedicated endpoints exist | 3.1, 6.11 |
| KPI is one value per strategy | KPI and its target value are held per format. | **Verified** | 6.4 |
| Creative durations are 10, 15, 20, 30 | Seven values exist: 10, 15, 20, 30, 40, 45, 60. | **Verified** | 6.4 |
| Audience data fee is £2.00 for Amazon and £1.50 for a third party | Staging returns 1.63 for video and 0.59 for standard display, in GBP. | **Verified** | 4.4.4 |
| KPI target value range is 1–5 | The platform control offers 2, 3, 4 and 5. | **Observed** | 6.4 |

### Endpoints that do not exist

Three endpoints named in version 3.0 are not present in the staging API. Two of them were already corrected in the version 2.0 review and were reintroduced.

| Named in 3.0 | Reality |
|---|---|
| `GET /api/advertisers/{id}/defaults/` | **Does not exist.** Advertiser settings are at `GET /api/admin/advertiser/{id}/` |
| `POST /api/rate-cards/match/` | **Does not exist.** Matching uses `GET /api/deals/` with `GET /api/deals/filter-properties/` |
| `POST /api/strategies/{id}/activate/` | **Does not exist.** Activation is `POST /api/strategies/{id}/set_status/` |

### Two internal inconsistencies in version 3.0

| Issue | Detail |
|---|---|
| **Currency contradicts itself** | Section 1.2 lists primary currency inside the advertiser defaults schema, while the Step 1 field matrix records it as derived from the market ISO. The platform confirms the advertiser reading. |
| **The activation gate ignores two of its own prerequisites** | The readiness condition checks creatives uploaded, creatives approved and credit. It does not check ad tag registration or ASIN attachment, although both are declared fields. A campaign could therefore activate with neither. |

## 1.4 What is new in this version

Material absent from every earlier revision.

| Added | Why it was needed |
|---|---|
| **Section 3 — Domain model.** Hierarchy, per-market versus campaign-level, identifiers, status model | No revision stated how a strategy is actually structured. Several design errors trace back to this gap. |
| **Section 4.5 — Currency model** | Four currency contexts can coexist in one plan. Getting this wrong produces a nine per cent error in every impression estimate. |
| **Section 4.6 — Taxonomies** | Five overlapping classifications exist for what looks like one concept, and the word "channel" carries six meanings across the UI and API. |
| **Section 4.7 — Numeric rules and guards** | Reach cannot be summed; one deal has a zero CPM; currencies mix within a plan. All three break naive arithmetic. |
| **Section 4.8 — Defaults, constants and advised values** | The review established a third category: a value that is pre-filled, overridable, **and** carries advice against overriding. |
| **Section 6.11 — Budget and bid allocation** | The platform's allocation model — per flight range, per market, per format — was undocumented. |
| **Section 6.18 — Sync and failure handling** | Creation does not mean the campaign exists on Amazon. Sync is asynchronous and can fail. |
| **Section 8 — Data contracts** | Verified request and response shapes, so payloads do not have to be reverse-engineered during implementation. |
| **Section 10 — Consolidated validation rules** | Validations were scattered across field descriptions with no single list. |

---

# 2. Core principles

Carried forward from version 1.1.0. All three remain in force.

**Zero-Hallucination Policy.** The agent never invents strategy parameters, metrics, targeting criteria, or deal identifiers. It populates only values verified against the VOW database and REST APIs.

**Self-Filling Form Paradigm.** The agent is a stateful slot-filling engine. Input arriving by chat or as an uploaded brief is parsed into registered slots.

**API-Driven Tool Execution.** Every step maps to an official VOW API endpoint. Where no endpoint exists, that is stated rather than assumed.

## 2.1 A fourth principle, added

**Stated Uncertainty.** Where the agent cannot verify an outcome, it says so rather than presenting an unverified change as a fix. Four cases arise repeatedly:

- Third-party inventory returns no reach forecast, so widening it cannot be shown to have worked
- Floor-rate pricing means the final cost is not known at planning time
- Where an advertiser policy is locked, the agent must name the lever it could not use
- Where a value was defaulted rather than stated, the agent must not present it as something the trader supplied

Zero-Hallucination covers not inventing. This covers not implying.

## 2.2 A separation that governs the whole design

Three sources of truth, and they must not be confused.

| Source | Holds | Changes | Owner |
|---|---|---|---|
| **The VOW API** | Live data — deal CPMs, audience reach, forecasts, advertiser settings | Continuously | The platform |
| **The specification** | Rules — what triggers a fee, what a tier can do, which values are valid | Rarely, by review | This document |
| **The conversation** | What the trader said | Per turn | The trader |

A figure copied from the API into this document goes stale, and the agent would then quote a price that no longer applies. That is why fee rates, CPMs and reach figures appear here only as verified examples, never as specification values.

---

# 3. Domain model

## 3.1 The hierarchy

**Verified** against the create payload and the post-creation screens.

```
Advertiser                        UUID. Scopes everything. Held in the session,
|                                 not passed as a request parameter.
|
+-- Strategy                      id, e.g. VMA2026368  (VMA + year + sequence)
    |
    +-- Flight ranges[]           MULTIPLE ranges are supported, each with its own budget
    |   +-- Market
    |       +-- Format -> budget
    |
    +-- Market info[]             Per market: bid, budget, currency, audience targeting
    +-- Market deals[]            Per market: matched deals
    +-- Assets[]                  Campaign-level
    +-- Targeting                 Written after creation, per market
    |
    +-- Campaigns[]               Created on Amazon DSP by the background sync
        +-- Ad groups[]           Amazon DSP's own structure
```

Two facts shape most of this document:

1. **Market is the organising unit of the payload.** Budget, bid, currency, audiences and deals are all per-market. Everything else is campaign-level.
2. **Flight ranges are a list, not a value.** The full budget granularity is strategy, then flight range, then market, then format.

## 3.2 Per-market versus campaign-level

**Verified** against the create payload.

| Per market | Campaign-level |
|---|---|
| Budget allocated to that market | Flight dates (per flight range) |
| Currency of that market's spend | Goal |
| Base bid | KPI and KPI target value (per format) |
| Matched deals, and therefore the CPM | Creative durations |
| **Audience targeting** | Assets and creatives |
| Available locations — endpoint keyed by market | Product categories |
| Available product categories — endpoint keyed by market | Conversion types |
| Reach forecast | Selected inventory sources |
| Conversion definitions (each carries a market flag) | Tracking, credit check |

**Correction from earlier revisions:** audiences were treated as campaign-level. They are nested inside the market info array, and an audience set carries a single market value rather than a list. Audiences are therefore not shared across markets.

Two entries are easy to miss: the locations and product-category endpoints are both keyed by market, so those lists differ even when the trader's intent does not.

## 3.3 Identifiers

**Verified.**

| Object | Identifier | Notes |
|---|---|---|
| Advertiser | UUID | Session-scoped |
| Strategy | `VMA2026368` | This **is** the id field. There is no separate UUID. |
| Deal | External deal id | At least seven distinct formats in use — see 4.2.4 |
| Audience set | UUID | |
| Audience segment | Amazon id | |
| Asset | UUID | |
| Creative | UUID **and** Amazon id | Two identifiers on one object |
| Location | Numeric location id | Obtained from a lookup — see 6.10 |
| Product category | Long numeric string | Amazon identifier. **Not an integer** — earlier revisions typed it as one |

## 3.4 Status model

**Verified.** A strategy carries **two status fields and five booleans**. They are not interchangeable.

### Lifecycle status

Eight values are exposed in the platform filter:

```
Delivering        Ready to deliver
Out of budget     Inactive
Ended             Archived
Not running       Draft
```

Two exact API values are confirmed: `3_ended` and `6_inactive`. The numbering suggests the following order, **Inferred** from the filter sequence:

```
1_delivering   2_out_of_budget   3_ended
4_not_running  5_ready_to_deliver  6_inactive
```

**Open:** the exact strings for the remaining four.

### Delivery activation status

A separate field recording whether the strategy is delivering, as distinct from where it sits in its lifecycle.

### Five booleans

| Field | Meaning |
|---|---|
| Is draft | Deliberately saved as a draft |
| Is syncing | Background sync to Amazon in progress |
| Is archived | Hidden from the default list |
| Is readonly | Cannot be edited |
| Is automated | Present in the API already. **Open:** is this the agent marker? |

**Important consequence.** `Archived` and `Draft` are **not** lifecycle status values — they are booleans. A draft row carries the lifecycle status `6_inactive`. Logic that reads only the status field will classify a draft as inactive.

**Mutability is state-derived**, not a property. Ended strategies return read-only true; drafts return false.

**Failure reason** is populated when the Amazon sync fails, for example `CAMPAIGN_SYNC_ISSUES`. See 6.18.

## 3.5 Advertiser profile defaults

Introduced by the review comment on the frequency cap and extended by four later comments.

Some settings belong to the advertiser rather than to the campaign. They do not change from one brief to the next, so asking for them each time treats a property of the advertiser as a decision about the campaign.

### Settings identified so far

| Setting | Confirmed by | Locked? |
|---|---|---|
| Frequency cap | Review comment | **Open** |
| Product categories | Review comment | **Open** |
| Selling location | Review comment | **Open** |
| Device types | Review comment | **Open** — the comment reads as a policy |
| Primary currency | **Verified** on the platform — pre-filled independently of the market | No |
| Budget cap | **Inferred** — assumed to behave like the frequency cap | **Open** |
| Brand-safety exclusions | **Inferred** | **Open** |

### The device-types default has exactly two states

Per review comment 36, the default is **either** all three device types **or** Connected TV alone. It is not an arbitrary combination. Which of the two applies is set per advertiser.

```
Default state A:  CONNECTED_TV, DESKTOP, MOBILE      "ALL"
Default state B:  CONNECTED_TV                        "CTV only"
```

The trader may then add or remove Desktop and Mobile, subject to the locked flag. `CONNECTED_TV` cannot be removed while the format is `streaming_tv` — see 6.10.

### When they are loaded

At the start of the session, **before the brief is parsed**.

```
GET /api/admin/advertiser/{id}/
```

The order matters: defaults fill the plan, and anything the brief states overrides them. Reversing it would let defaults overwrite the brief.

**Note:** version 1.1.0 and version 3.0 both specified `/api/advertisers/{id}/defaults/`. That endpoint does not exist.

### Why a plain default is not enough

The review comment on device type noted that some advertisers permit Connected TV only. That reads as a policy rather than a starting point — something the trader should not override, and that the repair loop must not quietly relax when reach falls short.

Each setting therefore records three things:

| Attribute | Purpose |
|---|---|
| **Value** | The default itself |
| **Locked** | Whether it is a brand policy the trader cannot override |
| **Reason** | Shown to the trader when locked, for example "brand policy: CTV only" |

Without the locked flag the agent cannot distinguish a starting point from a rule, and will offer to relax something it is not allowed to touch.

**Open decision D6:** the full list of settings, and which entries are locked. This is the single answer that most changes agent behaviour.

**Open:** what should the agent do when an advertiser has no value set — leave the field empty, or fall back to a platform default?

---

# 4. Business rules

## 4.1 Selling locations and attribution

Carried forward, with the timing corrected.

**On Amazon (endemic).** The advertiser sells on the Amazon marketplace. ASINs required. Enables detail page view, add-to-cart, purchase and ROAS tracking.

**Off Amazon (non-endemic).** The advertiser drives traffic to its own site, app or landing page. ASINs optional, and used to monitor organic Amazon halo sales. Ad tag conversions required for site event tracking.

**Verified on the platform:**

- On Amazon: an invalid ASIN blocks progress
- Off Amazon: the ASIN field is shown but zero ASINs is accepted
- Validation is batched — the trader pastes a comma-separated list and validation runs on submit, not as they type

**Attribution window:** 14-day post-view and post-click. For CTV only post-view is meaningful, since the ad cannot be clicked.

**Where selling location is collected:** the tracking step, not basics. The value itself comes from the advertiser's settings, so the agent already holds it at creation.

## 4.2 Deal types and pricing

### 4.2.1 The three deal types

| Type | Price type | Bid applies | Volume guaranteed | Full budget owed | Can pause |
|---|---|---|---|---|---|
| Preferred | Fixed CPM | No | No | No | Yes |
| Private auction | Floor rate | **Yes** | No | No | Yes |
| Programmatic guaranteed | Fixed CPM | No | **Yes** | **Yes** | **No** |

### 4.2.2 Floor rate versus fixed CPM

This distinction drives several decisions in this document.

```
Fixed CPM    the figure shown is the figure paid
Floor rate   the figure shown is a minimum that must be exceeded;
             the figure paid is determined by the auction and is
             not known at planning time
```

A floor of £22.96 and a fixed price of £15.26 look identical on screen and mean opposite things.

### 4.2.3 What is actually on the platform

**Verified** — 83 deals available for a GB Streaming TV plan.

| Observation | Consequence |
|---|---|
| Almost all deals are private auction with floor-rate pricing — all Netflix, all Freewheel, and some Prime Video | The bid lever exists on almost all inventory. See D3. |
| Some Prime Video deals are preferred with fixed CPM (£15.26, £24.79) | Fixed pricing is the minority case, not the norm |
| No programmatic guaranteed deal was found, although the filter offers it | **Open:** does PG inventory ever appear? |
| The platform blocks progress when base bid is empty, on a pure CTV plan | The agent must supply a bid. See D3. |
| One deal is priced at zero | Division-by-zero guard required. See 4.7. |
| GB deals are priced in USD as well as GBP | Currency normalisation required. See 4.5. |
| South African deals appear in a GB-filtered list | The agent must filter on the deal's own location list |

### 4.2.4 Deal identifier formats

**Verified** — at least seven shapes in use:

```
VIA-159-00100                            structured, sequential
a0f440c9-0159-40bf-aab5-b1108b10614a     UUID
EXT245WE18EEMKX                          Amazon external deal id
apsb8dd1c90                              lowercase alphanumeric
2653736                                  numeric
PM-RDDS-8837                             prefixed alphanumeric
Disney-FAST-SFV-IOA-AZ-2026              descriptive slug
```

The agent cannot validate the **format** of a trader-supplied deal id. It can only attempt a lookup and report whether the deal was found.

### 4.2.5 Deal metadata completeness

**Verified.** Metadata quality differs sharply between Amazon-owned and third-party deals.

| Field | Prime Video (preferred) | Netflix (private auction) |
|---|---|---|
| Genre | `ROS` | Empty |
| Devices | 3 entries with volumes | Empty list |
| Environments | App at 100 per cent | Empty list |
| Media types | Streaming TV video at 100 per cent | Empty list |
| Location bid-request volume | 1,457,882,193 | 1 |

A location volume of 1 is a placeholder rather than a measurement.

**Consequence:** matching on genre, device or environment works on Amazon inventory and does not work on third-party inventory. Deliverability cannot be assessed from volume on third-party deals. See section 12.

## 4.3 Inventory tiers

Three tiers, the primary fork in the CTV flow.

| Tier | Examples | Deal availability | Reach forecast |
|---|---|---|---|
| Amazon owned | Prime Video, Twitch | Pre-curated, selectable now | Available |
| Third-party pre-curated | Netflix, Hulu, Paramount+, Discovery+, Passion+ | Pre-curated, selectable now | Not available |
| Third-party needs curation | Disney+ and others | Rate-card CPM only; the deal is curated after the insertion order is signed | Not available |

**Correction.** The tier table in version 2.0 implied that the targeting source follows from the tier. It does not. Targeting on third-party inventory can come from **either** Amazon DSP **or** the inventory source, and which options exist is specific to the deal that is chosen or curated — so it is known only after matching, not at planning time.

What genuinely differs by tier is two things: whether a reach forecast comes back, and whether the deal exists yet.

Recorded on the plan as a targeting source per deal, with two values: Amazon DSP, or inventory source.

**Open decision D8:** can both run on the same deal? If so the field must hold a list, and the combination rule needs stating — intersection and union have opposite effects on reach.

**Blocked.** No inventory-tier field exists on a deal (**Verified**). The three-tier fork has no data source. See section 12.

**Also relevant:** the inventory-sources endpoint returns `Twitch` alongside `Amazon Streaming TV` for a GB Streaming TV awareness plan (**Verified**). Amazon-owned CTV inventory is not only Prime Video, and Twitch carries a materially different audience.

### 4.3.1 Curation capture

For the needs-curation tier, where deals cannot be selected yet, the agent records what VOW needs in order to curate later: genres, durations, targeting preferences, budget and flight dates.

This pattern — record the requirement rather than select the deal — is what the review asked for across all tiers. It was already present here and simply not applied where deals do exist.

### 4.3.2 Genre upsell

Client requirement, carried forward: based on the brief, the agent can suggest that a specific available genre would be a better match at a slightly higher CPM. The example given was Prime Video run-of-service at $18.22 against Action at $22.07.

**Dependent on D4.** With the genre field in its current state this cannot be built — see section 12.

### 4.3.3 Channels and exchanges are different things

The platform names nine channels: Amazon Prime Video, Disney+, Multilocal, Discovery+, Paramount+, Hulu, Netflix, Pubmatic, Passion+.

These are not the same kind of thing:

```
Streaming services   Prime Video, Netflix, Disney+, Hulu, Paramount+, Discovery+, Passion+
Supply platforms     Pubmatic, Multilocal, and in the data also Freewheel, Magnite
```

"This deal is on Netflix" is useful to a trader. "This deal is on Freewheel" names the pipe, not the content. Where the agent surfaces a channel it should surface the streaming service, not the exchange.

Eight exchanges appear in the filter: DRAX Web Video, Freewheel Video, Pubmatic Web Video, Netflix Web Video, Magnite Streaming Web Video, Prime Video ads, Microsoft Monetize, Amazon Publisher Direct.

## 4.4 Audience model

### 4.4.1 Structure

**Verified.** Fifteen audience sets are available for the test advertiser — not the approximately 3,400 figure quoted in version 1.1.0, which refers to individual **segments** held inside sets.

An audience set carries: identifier, name, market (a single value), goal, a natural-language prompt, a nested boolean group tree, an audience count, a reuse count, a standard display fee, a video fee, and a fee currency.

**Two implementation notes:**

- The boolean group tree is held as a **JSON string, not an object**. It requires two parse passes.
- The standard display fee can be an **empty string**, not null. Naive numeric parsing will fail.

### 4.4.2 The boolean tree

**Verified.** Segments are held in a nested tree of groups, each with an AND or OR operator, up to four levels deep. The structure of one set:

```
AND
+-- OR    Presence of children, Presence of children aged 5-11, 1 child
+-- AND
    +-- OR    Females
    +-- AND
        +-- OR    Age 36-40, Age 36-45 (high reach)
        +-- OR    Healthy Food, Healthy Lifestyle, Health Conscious,
                  Gluten Free, Diet and Nutrition, and 12 others
```

Read: households with young children **and** female **and** aged 36–45 **and** interested in healthy food.

**Consequence for the repair loop.** Widening the audience is not one operation. It is either adding a term to an OR or removing an AND branch, and the two have very different effects on reach. The agent needs to state which it did.

### 4.4.3 The suggest flow

**Correction from version 1.1.0.** There is no bundled narrow, balanced and broad object. The endpoint returns a flat list of segments with reach and relevance, and the grouping into three profiles is ours to do.

**New finding, Verified.** Audience sets carry a natural-language prompt, populated on sets created through the suggest flow. Two examples found on staging:

```
"Mums looking for healthier snacks for their kids school lunch boxes"
"find me audiences who are most likely to buy car accessories for luxury cars"
```

**This changes what the agent's job is at this step.** It writes a prompt; it does not browse segments or assemble boolean groups. Existing prompts are also usable as reference material, and reusable where an existing set matches.

**Grouping rule — proposed, pending a response sample.** Group by cumulative reach; keep the groups nested, so balanced contains narrow and wide contains balanced; and add segments until each group meets a reach target rather than a fixed segment count, so the profiles stay comparable across briefs of different sizes.

**Open decision D2:** a real request and response from the suggest endpoint. The grouping rule, the fee handling and the audience schema all depend on the actual shape.

### 4.4.4 Fees

Three rules, from the review comment.

1. **What triggers a fee** — using first-party data, whether Amazon's own or a third party's own first-party audience such as Lifestyle or Interest. This holds regardless of profile.
2. **No compounding** — one fixed CPM applies when first-party data is used, however many segments are selected from that provider.
3. **Cross-provider stacking** — where a segment is matched in both Amazon and a third-party provider, both fees are paid.

Recorded on the plan as the set of data providers in play, not as a segment count.

**Which categories carry a fee — Verified.** Six audience categories exist. Fee follows the category:

```
Free    Demographic, Device
Paid    In-market, Lifestyle, Interest, Custom-built
```

Sets containing only Demographic or only Device segments return a zero video fee. Sets containing any paid category return the same fee whether they hold 1 segment or 32 — confirming rule 2.

**Two exceptions found**, both with zero segments, so **Inferred** to be data errors rather than counter-examples.

### 4.4.5 Fee rates are read, not specified

**Verified staging values:** 1.63 for video and 0.59 for standard display, both GBP.

**These are examples, not specification values.** Version 3.0 recorded £2.00 for Amazon and £1.50 for a third party. Both figures are wrong against staging, and a figure written into a specification goes stale regardless.

```
GET /api/contextual-targeting/fees                       returns the rates
POST /api/audiences/{market}/overlapping-audiences/       detects the rule-3 case
```

### 4.4.6 Constraints for CTV

- Amazon audiences can be applied to third-party inventory as well as Amazon-owned. The inventory source's own targeting is the alternative, not the only option.
- Product audiences are not applicable to CTV.
- AMC audiences are conditional — available only where the advertiser has prior campaign data. Endpoint: `POST /api/audiences/amc-audiences/`.
- The agent uses the suggest endpoint. Nobody browses segments.
- The audience set does not need to exist before forecasting — and in fact the forecast takes no audience input at all (**Verified**, 6.7).
- The audience list is **not** filtered by goal (**Verified** — a conversion-goal set was returned for an awareness strategy). The agent must filter if filtering is wanted.

### 4.4.7 Profiles

| Profile | Description |
|---|---|
| Narrow | Highly targeted, elevated intent, risk of underdelivery |
| Balanced | Optimal blend; the usual recommendation |
| Wide | Broad demographic and interest reach, less precision |

Renamed from "Broad" to "Wide" per client vocabulary.

**The three profiles differ in reach and precision, not in cost.** This follows from the fee rules above. They are a way of presenting one flat list at three levels of breadth, not an API feature with three price points.

**Match type:** similar or exact, with exact as the default.

## 4.5 Currency model

**New section.** Four currency contexts can coexist in one plan.

| Context | Example |
|---|---|
| Strategy currency | `EUR` |
| Market currency | `GBP` |
| Deal currency | `GBP` **and** `USD` in the same list |
| Metrics display currency | `USD` |

**Correction.** Currency is **not** derived from the market. It is an advertiser default.

**Verified:**
- The field is pre-filled as EUR before any market is selected
- Selecting United Kingdom does not change it
- A strategy exists with primary currency `NOK` and market `US`

The trader can override it.

**Conversion is real and applied by the platform. Verified:**

```
Market view      £10,000        base bid £25
Primary view     EUR 10,909.09  base bid EUR 27.27
Rate             approximately 1.0909 GBP to EUR
```

Both figures are genuine and both are sent — the market currency in the market info array, and the strategy currency as the primary currency.

**Implementation rule.** All arithmetic must be performed in one currency, and the agent must state which. Mixing a budget in one currency with a CPM in another produces a nine per cent error at this rate:

```
Wrong    10,909.09 / 22.96 x 1000 = 475,178 impressions
Right    10,000.00 / 22.96 x 1000 = 435,540 impressions
Error     39,638 impressions
```

**Open:** the currency enumeration holds only EUR, GBP and USD. `NOK` exists in production data. The enumeration needs extending, or those advertisers are out of scope.

## 4.6 Taxonomies

**New section.** Five overlapping classifications exist for what appears to be one concept. This is the largest single source of confusion in the earlier revisions.

| Taxonomy | Values | Where it applies |
|---|---|---|
| Formats | display, online_video, streaming_tv, prime_video (plus netflix, disney+ in the list filter only) | Strategy, deals query, forecast |
| Asset target types | DISPLAY, VIDEO, STREAMING_TV, MOBILE | Assets |
| Deal media types | VIDEO_STV, VIDEO_OLV | Deals |
| Creative type | "Video", "Streaming TV Video" | Creatives |
| Forecast supply | DSP_STREAMING_TV, DSP_PRIME_VIDEO | Forecast response |

### 4.6.1 Format versus channel

Format is always `streaming_tv` for CTV. Prime Video is a channel, not a format.

```
Format    the kind of inventory          streaming_tv
Channel   who is showing the ad          Prime Video, Netflix, Disney+, Channel 4
```

The Prime Video format value is retained but deprecated rather than removed, since deleting it is a breaking change for anything already sending it.

**Correction, Verified.** The forecast endpoint treats formats as a set of **supply-line keys**, not as a content type. Sending both `streaming_tv` and `prime_video` returns two supply lines; sending `streaming_tv` alone omits the Prime Video line and loses 71,120 reach and 212,860 impressions.

| Endpoint | Does `prime_video` matter |
|---|---|
| Inventory sources | No — the same two Amazon sources are returned either way (**Verified**) |
| Reach forecast | **Yes** — a separate supply line (**Verified**) |
| Deals | Passed as a filter; effect untested |

**Implementation rule:** the model holds `streaming_tv` and a channel. The **forecast request** must send both values where Prime Video inventory is in the plan.

### 4.6.2 Format versus device type

Two things earlier revisions blended.

| | What it is | Where it is decided |
|---|---|---|
| Format | The kind of content — streaming video | A constant for CTV |
| Device type | The screen the ad plays on | The advertiser's setting |

Streaming content is not watched only on television sets. Prime Video runs on phones and desktop browsers, all of which remain `streaming_tv`.

**Review comment 35 confirms this** by allowing `DESKTOP` and `MOBILE` alongside `streaming_tv`.

**`streaming_tv` does not mean a television screen.**

### 4.6.3 Device type values

**Per review comment 35, Verified against the deals filter.**

| Value | Requirement for `streaming_tv` |
|---|---|
| `CONNECTED_TV` | **Required.** Cannot be removed |
| `DESKTOP` | Optional |
| `MOBILE` | Optional |

**There is no `TABLET` value.** Earlier revisions and the deals filter both suggest four device types; the filter's fourth value is `UNKNOWN`, which is a data artefact rather than a targeting option.

### 4.6.4 The word "channel"

Six distinct meanings across the UI and API:

| Term | Where | Values |
|---|---|---|
| "Channel type" | Strategy overview | On Amazon / Off Amazon |
| "Channels" column | Strategy list | On Amazon / Off Amazon |
| "Location" filter | Strategy list | On Amazon / Off Amazon |
| Product location | Strategy record | Sold on Amazon / Not sold on Amazon |
| Channel type | Strategy record | dsp / sponsored |
| "Strategy type" | Strategy overview | DSP |

**The UI labels are inverted relative to the API.** What the UI calls "Channel type" is the API's product location. What the API calls channel type appears in the UI as "Strategy type".

Separately, the deal schema's "provider" field has been renamed to "channel" per the review, with one caveat: "provider" survives in the audience context, where it means a **data** provider. Channel is who shows the ad; data provider is whose audience data is being paid for.

**Recommendation:** use the API's names in code and reserve the UI's labels for display.

## 4.7 Numeric rules and guards

**New section.** Four rules that naive arithmetic gets wrong.

### 4.7.1 Reach cannot be summed across supply lines

**Verified:**

```
Streaming TV supply   estimated reach  132,713
Prime Video supply    estimated reach   71,120
Sum                                    203,833
API total reach                        233,803       higher than the sum
```

There is no cross-platform deduplication, and the API's own total is not the sum. **Always report the API's total. Never derive it.**

**Impressions do sum**, and match exactly: 647,856 plus 212,860 equals the API total of 860,716.

**Across markets** reach can be added, since the audiences do not overlap.

### 4.7.2 Frequency must be derived

The forecast does not return frequency.

```
frequency = total impressions / total reach
          = 860,716 / 233,803
          = 3.68
```

**The window is per week**, not per flight (**Observed** — the platform's own label). A target of 3 means three exposures per person per week.

### 4.7.3 Effective CPM, not deal CPM

```
effective CPM = deal CPM + audience data fee
```

```
Deal CPM only        10,000 / 22.96 x 1000 = 435,540 impressions
Effective CPM        10,000 / 24.59 x 1000 = 406,669 impressions
Difference                                    28,871  (7 per cent)
```

Quoting impressions from the deal CPM overstates the plan by the size of the fee.

### 4.7.4 Guards required

| Guard | Why |
|---|---|
| Deal price of zero | One deal is priced at 0.00. Division by zero |
| Currency equality before arithmetic | GBP and USD deals appear in the same list; the plan may be in EUR |
| Empty-string fee | The standard display fee returns an empty string on some sets, not null |
| Ad-length deduplication | The filter-properties endpoint returns 16 entries with 7 distinct values |
| Deal location filter | South African deals appear in a GB-filtered list |
| Money and rates as strings | All money and rate fields are strings, for example "3.64" and "0.00000" |

### 4.7.5 Metrics that cannot be trusted

**Observed:** a video completion rate of 128.45 per cent appears in staging data. A completion rate above 100 per cent is not meaningful. The agent should report platform metrics rather than recompute or reason from them.

## 4.8 Defaults, constants and advised values

**New section**, arising from review comments 29 and 30.

Earlier revisions used two categories. A third is now required.

| Category | Trader can change | Agent comments | Example |
|---|---|---|---|
| **Constant** | No — no other value exists | Nothing to say | Format is `streaming_tv` |
| **Default** | Yes | Nothing | Currency, frequency cap, location |
| **Advised default** | Yes | **States the recommendation and the reason** | Goal is Awareness |

### The goal is an advised default

Review comment 29 corrected the goal from a constant to a default. Review comment 30 established the behaviour:

> "For CTV we don't advise to do non awareness but we should not stop the user selecting an alternative."

So the agent must do three things, not two:

1. Default the goal to Awareness
2. Accept a change to Consideration or Conversion — never block it
3. **State that non-Awareness is not advised for CTV, and why** — tracking further down the funnel is unreliable on streaming inventory

Silently accepting the override is as wrong as refusing it.

### KPI options follow the goal

Review comment 30 also reinstates the four KPIs that version 2.0 removed. The KPI list is conditional on the goal rather than fixed.

| Goal | KPI options |
|---|---|
| Awareness | Reach, Frequency |
| Consideration | **Open** — which of CTR, CPC, CPDPV |
| Conversion | **Open** — which of CPA, and whether ROAS |

**Open decision D12:** the goal-to-KPI mapping. Preferably read from `GET /api/strategies/choices/` or the formats-and-KPIs model rather than specified here, so it stays data.

### Locked settings are a fourth case

A locked advertiser setting is a default the trader **cannot** change — see 3.5. It differs from a constant in that the value varies by advertiser, and from a default in that it cannot be overridden.

```
Constant          one value exists, for everyone
Default           pre-filled, changeable
Advised default   pre-filled, changeable, agent comments on the change
Locked default    pre-filled per advertiser, NOT changeable
```

---

# 5. The flow

## 5.1 Flow order, and the two constraints that set it

Version 2.0 reordered the wizard sequence into an agent-first flow, and version 3.0 refined it further. Two of those steps cannot be executed in the position given, and the platform walkthrough established why.

### Constraint 1 — targeting cannot precede creation

**Verified.** Every targeting endpoint is nested under a strategy identifier:

```
GET/POST   /api/strategies/{id}/targeting/
POST       /api/strategies/{id}/targeting/auto-rec/
GET/POST   /api/strategies/{id}/targeting/{market}/locations/
GET/POST   /api/strategies/{id}/targeting/{market}/product-categories/
GET/POST   /api/strategies/{id}/targeting/{market}/products/
```

Each requires a strategy that already exists. The wizard has no targeting step; targeting appears under **Locations** on the strategy overview after creation.

### Constraint 2 — budget allocation happens at and after creation

**Verified.** The trader submits one budget per market. The platform splits it evenly across formats at creation and exposes both budget and bid for editing in the Planner. One submitted market budget of £10,000 became two allocations of EUR 5,454.55.

### The corrected order

```
PHASE A  -  PLAN                    nothing is persisted; all agent-side state
  1  Basics
  2  CTV inventory (deals matched)
  3  Audiences
  4  Reach forecast
  5  Finalise plan

PHASE B  -  CREATE                  one request
  6  Create the strategy

PHASE C  -  ATTACH                  parallel branches, no order between them
  7  Targeting
  8  Budget and bid allocation
  9  Creative upload
 10  Creative approval
 11  Tracking setup
 12  Credit check

PHASE D  -  ACTIVATE                join node
 13  Activate
```

**Phase A is ordered and cannot be rearranged.** Inventory determines the CPM; the CPM determines the impressions; the forecast needs the budget and the formats. It is a genuine chain.

**Phase C has no internal order.** This follows the review comment on the tracking step. Creatives arrive from an agency and are often late; an ad tag has to be installed by the advertiser's own developers, which can take days; credit is a finance matter. Forcing an order means one late item blocks everything.

### Mapping from earlier revisions

| v2.0 step | v3.0 step | v4.0 step | Change |
|---|---|---|---|
| 1 Basics | 1 Strategy details | 1 Basics | Position unchanged |
| 2 CTV inventory | 2 Inventory and matching | 2 CTV inventory | Position unchanged |
| 3 Budget split | 2 (substep) | **8** Budget and bid allocation | Moved to Phase C — the platform allocates |
| 4 Audiences | 3 Unified baseline targeting | 3 Audiences | Split from targeting by an API constraint |
| 5 Targeting | 3 (same step) | **7** Targeting | Moved to Phase C — API constraint |
| 6 Predict reach | 4 Forecast and repair | 4 Reach forecast | |
| 7 Plan approval | 5 Finalise plan | 5 Finalise plan | Renamed in 3.0; carried forward |
| 8 Create | 6 Create strategy | 6 Create the strategy | |
| 9 Upload creative | 7 Branch A | 9 Creative upload | Explicitly parallel |
| 10 Creative approval | 7 Branch A | 10 Creative approval | Explicitly parallel |
| 11 Tracking setup | 8 Branch B | 11 Tracking setup | Explicitly parallel |
| 12 Credit check | 9 Branch C | 12 Credit check | Explicitly parallel |
| 13 Activate | 10 Join node | 13 Activate | Join node with a corrected checklist |

### A note on the audience and targeting merge

Review comment 5 established that audiences are one kind of targeting and the trader should deal with one subject, not two. Version 3.0 merged them into a single step, which is right for the trader's experience.

**But the API splits them.** Audience selection goes into the create request as part of the market info array, whereas geographic and device targeting can only be written after creation.

So steps 3 and 7 are **one subject presented once, executed in two places**. The conversation should not expose that seam.

**Open decision D1** covers whether this split is acceptable.

## 5.2 What the trader is asked

Review comment 6 asked for two things: cut what does not apply to CTV, and imply the rest. The result:

### Asked outright — three things, and only when the brief does not state them

```
Market        Budget        Flight dates
```

### Asked conditionally — two

```
Creative durations       where the brief does not state them, and see D13
KPI target value         only where the KPI is frequency
```

### Presented as a choice — one

```
Audience         three options, or none. See 6.6
```

**Everything else** is generated, derived, taken from the advertiser's settings, constant for CTV, read from an API, or matched by the agent.

## 5.3 Source definitions

Earlier revisions had only a Requirement column, and "Required" was widely read as "the trader must be asked". Those are two separate statements. A field can be required by the plan and never put to the trader as a question.

```
Requirement   does the plan need a value?
Source        where does that value come from?
```

| Source | Meaning |
|---|---|
| `ASKED` | The agent asks the trader outright |
| `INFERRED` | Read from the brief; asked only when the brief does not say |
| `DERIVED` | Calculated from another field |
| `GENERATED` | Composed by the system |
| `ADVERTISER` | Pre-filled from the advertiser's profile |
| `CONSTANT` | One value exists for CTV; not a question |
| `DEFAULTED` | Pre-filled, and the trader may change it |
| `ADVISED` | Pre-filled, changeable, and the agent states its recommendation |
| `API` | Pre-populated from an API response |
| `MATCHED` | Worked out by the agent from what the plan already knows |
| `PLATFORM` | Set by the platform, not by the agent |

Three of these are new in this version. `CONSTANT` replaces the earlier `FIXED` to avoid the reading that caused review comment 29. `DEFAULTED` and `ADVISED` capture the distinction that comment established. `PLATFORM` covers values the server sets, such as the per-format budget allocation and the two brand-safety flags.

---

# 6. Step specifications

Each step gives its goal, its field matrix, its validations, the APIs it calls, and what the trader sees.

## 6.1 How to read a field matrix

| Column | Meaning |
|---|---|
| **Field** | The name used in the payload |
| **Type** | What the field holds. Not how it is drawn — review comment 11 |
| **Requirement** | Required, Optional, Conditional, or a dash where the plan holds it but never asks |
| **Source** | Where the value comes from — see 5.3 |
| **Default** | The value present before the trader touches anything |
| **Validation** | The rule that must hold |

---

## PHASE A — PLAN

Nothing in Phase A is persisted. Every value is agent-side state until step 6.

---

## 6.2 Step 1 — Basics

**Goal.** Capture the minimum from the brief, and fill everything else from the advertiser, from the market, or from what is constant for CTV.

### Field matrix

| Field | Type | Requirement | Source | Default | Validation |
|---|---|---|---|---|---|
| Strategy name | String | Optional | `GENERATED` | Composed from the brief | Must be unique for the advertiser. On collision, append a version suffix and re-check |
| Flight dates | List of date ranges | Required | `INFERRED` | — | Start on or after today; end after start. **Multiple ranges supported** — see 6.11 |
| Target markets | List of ISO country codes | Required | `INFERRED` | — | One market per strategy in M1; field stays a list. **Only `GB` and `US` exist on the platform** |
| Primary currency | Currency code | Optional | `ADVERTISER` | The advertiser's setting | One of EUR, GBP, USD. **`NOK` exists in production — see 4.5** |
| Creative durations | List of integers | Conditional | `INFERRED` | — | One of 10, 15, 20, 30, 40, 45, 60. **Seven values, not four.** See D13 |
| Goal | Enumeration | Optional | `ADVISED` | `AWARENESS` | One of Awareness, Consideration, Conversion. **Agent advises against non-Awareness but does not block it** — see 4.8 |
| KPI — **per format** | Enumeration | Required | `INFERRED` | Reach | Options depend on the goal — see 4.8. Held per format |
| KPI target value — **per format** | Integer | Conditional | `ASKED` | — | 2 to 5 inclusive. Applies only where the KPI is frequency. **Range is 2–5, not 1–5** |
| Market budgets | Decimal, one per market | Required | `INFERRED` | — | Greater than zero |
| Market currency | Currency code | Required | `DERIVED` | From the market | GB gives GBP, US gives USD |
| Base bid | Decimal, one per market | **Required** | `ASKED` or `DERIVED` | — | Greater than zero. **Contested — see D3.** The platform blocks progress when empty, even on a pure CTV plan |
| Frequency cap | Integer | Optional | `ADVERTISER` | The advertiser's setting | Per week. May be locked |
| Budget cap | Decimal | Optional | `ADVERTISER` | The advertiser's setting | **Inferred** to behave like the frequency cap |
| Formats | List of enumeration | — | `CONSTANT` | `streaming_tv` | **The forecast request must also send `prime_video`** where Prime Video inventory is in the plan — see 4.6.1 |
| Video product categories | List of strings | Required | `ADVERTISER` then `INFERRED` | The advertiser's setting | Long numeric strings, not integers. Only leaf subcategories are selectable |
| Product categories | List of strings | — | `CONSTANT` | Empty | Display only; empty for CTV |
| Conversion types | List of strings | Optional | `ASKED` | — | Four events: page view, add to cart, checkout, application. Each carries a market flag |
| Selected inventory sources | List of objects | Optional | `API` | The pre-flight result | Presented as removable, not as a question |

### Removed from this step

Selling location and product ASINs, both moved to tracking (6.14). The three non-CTV format options. Base bid as a trader-facing question, subject to D3.

### Strategy name convention

```
{Category}_{Market}_{Goal}_{MonthYear}      for example  Education_GB_Awareness_Sep2026
```

On a uniqueness collision the agent appends a version suffix and re-checks rather than stopping to ask.

**Open:** do traders already use a naming convention? Generating names in a different shape would make their own lists harder to scan.

### Pre-flight feasibility checks

**Verified.** Four calls fire when formats are selected. They establish whether there is anything workable in the market before the trader invests effort.

| Check | Endpoint | Returns |
|---|---|---|
| Audience sets exist | `GET /api/audience-sets/check_market_has_audience_set/` | Market and an exists flag, as an array |
| Creative recommendations exist | `GET /api/creatives/recs/check_market/` | Same shape |
| Assets exist and are DSP-approved | `GET /api/assets/check_market_has_assets/` | One entry per creative type |
| Inventory sources available | `GET /api/inventory-sources/` | Name, type and formats per source |

All four accept comma-separated markets and return an array, so a multi-market plan needs one call each rather than one per market.

**Two notes:**

- The assets check passes a DSP-approved flag. An asset existing is not sufficient; it must be approved.
- The inventory-sources call passes the **goal**. Available inventory therefore depends on the goal — which matters now that the goal is changeable (4.8).

### Product category cross-check

ASIN validation returns a product category alongside each valid ASIN. ASINs are collected at tracking, well after this step, so that category cannot populate this field — but it is worth using as a cross-check. If the advertiser is set to Education and the ASINs return Electronics, the agent should say so.

**Open decision D6:** is the advertiser-level value a product **category** or an **industry**? The advertiser endpoints expose industry choices, while product categories come from a different taxonomy. If the advertiser holds an industry, a mapping is required and does not exist anywhere.

### APIs called

```
GET /api/admin/advertiser/{id}/                              (session start)
GET /api/strategies/check_strategy_name_uniqueness/
GET /api/contextual-targeting/{market}/product-categories/
GET /api/audience-sets/check_market_has_audience_set/
GET /api/creatives/recs/check_market/
GET /api/assets/check_market_has_assets/
GET /api/inventory-sources/
GET /api/conversions/definitions/                            (off-Amazon advertisers)
GET /api/strategies/choices/                                 (enumerations, incl. goal-to-KPI mapping — see D12)
```

### What the trader sees

The agent confirms what it understood, separated from what it set:

```
From your brief:    market, budget, flight dates, durations
Set for you:        currency (advertiser default), goal (Awareness — the CTV default),
                    format, frequency cap (advertiser default)
```

**The two must be visually separate.** Presenting a defaulted value under "here is what I understood" claims the trader said something they did not — which is the class of error principle 2.1 exists to prevent.

---

## 6.3 Step 2 — CTV inventory

**Goal.** Match deals from the brief rather than presenting a table. Review comment 18 reversed the direction of this step.

### Field matrix

| Field | Type | Requirement | Source | Validation |
|---|---|---|---|---|
| Channel | List of strings | Optional | `INFERRED` | Which providers to run on. **This is the strategic choice**; the deal underneath it is not. **Blocked** — no channel field exists on a deal |
| Run-of-service or genre | String | Optional | `INFERRED` | Used to narrow the match. **Blocked** — the genre field is unusable, see section 12 |
| Selected deals | List of deal objects | Required | `MATCHED` | Matched on market, duration and channel, plus optional genre and the targeting requirements. At least one |
| Specific deal id | String | Optional | `ASKED` | Escape hatch. Format cannot be validated — see 4.2.4. Lookup only |
| Inventory tier — per deal | Enumeration | Required | `DERIVED` | **Blocked** — no source exists, see section 12 |
| Targeting source — per deal | Enumeration | Optional | `MATCHED` | Known only after matching. **Blocked** — capability is encoded in the deal name |
| Curation requirements | Object | Conditional | `ASKED` | Required for the needs-curation tier only — see 4.3.1 |

### What the trader decides, and what the agent works out

Choosing Prime Video over Netflix is a real decision. Choosing between two deal identifiers is not. The trader supplies the channel, optionally a genre or run-of-service, and the targeting they want; the agent matches and returns what fits.

### What is surfaced

Channel, effective CPM, and estimated impressions. Not deal identifiers, not raw deal names.

### Three things must surface even though the deal does not

| What | Why |
|---|---|
| **Tier capability** | Third-party tiers return no reach forecast. If only the CPM is shown, the trader has no way to know that the reach figure is missing for part of the plan |
| **Commercial commitment** | A programmatic guaranteed deal owes the full budget and cannot be paused. Hiding the deal must not hide that. The agent states it before the trader accepts the CPM |
| **Price certainty** | A floor rate and a fixed price look identical as a number and mean opposite things. Almost all VOW inventory is floor-rate, so the default case is the uncertain one |

The third is new in this version.

### What can and cannot be matched on

**Verified** against the deal payload.

| Matching input | Available | Notes |
|---|---|---|
| Market | Yes | From the deal's own location list |
| Duration | Partly | Ad lengths present, but empty on third-party deals |
| Channel | **No** | Only inside the deal name |
| Inventory tier | **No** | Field does not exist |
| Genre | **No** | Field exists but is unusable — see section 12 |
| Amazon-audience capability | **No** | Encoded in the deal name |
| Device | Partly | Populated on Amazon deals, empty on third-party |
| Volume | Partly | Real on Amazon deals, placeholder on some third-party |

**Open decision D4** is the consequence: two of the three stated matching inputs are not available as fields. This is the one answer that determines whether this step can be built as specified.

### A note on the deals query

**Verified.** The platform's own query pads two values:

```
markets = GB,ZZ                                  ZZ = unknown market
formats = streaming_tv,prime_video,UNKNOWN       UNKNOWN = missing format
```

These include deals whose metadata is incomplete. **The agent should replicate this**, or deals with missing metadata will be silently excluded.

### APIs called

```
GET /api/deals/
GET /api/deals/filter-properties/
GET /api/rates/ctv/{market}/
```

**Open:** when several deals match, how should the agent choose — cheapest CPM, largest volume, or best genre fit? This is a commercial judgement and needs a stated rule, because it applies to every plan.

**Open:** when nothing matches, should the agent widen the duration, drop the genre, or report back and ask?

**Open:** should a programmatic guaranteed deal ever be matched automatically, given the budget commitment?

---

## 6.4 Step 3 — Audiences

**Goal.** Offer three options and let the trader choose, or decline. Optional, per review comment 4.

### Field matrix

| Field | Type | Requirement | Source | Validation |
|---|---|---|---|---|
| Audience prompt | String | Optional | `GENERATED` | Natural language, composed from the brief. **This is how the platform's own suggest flow works** — see 4.4.3 |
| Audience options | Three profiles | Optional | `API` | Agent groups the flat suggest result into narrow, balanced and wide |
| Chosen option | Enumeration | Optional | `ASKED` | Narrow, balanced, wide, or none. **None is a valid plan** |
| Match type | Enumeration | Conditional | `ASKED` | Similar or exact; exact by default. Applies only where an audience is chosen |
| Audience data sources | List of enumeration | Required | `DERIVED` | Which providers are in play. Drives the fee — see 4.4.4 |
| Effective CPM per option | Decimal | Read-only | `DERIVED` | Deal CPM plus audience fee, shown per option |

### Declining all three is a valid plan

It is a run-of-service baseline, and because no first-party data is used it incurs no data fee — so it is the cheapest option, not a degraded one.

**Consequence for the repair loop.** Widening the audience is one of the levers used when reach falls short. Where no audience has been chosen that lever does not exist, and the agent should say plainly when it has nothing left to relax.

### The agent must not choose on the trader's behalf

Three options presented and then one silently selected is the same failure as refusing the choice. Where the trader answers ambiguously — "ok", "sounds good" — the agent asks again rather than defaulting.

### What is sent at creation

Audience selection is part of the create request, nested per market. See 8.2.

### APIs called

```
GET  /api/audience-sets/                             list existing sets
POST /api/audience-sets/suggest/                     returns an identifier
GET  /api/audience-sets/suggest/{id}/                read the result
GET  /api/contextual-targeting/fees                  read the fee rate, never assume it
POST /api/audiences/{market}/overlapping-audiences/  detect cross-provider overlap
POST /api/audiences/amc-audiences/                   retargeting, where prior campaign data exists
```

**Open decision D2** — a real request and response from the suggest endpoint. Also: the request model is named for groups; does that mean the caller can request a number of groups? And how long does the asynchronous call take, since that decides whether the agent waits in the conversation.

---

## 6.5 Step 4 — Reach forecast

**Goal.** Forecast where a forecast is possible, and state plainly where it is not.

### What the endpoint actually takes

**Verified.** This is materially narrower than every earlier revision assumed.

**Four inputs only:** flight dates, formats, goal, and market budgets. **No deals, no audiences, no targeting.**

Note that this endpoint names the bid differently from the create endpoint — see 8.1 and 8.2.

### What it returns

**Verified.** A total reach, a total impressions figure, and per market a list of supply lines. Each supply line carries an estimated and a maximum figure for reach and impressions, plus an average and a maximum CPM.

### Five things this response establishes

| Finding | Consequence |
|---|---|
| **Supply lines are keyed by format** | `prime_video` must be sent or its line is absent — see 4.6.1 |
| **Budget is split by the endpoint**, and not evenly | 4,931.71 and 5,068.29 against a £10,000 budget. This is an optimisation, and it differs from the even split the platform stores at creation (6.11) |
| **Estimated and maximum pairs give the deliverability ceiling** | This is what the repair loop needs. Where estimated reach already equals maximum reach, no lever will help |
| **The forecast CPMs are not the deal CPMs** | Selected deals were £24.79 and £34.80; the forecast returned £7.60 and £23.98. A blended supply average against a specific deal price — a different concept, not an error |
| **Impressions sum; reach does not** | See 4.7.1 |

### Fields presented to the trader

| Field | Availability |
|---|---|
| Estimated impressions | All tiers |
| Indicative CPM | All tiers |
| Estimated unique reach | Amazon-owned only |
| Average frequency | Amazon-owned only, derived |
| Reach curve | Amazon-owned only |
| Maximum available reach | Amazon-owned only |

### The honesty rule for third-party inventory

For Netflix, Disney+ and other third-party tiers the agent shows the rate-card CPM and derived impressions, states explicitly that reach is unavailable and why, and never invents a reach figure.

Consequences: the repair loop applies only to the Amazon portion, and total reach cannot be summed across providers.

### The repair loop

| Lever | Removed when |
|---|---|
| Widen the audience | No audience was chosen (6.4) |
| Raise the bid | Deal is fixed-CPM. **Present on floor-rate deals — see D3** |
| Relax the device targeting | The advertiser setting is locked (3.5) |
| Relax the geography | The trader chose geography deliberately as their targeting |
| Widen the inventory | Available, but third-party tiers return no forecast, so the effect cannot be verified |
| Increase the budget or extend the flight | A commercial decision, not the agent's to make |

**Three rules govern the loop:**

1. **Cap the iterations.** Two or three attempts, then report.
2. **Check the maximum before acting.** Where estimated reach already equals maximum reach, no lever will help and the agent should say the inventory is exhausted rather than trying.
3. **Name the levers it could not use.** A locked advertiser policy or an absent audience is information the trader needs, not something to omit silently.

### The repair loop does not exist in the product today

**Verified, and material.** Two audience-aware forecast endpoints exist:

```
POST /api/audience-sets/reach-forecast/
POST /api/strategies/{id}/audiences/reach-forecast/
```

**Nothing in the product calls either of them.** The one forecast the product runs is on the summary screen and takes no audience input. The Planner, after creation, is a budget and bid editor with no forecast at all.

So the repair loop as specified is a **new capability**, not a description of existing behaviour. That is legitimate to build, but it should be a decision rather than an assumption.

**Open decision D7:** build the audience-aware repair loop in M1, or match the product's single pre-creation forecast for the first release?

### APIs called

```
POST /api/strategies/reach-forecast/                      the product's forecast
POST /api/audience-sets/reach-forecast/                    exists; unused by the product
POST /api/strategies/{id}/audiences/reach-forecast/         exists; unused; post-creation
```

---

## 6.6 Step 5 — Finalise plan

**Goal.** The trader confirms the plan within the conversation. Reduced from an approval gate to a status change, per review comment 23.

### Field matrix

| Field | Type | Requirement | Source |
|---|---|---|---|
| Plan status | Enumeration | Required | `ASKED` |
| Finalised by | String | Set on finalisation | `DERIVED` |
| Finalised at | Timestamp | Set on finalisation | `GENERATED` |

Transition: draft to finalised.

### What this removes

An approval gate meant a second person: a notification, a wait of unknown length, a rejection route, a threshold rule deciding when approval was needed, and roles saying who could give it. All of that leaves M1.

It also removes a place where the flow had to stop and wait for a colleague.

**The wait at creative approval stays**, and correctly so — there the agent waits on an external reviewer, which is genuinely asynchronous. Pausing for a review the platform performs is not the same as pausing for a colleague.

### Kept deliberately extensible

The review comment said "for now". Two things follow:

- The plan status is its own enumeration rather than a reuse of the creative approval statuses. The plan and the creative have different lifecycles, and sharing one enumeration would force each to carry values the other cannot use.
- Where approval returns, the likely shape is an advertiser-level rule — "plans over £10,000 need my sign-off" — rather than a workflow inside VOW. Leaving room for an approval threshold on the advertiser settings costs nothing now.

**No API call.** This is agent-internal and logged in the audit trail.

**Open:** which endpoint records the status change, if any should? Nothing in the API covers a plan status as distinct from the activation endpoint.

**Open:** can a finalised plan return to draft, and what can still change after finalisation? Budget and matched deals are commercial commitments and are not obviously in the same category as targeting.

### Platform draft mechanics

**Verified.** The platform's own draft is a separate concept from the plan status above. Save-as-draft is disabled on step 1 and enabled from step 2, so a draft is created deliberately rather than automatically. Drafts carry a null budget and the inactive lifecycle status, and the payload includes a current-step value — **Inferred** to be how a draft resumes.

---

## PHASE B — CREATE

---

## 6.7 Step 6 — Create the strategy

**Goal.** One request. Everything gathered in Phase A is assembled into the payload.

### Which endpoint

**Contested.** Three candidates exist and all three are real.

| Endpoint | Status |
|---|---|
| `POST /api/strategies/` | **Verified** — this is what the product's own wizard uses. It is also what the project flowchart specifies |
| `POST /api/simple-strategies/` | Exists, **request only** — no read or update. Named in version 3.0 |
| `POST /api/automated-strategies/` | Exists. Strategies already carry an is-automated flag, and the name suggests it may be closer to what an agent needs |

**Open decision D5** — which endpoint, and the full field list for whichever it is. The payload in 8.2 is what the product sends to `POST /api/strategies/` and is **Verified**; a different endpoint needs re-verifying.

Note that the simple-strategies endpoint supports creation only, so a strategy created through it would have to be read and updated through the general endpoint. That is worth stating because it reads as inconsistent otherwise.

### Two fields the server sets

**Verified.** The response carries two fields that were not in the request:

```
Fraud and invalid traffic targeting     false
Brand safety targeting                  false
```

**Both are server-set and both default to off.** Neither appears anywhere in the wizard, so a trader has no way to know brand-safety targeting is disabled.

**Open:** should the agent set brand-safety targeting on by default, or surface it as a choice? Leaving it off silently seems wrong for a brand-sensitive advertiser, and this is exactly the kind of thing an advertiser-level policy would govern.

### What happens after creation

**Verified.** The created strategy lands in a paused, inactive state and synchronises to Amazon DSP in the background.

**This answers a question earlier revisions left open** — a created strategy does land paused, so activation remains a separate step.

**And it establishes something no revision said: creation does not mean the campaign exists on Amazon.** See 6.18.

### APIs called

```
POST /api/strategies/                              (or one of the two alternatives)
GET  /api/strategies/{id}/                          read-back
GET  /api/reports/performance-metrics/
```

---

## PHASE C — ATTACH

Steps 7 to 12 run in parallel. None waits on another. Each writes back to a strategy that already exists.

---

## 6.8 Step 7 — Targeting

**Moved from a pre-creation step.** The reason is constraint 1 in 5.1.

### Field matrix

| Field | Type | Requirement | Source | Default | Validation |
|---|---|---|---|---|---|
| Location — include | List of location references | Optional | `DERIVED` | **The market's country** | Identifiers from a lookup, not free text. See below |
| Location — exclude | List of location references | Optional | `ASKED` | Empty | Per review comment 32 |
| Instream position | Enumeration | Optional | `ASKED` | None | Pre-roll, mid-roll, post-roll |
| Content-category exclusions | List of strings | Optional | `ADVERTISER` | The advertiser's brand-safety settings | **Open** |
| Device types | List of enumeration | Optional | `ADVERTISER` | All three, or Connected TV alone | **`CONNECTED_TV` is required** while the format is `streaming_tv`. May be locked |
| Mobile operating system | Enumeration | Conditional | `ASKED` | None | `IOS` or `ANDROID`. Applies only where `MOBILE` is among the device types |

### Location is not a list of strings

**Review comments 31 to 34.** Earlier revisions typed this field as a list of strings. Locations are **identifiers obtained from a lookup**, and there are three ways to obtain one.

| Path | How | Endpoint |
|---|---|---|
| **Search** | The trader names a place; the agent searches and resolves it to an identifier | `GET /api/strategies/locations/{market}/` |
| **Postcode validation** | The trader supplies a list of postcodes; each is validated and returns an identifier. Some will be invalid | `POST /api/strategies/postcode-validation/{market}/` |
| **Custom radius** | The trader gives an address plus a distance and a unit. This **creates a new location identifier** in Amazon | `POST /api/strategies/locations/{market}/` |

The search and radius paths share one path and differ only by method — confirmed in review comment 34.

**A location reference therefore carries three things:** the identifier, a label to show the trader, and its type — country, region, city, postcode or custom radius.

### The radius path is a write

**This is the only write in Phase A or C that creates an object before a strategy exists** — although it now sits in Phase C, so a strategy does exist by then. Two consequences:

- The agent should call it only when the trader has actually asked for a radius, never speculatively
- Whether repeated identical requests create duplicates is **Open** and should be established before it is used at scale

### A specified location replaces the default

**Review comment 33.** The default is the market's country. If the trader supplies postcodes, those **replace** the country rather than being added to it.

```
Wrong    GB plus SW1 plus SW3       the country already contains the postcodes,
                                    so nothing was narrowed
Right    SW1 plus SW3               the country default is gone
```

**This is an exception to the accumulation rule.** Elsewhere the agent merges new information into what is already known — a market stated in turn one survives a budget stated in turn two. For location, a narrower value **replaces** a broader one.

### Markets and location are different fields

Both usually say GB, which makes them look like duplication. They answer different questions.

| | Question it answers | What it decides |
|---|---|---|
| Markets | Which market are we buying in? | Which deals exist, which rate card, which currency, which category and location lists |
| Location | Where should the ad be allowed to show? | Geographic delivery |

They start the same and diverge as soon as the trader narrows.

**Narrowing costs reach, and the agent should report it.** Moving from a country to a handful of postcodes can cut the addressable audience sharply. Since the trader did not see a forecast when they narrowed, the agent should state the effect rather than let the shortfall appear later as a surprise.

### Device types

**Review comments 35 and 36.**

```
CONNECTED_TV     required while the format is streaming_tv
DESKTOP          optional
MOBILE           optional
```

The default is **either all three or Connected TV alone**, set per advertiser — not an arbitrary combination.

**Restricting to Connected TV has two effects the trader did not choose.** A large share of streaming viewing happens on mobile, so available inventory shrinks; and Connected TV inventory is priced above mobile, so the CPM rises and the same budget buys fewer impressions. Since this comes from the advertiser rather than the brief, the agent should surface both effects.

### Mobile operating system

**Review comment 37.** Earlier revisions named this field for the app-versus-browser distinction and gave those as its values. **The values are operating systems.**

| | Earlier revisions | Corrected |
|---|---|---|
| Field name | Mobile environment | Mobile operating system |
| Values | in-app, mobile_web | `IOS`, `ANDROID` |

The conditional rule is unchanged: the field applies only where `MOBILE` is among the device types.

**Not setting the field means both operating systems**, which is the third state.

**Open:** app-versus-web does exist in the platform, as a property of a deal's inventory rather than as a targeting option. On staging that split is roughly 94 per cent app and 6 per cent web, which makes it look descriptive rather than worth targeting on. Is it targetable at all?

### Config-driven, not hard-coded

Client requirement, carried forward: the targeting list changes often, so adding a targeting type should be a configuration change rather than a code change.

**Not supported today** (future scope): genre exclusions, day-parting, language targeting.

### An endpoint that may replace the baseline logic

`POST /api/strategies/{id}/targeting/auto-rec/` recommends targeting automatically. The default baseline described above may not need to be assembled agent-side at all.

**Open:** what does it return, and should the agent use it?

### APIs called

```
GET/POST /api/strategies/{id}/targeting/
POST     /api/strategies/{id}/targeting/auto-rec/
GET/POST /api/strategies/{id}/targeting/{market}/locations/
GET/POST /api/strategies/{id}/targeting/{market}/product-categories/
GET/POST /api/strategies/{id}/targeting/{market}/products/
GET      /api/strategies/locations/{market}/                    search
POST     /api/strategies/locations/{market}/                    create a radius location
POST     /api/strategies/postcode-validation/{market}/
POST     /api/contextual-targeting/{market}/products/
```

---

## 6.9 Step 8 — Budget and bid allocation

**Moved from a pre-creation step, and substantially rewritten.** Earlier revisions treated the budget split as agent-side logic performed before creation. The platform performs it itself, at creation, and exposes the result for editing.

### What the platform does

**Verified.** One market budget was submitted; two allocations were stored.

```
Submitted     one market budget of £10,000       converted to EUR 10,909.09

Stored        market total       EUR 10,909.09
              Streaming TV       EUR  5,454.55
              Prime Video        EUR  5,454.55       exactly even

Bid           submitted as one value in GBP
              stored per format, in EUR, separately editable
```

### Three numbers, three different concepts

Earlier revisions conflated these.

| Number | Value in the test plan | What it is |
|---|---|---|
| Forecast estimated spend | 4,931.71 and 5,068.29 | A prediction of where spend will land, optimised |
| Platform allocation | 5,454.55 and 5,454.55 | The stored cap per format, split evenly |
| Agent's proposed split | Whatever the agent computes | A recommendation |

### Multiple flight ranges

**Verified.** A strategy supports several flight ranges, each with its own budget, and dedicated endpoints exist for creating, updating and deleting them.

The full budget granularity is therefore:

```
strategy -> flight range -> market -> format -> budget
```

Earlier revisions modelled a single flight date range.

**Open decision D14:** are multiple flight ranges needed in M1?

### What the agent contributes

| Field | Type | Requirement | Source |
|---|---|---|---|
| Split by format | Allocation | Optional | `MATCHED` |
| Split by duration | Allocation | Optional | `MATCHED` |
| Split method | Enumeration | Required where a split is proposed | `GENERATED` |
| Per-format allocation | Decimal | — | `PLATFORM` |

**Two split methods:**

```
Even by budget         equal spend per format or duration; impressions differ,
                       because a higher CPM buys fewer
Even by impressions    equal impressions; spend differs, because a higher CPM
                       requires more
```

The agent must state which it chose and why, so the trader can adjust.

### Why a split matters at all

Each format and each duration carries a different CPM, so a real split produces an accurate impression estimate. Without one the agent must present a blended estimate and should say so. The size of the error depends on how far the CPMs diverge:

```
CPMs close     £24 and £22
               split      208,333 + 227,273 = 435,606
               blended £23                  = 434,783
               error 823 impressions, immaterial

CPMs far       £40 and £15
               split      125,000 + 333,333 = 458,333
               blended £27.50               = 363,636
               error 94,697 impressions, 26 per cent
```

**Recommendation:** the agent proposes a split only where the CPMs diverge enough to matter, and otherwise accepts the platform's even allocation and explains it.

**Open decision D9** covers whether this is the intended division of labour.

### Also on this screen

**Verified.** A duplicate-strategy action exists, which explains the numerically suffixed names in the strategy list.

---

## 6.10 Step 9 — Creative upload

### Field matrix

| Field | Type | Requirement | Source | Validation |
|---|---|---|---|---|
| Video file | Upload | Required | `ASKED` | Always video for CTV. No display creatives, no responsive e-commerce |
| Click-through URL | URL | Optional | `ASKED` | **Nothing on a television screen can be clicked.** Recommended where device types include mobile or desktop |
| Duration | Decimal | Checked | `API` | **Verified** to be a structured field on the asset. No derivation needed. Must match a duration in the plan |

### Click-through URL — verified on the platform

Approved Streaming TV creatives exist with a null click-through URL, confirming review comment 25. The call to action on CTV takes other forms — a QR code in the creative, an on-screen or spoken prompt, or brand recall — and measurement comes from the ASINs or the ad tag rather than from a click.

**A refinement.** Device types come from the advertiser and may include mobile or desktop, where the ad *can* be clicked. So "optional for streaming TV" is two cases: with Connected TV alone there is nothing a URL could do, while with mobile or desktop in the mix a URL is worth having.

**Open:** the API has a model named for a market with a click-through URL. Is the URL held **per market**? For a multi-market campaign that matters.

**Open:** are QR codes permitted in CTV creatives, and is there a specification for them?

### Asset and creative are two different objects

**New in this version — Verified.** Earlier revisions treated these as one thing.

| | **Asset** | **Creative** |
|---|---|---|
| What it is | The video file | The file registered on Amazon, for one market, with a click-through URL |
| Identifier | One | **Two** — its own and Amazon's |
| Carries | dimensions, duration, file size, url, language, markets (a list), past metrics | type, market (single), approval status, click-through URL |
| Approval | filtered by a DSP-approved flag | its own approval status field |

**One asset produced 25 creatives** in the test data — all approved, all in one market, differing only in type and click-through URL.

**Creative type takes two values — Verified:** "Video" and "Streaming TV Video". The same asset can be registered as both. **A CTV plan needs "Streaming TV Video".**

The agent's deterministic filter is therefore: type is Streaming TV Video, market matches, and approval status is approved.

**Duration matching is free**, because duration is structured. A deal carrying 15 and 20 second lengths matches only the 20-second assets in a set that also holds 10 and 30.

**Assets carry past metrics — Verified.** Impressions, click-through rate, effective CPM and others. The agent can therefore say that a creative has run before and how it performed.

**Note:** the same video appeared twice in the test data at different resolutions — same name, same URL, different identifier. The agent should group these rather than presenting them as two options.

### Duration match check

If the uploaded video is 30 seconds but the plan specified 15-second deals, the economics change — a different CPM means different impressions for the same budget. This returns to step 5 with the amended plan.

### APIs called

```
GET  /api/assets/
GET  /api/creatives/
POST /api/assets/amz_assets/gen_upload_urls/     obtain upload URLs
POST /api/assets/amz_assets/register/            register the asset on Amazon
```

---

## 6.11 Step 10 — Creative approval

Every video must pass the platform's content and technical review before it can run. Each platform reviews its own inventory independently. A plan can be fully approved and funded and still not launch until the creative clears.

### Field matrix

| Field | Type | Requirement | Source |
|---|---|---|---|
| Creative approval statuses | Map of channel to status | Read-only | `API` |

Per review comment 26, the three hard-coded publisher rows become one field holding a status per channel, keyed by the channels the plan actually matched.

**Keys are data; values are an enumeration.** Publisher names change and are market-specific — the UK has ITVX and Channel 4, the US has Hulu and Peacock — so a row per publisher would not scale past one market, and adding one would require a schema change, a migration and a release to add a name. The set of states is stable and the agent's logic depends on it, so that stays typed.

**This is the same rule the targeting step already carries** — that a frequently changing list must be config-driven. It was written down and not applied here.

### Blocked

**Verified.** A creative object carries market and approval status with **no channel dimension at all**. The granularity on the platform is creative × **market**, not creative × channel. The map above cannot be populated from current data.

**This blocks more than this step.** The activation checklist at 6.16 includes approval by every channel. If per-channel statuses are not readable, that prerequisite cannot be evaluated.

**Open decision D10.**

**On rejection:** the agent reports the reason and asks for a replacement, returning to step 9.

**The wait here is external.** This step retains the pause the plan-approval step lost, because the reviewer is Amazon or a publisher rather than a colleague.

**Open:** where should the channel list come from — the advertiser channel-choices endpoint, or derived from the matched deals?

**Open:** is the status held per channel, or per creative-and-channel pair? A plan with a 15-second and a 30-second creative could have one approved and the other not on the same channel.

---

## 6.12 Step 11 — Tracking setup

ASIN validation was in step 1 of version 1.1.0 and ad-tag conversions in its step 2. Both now sit here.

### Field matrix

| Field | Type | Requirement | Source | Validation |
|---|---|---|---|---|
| Sells on Amazon | Enumeration | Required | `ADVERTISER` | Moved from basics. Comes from the advertiser, so the agent holds it at creation |
| Product ASINs | List of strings | Required if endemic | `ASKED` | Sent empty at creation, attached here. Validated in a batch |
| Sells on own website | Boolean | Asked here | `ASKED` | |
| Ad tag registered | Boolean | Required if selling off Amazon | `API` | **The tag must be installed before the campaign runs** — tracking only records activity after it goes live |
| Ad tag conversions | List of strings | Required if an ad tag exists | `ASKED` | Four events, each carrying a market flag |

### How the timing question resolves

Version 2.0 flagged twice that product location is required by the create payload yet was being collected after creation. Both halves are now closed:

- Product location comes from the advertiser's settings, loaded at session start, so the agent holds it at creation — nothing needs patching
- ASINs are sent empty at creation and attached here through an update request

**Open:** should the ASIN list be validated in one call here, or as the trader pastes them? Validating late means a trader can enter twenty ASINs and only then learn that three are wrong.

**Open:** can conversions be skipped entirely — activating with no conversion tracking — or is at least one always required?

### APIs called

```
POST  /api/contextual-targeting/{market}/asin-validation/
GET   /api/conversions/definitions/
PATCH /api/strategies/{id}/
```

---

## 6.13 Step 12 — Credit check

Credit is checked only at activation, not during planning. Everything before this point is a costless plan.

| Field | Type | Requirement | Source |
|---|---|---|---|
| Account balance | Decimal | Read-only | `API` |
| Strategy budget | Decimal | Read-only | `DERIVED` |
| Sufficient | Boolean | Derived | `DERIVED` |

**Verified.** The same figure appears in the platform header as available credit.

If insufficient, the agent prompts a top-up.

**Open:** is the credit check genuinely order-free? Its outcome can change the budget, which would argue for running it before the plan is finalised rather than alongside the creative work.

### APIs called

```
GET  /api/credits/summary/?advertiser={id}
POST /api/credits/
POST /api/credits/stripe/
```

---

## PHASE D — ACTIVATE

---

## 6.14 Step 13 — Activate

The single spend action in the entire flow. Everything before this was free.

**A join node, not just a step.** Because the Phase C branches run in any order, this is where completeness is checked. Removing the order made an explicit checklist necessary — previously the order itself was the guarantee.

### The prerequisite checklist

| Prerequisite | Holds when |
|---|---|
| Creatives uploaded | One per duration in the plan — a plan with 15-second and 30-second inventory needs both |
| Creatives approved | Every matched channel has returned approved. **Blocked — see 6.11** |
| Targeting written | The baseline is applied, or the trader's refinement is saved |
| Budget allocated | Per format, and accepted or edited |
| Ad tag registered | The advertiser does not sell on Amazon and a tag is in place |
| ASINs attached | The advertiser does sell on Amazon and the ASINs validated |
| Conversions chosen | Selected, or explicitly skipped |
| Credit sufficient | Balance is at least the strategy budget |

### The readiness condition must check every prerequisite

**A correction to version 3.0.** The readiness condition there declared ad tag registration and ASIN attachment as fields but did not check them. A campaign could therefore activate with neither, which would make the whole tracking branch optional in practice.

Every prerequisite in the table above must be evaluated. Where one is not applicable — ASINs for a non-endemic advertiser — it is satisfied rather than skipped, and the difference between "not applicable" and "not done" must be representable.

### The agent reports every failure at once

Where the plan is not ready, the agent lists **all** unmet prerequisites rather than the first one. A trader who is told about the creative, fixes it, and is then told about the credit has been made to do two rounds for no reason.

### Two prerequisites are new in this version

Targeting written and budget allocated, because both moved into Phase C.

### APIs called

```
POST /api/strategies/{id}/set_status/
```

**Note:** version 3.0 named an activate endpoint. It does not exist.

**Open:** is the prerequisite list complete? And is there an endpoint that reports activation readiness, or must the agent assemble it from the individual checks?

---

## 6.15 Post-creation update rules

Per review comment 28, a strategy can be updated after creation through an update request.

This is what makes Phase C's parallelism possible. Removing the order between the branches only works if those branches can write back to a strategy that already exists. The two are one change seen from two sides: no order necessary is the behaviour, updatable after creation is the mechanism.

### But not everything should be freely updatable

The review answer concerned the measurement fields and should not be read as "anything may change". Some fields carry money.

| Safely updatable | Needs a guardrail | Why |
|---|---|---|
| Product ASINs | Market budgets | A guaranteed deal already owes the full budget |
| Product location | Market deals | The deal is booked |
| Ad tag, conversion types | Flight dates | Tied to the booking |
| Creatives, assets | Markets | Invalidates the whole plan |
| Targeting, frequency cap | | |

Without that distinction, someone will patch a budget on a strategy whose guaranteed deal has already committed it, and the plan and the commitment will disagree.

**Open decision D11:** which fields are updatable and which fixed? The table is a proposal.

**Open:** does "after creation" extend to "after activation"? A live campaign is a different case from one created but not yet launched.

**Open:** does an update re-run anything — validation, or the reach forecast? If a change to the targeting invalidates the forecast the trader was shown, the agent should say so.

---

## 6.16 Sync and failure handling

**New section.** Nothing in any earlier revision covered what happens after creation on the Amazon side.

**Creation does not mean the campaign exists on Amazon. Verified:**

- The created strategy shows a syncing flag and a spinner
- Synchronisation to Amazon DSP runs in the background
- **It can fail.** Several strategies in the list carry a campaign sync failure reason with an amber indicator

### What the agent must handle

| Situation | Behaviour |
|---|---|
| Syncing | Report that the strategy is publishing, and do not present it as live |
| Failure reason populated | Report the failure and its reason. Do not report success |
| Sync completes | Campaigns appear under the strategy; activation can proceed |

**Open:** how is sync completion or failure detected — is there a webhook, or must the agent poll? This decides whether the agent can tell the trader when the campaign is genuinely live.

### Amazon-side structure

After a successful sync the strategy holds campaigns, each holding ad groups. These are Amazon DSP's own objects. Nothing in the planning flow creates them directly.

---

# 7. Consolidated field registry

Every field in the plan, in one table. Section 6 gives the reasoning; this is the list to build against.

**Requirement key:** `R` required, `O` optional, `C` conditional, `—` present in the payload but never asked.

| Step | Field | Type | Req | Source | Notes |
|---|---|---|---|---|---|
| 1 | Strategy name | String | O | `GENERATED` | Uniqueness checked |
| 1 | Flight dates | List of date ranges | R | `INFERRED` | Multiple ranges supported |
| 1 | Markets | List of ISO codes | R | `INFERRED` | GB and US only on the platform |
| 1 | Primary currency | Currency code | O | `ADVERTISER` | **Not derived from the market** |
| 1 | Creative durations | List of integers | C | `INFERRED` | 10, 15, 20, 30, 40, 45, 60 |
| 1 | Goal | Enumeration | O | `ADVISED` | Awareness default; changeable with advice |
| 1 | Formats and KPIs — format | Enumeration | — | `CONSTANT` | `streaming_tv` |
| 1 | Formats and KPIs — KPI | Enumeration | R | `INFERRED` | Options follow the goal |
| 1 | Formats and KPIs — KPI target value | Integer | C | `ASKED` | 2 to 5, frequency only |
| 1 | Market info — budget | Decimal | R | `INFERRED` | Greater than zero |
| 1 | Market info — currency | Currency code | R | `DERIVED` | From the market |
| 1 | Market info — base bid | Decimal | R | `ASKED` / `DERIVED` | **Contested, D3** |
| 1 | Frequency cap | Integer | O | `ADVERTISER` | Per week; may be locked |
| 1 | Budget cap | Decimal | O | `ADVERTISER` | **Open** |
| 1 | Video product categories | List of strings | R | `ADVERTISER` / `INFERRED` | Long numeric strings |
| 1 | Product categories | List of strings | — | `CONSTANT` | Empty for CTV |
| 1 | Conversion types | List of strings | O | `ASKED` | Four events, per market |
| 1 | Selected inventory sources | List of objects | O | `API` | Pre-filled from pre-flight |
| 2 | Channel | List of strings | O | `INFERRED` | **Blocked, D4** |
| 2 | Run-of-service or genre | String | O | `INFERRED` | **Blocked, D4** |
| 2 | Market deals — deals | List of deal objects | R | `MATCHED` | Complete objects, not identifiers |
| 2 | Specific deal id | String | O | `ASKED` | Lookup only; no format validation |
| 2 | Inventory tier — per deal | Enumeration | R | `DERIVED` | **Blocked, D4** |
| 2 | Targeting source — per deal | Enumeration | O | `MATCHED` | **Blocked, D8** |
| 2 | Curation requirements | Object | C | `ASKED` | Needs-curation tier only |
| 3 | Audience prompt | String | O | `GENERATED` | Natural language |
| 3 | Market info — audience targeting | List of references | O | `ASKED` | **Per market** |
| 3 | Audience match type | Enumeration | C | `ASKED` | Exact by default |
| 3 | Audience data sources | List of enumeration | R | `DERIVED` | Drives the fee |
| 4 | Forecast | Object | — | `API` | Four inputs only |
| 5 | Plan status | Enumeration | R | `ASKED` | Draft to finalised |
| 5 | Finalised by | String | — | `DERIVED` | |
| 5 | Finalised at | Timestamp | — | `GENERATED` | |
| 6 | Product location | Enumeration | R | `ADVERTISER` | Required at creation |
| 6 | Product ASINs | List of strings | — | `CONSTANT` | Empty at creation |
| 6 | Current step | Integer | R | `GENERATED` | Draft resumption |
| 6 | Brand safety targeting | Boolean | — | `PLATFORM` | Defaults off. **Open** |
| 6 | Fraud and invalid traffic targeting | Boolean | — | `PLATFORM` | Defaults off |
| 7 | Location — include | List of references | O | `DERIVED` | Defaults to the market country |
| 7 | Location — exclude | List of references | O | `ASKED` | |
| 7 | Instream position | Enumeration | O | `ASKED` | |
| 7 | Content-category exclusions | List of strings | O | `ADVERTISER` | **Open** |
| 7 | Device types | List of enumeration | O | `ADVERTISER` | `CONNECTED_TV` required |
| 7 | Mobile operating system | Enumeration | C | `ASKED` | `IOS` or `ANDROID`; mobile only |
| 8 | Per-format budget | Decimal | — | `PLATFORM` | Even split at creation |
| 8 | Per-format bid | Decimal | — | `PLATFORM` | From the submitted base bid |
| 8 | Split method | Enumeration | C | `GENERATED` | Where a split is proposed |
| 9 | Assets | List of references | R | `ASKED` | |
| 9 | Click-through URL | URL | O | `ASKED` | **Open:** per market? |
| 9 | Asset duration | Decimal | — | `API` | Structured, not derived |
| 10 | Creative approval statuses | Map | — | `API` | **Blocked, D10** |
| 11 | Ad tag registered | Boolean | C | `API` | Off-Amazon only |
| 12 | Credit sufficient | Boolean | — | `DERIVED` | |
| 13 | Activation prerequisites | Object | R | `DERIVED` | Join node |

### Fields sent empty but required by the payload

```
product_categories            display only
product_asins                 attached later
pre_approved_creatives        display only
rec_creatives                 display only
third_party_creatives         display only
```

---

# 8. Data contracts — what is passed

Verified request and response shapes. Presented so that the payloads do not have to be reverse-engineered during implementation.

## 8.1 Reach forecast

### Request

```
POST /api/strategies/reach-forecast/
```

| Field | Type | Notes |
|---|---|---|
| `flight_dates` | Object with `lower` and `upper` | ISO dates |
| `formats` | List of strings | **Must include `prime_video`** where Prime Video is in the plan |
| `goal` | String | Affects available supply |
| `market_budgets` | List of objects | Each carrying market, budget, **`base_bid`**, currency |

**Four inputs only. No deals, no audiences, no targeting.**

**Note the field name.** This endpoint calls the bid `base_bid`; the create endpoint calls it `base_supply_bid`. Same value, two names.

```json
{
  "flight_dates": {"lower": "2026-09-01", "upper": "2026-09-30"},
  "formats": ["streaming_tv", "prime_video"],
  "goal": "AWARENESS",
  "market_budgets": [
    {"market": "GB", "budget": 10000, "base_bid": "25", "currency": "GBP"}
  ]
}
```

### Response

| Field | Type | Notes |
|---|---|---|
| `total_reach` | Integer | **Use this. Never sum the supply lines** |
| `total_impressions` | Integer | Equals the sum of the supply lines |
| `market_reach` | List of objects | One per market |
| `market_reach[].supplies` | List of objects | One per format, keyed as `DSP_STREAMING_TV` and `DSP_PRIME_VIDEO` |

Each supply line carries:

| Field | Meaning |
|---|---|
| `supply` | The format key |
| `est_spend` | Predicted spend on this line |
| `est_reach`, `max_reach` | Estimated and the ceiling |
| `est_impressions`, `max_impressions` | Estimated and the ceiling |
| `avg_cpm`, `max_cpm` | Blended supply average, not the deal price |

```json
{
  "total_reach": 233803,
  "total_impressions": 860716,
  "market_reach": [{
    "market": "GB", "reach": 233803, "impressions": 860716,
    "budget": "10000.00", "currency": "GBP",
    "supplies": [
      {"supply": "DSP_STREAMING_TV",
       "est_spend": 4931.71, "est_reach": 132713, "max_reach": 285186,
       "est_impressions": 647856, "max_impressions": 6759074,
       "avg_cpm": "7.60", "max_cpm": "14.98"},
      {"supply": "DSP_PRIME_VIDEO",
       "est_spend": 5068.29, "est_reach": 71120, "max_reach": 950000,
       "est_impressions": 212860, "max_impressions": 52757286,
       "avg_cpm": "23.98", "max_cpm": "23.98"}
    ]
  }]
}
```

**Frequency is not returned.** Derive it: total impressions divided by total reach. The window is per week.

## 8.2 Create strategy

### Request

```
POST /api/strategies/          Verified as what the product uses. See D5
```

**Sixteen campaign-level fields plus three nested arrays.**

| Field | Type | Notes |
|---|---|---|
| `name` | String | |
| `flight_dates` | Object | |
| `goal` | String | |
| `primary_currency` | String | From the advertiser |
| `product_location` | String | From the advertiser |
| `current_step` | Integer | Draft resumption |
| `formats_and_kpis` | List of objects | **KPI per format**, with the target value |
| `markets_info` | List of objects | Per market: bid, budget, currency, **audience targeting** |
| `market_deals` | List of objects | Per market: **complete deal objects** |
| `selected_inventory_sources` | List of objects | Name and type |
| `video_product_categories` | List of strings | Long numeric strings |
| `product_categories` | List | Empty for CTV |
| `audience_targeting_match_type` | String | |
| `conversion_types` | List of strings | |
| `product_asins` | List | **Empty at creation** |
| `assets` | List of objects | |
| `pre_approved_creatives` | List | Empty, but must be present |
| `rec_creatives` | List | Empty, but must be present |
| `third_party_creatives` | List | Empty, but must be present |

```json
{
  "name": "CTV Test GB Sep2026 KA",
  "flight_dates": {"lower": "2026-09-01", "upper": "2026-09-30"},
  "goal": "AWARENESS",
  "primary_currency": "EUR",
  "product_location": "NOT_SOLD_ON_AMAZON",
  "current_step": 5,

  "formats_and_kpis": [
    {"format": "streaming_tv", "kpi": "REACH"},
    {"format": "prime_video",  "kpi": "FREQUENCY", "kpi_target_value": 3}
  ],

  "markets_info": [{
    "market": "GB",
    "base_supply_bid": "25",
    "budget": 10000,
    "currency": "GBP",
    "audience_targeting": [
      {"audience_set_id": "26f2cbb3-...", "audience_type": "AUDIENCE_SET"}
    ]
  }],

  "market_deals": [{"market": "GB", "deals": [ /* complete deal objects */ ]}],

  "selected_inventory_sources": [
    {"name": "Amazon Streaming TV", "type": "AMAZON"},
    {"name": "Twitch", "type": "AMAZON"}
  ],

  "video_product_categories": ["304861615492321169", "345704700972773738"],
  "product_categories": [],
  "audience_targeting_match_type": "EXACT",
  "conversion_types": ["PAGE_VIEW", "CHECKOUT"],
  "product_asins": [],

  "assets": [{"id": "d246bc9a-...", "name": "VOWtestVid1"}],
  "pre_approved_creatives": [],
  "rec_creatives": [],
  "third_party_creatives": []
}
```

### Seven implementation notes

1. **Complete deal objects are sent back, not identifiers.** The agent cannot discard the deals list after matching.
2. **The bid field is named differently here** than on the forecast endpoint.
3. **KPI and target value are per format**, as a list of pairs.
4. **Two category fields exist.** CTV populates the video one and sends the other empty.
5. **All four creative arrays must be present**, three of them empty.
6. **ASINs are sent empty** and attached later.
7. **Audience targeting is nested per market**, not campaign-level.

### Response

`201 Created`, and a **subset** of what was sent. Market info, market deals, assets and formats-and-KPIs are **not** returned; a read-back is required to confirm them.

Two fields appear that were not in the request: brand safety targeting and fraud and invalid traffic targeting, **both defaulting to off**.

## 8.3 Deal object

**Verified — twelve fields.**

| Field | Type | Notes |
|---|---|---|
| `external_deal_id` | String | Seven formats in use |
| `name` | String | **Carries channel, genre and audience capability that are not available as fields** |
| `deal_type` | Enumeration | Preferred, private auction, programmatic guaranteed |
| `deal_price_type` | Enumeration | Fixed CPM or floor rate |
| `deal_price_amount` | String | **One deal is zero — guard required** |
| `deal_price_currency` | String | **Can differ from the market currency** |
| `media_types` | List | Each with bid-request volume and rate |
| `devices` | List | Each with volume. **Empty on third-party deals** |
| `environments` | List | App and web. **Empty on third-party deals** |
| `locations` | List | Country code and volume. **Filter on this** |
| `genre` | String or null | **Unusable — see section 12** |
| `ad_lengths` | List of strings | **Empty on third-party deals** |

Three fields the agent needs and **does not** get: inventory tier, channel, and Amazon-audience capability.

## 8.4 Audience set object

**Verified.**

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | |
| `name` | String | Staging names are test data; do not infer from them |
| `goal` | Enumeration | **The list is not filtered by this** |
| `market` | String | **Single value, not a list** |
| `prompt` | String | Natural language. **Populated on sets created through the suggest flow** |
| `audience_groups` | **JSON string** | Nested boolean tree. Requires two parse passes |
| `audience_count` | Integer | |
| `strategy_count` | Integer | Reuse count; one set is used by 56 strategies |
| `standard_display_fee` | String | **Can be an empty string, not null** |
| `video_fee` | String | Zero where only free categories are present |
| `fee_currency` | String | |

## 8.5 Asset and creative objects

**Verified.** Two levels — see 6.12.

**Asset:** identifier, name, extension, target types, asset type, content type, width, height, file size, **duration**, language, **markets (a list)**, metrics, status, url, archived flag.

**Creative:** identifier, **Amazon identifier**, name, **type**, **market (single)**, **approval status**, click-through URL.

The creatives request accepts a no-pagination flag, which returns the complete set in one call.

## 8.6 Strategy read model

**Verified — twenty fields.** Needed for status checks and reporting.

| Group | Fields |
|---|---|
| Identity | `id` (the VMA code), `name`, `channel_type` |
| Plan | `goal`, `flight_dates`, `product_location`, `formats`, `markets`, `budget`, `primary_currency` |
| Status | `status`, `delivery_activation_status`, `failure_reason` |
| Booleans | `is_draft`, `is_syncing`, `is_archived`, `is_readonly`, `is_automated` |
| Risk | `budget_at_risk` — **Open**, definition not documented |
| Metrics | `metrics` — 29 fields |

### The metrics object

**Verified — 29 fields in six groups.**

| Group | Fields |
|---|---|
| Counts | impressions, click-throughs, viewable impressions, purchases, off-Amazon purchases, off-Amazon conversions |
| Rates | view rate, click-through rate, video completion rate, detail page view rate, ACOS, off-Amazon conversion rate |
| Returns | ROAS, click-attributed ROAS, total ROAS, off-Amazon ROAS |
| Money | sales, total cost, total sales, product sales, off-Amazon product sales |
| Unit costs | effective CPM, effective CPC, cost per video completion, cost per detail page view, off-Amazon CPA, off-Amazon purchase CPA |
| Context | display currency |

**All money and rate values are strings**, not numbers. Rates carry five decimal places.

**Three attribution families** are reported separately and must not be conflated: off-Amazon (the advertiser's own site, via the ad tag), on-Amazon (via the ASINs), and the total.

### Which metrics are meaningful for CTV

```
Meaningful       reach, frequency, impressions, video completion rate,
                 view rate, effective CPM, cost per video completion
Not meaningful   click-through rate, effective CPC, and anything click-derived
Conditional      detail page view rate and the sales metrics — only where
                 ASINs or an ad tag exist
```

This is the underlying reason the goal defaults to Awareness.

## 8.7 Deal filter properties

**Verified.**

| Field | Notes |
|---|---|
| `genres` | 12 values, of which four are genuine genres. **See section 12** |
| `ad_lengths` | 16 entries, 7 distinct. **Not deduplicated by the endpoint** |
| `exchanges` | 8 values |
| `devices` | Mobile, connected TV, desktop, unknown |

---

# 9. API contract map

Checked against the staging OpenAPI listing, 4 August 2026. **Verified** means the call was observed in the product with its payload and response.

## 9.1 Corrections to earlier revisions

| Named in an earlier revision | Reality |
|---|---|
| `POST /api/rate-cards/match/` | **Does not exist.** Use `GET /api/deals/` with `GET /api/deals/filter-properties/` |
| `GET /api/advertisers/{id}/defaults/` | **Does not exist.** Use `GET /api/admin/advertiser/{id}/` |
| `POST /api/strategies/{id}/activate/` | **Does not exist.** Use `POST /api/strategies/{id}/set_status/` |
| `POST /api/strategies/draft/` | Not used. Draft is a boolean on the strategy |
| No update endpoint listed | `PATCH /api/strategies/{id}/` exists |
| Postcode support unknown | `POST /api/strategies/postcode-validation/{market}/` exists |
| Fee values unknown | `GET /api/contextual-targeting/fees` exists |
| Audience reach forecast assumed to be the plan's forecast | The plan's forecast is `POST /api/strategies/reach-forecast/` |

## 9.2 The seventeen calls the product makes

| # | Endpoint | Method | When | Status |
|---|---|---|---|---|
| 1 | `/api/credits/summary/` | GET | List load, credit check | **Verified** |
| 2 | `/api/reports/user-preferences/` | GET | List load | **Verified** |
| 3 | `/api/strategies/` | GET | List load, 11 parameters | **Verified** |
| 4 | `/api/audience-sets/check_market_has_audience_set/` | GET | Step 1 | **Verified** |
| 5 | `/api/creatives/recs/check_market/` | GET | Step 1 | **Verified** |
| 6 | `/api/assets/check_market_has_assets/` | GET | Step 1 | **Verified** |
| 7 | `/api/inventory-sources/` | GET | Step 1 | **Verified** |
| 8 | `/api/conversions/definitions/` | GET | Step 1, off-Amazon | **Verified** |
| 9 | `/api/strategies/check_strategy_name_uniqueness/` | GET | Step 1 to 2 | **Verified** |
| 10 | `/api/deals/` | GET | Step 2, 11 parameters | **Verified** |
| 11 | `/api/deals/filter-properties/` | GET | Step 2 | **Verified** |
| 12 | `/api/audience-sets/` | GET | Step 3 | **Verified** |
| 13 | `/api/assets/` | GET | Step 9 | **Verified** |
| 14 | `/api/creatives/` | GET | Step 9 | **Verified** |
| 15 | `/api/strategies/reach-forecast/` | POST | Step 4 | **Verified** |
| 16 | `/api/strategies/` | POST | Step 6 | **Verified** — returns 201 |
| 17 | `/api/strategies/{id}/` | GET | After creation | **Verified** |

**Common to all:** session-cookie authentication, and the advertiser held in the session rather than passed as a parameter. The strategy list call carries no advertiser parameter, unlike the credits call.

## 9.3 Endpoints the agent needs that the product does not call

| Endpoint | Purpose | Status |
|---|---|---|
| `GET /api/admin/advertiser/{id}/` | Advertiser profile defaults | Exists |
| `POST /api/audience-sets/suggest/` | Audience suggestion | Exists. **D2** |
| `GET /api/audience-sets/suggest/{id}/` | Read the suggestion | Exists |
| `POST /api/audiences/amc-audiences/` | Retargeting audiences | Exists |
| `GET /api/contextual-targeting/fees` | Fee rates | Exists |
| `POST /api/audiences/{market}/overlapping-audiences/` | Cross-provider overlap | Exists |
| `GET /api/contextual-targeting/{market}/product-categories/` | Category taxonomy | Exists |
| `POST /api/contextual-targeting/{market}/asin-validation/` | ASIN validation | Exists |
| `GET /api/rates/ctv/{market}/` | CTV rate card | Exists |
| `GET /api/strategies/locations/{market}/` | **Location search** | Exists |
| `POST /api/strategies/locations/{market}/` | **Create a radius location** | Exists |
| `POST /api/strategies/postcode-validation/{market}/` | Postcode validation | Exists |
| `POST /api/strategies/{id}/targeting/auto-rec/` | Recommended targeting | Exists. **Open** |
| `GET/POST /api/strategies/{id}/targeting/{market}/locations/` | Write targeting | Exists |
| `GET/POST /api/strategies/{id}/flight-ranges/` | Flight range CRUD | Exists |
| `PATCH /api/strategies/{id}/` | Post-creation update | Exists |
| `POST /api/strategies/{id}/set_status/` | Activation | Exists |
| `POST /api/strategies/duplicate/` | Duplicate a strategy | Exists |
| `POST /api/assets/amz_assets/gen_upload_urls/` | Creative upload | Exists |
| `POST /api/assets/amz_assets/register/` | Register on Amazon | Exists |
| `POST /api/credits/` , `POST /api/credits/stripe/` | Top-up | Exists |
| `GET /api/strategies/choices/` | Enumerations. **May carry the goal-to-KPI mapping — D12** | Exists |
| `POST /api/simple-strategies/` | CTV creation variant | Exists, create only. **D5** |
| `POST /api/automated-strategies/` | Automated creation | Exists. **D5** |

---

# 10. Validation rules

Consolidated. Every rule that must hold, in one place.

## 10.1 Field-level

| Field | Rule |
|---|---|
| Strategy name | Unique for the advertiser. On collision, append a version suffix and re-check rather than stopping |
| Flight dates — start | On or after today |
| Flight dates — end | After the start |
| Markets | Valid ISO codes. Only GB and US exist on the platform. One per strategy in M1 |
| Primary currency | One of EUR, GBP, USD. `NOK` exists in production — see the open question |
| Creative durations | One of 10, 15, 20, 30, 40, 45, 60 |
| Goal | One of the three. Non-Awareness is allowed with advice, never blocked |
| KPI | Must be valid for the chosen goal |
| KPI target value | Integer 2 to 5 inclusive. Present only where the KPI is frequency; absent otherwise |
| Market budget | Greater than zero |
| Base bid | Greater than zero. Must exceed the floor on a floor-rate deal — see D3 |
| Product categories | Leaf subcategories only; parents are not selectable |
| Selected deals | At least one |
| Specific deal id | Format cannot be validated. Lookup and report |
| Device types | `CONNECTED_TV` must be present while the format is `streaming_tv` |
| Mobile operating system | Set only where `MOBILE` is among the device types |
| Location | Identifiers from a lookup. A narrower value replaces the market-country default |
| Postcodes | Validated in a batch. Report which failed |
| ASINs | Required if endemic. Validated in a batch. Report which failed |
| Click-through URL | Validated as a URL when supplied. Not required |
| Asset duration | Must match a duration in the plan |

## 10.2 Cross-field

| Rule | Why |
|---|---|
| Currency must match before any arithmetic | Deals can be priced in a currency other than the plan's — nine per cent error at the observed rate |
| KPI options depend on the goal | Review comment 30 |
| KPI target value exists only with a frequency KPI | Review comment 10 |
| Mobile operating system exists only with a mobile device type | Review comment 37 |
| Curation requirements exist only for the needs-curation tier | 4.3.1 |
| Match type exists only where an audience is chosen | 6.6 |
| ASINs required only where the advertiser is endemic | 4.1 |
| Ad tag required only where the advertiser is not endemic | 4.1 |
| Budget split applies only where more than one deal is matched | Review comment 3 |
| Reach forecast fields are populated only for Amazon-owned inventory | 6.7 |

## 10.3 Arithmetic guards

| Guard | Consequence if missed |
|---|---|
| Deal price of zero | Division by zero |
| Currency mismatch | Nine per cent error in every impression figure |
| Empty-string fee | Parse failure |
| Reach summed across supply lines | Understated by roughly 13 per cent against the API total |
| Frequency not derived | Not returned by the API; absent from the plan |
| Effective CPM not used | Impressions overstated by the size of the fee |
| Ad lengths not deduplicated | Duplicate options presented |
| Deal locations not filtered | Out-of-market deals in a market-filtered plan |

## 10.4 Behavioural rules

These are not field validations but they are testable, and each exists because getting it wrong is worse than failing.

| Rule | Source |
|---|---|
| Never present a defaulted value as something the trader stated | 2.1 |
| Never choose an audience on the trader's behalf | 6.6 |
| Never invent a reach figure for third-party inventory | 6.7 |
| Always state a commercial commitment before the trader accepts a CPM | 6.5 |
| Always state whether a price is a floor or a fixed rate | 6.5 |
| Always name the repair levers that could not be used | 6.7 |
| Always advise against a non-Awareness goal, and never block it | 4.8 |
| Always report every unmet activation prerequisite at once | 6.16 |
| Never report a strategy as live while it is still syncing | 6.18 |
| Never call the radius-creation endpoint speculatively | 6.10 |

---

# 11. Open questions for the client

Ranked. The first six block implementation.

## 11.1 Blocking

| # | Question | Why it blocks |
|---|---|---|
| **D1** | **Targeting timing.** Every targeting endpoint requires a strategy identifier, so targeting cannot precede the forecast as earlier revisions specified. Should the agent hold targeting in its own state, forecast, create, then write it? Or does targeting genuinely belong after creation? | Determines the flow order, and whether audiences and targeting can be presented as one subject |
| **D2** | **A real request and response from the audience suggest endpoint.** Knowing that the bundled object does not exist is only half the answer; the grouping rule, the fee handling and the audience schema all depend on the actual shape. Also: the request model is named for groups — can the caller request a number of groups? And how long does the asynchronous call take? | Nothing in step 3 can be built without it |
| **D3** | **Does the bid apply on floor-rate deals?** Private auctions are described as floor-priced and competitive. Almost all 83 deals on staging are floor-rate, and the platform blocks progress when base bid is empty even on a pure CTV plan. If the bid applies, the repair loop keeps a lever the current specification removes. And what should be sent for the bid if the trader is never asked? | Changes agent behaviour, and the create payload requires a value |
| **D4** | **Are the deal matching inputs available as fields?** There is no channel and no inventory tier on a deal; genre exists but returns years, a test label and an ad-length list; Amazon-audience capability is encoded in the deal name. Is there a source we have missed, or can these be added? | Step 2 cannot be built as specified. The largest single blocker |
| **D5** | **Which create endpoint, and its field list?** Three exist: the general strategies endpoint (what the product and the project flowchart both use), the simple-strategies endpoint (create only, named in version 3.0), and the automated-strategies endpoint (whose name suggests agent use; strategies already carry an is-automated flag). | The entire create payload depends on the answer |
| **D6** | **Advertiser profile defaults: the full list, and which are locked.** Seven identified so far. Locked versus default determines what the repair loop may relax. Also: is the advertiser-level value a product **category** or an **industry**? The two are separate taxonomies with no mapping between them. | Determines repair-loop behaviour and the resolution order in step 1 |

## 11.2 Behaviour-changing

| # | Question | Why it matters |
|---|---|---|
| **D7** | **Build the audience-aware repair loop in M1?** The endpoints exist but nothing in the product calls them, and the product's forecast takes no audience input. The repair loop is therefore a new capability rather than existing behaviour. | Scope. A significant piece of work either way |
| **D8** | **Can Amazon audiences and the inventory source's targeting run on the same deal?** If both, the targeting-source field must hold a list, and the combination rule needs stating — intersection and union have opposite effects on reach. Also, how limited is Amazon's targeting on third-party inventory in practice? | Field design, cost model, and what the agent recommends |
| **D9** | **Who owns the budget split?** The platform allocates evenly per format at creation and allows editing. Three numbers exist — the forecast's estimate, the platform's allocation, and any agent proposal. Which does the trader see, and which does the agent set? | Whether step 8 is agent logic or explanation |
| **D10** | **Where do per-channel creative approval statuses live?** A creative carries market and approval status with no channel dimension. If these are tracked outside VOW, the activation prerequisite cannot be evaluated. Is the status per channel, or per creative-and-channel pair? | Whether the activation gate can be built |
| **D11** | **Which fields are updatable after creation, and which fixed?** The proposal at 6.17 separates measurement fields from those that carry money. Budget and deals matter most, because a guaranteed deal has already committed the budget. Does "after creation" extend to "after activation"? | Prevents a plan and a commitment disagreeing |
| **D12** | **The goal-to-KPI mapping.** Awareness gives reach and frequency. Which of CTR, CPC, CPA and CPDPV belong to Consideration versus Conversion? Preferably readable from an endpoint rather than specified here — the choices endpoint and the formats-and-KPIs model both look like candidates. | The KPI list is conditional on the goal; without the mapping it cannot be built |
| **D13** | **Creative durations: ask, default, or plan across several?** Duration determines which deals are available and what CPM applies, so the plan needs it. But the trader may not know at planning time — the creative is often still with an agency, and the review's own question was whether they have a supplier to create the cut-downs, which implies the agent recommends rather than the trader states. | Whether the flow can proceed without it |
| **D14** | **Are multiple flight ranges needed in M1?** The platform supports them, each with its own per-market, per-format budget. Earlier revisions modelled one. | Budget model complexity |

## 11.3 Scope and smaller questions

| # | Question |
|---|---|
| D15 | One market per strategy in M1, or is multi-market needed in the first release? |
| D16 | When several deals match, how should the agent choose — cheapest CPM, largest volume, or best genre fit? |
| D17 | When nothing matches, should the agent widen the duration, drop the genre, or ask? |
| D18 | Should a programmatic guaranteed deal ever be matched automatically? Does PG inventory appear at all — none was found on staging |
| D19 | Should brand-safety targeting default to on? It is currently off and invisible to the trader |
| D20 | Should the agent show every inferred value for correction, or only the uncertain ones? |
| D21 | What does the targeting auto-recommendation endpoint return? It may replace the baseline logic entirely |
| D22 | Is the click-through URL held per market? A model named for a market with a click-through URL suggests it may be |
| D23 | Are QR codes permitted in CTV creatives, and is there a specification? |
| D24 | How is sync completion or failure detected — webhook, or polling? |
| D25 | Should the ASIN list be validated in one call, or as the trader pastes? |
| D26 | Can conversions be skipped entirely, or is at least one always required? |
| D27 | Is the credit check genuinely order-free? Its outcome can change the budget |
| D28 | Can a finalised plan return to draft? What can change after finalisation? |
| D29 | Should an advertiser-level approval threshold be planned for? |
| D30 | Where should the channel list come from — the advertiser channel-choices endpoint, or derived from matched deals? |
| D31 | The currency enumeration holds EUR, GBP and USD. `NOK` exists in production. Extend, or scope out? |
| D32 | Can the trader override the derived market currency? Doing so makes the plan total and the deal CPMs disagree unless a rate is applied |
| D33 | Do traders use an existing strategy naming convention? |
| D34 | Is the is-automated flag the agent marker, or does it mean something else? |
| D35 | What is budget-at-risk? The field and the column exist; the definition does not |
| D36 | Is app-versus-web targetable, or only a property of the inventory? The staging split is roughly 94 per cent app |
| D37 | Are there minimum spends by market and channel? Raised in the client's own question list; we have no answer |
| D38 | Should planning against an impression target rather than a budget be supported in M1? Raised in the client's own question list |
| D39 | Where a brief gives a budget range, should the agent take the upper figure, the lower, or ask? |
| D40 | Where a currency symbol and the market disagree, which wins? |
| D41 | Is a reset or start-over command needed? |
| D42 | What are the exact lifecycle status strings for the four values not yet observed? |
| D43 | What other values does the audience type take beyond the audience-set value? |
| D44 | Does the deals endpoint accept a no-pagination flag? 83 deals in one call would be simpler |
| D45 | Is the sponsored-products endpoint family irrelevant to CTV? |
| D46 | Does repeated identical radius creation produce duplicate locations? |

## 11.4 A tension worth resolving

The client's own question list contains twelve discovery questions to put to a trader, including the goal, where they sell, their audience, their devices, and whether they want geo targeting.

Review comment 6 says the trader should be asked for very little — in practice the market, the budget and the dates.

These pull in opposite directions. **Our reading** is that the twelve are a *checklist of what the plan needs*, and comment 6 says most of them should be answered from the advertiser profile, the brief, or a CTV constant rather than asked. Section 5.2 reflects that reading.

**This should be confirmed**, because it decides how many questions the trader is asked and therefore what the product feels like.

---

# 12. Data quality requests

Four issues that cannot be resolved on our side. Each blocks or degrades a specific capability.

## 12.1 The genre field is unusable

**Verified.** The deal filter-properties endpoint returns twelve genre values:

| Value | What it actually is |
|---|---|
| Action, Comedy, Drama, Suspense | Genuine genres |
| Top Trending, Winter Holiday | Content categories — workable |
| RON, ROS | Placement types, not genres |
| 2026, 2027 | Years |
| TEST | A test label |
| "15, 20, 30" | An ad-length list |

And the Netflix deals carry their genre **in the name** while the field is null.

**Inferred:** the field takes the last token of the deal name. Where a name ends on a genre it is correct; where it ends on a year it is wrong; where the genre sits mid-name it is empty.

**Request:** populate genre from a controlled vocabulary.
**Blocks:** genre matching and the genre upsell feature.

## 12.2 Amazon-audience capability is encoded in the deal name

**Verified.** Five Netflix deals carry "NOT Amazon Audience Enabled" in the name and one carries "Amazon Audience Enabled". The deal object carries no audience-capability field.

**Request:** expose this as a boolean.
**Blocks:** setting the targeting source reliably, which review comment 1 introduced.

## 12.3 No source exists for the inventory tier

**Verified.** No inventory-tier field on a deal, and no channel field either. The three-tier fork is the primary branch of the CTV flow and has no data source.

**Request:** a source for tier and channel.
**Blocks:** the entire tier fork — reach-forecast availability, curation capture, and what the agent tells the trader about capability.

## 12.4 Third-party deal metadata is largely absent

**Verified.** On third-party deals the device, environment, media-type and ad-length lists are empty, and the location bid-request volume is a placeholder of 1. On Amazon deals all four are populated and the volume is in the billions.

**Request:** clarification — is this a data gap, or is the metadata genuinely unavailable upstream from third-party exchanges?
**Degrades:** duration matching, device matching and deliverability assessment on all third-party inventory, which is the majority of available deals.

## 12.5 Smaller items

| Item | Detail |
|---|---|
| One deal priced at zero | Data error, or intentional? |
| Ad lengths not distinct | The filter endpoint returns 16 entries with 7 distinct values |
| Empty-string fees | The standard display fee returns an empty string rather than null on some sets |
| Two audience sets break the fee pattern | Both have zero segments; **Inferred** to be data errors |
| Video completion rate above 100 per cent | 128.45 per cent observed. Not meaningful |
| Out-of-market deals in a filtered list | South African deals appear in a GB list. Confirming this is expected would help |
| Click-through URLs contain application URLs | Testers have pasted platform addresses. The field does not validate |
| Duplicate assets | The same video appears twice at different resolutions with the same name and URL |

---

# 13. Out of scope

Recorded so the boundary is explicit and nothing here is mistaken for an omission.

## 13.1 Out of scope for CTV

| Item | Reason |
|---|---|
| Display and online video formats | This agent is CTV-first. Both remain valid in the platform |
| Product audiences | Not applicable to CTV |
| Responsive e-commerce creatives | Display only |
| Third-party creative tags | Display only |
| Pre-approved creative selection | Display only |

**Note on goals and KPIs.** Consideration and Conversion goals, and the four click-derived KPIs, are **no longer out of scope** — review comment 30 reinstated them, conditional on the goal. See 4.8.

## 13.2 Not supported by the platform today

| Item | Note |
|---|---|
| Genre exclusions | Future scope |
| Day-parting | Future scope |
| Language targeting | Future scope |
| Cross-platform reach deduplication | Does not exist. This is why reach cannot be summed |
| Reach forecast on third-party inventory | Does not exist. This is the basis of the honesty rule |

## 13.3 Deferred by decision

| Item | Where it would return |
|---|---|
| Manager approval workflow | As an advertiser-level threshold rather than a gate — see 6.8 |
| Multi-market strategies | The field is already a list, so this is additive — D15 |
| Multiple flight ranges | The platform supports it — D14 |
| AMC audiences | Conditional on the advertiser having prior campaign data |
| Question answering on a live plan | The client's question list describes a substantial capability; not in this specification |
| Reporting, insights and optimisation | The client's question list describes these separately from planning |

---

# 14. Glossary

| Term | Meaning |
|---|---|
| **ACOS** | Advertising cost of sale. The inverse of ROAS |
| **Ad tag** | A tracking snippet installed on the advertiser's own site. Must be in place before the campaign runs |
| **ASIN** | Amazon Standard Identification Number. A product identifier |
| **Bid request volume** | How much inventory is available on a deal |
| **CPM** | Cost per mille — the price of one thousand impressions |
| **CTV** | Connected TV. An internet-connected television, or a device attached to one |
| **Curation** | The process by which VOW creates a deal that does not yet exist, after an insertion order is signed |
| **DSP** | Demand-side platform. Where inventory is bought |
| **Effective CPM** | Deal CPM plus the audience data fee. The figure the impression estimate must use |
| **Endemic** | An advertiser that sells on Amazon. Non-endemic sells elsewhere |
| **Fixed CPM** | A price that is paid as shown |
| **Floor rate** | A minimum that must be exceeded. The paid price is set by auction |
| **Flight range** | A date range in which the campaign runs. A strategy may hold several |
| **Frequency** | Impressions divided by reach. The window is per week |
| **Halo sales** | Amazon sales attributable to a non-endemic advertiser's off-Amazon advertising |
| **Impression** | One instance of the ad being shown |
| **Preferred deal** | Fixed price, first refusal, no volume guarantee, no commitment |
| **Private auction** | Floor-priced, invited buyers, competitive, no commitment |
| **Programmatic guaranteed** | Fixed price and guaranteed volume, with the full budget owed and no ability to pause |
| **Reach** | The number of unique people who saw the ad. Not additive across supply lines |
| **ROS / RON** | Run of service, run of network. Unnarrowed placement, priced below genre-specific inventory |
| **SSP** | Supply-side platform. Where inventory is sold |
| **VCPM** | Here, the audience data fee per thousand impressions |

---

# 15. Change log

| Version | Change |
|---|---|
| 1.1.0 | Initial schema. Followed the six-step UI wizard. Covered display, online video and CTV |
| 2.0.0 | Reordered to a CTV-first agent flow. Client feedback incorporated. **Received 28 review comments** |
| 3.0.0 | Restructured into ten steps with three parallel post-creation branches. **Received a further nine review comments** |
| **4.0** | Consolidates all three. Applies all 37 review resolutions. Corrects fourteen positions against verified platform behaviour, including three endpoints that do not exist and two internal inconsistencies. Adds the domain model, the currency model, the taxonomy map, the numeric guards, the defaults-and-advised-values model, the budget allocation model, sync handling, the data contracts, and the consolidated validation rules. Records 46 open questions and four data quality requests. Contains no code. |

---

**End of specification.**

*Verified against `staging.vowmade.dev` on 4 August 2026, using test strategy `VMA2026368`. Where a position is contested, the evidence is stated inline so the disagreement can be settled on facts. Comments are welcome on any section; section 11 lists the questions that need answers before implementation can proceed.*
