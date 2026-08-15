# VOW Platform — Strategy Schema v3

Aligned to the confirmed CTV-first agentic flow (v5)

Original version: 1.1.0. Previous revision: 2.0.0. **This revision: 3.1 — v3.0 plus the v3.0 review comments and a full verification pass against the live staging API.** Status: For client verification

**This is the current schema document.** Where any other revision disagrees with it, this one is correct.

**How to read this document.** Every section is marked:

- UNCHANGED — kept exactly as written in v1.1.0
- CHANGED — the concept existed but is modified (original shown for comparison)
- NEW — did not exist in v1.1.0, added from client feedback
- REMOVED — existed in v1.1.0 but dropped for CTV scope (kept as future scope)

Two further markers appear in this revision:

- 🔴 **CORRECTION** — something this document previously asserted is **wrong**, with the evidence
- ✅ **API-VERIFIED** — confirmed by a live call against staging on 6 August 2026

The document follows the confirmed agentic flow order, not the existing wizard order.

---

## What changed in v3.1

Two things happened after v3.0 went out.

### 1. A second round of review comments

Six comments on v3.0, all in Step 1 and Step 5. Every one is addressed in place, with the note sitting beneath the row it was made on:

| Comment | Where | What it changed |
|---|---|---|
| Goal is defaulted for CTV, not fixed | Step 1 | `FIXED` → `DEFAULTED (advised)`. A four-category model for pre-filled values was added, because "fixed", "defaulted" and "locked" had all been written as the same thing |
| Can the user search for locations? A trader-supplied postcode list needs validating to get location IDs | Step 1, Step 5, §5 | Yes — and confirmed as a **search** endpoint, minimum two characters. New `PostcodeResolutionSchema` handles the ambiguous and unresolved cases |
| A custom radius location can be created from an address plus a distance | Step 5, §5 | Confirmed in the API. New `CustomRadiusLocationSchema`. A radius is a way to mint a location ID, not a separate targeting mode |
| There is a list of inclusions and exclusions; this replaces the GB default | Step 5, §5 | The flat `locations` list is split into `location_include` and `location_exclude` |
| `device_types`: CONNECTED_TV **required** for streaming TV, DESKTOP and MOBILE optional, default ALL or CTV | Step 5, §5 | Requirement recorded per value rather than per field. There is no TABLET value |
| `mobile_environment` is IOS or ANDROID only, and only relevant if MOBILE is selected | Step 5, §5 | Renamed to `mobile_operating_systems`. Setting it without MOBILE is now a validation error, not a silent no-op |

### 2. A verification pass against the live API

The OpenAPI document was read (**192 paths, 197 definitions**) and **60+ authenticated calls** were made. This found fourteen things that change the schema. **Eleven of them are errors in this document, not gaps.**

**Every count was too low, and all of them for the same reason** — a filtered view in the interface was read as the whole set:

| | Was documented | Actual |
|---|---|---|
| Deals | 83 | **369** |
| Audience sets | 15 | **35** |
| Assets | 4 | **58** |
| Markets with deals | 2 | **18** |
| Product categories | not counted | **25,973** |

**Every enum was too small**, for the same reason:

| | Was documented | Actual |
|---|---|---|
| `goal` | 3 | **15** |
| `format` | 4 | **21** — and twelve are channels |
| `kpi` | 6 | **16**, restricted to **5** on the automated endpoint |
| `primary_currency` | 3 | **19** |
| `market` | 2 | **21** |
| `conversion_type` | 4 | **6**, and market-specific |
| `duration` | 4 | **7** |

**Six positions in this document were wrong, not merely incomplete:**

| # | What this document said | What is true |
|---|---|---|
| 1 | The audience fee comes from `/contextual-targeting/fees` | Two different fees. The audience fee is on the audience set; that endpoint prices contextual targeting (§4.3) |
| 2 | Currency is derived from the market | It is an **advertiser** default. A live strategy has `NOK` on a `US` market (Step 1) |
| 3 | CTV deal CPMs are fixed, so the repair loop has no bid lever | **92% of deals are floor-rate.** The bid is the least invasive repair (Step 6) |
| 4 | `simple-strategies` is the CTV create endpoint | It is a minimal single-market shell. `automated-strategies` is the fit (§4.2, Step 8) |
| 5 | Deals carry channel and tier | Neither field exists on any of the 369 deals. Both must be parsed from the name (Step 2) |
| 6 | No non-Amazon inventory source was ever returned | Three source types exist; they simply do not serve `streaming_tv` (§5) |

**Five open questions are now closed:** the create endpoint, the goal-to-KPI restriction, whether the currency enum needs extending, whether impression targets are supported, and all three location comments.

🔴 **Two new blockers were found:**

- **D47** — `GET /api/admin/advertiser/{id}/` returns **403** to a valid trader session. This is the endpoint the entire advertiser-defaults concept depends on. Until it is resolved, every advertiser-default field in this document is unimplementable
- **D50** — the strategy record carries **40 keys, not 20.** The fifteen missing ones form a delivery-control layer — `pacing_ratio`, `planned_cpm`, `cpm_target`, `allocation_mode`, `creative_rotation_type`, `user_location_signal` — that nobody has specified and no document mentions

---

## What changed in v3.0, and where

Every change made in this revision comes from a review comment on v2.0. The structure, section order and step numbering of v2.0 are unchanged deliberately, so that each comment still sits next to the text it was made on. Only the affected row, cell or paragraph has been edited, with a note beneath it.

**Sections with no comments on them are identical to v2.0.** In particular, each step's *"What was in v1.1.0"* block is historical and has not been touched — the changes are in the *"What it is now"* table that follows it.

| # | Section | Row or text changed | What changed |
|---|---|---|---|
| 1 | 2.3 Deal Types | Audiences column, both 3P rows | Third-party targeting can come from Amazon DSP **or** the inventory source — it is a choice per deal, not fixed by the tier |
| 2 | 2.4 Audience Profiles | Narrow and Wide rows; the fee note | Fee depends on the data provider, not on the profile, and does not compound. Profiles differ in reach and precision, not cost |
| 3 | 3 Flow comparison | Budget split row | Marked optional |
| 4 | 3 Flow comparison, 2.4, Step 4 | "mandatory" | Audiences are optional, not mandatory |
| 5 | 3 Flow comparison, Step 5 | Targeting row | Audiences are part of targeting; targeting arrives pre-filled with defaults |
| 6 | Step 1 | Whole field table | **Source column added.** "Required" and "asked" are separate things — most fields are now inferred, derived or taken from the advertiser |
| 7 | Step 1 | Strategy name | Requirement Required → Optional; generated from the brief |
| 8 | Step 1 | Target markets | One market per strategy in M1; per-market versus campaign-level fields documented |
| 9 | Step 1 | Primary currency | Required → Optional; taken from the market rather than asked |
| 10 | Step 1 | KPI | **New row added:** KPI target value, 1–5, when the KPI is frequency |
| 11 | Step 1 | Market budgets, Base bids | Type column corrected — "Table" was a UI widget, not a data type |
| 12 | Step 1, Step 6 | Base bids; repair-loop table | Base bids do not apply to CTV. The repair loop loses its bid lever |
| 13 | Step 1 | Frequency cap | **New concept:** advertiser-level defaults, loaded at session start |
| 14 | Step 1, §5 | Formats; `FormatEnum` | Format is always `streaming_tv`. Prime Video is a channel, not a format |
| 15 | Step 1 | Product categories | "Required for video" dropped; taken from the advertiser or implied from the brief |
| 16 | Step 1 | Selling location | **Row removed** — belongs with tracking |
| 17 | Step 1 | Product ASINs | **Row removed** — collected at tracking. Closes the timing question raised twice in v2.0 |
| 18 | Step 2, §6 | Selected deals; state machine | Deals are **matched, not selected**. The checkbox table goes; only channel and CPM are surfaced. Three new rows added |
| 19 | Step 4 | Constraints list, first bullet | Amazon audiences apply to third-party inventory too |
| 20 | Step 4 | The open question below the table | `bundles.narrow/balanced/broad` does not exist. The agent groups a flat list itself |
| 21 | Step 5 | Location row | **Source and Default columns added.** Location defaults to the market's country |
| 22 | Step 5 | Device type, Mobile environment | Device type comes from the advertiser and may be a locked policy. Mobile environment becomes conditional |
| 23 | Step 7, §5, §6 | Whole step; `PlanStatusEnum` | Approval becomes a status change. Manager routing, rejection and the interrupt are removed |
| 24 | Step 8, §4 | Endpoint; API catalogue | Creation moves off `/api/strategies/`. **Fourteen catalogue rows added or corrected** against the staging API. (v3.1 corrects this further — the endpoint is `automated-strategies`, not `simple-strategies`) |
| 25 | Step 9, §5 | Click-through URL | Required → Optional — nothing on a television screen is clickable |
| 26 | Step 10, §5 | Three approval rows | Replaced by one status per channel, keyed by data. `provider` renamed to `channel` |
| 27 | Step 11, Step 13, §6 | Whole step; activation | No order between creatives, tracking and credit. **Activation prerequisite checklist added** |
| 28 | Step 11 | "Confirm with client" | A strategy can be updated after creation. Closes the timing question |

**Four questions raised in v2.0 are now answered** and marked `RESOLVED` in place: the ASIN and product-location timing (twice), the audience suggest response shape, and postcode support.

**Two remain open** and are marked `STILL OPEN`: what status a created strategy lands in, and whether per-channel creative approval statuses are readable through the API.

**Twenty-two blocks of questions** are marked `OPEN QUESTIONS` under the relevant notes, for the team to answer before the schema is locked.

---

## 1. Core Principles

CHANGED — the first principle is extended, and a fourth is added.

**Zero-Hallucination Policy:** The agent NEVER invents strategy parameters, metrics, targeting criteria, or deal IDs. It only populates values verified against the VOW database and REST APIs.

> 🔴 **EXTENDED — and this half was missing.** "Do not invent" is only one direction of the rule. The other direction is:
>
> **A value the trader supplied is not verified merely because they supplied it. Every value must be checked against the registry, the database or the API before it enters the plan — no matter who produced it.**
>
> The original wording could be read as *"invented values need checking, stated values do not"*. That reading breaks the plan in a worse way than hallucination does, because a hallucinated value looks suspicious while a trader-supplied wrong value looks authoritative.
>
> **Three examples of the same failure:**
>
> | The trader says | Naive behaviour | What actually happens |
> |---|---|---|
> | *"Call it Nike UK Sep 2026"* | Name goes into the plan | A strategy with that name already exists. Creation fails at the last step, after everything else was agreed |
> | *"Run it on Netflix"* | `channel = Netflix` | No Netflix deal exists for GB at 30s. The plan has an unbuyable line in it and nobody knows until create time |
> | *"Exclude tablets"* | `device_types` gets `TABLET` | There is no `TABLET` value in the API. The field is silently wrong |
>
> In all three cases the agent did not invent anything. It also did not verify anything. **The plan is equally broken.**
>
> **The rule therefore has three parts, not one:**
>
> 1. **Never invent** — no value comes from the model's own guess
> 2. **Always verify** — every value, including the trader's own words, is checked against its authority before it enters the plan
> 3. **Never silently fix** — a value that fails verification is reported back, not quietly corrected, dropped or substituted
>
> Part 3 matters as much as the other two. Appending `-2` to a duplicate name, dropping `TABLET` because it is invalid, or picking the first of five matching postcodes are all *helpful* actions that leave the trader believing something untrue about their own plan. **Verification failures are conversation, not cleanup.**
>
> The per-field authorities and the timing rule are in §5.5.

**Self-Filling Form Paradigm:** The agent operates as a stateful slot-filling engine backed by LangGraph. Inputs via chat or uploaded briefs are parsed into registered Pydantic slot schemas.

**API-Driven Tool Execution:** Every step maps to official VOW API endpoints.

**Stated Uncertainty (NEW):** Where a value is derived rather than read — a channel parsed from a deal name, an impression count computed rather than guaranteed — the agent says so. A guess presented as a fact is a hallucination with extra steps.

> This principle was added after the API verification pass. It exists because the deal object carries no `channel` field, so the agent must parse one out of a free-text name across eight inconsistent naming conventions. That parsed value is real work and useful — but it is an inference, and the interface must not render it identically to a value the API returned.

---

## 2. Business Logic

### 2.1 Product Attribution & Selling Locations

UNCHANGED

**On Amazon (ON_AMAZON) [Endemic]:** ASINs required. Enables DPV, ATC, Purchase, ROAS tracking.

**Off Amazon (NOT_SOLD_ON_AMAZON) [Non-Endemic]:** ASINs optional (monitors halo sales). Ad tag conversions required for site event tracking.

### 2.2 Attribution Window

UNCHANGED — 14-day post-view and post-click.

### 2.3 Deal Types

CHANGED — deal types unchanged, but inventory tiers added.

Original deal types (kept):

| Type | Price | Commitment | Can pause? |
|---|---|---|---|
| Programmatic Guaranteed (PG) | Fixed CPM, guaranteed volume | Full budget owed | No |
| Preferred Deals | Fixed CPM | None | Yes |
| Private Auctions | Floor CPM, competitive | None | Yes |

**NEW — Three inventory tiers** (the primary fork in the CTV flow):

The tier drives most of the downstream branching — whether reach can be forecast, where the targeting comes from, and whether the deal is selectable now.

🔴 **CORRECTION — "every deal now carries an inventory tier" is wrong.** This was the previous wording and it reads as though the tier were a field on the deal. It is not. Verified across all 369 deals: there is no `inventory_tier`, no `channel`, no `provider` and no `publisher`. **The tier is our concept, derived from a channel that is itself parsed out of the deal name.** That makes this fork — the primary fork in the flow — dependent on string parsing, which is why D53 asks for a real channel field.

🔴 **And a second correction, about inventory sources.** An earlier note in this document said no non-Amazon inventory source was ever returned. That was wrong. There are three source **types** and four sources in total:

```
Amazon Publisher Direct   AMAZON_PUBLISHER_DIRECT   display, online_video
Amazon Streaming TV       AMAZON                    streaming_tv
Third Party Exchange      THIRD_PARTY_EXCHANGE      display, online_video
Twitch                    AMAZON                    display, streaming_tv
```

The non-Amazon types exist; they simply do not serve `streaming_tv`. **For CTV there are exactly two sources** — Amazon Streaming TV and Twitch — and that is the whole supply surface at the source level. Note also that Twitch serves `display` as well, which an earlier note denied.

**Inventory sources are not the tiers, and neither is the "50+" figure.** `/inventory-sources/` requires `goal`, `strategy_formats` and `markets` together, and the most it ever returns is four. Whatever "50+ inventory" counted, it was not this — see D54.

| Tier | Examples | Deals | Reach forecast | Audiences |
|---|---|---|---|---|
| Amazon owned | Prime Video | Pre-curated, selectable now | Available | Amazon audiences |
| 3P pre-curated | Netflix, Hulu, others | Pre-curated, selectable now | Not available | Choice per deal — Amazon audiences (may be limited, e.g. device only) or targeting at the inventory source / SSP (adds CPM) |
| 3P needs curation | Disney+, others | Rate-card CPM only; VOW curates the deal after the IO is signed | Not available | Choice, decided at curation — Amazon audiences (may be limited) or targeting at the inventory source / SSP (adds CPM) |

> **REVIEW NOTE — 3P targeting source** (review comment on *"Their own targeting (adds CPM)"*): Targeting on third-party inventory can come from either side: Amazon DSP, or the inventory source / SSP. Amazon's option may be limited in functionality — device only, in some cases. Which options exist is specific to the deal that is chosen or curated, so it is known only after the deal is matched, not at planning time. Recorded on the plan as `targeting_source` (`AMAZON_DSP` / `INVENTORY_SOURCE`). Note that the Audiences column no longer separates the tiers: Amazon audiences can apply to third-party inventory too, so what actually differs by tier is the reach forecast and whether the deal exists yet.

**Why this matters:** a plan spanning Prime + Netflix + Disney has three portions, each with different capabilities. The agent must handle them differently — and be honest about what it can and cannot forecast.

### 2.4 Audience Set Profiles

CHANGED — renamed "Broad" to "Wide" per client vocabulary; fee rules corrected.

| Profile | Was (v1.1.0) | Now |
|---|---|---|
| 1 | Narrow (High Precision) | Narrow — highly targeted, elevated intent, risk of underdelivery |
| 2 | Balanced (Recommended) | Balanced — optimal blend, the usual recommendation |
| 3 | Broad (Maximum Scale) | Wide — broad demographic/interest reach, less precision |

NEW note: the audience fee (VCPM) stacks on top of the deal CPM, so the agent should surface the effective CPM (deal + audience fee), not just the deal price. The fee is set by which data is used — not by how many segments are selected, and not by which profile.

> **REVIEW NOTE — audience data fees** (review comment on *"added fee consequence"*): There is not necessarily a fee consequence, and any fee is not driven by the profile. Three rules apply:
>
> 1. **What triggers a fee** — using 1P data, whether Amazon's own or a third-party first-party audience such as Lifestyle or Interest. This holds regardless of profile.
> 2. **No compounding** — one fixed CPM applies when 1P data is used, however many segments are selected from that provider.
> 3. **Cross-provider stacking** — if the user matches a segment in both Amazon and a third-party provider, both fees are paid.
>
> Narrow, Balanced and Wide therefore differ in reach and precision, not in cost. Recorded on the plan as `audience_data_sources` (`AMAZON_1P` / `THIRD_PARTY` / `NONE`), so the effective CPM is built from the providers in play rather than from the segment count.
>
> 🔴 **CORRECTION — where the fee values come from.** An earlier revision said `GET /api/contextual-targeting/fees` returns the audience fee. **It does not.** Live calls on 6 August 2026 show there are **two different fees**, and conflating them puts the wrong number into the effective CPM:
>
> | Fee | Where it actually lives | GB streaming TV |
> |---|---|---|
> | **Audience data fee** | On the **audience set object** — `video_fee`, `standard_display_fee`, `fee_currency` | **1.63** GBP |
> | **Contextual targeting fee** | `GET /api/contextual-targeting/fees` | **0.450** GBP |
>
> The path name was the clue that was missed: `contextual-targeting/fees` prices **contextual (product-category) targeting**, not audience targeting. The 1.63 GBP figure quoted elsewhere in this document is correct — only its stated source was wrong.
>
> The contextual endpoint returns 16 markets, each with three format rates:
>
> ```
> market  currency  display  online_video   stv
> AE      AED       0.825    1.650          1.650
> AU      AUD       0.300    0.450          0.450
> BR      BRL       0.450    1.275          1.275
> CA      CAD       0.300    0.450          0.450
> DE      EUR       0.180    0.450          0.450
> ES      EUR       0.108    0.450          0.450
> FR      EUR       0.147    0.450          0.450
> GB      GBP       0.162    0.450          0.450
> ```
>
> **Both fees can apply to one plan** — an audience plus product-category targeting. At GB streaming-TV rates that is 1.63 + 0.450 = **2.08 GBP per thousand impressions** on top of the deal CPM, which is a material change to the forecast rather than a rounding detail.
>
> The principle the earlier note was reaching for still holds, and now applies to both: **read the rate, never write the figure into the specification.** A stale rate produces a plausible-looking effective CPM that is quietly wrong.
>
> Rule 3 above — paying both fees where a segment is matched in both providers — has an endpoint too: `POST /api/audiences/{market}/overlapping-audiences/` reports audience overlap, so the double-fee case can be detected rather than guessed at.
>
> > **OPEN QUESTION D49:** do the audience fee and the contextual fee **add**, or does one supersede the other? Rules 2 and 3 above govern audience fees among themselves and say nothing about the contextual fee. Until this is answered the agent cannot state a correct effective CPM for a plan that uses both.

NEW: audiences are optional and suggestion-driven. The agent always suggests three options using VOW's existing pgvector + OpenAI feature (`POST /audience-sets/suggest/`), and the trader may decline them all. Nobody browses the ~3,400 segments manually.

**API-VERIFIED:** `GET /api/audience-sets/` returns **35 audience sets** for the test advertiser, not the 15 recorded earlier — that count came from the first page of the interface. The ~3,400 figure is segments, which is a different unit from sets, and has not been verified. The audience fee lives on this object: `video_fee`, `standard_display_fee` and `fee_currency`.

REMOVED for CTV: product audiences (not applicable per client). AMC audiences are conditional — available only when the advertiser has prior campaign data (retargeting tactic).

---

## 3. The Agentic Flow — Step by Step

CHANGED — entirely reordered. The original followed the 6-step UI wizard. This follows the client-confirmed CTV-first agentic flow (v5).

**Comparison: old order vs new order**

| Old (v1.1.0 wizard) | New (v2.0 agentic, confirmed) |
|---|---|
| Strategy details | Basics (+ durations) |
| Goal, KPI & bid | (goal/KPI/bid folded into Basics) |
| Deals | CTV inventory (three-tier fork) |
| — | Budget split NEW (optional) |
| Audiences | Audiences (optional, suggestion-driven) |
| — | Targeting NEW (audiences form part of this step) |
| (forecast was a sub-step) | Predict reach (Amazon only; repair loop) |
| — | Plan approval NEW |
| (create was at the end) | Create the real strategy |
| Creatives | Upload video creative (+ duration check) |
| — | 10. Platform creative approval NEW |
| (ASINs were in step 1) | 11. Tracking setup (ASINs + ad tag) MOVED |
| — | 12. Credit check NEW |
| Summary → create | 13. Activate NEW |

### Step 1: Basics

CHANGED — merged original Steps 1 and 2 (strategy details + goal/KPI/bid), added durations, scoped to CTV.

**What was in v1.1.0 (Step 1 + Step 2):**

Strategy name, flight dates, target markets, primary currency, formats (all four), product categories, selling location, ASINs

Goal (three choices), KPI (six choices), ad tag conversions, market budgets, base bids

**What it is now:**

NEW — a **Source** column. "Required" says whether the plan needs a value; **Source** says where that value comes from. The two are not the same, and conflating them is what made this step look like a form the trader has to fill in. Source values:

| Source | Meaning |
|---|---|
| ASKED | The agent asks the trader outright |
| INFERRED | Read from the brief; asked only when the brief does not say |
| DERIVED | Calculated from another field |
| GENERATED | Composed by the system |
| ADVERTISER | Pre-filled from the advertiser's own settings — read from `GET /api/admin/advertiser/{id}/` (model `AdvertiserAdminRetrieve`) |
| FIXED | A system constant for CTV |
| API | Pre-populated from an API response |
| MATCHED | The agent works it out from what the plan already knows |
| LATER | Not collected in this step |

| Field | Type | Requirement | Source | Change from v1.1.0 |
|---|---|---|---|---|
| Strategy name | String | Optional | GENERATED | CHANGED. Composed from the brief rather than asked for; the trader can rename it. Uniqueness still validated via `GET /api/strategies/check_strategy_name_uniqueness/` |
| Flight dates | Date range | Required | INFERRED | Unchanged. lower ≥ today, upper > lower. **API-VERIFIED:** the platform supports **multiple** flight ranges per strategy, each with its own per-market, per-format budget — see Step 3 |
| Target markets | List of str | Required | INFERRED | CHANGED. ISO country codes. Held as a list, but one market per strategy in M1 — see review note. **API-VERIFIED:** the enum holds **21 markets** (`AU AT BE BR CA FR DE IN IT JP MX NL NZ SA SG ES SE TR AE GB US`), and **18 of them have live deals**. An earlier note said only GB and US exist; that came from the UI filter, not the API |
| Primary currency | Currency code | Optional | **ADVERTISER** | CHANGED, then **CORRECTED**. It is *not* derived from the market — it is an advertiser default, pre-filled before a market is chosen and unchanged when one is selected. A live strategy exists with `primary_currency: NOK` and `markets: ["US"]`. **API-VERIFIED:** the enum holds **19 currencies** (`USD MXN CAD BRL AED SAR GBP EUR SEK TRY AUD INR SGD JPY NOK DKK NZD CNY CHF`) — the earlier "EUR, GBP, USD only" was wrong, and no enum extension is needed |
| Creative durations | List of int | Conditional | INFERRED | NEW. **API-VERIFIED:** **seven** values exist, not four — 10, 15, 20, 30, 40, 45, 60. Determines which deals are available and what CPM applies. See the open question on whether this can be asked at all |
| Goal | Enum | Optional | **DEFAULTED (advised)** | CHANGED, then **CORRECTED by review**. Awareness is a **default for CTV, not a constant** — the trader may change it, and the agent states that non-Awareness is not advised rather than blocking it. **API-VERIFIED:** the enum holds **15 values**, not three: `AWARENESS CONVERSION CONSIDERATION OTHER PROSPECTING REMARKETING RETENTION UPPER_FUNNEL_PROSPECTING CONVERSIONS_OFF_AMAZON ENGAGEMENT_WITH_MY_AD CONSIDERATIONS_ON_AMAZON PURCHASES_ON_AMAZON MOBILE_APP_INSTALLS PURCHASES_ON_OFF_AMAZON MULTI_FUNNEL` |
| KPI — **per format** | Enum | Required | INFERRED | CHANGED, then **CORRECTED**. Held **per format** in `formats_and_kpis[]`, not once per strategy. Options **follow the goal** — the four non-Awareness KPIs return, per review. **API-VERIFIED:** the general enum holds **16 values**; the automated-strategy endpoint restricts it to **five** — `REACH FREQUENCY COST_PER_ACTION RETURN_ON_AD_SPEND TOTAL_RETURN_ON_AD_SPEND` |
| KPI target value — **per format** | String | Conditional | ASKED | NEW, then **CORRECTED**. The API field is `target_kpi`, a **string**, and it is optional on both `FormatsAndKpis` and `AutomatedStrategyFormatsAndKpis`. Values 2 to 5 inclusive when the KPI is frequency; absent when the KPI is reach. A frequency of 1 is not offered — one exposure per person is the absence of a frequency target rather than a value for one |
| Market budgets | Decimal, one per market | Required | INFERRED | CHANGED. Type was recorded as "Table", which is how it renders rather than what it holds. Stored inside `markets_info[]`; with one market that is a single amount. Must be > 0 |
| Impression target | Integer | Optional | ASKED | **NEW — API-VERIFIED.** An alternative to a budget. Present on `SimpleStrategyCreate` and on the strategy read model as `impression_target`, alongside `allocation_mode` (`BUDGET` observed). This answers the client's own question about planning against an impression target rather than a fixed budget |
| Base bids | Decimal, one per market | **Required** | ASKED / DERIVED | CHANGED, then **CONTESTED**. Review concluded this does not apply to CTV. **API-VERIFIED against 369 deals: 341 of them (92%) are `FLOOR_RATE`**, where a bid is exactly what decides whether an auction is won. The platform also blocks progress when it is empty on a pure CTV plan. See the open question |
| Frequency cap | Number | Optional | ADVERTISER | CHANGED. Pre-filled from the advertiser's own setting rather than asked; the trader can override it for a single campaign — unless the setting is locked |
| Budget cap | Number | Optional | ADVERTISER | NEW. Was absent; client confirmed optional |
| Formats | List of enum | — | CONSTANT | CHANGED, then **CORRECTED**. `["streaming_tv"]` in the model. **API-VERIFIED: the enum holds 21 values and twelve of them are channels** — `standard_display amazon_mobile_display aap_mobile_app video display online_video streaming_tv prime_video discovery paramount channel4 netflix disney pluto bskyb hulu tubi roku vevo dazn other`. So the API does **not** separate format from channel the way the model does; see the note under §2.3. And the **forecast request must also send `prime_video`** or its supply line is absent |
| Product categories | List of **str** | Required | ADVERTISER → INFERRED | CHANGED, then **CORRECTED**. "for video" dropped — CTV is always video, so the condition was always true. Type was `List[int]`; the values are **long numeric strings**, not integers. Taken from the advertiser's settings, else implied from the brief. **API-VERIFIED:** `GET /api/contextual-targeting/{market}/product-categories/` returns **25,973** categories for GB, paginated 100 at a time. Only leaf subcategories are selectable |
| Conversion types | List of str | Optional | ASKED | **NEW — API-VERIFIED.** **Six** events exist, not four, and they are **market-specific**: `ADD_TO_SHOPPING_CART` [GB, US], `APPLICATION` [GB, US], `CHECKOUT` [GB only], `PAGE_VIEW` [GB only], `SEARCH` [US only], `OTHER` [US only]. `GET /api/conversions/definitions/` requires a `selected_advertiser_id` query parameter |

> **REVIEW NOTE — simplify for CTV and imply the answers** (review comment on the two v1.1.0 field lists above): Much of this list came from the general strategy flow rather than a CTV one. Two things follow.
>
> **Cut what does not apply to CTV.** The multi-format choice, the click-based KPIs and the per-market base bid all exist because the original flow covered Display and non-CTV video. For CTV the format is a constant and the price comes from the deal, so those choices have nothing to decide.
>
> **Imply the rest.** The trader should end up being asked for very little — in practice the market, the budget and the dates, and even those are read from the brief when the brief states them. Everything else is generated, derived, taken from the advertiser's settings, or fixed. Hence the Source column above: a field can be required by the plan and still never be put to the trader as a question.
>
> **OPEN QUESTIONS:**
>
> - Is there anything left in this table you would still want the trader **asked outright**, rather than implied? The list is currently down to market, budget and dates.
> - `Budget cap` is marked ADVERTISER here on the assumption it behaves like the frequency cap. Is a budget cap held per advertiser, or is it per campaign?
> - When the agent infers a value, should it show what it inferred and let the trader correct it, or only surface the ones it is unsure about? The first is safer; the second is shorter.
>
> Individual rows in this table are confirmed by later comments in this same review — currency, KPI, frequency cap, formats, product categories, selling location and ASINs each have their own note further down.

> **REVIEW NOTE — strategy name is generated, not asked** (review comment on *"Required"* against Strategy name): The name carries no planning decision — it is a label for finding the strategy again later — so the agent composes it from the brief instead of spending a question on it.
>
> Convention: `{Category}_{Market}_{Goal}_{MonthYear}`, for example `Education_GB_Awareness_Sep2026`. Uniqueness is still checked against `GET /api/strategies/check_strategy_name_uniqueness/`; on a collision the agent appends a version suffix (`_v2`) and re-checks rather than stopping to ask.
>
> The requirement becomes **Optional** and the source **GENERATED**. Those are two separate statements: the plan will always end up with a name, but the trader is never required to supply one, and can rename it afterwards. "Auto-generated" is not a requirement level — it belongs in the Source column.
>
> **OPEN QUESTIONS:**
>
> - Do traders already use a naming convention for finding strategies later? Generating names in a different shape would make their own lists harder to scan, so it is better to match an existing habit than to invent one.
> - `{Category}` comes from the product category, which is itself taken from the advertiser's settings or implied from the brief. If neither is known when the name is composed, what should stand in its place — the advertiser name, or a shorter convention without the category?

> **REVIEW NOTE — multi-market scope and its effect on the flow** (review comment on *"Multi-select"* against Target markets, asking whether multi-market is supported and whether it means repeating choices per market): Recommendation is **one market per strategy in M1**, with the field kept as a list so that adding multi-market later is not a rebuild. If a brief names several markets the agent says so plainly and proposes starting with one rather than silently picking.
>
> On the second half of the question — nothing should be asked twice. Most of the flow is decided once for the campaign; only a few things genuinely vary by market:
>
> | Varies per market | Asked once for the campaign |
> |---|---|
> | Budget allocated to that market | Flight dates |
> | Currency of that market's spend | Goal and KPI |
> | Deals matched, and therefore the CPM | Creative durations |
> | Available locations — `GET /api/strategies/locations/{market}/` | Audience choice |
> | Available product categories — `GET /api/contextual-targeting/{market}/product-categories/` | Creatives and their approval |
> | Reach forecast for that market | Tracking (ASINs, ad tag), credit check |
>
> Two of those are easy to miss: the locations and product-category endpoints are both keyed by market, so those lists differ even when the trader's intent does not. Reach can be added together across markets, since the audiences do not overlap — unlike across providers within one market, where there is no deduplication.
>
> **OPEN QUESTIONS:**
>
> - Is one market per strategy acceptable for M1, or is multi-market needed in the first release? It affects the budget split, the currency rule and per-market deal matching.
> - `primary_currency` is currently a single field. For a multi-market campaign, should the plan total be shown in the advertiser's primary currency with each market's spend in its own, or should the whole plan sit in one currency?
> - When a brief names several markets and M1 supports one, should the agent ask which market to start with, or start with the first named and say so?

> **REVIEW NOTE — currency comes from the market** (review comment on *"Required"* against Primary currency): For a single-market strategy the currency is not a decision — it follows from the market. `GB → GBP`, `US → USD`, `DE` or `FR → EUR`. The dropdown goes, and the requirement becomes **Optional** with source **DERIVED**: the plan always has a currency, but the trader is never asked for one and can still override it.
>
> As with the strategy name, "auto-derived" is not a requirement level. Whether the plan needs a value and where the value comes from are two separate columns, and keeping them separate is the whole point of adding Source.
>
> For multi-market, the proposal is to show the campaign total in the advertiser's primary currency and each market's spend in that market's own currency — flagged as a question under the Target markets note above rather than settled here.
>
> 🔴 **CORRECTION — the mechanism above is wrong, though the behaviour is right.** The comment asked for the currency not to be a question, and that stands. But it is **not derived from the market** — it is an **advertiser default**.
>
> **VERIFIED on the platform:**
>
> - The field arrives pre-filled as `EUR` **before any market is selected**
> - Selecting `United Kingdom` leaves it as `EUR`
> - A live strategy exists with `primary_currency: NOK` and `markets: ["US"]`, which a market-derived rule could not produce
>
> So the source is **ADVERTISER**, not DERIVED. The Step 1 row has been corrected.
>
> **This also means two currencies coexist in every plan**, and both are sent:
>
> ```
> primary_currency          the strategy's currency, from the advertiser        EUR
> markets_info[].currency   the market's own currency, derived from the market  GBP
> ```
>
> The platform converts between them. Verified at roughly 1.0909 GBP to EUR: a submitted £10,000 stored as EUR 10,909.09, and a base bid of £25 stored as EUR 27.27.
>
> 🔴 **The arithmetic consequence matters more than the field.** Deals carry their own `deal_price_currency`, and **verified across 369 deals there are eight of them** — USD 156, EUR 95, GBP 35, CAD 22, MXN 19, BRL 16, AUD 14, JPY 12. A GB plan can therefore hold a USD-priced deal. Mixing a budget in one currency with a CPM in another produces a nine per cent error at the observed rate:
>
> ```
> Wrong    10,909.09 / 22.96 x 1000 = 475,178 impressions
> Right    10,000.00 / 22.96 x 1000 = 435,540 impressions
> Error     39,638 impressions
> ```
>
> All arithmetic must be performed in one currency, and the agent must state which.
>
> **API-VERIFIED — the enum is far larger than assumed.** `primary_currency` holds **19 values**, not three:
>
> ```
> USD · MXN · CAD · BRL · AED · SAR · GBP · EUR · SEK · TRY · AUD ·
> INR · SGD · JPY · NOK · DKK · NZD · CNY · CHF
> ```
>
> ✅ **This closes the first open question below.** `NOK` is already in the enum, so no extension is needed and no market is out of scope on currency grounds. The "EUR, GBP, USD only" in earlier revisions was simply wrong.
>
> **OPEN QUESTIONS:**
>
> - Should a trader be able to override the currency at all? Overriding it makes the plan total and the deal CPMs disagree unless a rate is applied somewhere, and the platform clearly does apply one — so the question is whether the agent should expose that.
> - For multi-market, the proposal is to show the campaign total in the advertiser's primary currency and each market's spend in that market's own currency. Confirm.
> - Where does the conversion rate come from, and when is it fixed — at plan time, at creation, or at delivery? A rate that moves between planning and delivery changes what the budget buys.

> **REVIEW NOTE — a frequency KPI can carry a target value** (review comment on *"KPI"*): Choosing frequency as the KPI was recorded without anywhere to put the number the trader is aiming for. A field holds it, shown only when the KPI is frequency and absent when it is reach. The comment said "1-5"; the platform's own control offers 2, 3, 4 and 5, and omitting 1 is right — a frequency of one exposure per person is not a frequency target.
>
> 🔴 **CORRECTED — the field is `target_kpi` and it is a STRING, not `kpi_target_value` as an integer.** Both the name and the type in the earlier version were invented rather than read. The API field is `target_kpi: str`.
>
> **A string is right, and not merely what the API happens to do.** The field has to carry the target for whichever KPI is chosen, and the sixteen KPIs do not share a type:
>
> ```
> FREQUENCY                 3          an integer
> RETURN_ON_AD_SPEND        4.5        a decimal — an int cannot hold this
> VIDEO_COMPLETION_RATE     0.85       a rate
> REACH                     500000     a large integer
> ```
>
> An integer field would silently truncate a 4.5 ROAS target to 4. The range check therefore belongs in **validation conditional on the KPI**, not in the type: 2 to 5 when the KPI is frequency, and something different for every other KPI.
>
> **This is not a label; it changes the forecast.** The impressions are already fixed by budget and CPM, so a frequency target implies the reach the plan has to hit:
>
> ```
> impressions = budget ÷ effective CPM × 1000
> reach = impressions ÷ target frequency
> ```
>
> A target of 3 on 300,000 impressions means the plan needs to reach 100,000 people. If the forecast comes back at a frequency of 5, the audience is too narrow — the same impressions are landing on too few people — and that is what the repair loop should act on. Without the target the agent has nothing to compare the forecast against.
>
> **OPEN QUESTIONS:**
>
> - Should the target feed the forecast and the repair loop as described, or is it recorded for reporting only? The two lead to different agent behaviour.
> - When the KPI is frequency and the trader does not state a target, should the agent assume one — 3 is the obvious middle — or leave it empty and forecast without a target to check against?
> - Is there an equivalent target for a **reach** KPI, or does only frequency carry a number?

> **REVIEW NOTE — "Table" is a widget, not a data type** (review comment on *"Table"* against Market budgets, asking whether it is a single market budget): With one market there is one budget, and a table is a strange way to present a single number. The deeper point is that the Type column had a UI widget in it. Type should say what the field holds; how it is drawn belongs to the interface.
>
> The same correction applies to Base bids, which also read "Table". Both are now stated as an amount per market, with the schema unchanged underneath: `market_budgets: list[MarketBudgetBidSchema]` stays a list so multi-market needs no rebuild, while a single-market plan asks for one number — in practice read from the brief, since briefs state the budget.
>
> **OPEN QUESTIONS:**
>
> - Are there other rows in this table where the Type column still names a widget rather than a type? "Multi-select", "Dropdown", "Radio", "Textarea" and "Checkbox table" all describe controls. Worth agreeing whether this column should hold data types throughout, with the controls recorded separately for the interface.
> - The budget is read from the brief where the brief states one. If a brief gives a range — "eight to ten thousand" — should the agent take the upper figure, the lower, or ask?

> **REVIEW NOTE — base bids do not apply to CTV** (review comment on *"Required"* against Base bids): The price is the deal's CPM, so there is no bid for the trader to set. The field stops being a question and the effective rate is read from the matched deal's rate card, plus any audience data fee.
>
> **This costs the repair loop a lever, which matters more than the field does.** The v1.1.0 loop had two moves when reach fell short: widen the audience, and raise the bid. With fixed-CPM deals the second one is gone. What remains is relaxing the targeting and widening the inventory — and per the audiences note above, even the audience lever may be absent when the trader has chosen no audience. The repair-loop row in Step 6 has been corrected accordingly.
>
> Widening the inventory has its own limit worth stating: adding Netflix or Disney+ raises impressions, but those tiers return no reach forecast, so the agent cannot verify that the added inventory fixed the reach shortfall. It should say so rather than imply the problem is solved.
>
> **OPEN QUESTIONS:**
>
> - **Private auction deals carry a floor CPM, not a fixed one** — §2.3 describes them as "Floor CPM, competitive". Does a bid still matter there? If it does, the agent keeps a bid lever on that deal type and the answer is narrower than "base bids do not apply to CTV".
> - `MarketBudgetBidSchema.base_bid` is a required field on the create payload. If the trader is never asked for it, what should be sent — the deal's CPM, a null, or does the CTV create endpoint drop the field entirely?

> **REVIEW NOTE — advertiser-level defaults** (review comment on *"Optional"* against Frequency cap: *"we have a default per advertiser"*): This introduces a concept the document did not have. Some settings belong to the advertiser, not to the campaign — they do not change from one brief to the next, so asking for them every time is wasted effort. The frequency cap is the first of several: product categories, selling location and device type all turn out to sit here too, each confirmed in a later comment.
>
> **Where they come from and when.** Advertiser settings are read at the start of the session, before the brief is parsed — `GET /api/admin/advertiser/{id}/`, model `AdvertiserAdminRetrieve`. Loading them first and parsing the brief second gives the right precedence: the defaults fill the form, and anything the brief states overrides them.
>
> **One thing a plain default cannot express.** A later comment notes that some advertisers permit Connected TV only. That reads less like a default and more like a policy — something the trader should not be able to override, and that the repair loop must not quietly relax when reach falls short. So each setting needs to carry whether it is binding, not just its value:
>
> ```python
> class AdvertiserSetting(BaseModel):
> value: Any
> is_locked: bool = False # a brand policy the trader cannot override
> reason: Optional[str] = None # shown to the trader when locked
> ```
>
> Without `is_locked` the agent cannot tell the difference between a starting point and a rule, and will offer to relax something it is not allowed to touch.
>
> **OPEN QUESTIONS:**
>
> - **What is the full list of settings held per advertiser?** Knowing it now means building the section once instead of adding a field each time one surfaces. So far: frequency cap, product categories, selling location, device type — and possibly budget cap.
> - Which of them are **locked** brand policies rather than overridable defaults? That decides what the repair loop is allowed to change.
> - Does the advertiser record already hold a frequency cap, or does that field need adding? The endpoint exists; whether it carries this value is not visible from the API listing alone.
> - When an advertiser has no value set for one of these, what should the agent do — leave it empty, or fall back to a platform-wide default?

> **REVIEW NOTE — the goal is a default, not a constant** (review comment on *"FIXED"* against Goal: *"Defaulted for CTV"*): The row read Constant / FIXED / "Always AWARENESS". It is a **default**. The trader may change it.
>
> **This was the document hardening a soft statement.** The client's own note said CTV is *"**typically** used as an Awareness goal"*, and the row turned "typically" into "always". That is the same shape of error as the *"only"* on the audience row and the *"we have a **default** per advertiser"* on the frequency cap — a preference recorded as a rule.
>
> **The follow-up answer establishes the behaviour**, and it is a third category the document did not have:
>
> > *"yeah we would then support those based on the goal. For CTV we don't advise to do non awareness but we should not stop the user selecting an alternative."*
>
> So the agent does three things, not two:
>
> 1. Defaults the goal to Awareness
> 2. **Accepts** a change to another goal — never blocks it
> 3. **States that non-Awareness is not advised for CTV, and why** — tracking further down the funnel is unreliable on streaming inventory
>
> Silently accepting the override is as wrong as refusing it. Hence a new source value, **DEFAULTED (advised)**, distinct from both CONSTANT and a plain default.
>
> **Four categories now exist where the document had two:**
>
> ```
> CONSTANT          one value exists, for everyone            formats
> DEFAULTED         pre-filled, changeable, no comment        currency, location
> DEFAULTED-ADVISED pre-filled, changeable, agent comments    goal
> LOCKED            pre-filled per advertiser, NOT changeable device types, possibly
> ```
>
> **The KPI list follows the goal.** The same answer reinstates the four KPIs v2.0 removed on the basis that the goal was fixed. The KPI options are therefore conditional on the goal rather than a fixed pair.
>
> **API-VERIFIED, and larger than expected.** The goal enum holds **15 values**, not three:
>
> ```
> AWARENESS · CONVERSION · CONSIDERATION · OTHER · PROSPECTING · REMARKETING ·
> RETENTION · UPPER_FUNNEL_PROSPECTING · CONVERSIONS_OFF_AMAZON ·
> ENGAGEMENT_WITH_MY_AD · CONSIDERATIONS_ON_AMAZON · PURCHASES_ON_AMAZON ·
> MOBILE_APP_INSTALLS · PURCHASES_ON_OFF_AMAZON · MULTI_FUNNEL
> ```
>
> With fifteen options rather than three, treating the field as a constant would have hidden a great deal more than it appeared to.
>
> **And the KPI enum is larger too — 16 values**, of which the automated-strategy endpoint accepts **five**:
>
> ```
> All 16      REACH · FREQUENCY · COST_PER_VIDEO_COMPLETION · VIDEO_COMPLETION_RATE ·
>             CLICK_THROUGH_RATE · COST_PER_CLICK · COST_PER_DETAIL_PAGE_VIEW ·
>             DETAIL_PAGE_VIEW_RATE · RETURN_ON_AD_SPEND · TOTAL_RETURN_ON_AD_SPEND ·
>             COMBINED_RETURN_ON_AD_SPEND · COST_PER_INSTALL · COST_PER_ACTION ·
>             COST_PER_FIRST_APP_OPEN · COST_PER_SIGN_UP · OTHER
>
> Automated   REACH · FREQUENCY · COST_PER_ACTION ·
>             RETURN_ON_AD_SPEND · TOTAL_RETURN_ON_AD_SPEND
> ```
>
> That restricted set is most of the goal-to-KPI mapping already: reach and frequency for Awareness, cost-per-action and the two return-on-ad-spend variants for Conversion.
>
> **The goal also affects available inventory.** `GET /api/inventory-sources/` takes `goal` as a **required** query parameter — omit it and the call returns `"None is not a valid StrategyGoal"`. So changing the goal changes what inventory comes back, which the flow has to re-run rather than assume.
>
> **OPEN QUESTIONS:**
>
> - Which of the fifteen goals are in scope for CTV? Five map obviously to CTV; the rest look like sponsored-products or app-install goals.
> - Is the full goal-to-KPI mapping readable from an endpoint? `GET /api/strategies/choices/` looked like the place, but it returns a **list of strategies** rather than enumerations — so the mapping is not there. The restricted automated-strategy enum is the best evidence we have.
> - When a trader picks a non-Awareness goal, does the reach forecast still work? The forecast takes `goal` as an input, so a different goal may return a different supply set or none at all.

> **REVIEW NOTE — the format is always `streaming_tv`; Prime Video is a provider** (review comment on *"Required"* against Formats: *"is always streaming_tv"*): With one possible value there is no choice to present, so the field becomes a constant and leaves the list of things the trader is asked.
>
> The row also mixed up two levels. `prime_video` was listed as a format, but Prime Video is a **provider** — it sits inside `streaming_tv` alongside Netflix, Disney+ and others. Format is the kind of inventory; provider is who is showing the ad.
>
> **The document already contradicted itself on this.** Step 2 fetches deals with `GET /api/deals/?markets={market}&formats=streaming_tv` — `streaming_tv` only. And `SelectedDealSchema.provider` is described as *"e.g. Prime Video, Netflix, Disney+"*, so Prime Video was already captured correctly one step later. Step 2 was right; Step 1 was carrying a v1.1.0 mistake, where the deals table was even headed "Prime Video Deals". `FormatEnum.PRIME_VIDEO` has been annotated rather than deleted, since removing an enum value is a breaking change for anything already sending it.
>
> **API-VERIFIED — and the API does not make this distinction.** The open question below asked which format values the API accepts. The answer complicates the position above rather than confirming it. `FormatsAndKpis.format` holds **21 values, and twelve of them are channels**:
>
> ```
> standard_display · amazon_mobile_display · aap_mobile_app · video · display ·
> online_video · streaming_tv · prime_video · discovery · paramount · channel4 ·
> netflix · disney · pluto · bskyb · hulu · tubi · roku · vevo · dazn · other
> ```
>
> So `netflix`, `disney`, `paramount`, `channel4`, `pluto`, `bskyb`, `hulu`, `tubi`, `roku`, `vevo`, `dazn` and `discovery` are all format values. **In the API, `format` *is* the channel dimension.**
>
> **The review comment is still right about the model** — Prime Video is a channel, and treating it as a peer of "streaming video" confuses two levels. But the API does not agree, and that has a consequence the document has to state rather than resolve by preference:
>
> | Endpoint | Does `prime_video` matter |
> |---|---|
> | `GET /api/inventory-sources/` | **No** — the same two Amazon sources come back either way, verified |
> | `POST /api/strategies/reach-forecast/` | **Yes** — it returns a separate `DSP_PRIME_VIDEO` supply line. Omitting it loses 71,120 reach and 212,860 impressions |
> | `GET /api/deals/` | Passed as a filter. Verified: adding all fourteen CTV channel formats to a GB query returns **62 deals — exactly the same as `streaming_tv` alone** |
>
> **Practical rule for the implementation:** the plan model holds `streaming_tv` plus a channel, because that is the honest structure. The **forecast request** additionally sends `prime_video` where Prime Video inventory is in the plan, because that endpoint keys its supply lines on the format field. The two are not in conflict once it is written down.
>
> `FormatEnum.PRIME_VIDEO` has been annotated rather than deleted, since removing an enum value is a breaking change for anything already sending it.
>
> **OPEN QUESTIONS:**
>
> - Given that the API's `format` enum is the channel list, should the plan carry a separate `channel` field at all, or should it use format values throughout and accept the naming? Two representations of one idea is the thing that caused this comment.
> - The channel-shaped format values (`netflix`, `disney`, `hulu`, `roku`, `tubi`, `pluto`, `bskyb`, `dazn`, `vevo`, `channel4`, `paramount`, `discovery`) do not change the deals returned for GB. Are they live anywhere, or reserved?
> - The v1.1.0 create payload example sends `"formats": ["prime_video"]`. Corrected to `["streaming_tv"]` in the examples below; confirm the endpoint still accepts the old value for anything already sending it.

> **REVIEW NOTE — product categories come from the advertiser or the brief** (review comment on *"Required for video"*: *"we have a default on the advertiser, or maybe could imply from the brief"*): A product category does not change from one campaign to the next — BrightPath is an education advertiser on every brief — so asking for it each time treats a property of the advertiser as if it were a decision about the campaign.
>
> Resolution order: the advertiser's own setting first, and where that is absent, what the brief implies — "an education website" is enough to place it.
>
> The **"for video"** qualifier goes too. It arrived from v1.1.0, where Display was also in scope. CTV is always video, so the condition is always true and reads as if there were a case where the field did not apply.
>
> **A third source exists but arrives too late to fill this field.** `POST /api/contextual-targeting/{market}/asin-validation/` returns a product category alongside each valid ASIN. Since ASINs are collected at the tracking step, well after this one, that category cannot populate Step 1 — but it is worth using as a **cross-check**: if the advertiser is set to Education and the ASINs come back as Electronics, something is wrong and the agent should say so rather than let the mismatch through.
>
> **OPEN QUESTIONS:**
>
> - **Is the advertiser-level value actually a product category, or an industry?** The advertiser endpoints expose `GET /api/admin/advertiser/get_industry_and_sub_industry_choices/`, while product categories come from a different taxonomy entirely (`GET /api/contextual-targeting/{market}/product-categories/`, models `ProductCategory` and `ProductSubcategory`). If the advertiser holds an industry, a mapping between the two is needed and is not currently anywhere in this document.
> - Does an advertiser carry one category or several? The field is a list, so the agent should match whatever shape the advertiser record uses.
> - Product categories are fetched per market. For a multi-market campaign, can the same category be assumed available in every market, or must each be checked?

> **REVIEW NOTE — selling location leaves this step** (review comment on *"Required"* against Selling location: *"can leave out"*): The row has been removed from the table above. Whether the advertiser sells on Amazon decides **how conversions are measured**, not how the plan is built — so it belongs with the tracking step, where the ASIN and ad-tag questions already sit. The tracking step asks *"Sells on Amazon?"* already; this is the same question, and it was being asked in two places.
>
> It is also an advertiser-level property rather than a campaign one, so it arrives pre-filled from the advertiser's settings and the trader only changes it in the rare case a campaign differs.
>
> **This quietly resolves half of the open question flagged twice in this document.** The concern was that `product_location` is required by the `POST /strategies/` payload at Step 8, yet was being collected at Step 11 afterwards. If the value comes from the advertiser's settings — loaded at the start of the session — then the agent already holds it when it creates the strategy, and nothing needs patching. Only the ASINs still arrive later; that half is dealt with in the notes on the ASIN row and on post-creation updates.
>
> **OPEN QUESTIONS:**
>
> - Can one advertiser have campaigns with different selling locations — some driving to Amazon, some to their own site? If so this stays an overridable default rather than a fixed advertiser property.
> - If an advertiser has no selling location set and the brief does not say, is it safe to assume `NOT_SOLD_ON_AMAZON` and rely on ad-tag tracking, or should the agent ask?

> **REVIEW NOTE — product ASINs leave this step too** (review comment on *"Conditional"* against Product ASINs: *"comes later"*): This one confirms what the revision already said — ASINs moved to the tracking step. The correction is smaller: if they come later, they should not still be listed here with a note attached. The row has been removed.
>
> The sequence is: create the strategy with `product_asins: []`, then collect and validate the ASINs at the tracking step and update the strategy. Validation is unchanged — `POST /api/contextual-targeting/{market}/asin-validation/`, keyed by market rather than hard-coded to a single one.
>
> With the selling-location note above, this closes the timing question that appeared twice in this document.
>
> **OPEN QUESTION:**
>
> - Should the ASIN list be validated in one call at the tracking step, or as the trader pastes them in? Validating late means a trader can enter twenty ASINs and only then learn that three are wrong.

**API calls at this step:** `GET /api/strategies/check_strategy_name_uniqueness/`, `GET /api/contextual-targeting/{market}/product-categories/`

REMOVED from this step: ad tag conversions (moved to Step 11), the three non-CTV format options (Display, Online Video — future scope), the four non-awareness KPIs (CTR, CPC, CPA, CPDPV — future scope)

> **RESOLVED — was: open question on `product_location` and `asin_numbers` timing.** Both were listed in this step while also being collected at the tracking step, after the strategy is created. The answer is to collect them late and let the strategy be updated afterwards:
>
> - `product_location` arrives from the advertiser's settings, so the agent already holds it when it creates the strategy — nothing to patch.
> - `asin_numbers` is sent as an empty list at creation and filled in at the tracking step via `PATCH /api/strategies/{id}/` (model `StrategyUpdate`, confirmed present in the staging API).
>
> The second half of this question is repeated further down at the tracking step and is closed there too.

### Step 2: CTV Inventory (the tier fork)

CHANGED — was Step 3 "Deals" in v1.1.0. Now comes before audiences, and introduces the three-tier fork.

**What was in v1.1.0:**

A flat deals table filtered by market and format, with checkbox selection

**What it is now:**

| Field | Type | Requirement | Source | Change from v1.1.0 |
|---|---|---|---|---|
| Channel | List of str | Optional | INFERRED | NEW. Which providers to run on — Prime Video, Netflix, Disney+. This is the strategic choice; the deal underneath it is not |
| ROS or genre | String | Optional | INFERRED | NEW. Run-of-service, or a named genre, used to narrow the match |
| Selected deals | List of deal objects | Required | MATCHED | CHANGED. No longer picked from a table. Matched from the market, duration and channel, with optional ROS or genre and the targeting requirements. Candidates from `GET /api/deals/?markets={market}&formats=streaming_tv` |
| Specific deal ID | String | Optional | ASKED | NEW. `specific_deal_id` — an escape hatch for a trader who already has a particular deal in mind |
| Inventory tier (per deal) | Enum | Derived | DERIVED | NEW. Each deal classified as AMAZON_OWNED, THIRD_PARTY_PRECURATED, or THIRD_PARTY_NEEDS_CURATION |
| CTV rate card | Reference | Read | API | NEW. `GET /api/rates/ctv/{market}/` — channels, durations, CPMs |

**NEW — Genre upsell logic:** The client asked: "based on the brief we can suggest whether a specific available genre would be a better match at a slightly higher CPM." Example: Prime Video ROS at $18.22 vs Action at $22.07 — the agent should recommend when the brief implies a genre match.

**NEW — Curation capture** (for 3P-needs-curation tier): When deals can't be selected yet (Disney+ etc.), the agent captures what VOW needs to curate later: genres, durations, targeting preferences, budget, flight dates.

| Field | Type | Requirement |
|---|---|---|
| Curation: genres | Multi-select | Required for curation tier |
| Curation: durations | Multi-select | Required for curation tier |
| Curation: targeting prefs | Text | Optional |
| Curation: budget | Number | Required for curation tier |
| Curation: flight dates | Date range | Required for curation tier |

**API calls at this step:** `GET /api/deals/`, `GET /api/deals/filter-properties/`, `GET /api/rates/ctv/{market}/`

> **REVIEW NOTE — deals are matched, not selected** (review comment on *"Checkbox table"* against Selected deals): This reverses the order of the step. The table went; the trader states requirements and the agent finds the deals that fit them.
>
> **What the trader decides, and what the agent works out.** Choosing Prime Video over Netflix is a real decision. Choosing between `EXT7P75718S8MNR` and `EXT7P75719Q2LKM` is not — it is plumbing. So the trader supplies the channel, optionally a genre or run-of-service, and the targeting they want; the agent matches on market, duration and channel and returns what fits. A trader who already has a deal in mind can name it through `specific_deal_id`, which keeps the shortcut without making everyone use it.
>
> **What is surfaced.** The channel, the effective CPM and the estimated impressions. Not deal IDs, not raw deal names — a name like *"Prime Video | Preferred Deal | UK - 30 - ROS"* carries nothing the trader cannot see more plainly elsewhere, and mis-reading one silently changes the plan.
>
> **Two things must still surface, even though the deal does not.**
>
> - **Tier capability.** Third-party tiers return no reach forecast. If only the CPM is shown, the trader has no way to know that the reach figure is missing for part of the plan — and Step 6's honesty rule requires telling them.
> - **Commercial commitment.** A Programmatic Guaranteed deal owes the full budget and cannot be paused (§2.3). Hiding the deal must not hide that. The agent should say it plainly before the trader accepts the CPM — *"this is a guaranteed deal, so the full £6,000 is committed and cannot be paused"* — rather than let a commitment pass unnoticed because the deal type was internal.
>
> This pattern was already in the revision, in one place: the curation capture below, where deals cannot be selected yet and the agent records genres, durations, targeting and budget instead. That is exactly the model being described. It simply was not applied to the tiers where deals do exist.
>
> The graph node has been renamed from `select_inventory` to `match_inventory_deals` so the code says what it does.
>
> 🔴 **API-VERIFIED — the decisive open question is now answered, and the answer is bad.** All 369 deals were fetched and every field inspected.
>
> **What the deal object actually carries:**
>
> ```
> ✅ external_deal_id · name · deal_type · deal_price_type · deal_price_amount ·
>    deal_price_currency · media_types · devices · environments · locations ·
>    genre · ad_lengths
>
> ❌ channel          — does not exist
> ❌ inventory_tier   — does not exist
> ❌ provider         — does not exist
> ❌ publisher        — does not exist
> ```
>
> **So the channel is only in the name, and the tier can only be derived from the channel.** The question above said this "decides whether this step can be built as described". It can be built, but only with a name parser — and the parser is worse than it sounds.
>
> **`genre` exists but is null.** Three Paramount deals were checked. All three carry a channel in the name and `genre: null`:
>
> ```
> 3PS_Freewheel_UK_STV_Paramount_My 5           genre: null
> 3PS_Freewheel_UK_STV_Paramount_Paramount+     genre: null
> 3PS_Freewheel_UK_STV_Paramount_PlutoTV        genre: null
> ```
>
> The genre upsell logic above therefore has no structured field to read. It would have to parse the name too.
>
> **Eight naming conventions, and the casing is inconsistent:**
>
> | Prefix | Deals | Example |
> |---|---|---|
> | pipe-form | 148 | `Prime Video \| Preferred Deal \| Video \| UK - 15, 20 – ROS` |
> | `3PS` | 129 | `3PS_Freewheel_UK_STV_Paramount_My 5` |
> | `VowMade` | 78 | `VowMade_Fifa 2026_ZA_Football_CTV_Amazon DSP_3P_MS_MLMBRID8184` |
> | `EB` | 6 | |
> | `Tubi` | 4 | |
> | `TUBI` | 2 | 🔴 same channel, different casing |
> | `62797` | 1 | |
> | `APC` | 1 | |
>
> One parser cannot handle all eight reliably, and `Tubi` versus `TUBI` shows the data is not being entered against a controlled vocabulary. **Anything the agent derives from a deal name must be marked as derived** — hence `channel_confidence` on the deal schema in §5.
>
> 🔴 **And the deal counts in earlier revisions were wrong.** This document said 83 deals; there are **369**. The 83 came from a filtered query. Filters change the number dramatically:
>
> ```
> Unfiltered                                            369
> GB + streaming_tv                                      62
> GB,ZZ + streaming_tv,prime_video,UNKNOWN               83   ← the old number
> GB + all 14 CTV channel formats                        62   ← adding channels changes nothing
> ```
>
> Note the third row against the fourth: adding every channel format adds no deals, but adding the `UNKNOWN` format and the `ZZ` market adds 21. **So the padding is doing real work** — an unpadded query silently loses inventory.
>
> **Deals exist in 18 markets, not two:**
>
> ```
> GB 82 · US 78 · ES 25 · DE 23 · FR 23 · IT 23 · CA 22 · MX 20
> BR 16 · AU 14 · JP 12 · NO 3 · IE 2 · AT 2 · DK 2 · FI 2 · SE 2 · NL 1
> ```
>
> 🔴 **Two deal types, and the missing one matters:**
>
> ```
> PRIVATE_AUCTION           341   (92%)
> PREFERRED                  28   (8%)
> PROGRAMMATIC_GUARANTEED     0   ← none at all
> ```
>
> The commercial-commitment warning above is written for PG deals. **There are none in the inventory**, so that warning currently never fires — and more importantly, PG is the only deal type with guaranteed delivery. Without it **no plan can promise impressions**, and every forecast is an estimate. That belongs in what the agent says at Step 6.
>
> ✅ **92% of deals are FLOOR_RATE, 8% FIXED_CPM.** A floor is a minimum, not a price, so on almost all inventory the bid decides what is actually paid. This is the evidence behind treating base bid as a plannable field.
>
> **Two deals are priced at zero** (both FIFA 2026 ZA), not one as previously recorded. A zero CPM breaks impression arithmetic by division, so it needs an explicit guard rather than a comment.
>
> **OPEN QUESTIONS:**
>
> - 🔴 **D53 — can a controlled `channel` field be added to the deal object?** Eight naming conventions with inconsistent casing is not something a parser can be made reliable against. This is the highest-value data-quality request in the document: one field removes an entire class of silent error.
> - Why is `genre` null on deals whose name states a genre? Is the field unpopulated, or populated only on some sources?
> - When several deals match, how should the agent choose — cheapest CPM, best genre fit, or largest forecastable reach?
> - When nothing matches, what should happen? Widen the duration, drop the genre, or report back and ask?
> - Given no PG deals exist, should PG handling be built now or deferred until such a deal appears?
> - A GB plan can hold a USD-priced deal (see the currency note at Step 1). Which currency should the matched-deal CPM be shown in — the deal's, or the plan's?

### Step 3: Budget Split

ENTIRELY NEW — did not exist in v1.1.0. Added per client requirement.

> "We will need to support the suggested budget split across inventories or creative durations."

The agent proposes how the total budget is divided across inventories (Prime / Netflix / Disney) and across creative durations (15s / 30s). This is genuinely hard — different durations have different CPMs, and there's no reach data for Netflix/Disney to optimise against.

| Field | Type | Requirement |
|---|---|---|
| Split by inventory | Allocation (%) | Optional — preferred when more than one inventory is selected |
| Split by duration | Allocation (%) | Optional — preferred when more than one duration is selected |
| Split method | Enum | Agent states its assumption |

**Split method options:**

- **EVEN_BY_BUDGET** — same £ per inventory/duration; uneven impressions (higher CPM = fewer impressions)
- **EVEN_BY_IMPRESSIONS** — same impression count; uneven £ (higher CPM = more spend)

The agent must state which it chose and why, so the trader can adjust. Example: "I've split evenly by impressions, which weights spend toward the 30s at its higher CPM."

No API call — this is agent-side logic. The resulting budgets feed into the `market_budgets` field at strategy creation.

> **REVIEW NOTE — budget split is optional** (review comment on *"Budget split NEW"*; UI placement from a separate comment): The split is optional, not required. It is preferred because each inventory and each duration carries a different CPM, so a real split produces an accurate CPM; without one the agent must present a blended estimate and should say so plainly. The agent proposes a split by default and the trader can accept, adjust or skip it.
>
> **UI placement:** rather than a standalone step, the split is surfaced as a substep inside Step 2 (CTV Inventory), appearing only when more than one inventory deal is matched — with a single deal there is nothing to split. The step numbering here is left unchanged so the review comments stay anchored; the substep is a presentation decision, not a change to the flow's logic.

### Step 4: Audiences

CHANGED — was Step 4 in v1.1.0 and optional. Still optional, now suggestion-driven, and positioned after the budget split.

**What was in v1.1.0:**

Browse/search audience sets, checkbox selection, Similar/Exact toggle

**What it is now:**

| Field | Type | Requirement | Change from v1.1.0 |
|---|---|---|---|
| Audience options | 3 profiles | Optional | Requirement unchanged — still optional. Agent always generates narrow / balanced / wide |
| Chosen option | Select one | Optional | NEW. Trader picks one of the three, or declines them all and runs with no audience |
| Matching mode | Toggle | Conditional | Unchanged. Similar vs Exact — applies only when an audience is chosen |
| Effective CPM (per option) | Display | Read-only | NEW. Deal CPM + audience VCPM fee, shown per option so the trader sees the real cost |

**Constraints for CTV:**

- Amazon audiences can be applied to third-party inventory as well as Amazon-owned. The alternative is the inventory source's own targeting — a choice made per deal, not a property of the tier
- Product audiences not applicable to CTV (removed)
- AMC audiences are conditional — only when the advertiser has prior campaign data
- Nobody browses — the agent uses `POST /api/audience-sets/suggest/` exclusively
- The audience set does not need to be created before forecasting — it's created later at strategy creation via a simplified CTV endpoint

> **REVIEW NOTE — audiences are optional** (review comment on *"mandatory"* in the flow comparison above): Audiences were optional in v1.1.0 and remain optional. This revision had promoted them to mandatory; that is reverted. The agent still suggests three options every time, but the trader can decline all of them and run with no audience — a run-of-service baseline, which also means no 1P data and therefore no data fee (see §2.4).
>
> **Consequence for the repair loop:** widening the audience is one of the levers the agent uses when reach falls short. When no audience has been chosen that lever does not exist, so the agent has to work with budget, flight duration and the other targeting instead — and should say plainly when it has nothing left to relax rather than implying a fix is available.

> **REVIEW NOTE — Amazon audiences reach third-party inventory too** (review comment on *"Netflix/Disney"* in the constraints above: *"can use amazon audiences too"*): The word "only" was wrong. Amazon audiences are not confined to Amazon-owned inventory — they can be attached to Netflix, Disney+ and the rest. The inventory source's own targeting is the alternative, not the only option.
>
> This is the same mistake as the one on the tier table in §2.3, appearing a second time in this list. Both now describe a choice made per deal.
>
> **It changes the cost arithmetic, which matters more than the wording.** The earlier assumption was that an Amazon data fee could only apply to the Amazon portion of a plan. If Amazon audiences run on the third-party portion as well, the fee applies there too, and the effective CPM for that portion rises accordingly. The trader is comparing three situations rather than two: no audience data at all, Amazon data across the whole plan, or Amazon data on Amazon inventory with the source's own targeting elsewhere.
>
> **What the agent still cannot do on third-party inventory is verify the result.** Those tiers return no reach forecast, so the agent can widen an audience there but cannot show that it worked. It should say so rather than present an unverified change as a fix.
>
> The Audiences column in the §2.3 tier table therefore stops separating the tiers. What genuinely differs by tier is whether a reach forecast comes back and whether the deal exists yet.
>
> **OPEN QUESTIONS:**
>
> - Can Amazon audiences and the inventory source's own targeting both run on the **same** deal, or is it one or the other?
> - How limited is Amazon's targeting on third-party inventory in practice? The tier-table note says it may be device-only in some cases; knowing where the line falls decides whether the agent should recommend it or the source's own targeting.
> - The reply on this comment quoted a £2.00 VCPM Amazon data fee. Should figures like that be read from `GET /api/contextual-targeting/fees` in every case rather than written into the specification, so the plan never quotes a stale rate?

**API calls at this step:** `POST /api/audience-sets/suggest/` → `GET /api/audience-sets/suggest/{id}/`

> **RESOLVED — was: open question on the suggest endpoint's response shape.** There is no `bundles.narrow/balanced/broad` object; the endpoint returns a flat list of segments and the grouping is ours to do.
>
> **REVIEW NOTE — the three profiles are built by the agent, not returned by the API** (review comment on *"bundles.narrow/balanced/broad"*: *"not currently supported"*): v1.1.0 assumed the endpoint handed back three ready-made groups. It does not. The agent receives a flat list of segments with their reach and relevance, and assembles the three profiles itself.
>
> **This changes what the three profiles are.** Taken with the two earlier notes — the fee depends on the data provider rather than the profile, and choosing a profile is optional — Narrow, Balanced and Wide are no longer an API feature with three price points. They are a way of presenting the same flat list at three levels of breadth. They differ in reach and precision. They do not differ in cost.
>
> **The grouping rule now has to be written down, because nothing upstream provides it.** Proposal: group by **cumulative reach**, since the fee no longer separates the options and reach is what actually distinguishes them; keep the groups **nested**, so Balanced contains Narrow and Wide contains Balanced, which is easier to reason about than three unrelated sets; and add segments until each group meets a reach target rather than a fixed segment count, so the profiles stay comparable across briefs of different sizes.
>
> The `broad` versus `WIDE` naming mismatch noted in v1.1.0 disappears with the `bundles` object — there is no API field to disagree with, and `AudienceProfileEnum.WIDE` stands.
>
> **OPEN QUESTIONS:**
>
> - **Could we have a real response sample from `POST /api/audience-sets/suggest/`?** Knowing that `bundles` is wrong is only half the answer; the grouping rule, the fee handling and the audience schema all depend on the actual shape. This is the single most useful thing to unblock the audience work.
> - The request model in the staging API is named `SuggestAudienceGroupsInput`. Does "groups" mean the **caller** asks for a number of groups? If the endpoint can be told how to group, the agent may not need its own logic at all.
> - `POST` returns an id and `GET /api/audience-sets/suggest/{id}/` reads the result, so suggestion looks asynchronous. How long does it usually take? It decides whether the agent waits in the conversation or tells the trader it will come back.
> - Is grouping by cumulative reach the right basis, or should relevance score lead? The proposal above assumes reach.
> - the comment said "not **currently** supported". If `bundles` arrives later, the agent's grouping should be replaceable rather than baked in — is it worth designing for that now?

### Step 5: Targeting

ENTIRELY NEW — did not exist in v1.1.0.

| Field | Type | Requirement | Source | Default |
|---|---|---|---|---|
| Location — **include** | List of LocationRef | Optional | DERIVED | The market's country. **A narrower value REPLACES this rather than adding to it** — see review note |
| Location — **exclude** | List of LocationRef | Optional | ASKED | Empty. **NEW per review** — location holds two lists, not one |
| Instream position | Enum | Optional | ASKED | None |
| Content-rating exclusions | List of str | Optional | ADVERTISER | The advertiser's brand-safety exclusions, where it has any. **API-VERIFIED:** the strategy field is `content_rating_exclusions` — "content **rating**", not "content category" |
| Device types | List of enum | Optional | ADVERTISER | **CORRECTED per review.** Values are `CONNECTED_TV`, `DESKTOP`, `MOBILE`. **`CONNECTED_TV` is REQUIRED whenever the format is `streaming_tv`**; the other two are optional. The default is **either all three or `CONNECTED_TV` alone** — not an arbitrary combination — and which one is set per advertiser. May be locked rather than merely defaulted |
| **Mobile operating system** | Enum | Conditional | ASKED | None. **CORRECTED per review.** Values are **`IOS` or `ANDROID`** — not in-app versus mobile web. Applies **only when `MOBILE` is among the device types.** The field was named `mobile_environment`, which describes app-versus-browser; it is renamed because the values are operating systems |
| User location signal | Enum | Optional | PLATFORM | **NEW — API-VERIFIED.** `user_location_signal` on the strategy read model, observed as `CURRENT`. Undocumented anywhere; its full value set and meaning are an open question |

**There is no `TABLET` device value.** Earlier revisions and the deals filter both suggest four device types; the filter's fourth value is `UNKNOWN`, which is a data artefact rather than a targeting option. The conditional on the operating-system field therefore depends on `MOBILE` alone.

**Critical design note from the client:** "This targeting list frequently changes so it should be easy to add new targeting types." — the implementation must be config-driven, not hard-coded. Adding a new targeting type should be a configuration change, not a code change.

Not supported by VOW today (future scope): genre exclusions, day-parting, language.

---

#### Location is not a list of strings — three ways to obtain one

> **REVIEW NOTE — locations are identifiers from a lookup** (review comment on *"List[str]"* against Location: *"can the user search for locations? we will need to validate a user provided list of postcodes to get location ids. There is also a custom radius location you can create in Amazon from a given address + a numeric value and unit (km / miles) to get a new location id."*): The field was typed as a list of strings, which reads as though a trader could type a place name. They cannot. A location is an **identifier obtained from a lookup**, and there are three ways to obtain one.
>
> | Path | How it works | Endpoint |
> |---|---|---|
> | **Search** | The trader names a place; the agent searches and resolves it to an identifier | `GET /api/strategies/locations/{market}/?query=…` |
> | **Postcode validation** | The trader supplies a list of postcodes; each is validated and returns an identifier. Some will be invalid and the agent must say which | `POST /api/strategies/postcode-validation/{market}/` |
> | **Custom radius** | An address plus a distance and a unit. This **creates a new location identifier** in Amazon | `POST /api/strategies/locations/{market}/` |
>
> **The search and radius paths share one path and differ only by method** — confirmed in reply: *"GET /strategies/locations/{market}/ is for searching location and POST /strategies/locations/{market}/ is for creating a new radius location."* An earlier pass through the API listing saw the POST and assumed it was something else, which is why the radius path looked missing.
>
> **API-VERIFIED shape.** The search requires a query of at least two characters — without one it returns `["Query must be at least 2 characters long"]`. With one it returns Amazon's own geo response:
>
> ```json
> {
>   "nextToken": null,
>   "geoLocations": [
>     {"name": "London, England, UK - SW1Y", "id": "XHvCjcKHXsKGemnCjsKQbMKX", "category": "POSTAL_CODE"},
>     {"name": "London, England, UK - SW1X", "id": "XHvCjcKHXsKGemnCjsKQbMKW", "category": "POSTAL_CODE"}
>   ]
> }
> ```
>
> Three things follow. The identifier is an **opaque string**, not a number. `category` classifies the kind of place — `POSTAL_CODE` observed. And `nextToken` means the result set is paginated, so a broad query does not return everything at once.
>
> A location reference therefore carries three things rather than one: the identifier, a label to show the trader, and its category.
>
> **The radius path is a write.** It creates a persistent object in Amazon. So the agent calls it only when the trader has actually asked for a radius, never speculatively.
>
> **OPEN QUESTIONS:**
>
> - Does repeated identical radius creation produce duplicate locations, or is it idempotent? Discovering this at scale would leave orphaned locations behind.
> - What is the full `category` set? `POSTAL_CODE` is observed; country, region and city are presumably there.
> - The response is Amazon's own shape (`nextToken`, `geoLocations`) rather than VOW's usual pagination. Is this a passthrough, and does it carry Amazon's rate limits?

> **REVIEW NOTE — location holds inclusions and exclusions** (review comment: *"there is a list of inclusions and excliusions"*): The field was one flat list. It is two.
>
> **API-VERIFIED — the platform already models this exactly:**
>
> ```
> StrategyLocation            include: [StrategyTargetLocation]   exclude: [StrategyTargetLocation]
> UpdateStrategyLocation      include: [str]                      exclude: [str]        ← what is written
> StrategyTargetLocation      amz_id · name · filter_type {INCLUDE, EXCLUDE} · market · category
> StrategyLocationSummary     market · filter_type · count
> ```
>
> Note the asymmetry: reads return full location objects, writes take **identifiers only**.
>
> **Why exclusion matters more than it looks.** Without it, "the whole of the UK except London" has to be expressed as an include list of every other region — a dozen entries, and a gap if one is forgotten. With it, that is two lines.
>
> Typical uses: dropping a market that is expensive, dropping one where another campaign is already running so the two do not bid against each other, and dropping one with a legal restriction.
>
> **OPEN QUESTION:** can a location appear in both lists, and if so which wins? The `filter_type` field on the read model suggests the platform tracks it per location rather than by which array it sits in.

> **REVIEW NOTE — a specified location replaces the country default** (review comment: *"this would replace the GB default"*): The default is the market's country. If the trader supplies postcodes, those **replace** the country rather than being added to it.
>
> ```
> Wrong    ["GB", "SW1", "SW3"]     the country already contains the postcodes,
>                                   so nothing has been narrowed
> Right    ["SW1", "SW3"]           the country default is gone
> ```
>
> **This is an exception to the accumulation rule, and the exception has to be built deliberately.** Everywhere else the agent merges new information into what is already known — a market stated in the first message survives a budget stated in the second. That is what stops a conversation from losing context. For location, a narrower value must **replace** a broader one, or the trader's attempt to narrow does nothing at all.
>
> **Narrowing costs reach, and the agent should report it.** Country to a handful of postcodes can cut the addressable audience sharply, and the trader did not see a forecast at the moment they narrowed.

> **REVIEW NOTE — device types, and what is required** (review comment on *"List[str]"* against Device type: *"DESKTOP, MOBILE (optional) CONNECTED_TV (required) for streaming_tv"* and *"by default either ALL or just CONNECTED_TV (CTV)"*): Two corrections and one new rule.
>
> **The values are enum form, not display labels.** The row read `["Connected TV"]`; the values are `CONNECTED_TV`, `DESKTOP`, `MOBILE`. The earlier row carried what the screen shows rather than what the API takes — the same class of error as the Type column holding widgets.
>
> **`CONNECTED_TV` is required, not merely defaulted.** While the format is `streaming_tv`, it cannot be removed. A "streaming TV" campaign that excludes television screens is not one. Desktop and mobile extend it; they do not replace it.
>
> **The default is one of two states.** Either all three, or `CONNECTED_TV` alone — set per advertiser. Not an arbitrary combination.
>
> **There is no `TABLET`.** Earlier revisions assumed four device types. The deals filter's fourth value is `UNKNOWN`, a data artefact. So the operating-system field below is conditional on `MOBILE` alone.
>
> **Restricting to Connected TV has two effects the trader did not choose.** A large share of streaming viewing happens on mobile, so available inventory shrinks; and Connected TV inventory is priced above mobile, so the CPM rises and the same budget buys fewer impressions. Since this comes from the advertiser rather than the brief, the agent should surface both rather than let the plan come back smaller than expected.
>
> **OPEN QUESTIONS:**
>
> - Is the device setting a **default the trader can override**, or a **locked brand policy**? This is the one answer that changes agent behaviour rather than wording, and it decides whether the repair loop may widen the devices.
> - Which other advertiser settings can be locked in the same way?
> - If an advertiser has no device setting at all, is the fallback all three or Connected TV alone?

> **REVIEW NOTE — the mobile field holds operating systems, not environments** (review comment on *"Enum"* against mobile_environment: *"IOS or ANDROID only relevant if MOBILE device is selected"*): The row gave the values as `in-app` versus `mobile_web`. They are `IOS` and `ANDROID`. Those are not variants of the same question — one asks *where* the ad appears, the other asks *which operating system*.
>
> **The field name is wrong too.** "Mobile environment" describes app-versus-browser. With operating-system values the name misdescribes the field, so it becomes `mobile_operating_system`.
>
> The conditional rule is unchanged and was already right: it applies only when `MOBILE` is among the device types.
>
> **Not setting the field means both**, which is the third state. An enum of two values plus absent covers it.
>
> **Why operating system is worth targeting.** For an app-install campaign it is decisive — showing an iOS app to Android users is entirely wasted spend. Some advertisers also use it as an affluence proxy in markets where iOS skews higher-income.
>
> **API-VERIFIED — app-versus-web does exist, but as inventory data rather than a targeting option.** Deals carry an `environments` array with `APP` and `WEB` entries and their volumes. On staging that split is roughly **94 per cent app and 6 per cent web**, which makes it descriptive rather than something worth narrowing on — targeting "app" would exclude almost nothing.
>
> **OPEN QUESTION:** is app-versus-web targetable at all, or is it only a property of the inventory? The 94/6 split suggests the latter, and it may be why the mobile field carries operating systems instead.

> **REVIEW NOTE — audiences are part of targeting, and targeting arrives pre-filled** (review comment on *"Targeting NEW"*): Audiences are one kind of targeting, not a separate stage. Once the inventory is decided or inferred, the trader is shown a default targeting baseline already applied — country targeting and Connected TV device only — and then either refines it or accepts it as sufficient.
>
> Three ways to proceed from the baseline, and they are alternatives rather than a sequence:
>
> - define audience segments;
> - narrow the geography instead — the example given is a trader who wants postcodes rather than audiences;
> - accept the baseline as it stands.
>
> The practical consequence is that no field in this step starts empty, and the trader is never asked to fill a blank targeting form. Geography can substitute for audience targeting entirely.
>
> Steps 4 and 5 are therefore a single step in the flow. The numbering here is left unchanged so the review comments stay anchored; the merge is how the step is presented, not a change to what it collects.

**API calls at this step:** `POST /api/contextual-targeting/{market}/products/`, `GET /api/strategies/locations/{market}/`

> **RESOLVED against the API** (staging Swagger, checked 4 Aug 2026): postcode targeting is supported — `POST /api/strategies/postcode-validation/{market}/` validates postcodes for a market, alongside `GET` and `POST /api/strategies/locations/{market}/` for country, region and city. the postcode example is therefore buildable.
>
> The same check turned up `POST /api/strategies/{id}/targeting/auto-rec/` (model `StrategyTargetAutoREC`), which recommends targeting automatically. The default baseline described above may not need to be assembled agent-side at all — this endpoint looks like it already does it. Worth confirming what it returns before writing that logic ourselves.

> **REVIEW NOTE — location defaults to the market's country** (review comment on *"Optional"* against Location: *"defaults to market country"*): The field does not start empty. It is filled with the market's own country, and the trader narrows it from there — to a region, a city, or a postcode. Optional therefore means "you need not touch it", not "it is blank until you do".
>
> **`markets` and `location` are not the same field, even though both usually say GB.** The document has never said so, which makes them look like duplication. They answer different questions:
>
> | | Question it answers | What it decides |
> |---|---|---|
> | `markets` | Which market are we buying in? | Which deals exist, which rate card applies, which currency, which category and location lists |
> | `location` | Where should the ad be allowed to show? | Geographic delivery |
>
> They start the same and diverge as soon as the trader narrows: buying GB inventory but delivering only in London is `markets = ["GB"]` with `location = ["London"]`.
>
> **Narrowing costs reach, and the agent should say so.** Moving from country to a handful of postcodes can cut the addressable audience sharply. Since the trader did not see a forecast when they narrowed, the agent should report the effect rather than let the reach shortfall appear later as a surprise.
>
> Device type is also defaulted rather than asked, but from the advertiser rather than the market — that is the subject of the next comment.
>
> **OPEN QUESTIONS:**
>
> - Should content-category exclusions default from the advertiser's brand-safety settings? They are marked that way above on the assumption that brand safety is an advertiser-level rule rather than a per-campaign choice, but that has not been confirmed.
> - When a trader narrows the geography, should the agent re-forecast immediately and show the reach change, or wait until the forecast step?

> **REVIEW NOTE — device type is an advertiser setting, and "CTV" means two different things** (review comment on *"Optional"* against Device type: *"Some advertisers only want CTV only - set at advertiser level"*): The field arrives filled from the advertiser rather than asked. This is the third setting to turn out to live on the advertiser, after the frequency cap and the product category.
>
> **The comment also separates two things this document had been blending.**
>
> | | What it is | Where it is decided |
> |---|---|---|
> | `formats = ["streaming_tv"]` | The kind of content — streaming video | A constant for CTV |
> | `device_types = ["Connected TV"]` | The screen the ad plays on | The advertiser's setting |
>
> Streaming content is not watched only on television sets. Prime Video runs on phones, tablets and desktop browsers, all of which are still `streaming_tv`. **The document proves this itself:** the `Mobile environment` field in this same table — in-app versus mobile web — would be meaningless if delivery were confined to television screens. Its existence is the evidence that it is not.
>
> That field has accordingly become **Conditional**: it only applies when Mobile or Tablet is among the device types, and is meaningless otherwise.
>
> **Restricting to Connected TV has two effects the trader did not choose.** A large share of streaming viewing happens on mobile, so the available inventory shrinks; and Connected TV inventory is priced above mobile, so the CPM rises and the same budget buys fewer impressions. Since this comes from the advertiser rather than the brief, the agent should surface both effects rather than let the plan simply come back smaller than expected.
>
> **This is where the difference between a default and a policy starts to matter.** "Only want CTV only" reads like a rule, not a starting point. Relaxing the device targeting is one of the levers the repair loop reaches for when reach falls short — and if the advertiser has ruled it out, that lever is not available. The agent must not offer to widen something it is not allowed to touch, and should say which lever it could not use. This is what the `is_locked` flag on `AdvertiserSetting` is for, introduced in the frequency-cap note above.
>
> **OPEN QUESTIONS:**
>
> - Is the device setting a **default the trader can override**, or a **locked brand policy**? This decides whether the repair loop may touch it, and it is the one answer that changes agent behaviour rather than wording.
> - Which other advertiser settings can be locked in the same way? Brand-safety exclusions look like candidates.
> - If an advertiser has no device setting at all, what should the fallback be — Connected TV only, or all devices?
> - Are `Connected TV`, `Mobile`, `Tablet` and `Desktop` the full set of device types, and does that list come from an endpoint rather than being fixed in the schema?

### Step 6: Predict Reach

CHANGED — was embedded in the original flow. Now a first-class step with the tier-based honesty rule.

| Field | Type | Requirement | Change from v1.1.0 |
|---|---|---|---|
| Reach curve | Chart | Read-only (Amazon only) | CHANGED. Only available for Amazon-owned inventory. For 3P, state honestly that reach is unavailable |
| Estimated impressions | Number | Read-only | Unchanged |
| Estimated unique reach | Number | Read-only (Amazon only) | CHANGED. Not available for Netflix/Disney |
| Average frequency | Number | Read-only (Amazon only) | CHANGED. Not available for Netflix/Disney |
| Indicative CPM | Number | Read-only | Unchanged |

**NEW — the honesty rule for 3P inventory:** For Netflix/Disney, the agent shows: rate-card CPM and derived impressions (budget ÷ CPM × 1,000). It explicitly states that reach is unavailable and why. Never invent a reach number.

**NEW — consequences:**

- The repair loop (too narrow → widen → re-forecast) applies only to the Amazon portion
- Total reach cannot be summed across providers (no cross-platform deduplication)

**Repair loop** (v1.1.0 §7.1 — concept correct, mechanism updated):

| Was (v1.1.0) | Now |
|---|---|
| If `estimated_unique_reach == 0`, switch from Narrow to Balanced/Broad | If reach is insufficient, extend the audience (not necessarily switch profiles — could add segments within the chosen profile) |
| Also adjust base CPM bid upward | 🔴 **This is reinstated — see below.** |
| Re-run forecast | Unchanged |

🔴 **API-VERIFIED — the bid lever comes back.** The row above says CTV deal CPMs are fixed, so there is no bid to raise. **That is wrong for 92% of the inventory.** Counted across all 369 deals:

```
FLOOR_RATE   341   (92%)     a floor is a MINIMUM, not a price
FIXED_CPM     28   (8%)      only these are genuinely fixed
```

On a floor-rate deal the bid decides what is actually paid, so raising it is a real repair action — it buys into more of the available supply rather than changing the plan's shape. The repair loop therefore has **three** levers, not two, and they should be tried in order of how much they change what the trader agreed to:

| Order | Lever | What the trader gives up |
|---|---|---|
| 1 | Raise the bid on floor-rate deals | Nothing about the plan — only the price per impression rises |
| 2 | Widen the audience | Precision |
| 3 | Widen the inventory or relax targeting | The shape of the plan they described |

The bid is the **least invasive** repair, which is the opposite of how it was ranked before.

🔴 **And no plan can promise delivery.** Across all 369 deals there is **not one PROGRAMMATIC_GUARANTEED deal** — only PRIVATE_AUCTION (341) and PREFERRED (28). PG is the only deal type with guaranteed delivery. So:

- Every impression figure at this step is an **estimate**, not a commitment, and the agent must say so in those words
- The honesty rule below is not only about third-party reach — it applies to impressions across the whole plan
- A trader who reads "435,000 impressions" as a number they will receive has been misled by omission

**Two zero-priced deals exist** (both FIFA 2026 ZA). Impressions are computed as budget ÷ CPM × 1,000, so a zero CPM is a division by zero. That needs an explicit guard at this step, not a comment.

**API calls at this step:** `POST /api/strategies/reach-forecast/`, and `POST /api/audience-sets/reach-forecast/` for the audience-level figure

### Step 7: Finalise Plan

ENTIRELY NEW — did not exist in v1.1.0.

The plan is finalised by the trader within the conversation. Nothing is routed to a manager for now.

| Field | Type | Requirement | Source |
|---|---|---|---|
| Plan status | Enum | Required | ASKED |
| Finalised by | String (user) | Set on finalisation | DERIVED |
| Finalised at | Timestamp | Set on finalisation | GENERATED |

Values: DRAFT → FINALISED

**Implementation:** a status change, not a gate. The graph does not stop and wait for a second person — the trader finalises the plan in the same conversation and the flow continues.

No API call — this is agent-internal. The change is logged in the audit trail.

> **REVIEW NOTE — approval became a status change** (review comment on the *"Plan Approval"* heading: *"we simplified this so it's just a status changed to finalise the plan - no manager approval required for now"*): The step is renamed **Finalise Plan** and reduced to one status moving from `DRAFT` to `FINALISED`, done by the trader in the conversation. The `Manager required` and `Rejection reason` fields are gone, as is the rejection path back to the audience step.
>
> **What this removes is larger than one field.** An approval gate meant a second person: a notification to send, a wait of unknown length, a rejection route, a threshold rule deciding when approval was needed, and roles saying who could give it. All of that leaves M1.
>
> **It also removes a place where the agent had to stop.** The step used a LangGraph `interrupt()` — the graph halted and persisted state until someone else acted, which could be hours later, with the conversation left open in between. That interrupt goes. The one at the creative-approval step stays, and correctly so: there the agent is waiting on Amazon's or a publisher's review, which genuinely is external and asynchronous. The distinction is worth keeping clear — pausing for a review the platform performs is not the same as pausing for a colleague.
>
> **Two things kept deliberately extensible**, because the comment said "for now":
>
> - `PlanStatusEnum` is its own enum rather than reusing `ApprovalStatusEnum`. The plan and the creative now have different lifecycles — `DRAFT`/`FINALISED` against `PENDING`/`APPROVED`/`REJECTED` — and sharing one enum would force one to carry values the other cannot use. Adding `PENDING_APPROVAL` later is then additive rather than a rework.
> - The `approval_status`, `approved_by` and `approved_at` fields have been renamed to `plan_status`, `finalised_by` and `finalised_at`, so the names describe what actually happens.
>
> **Where approval may return is not as a manager gate.** After the advertiser-defaults note above, the more likely shape is an advertiser-level rule — "plans over £10,000 need my sign-off" — which is an advertiser policy rather than an approval workflow inside VOW. Leaving room for `approval_threshold` on the advertiser settings costs nothing now and avoids a rework if it appears.
>
> **OPEN QUESTIONS:**
>
> - Can a finalised plan return to `DRAFT`? It decides whether the agent should warn before finalising or treat it as reversible.
> - What can still change after a plan is finalised? The budget and the matched deals are commercial commitments, so they are not obviously in the same category as, say, the targeting.
> - Is an advertiser-level approval threshold something to plan for, or is approval out of scope entirely for now?
> - Which endpoint records the status change? Nothing in the staging API obviously covers a plan status as distinct from `POST /api/strategies/{id}/set_status/`, which is activation.

### Step 8: Create the Real Strategy

CHANGED — was "Summary & Create" (Step 6) in v1.1.0. Key change: create the real strategy, not a draft.

**What was in v1.1.0:**

Summary view → `POST /api/strategies/` or `POST /api/strategies/draft/` → returns `status: "draft"`

**What it is now:**

| Field | Change |
|---|---|
| Endpoint | `POST /api/strategies/` — not `/strategies/draft/`. Client: "don't need to create draft strategy; draft is just for the wizard creation" |
| Audience set | Created at this step via the simplified CTV endpoint (not before forecasting) |
| All slots | All filled slots from Steps 1–7 are assembled into the creation payload |

**API calls at this step:** 🔴 **`POST /api/automated-strategies/`** — corrected from `simple-strategies`, see the verification block below. Audience-set creation via the CTV endpoint.

> **STILL OPEN:** what status does the created strategy land in? If it is `draft` by default, activation via `set_status` remains a separate step. This is a different question from the plan status settled at Step 7 — the plan being `FINALISED` says nothing about what state the created strategy sits in.

> **REVIEW NOTE — creation does not use `/api/strategies/`** (review comment on *"api/strategies"*: *"probably more likely simple-strategies endpoint"*): The comment was right that the general endpoint was wrong. `POST /api/simple-strategies/` does exist, with request model `SimpleStrategyCreate`, and this document then recorded it as "the CTV variant".
>
> 🔴 **That second part was an inference from the endpoint name, and reading the schema disproved it.** `simple-strategies` is a minimal shell that cannot hold a plan. The correct endpoint is `automated-strategies`. The full comparison is in the verification block at the end of this step and in §4.2.
>
> **The wider point was that one wrong endpoint is rarely alone.** The API calls in this document came across from v1.1.0 and were never re-checked, so the whole list was read against the staging Swagger. What that found:
>
> | Assumed here | Reality |
> |---|---|
> | `POST /api/strategies/` for creation | Not that, and — as v3.1 corrects — not `simple-strategies` either. It is `POST /api/automated-strategies/`, POST only |
> | *(no update endpoint listed)* | `PATCH /api/strategies/{id}/` exists — model `StrategyUpdate` |
> | `POST /api/rate-cards/match/` for deal matching | **Does not exist.** Matching uses `GET /api/deals/` with `GET /api/deals/filter-properties/` |
> | `/api/advertisers/{id}/defaults/` for advertiser settings | **Does not exist.** Settings are at `GET /api/admin/advertiser/{id}/` |
> | Postcode support unknown | `POST /api/strategies/postcode-validation/{market}/` exists |
> | Fee values unknown | `GET /api/contextual-targeting/fees` exists |
>
> Note that `simple-strategies` supports **POST only** — there is no read or update on it. So a strategy is created through the CTV endpoint and then updated through the general one, which is worth stating plainly since it looks inconsistent otherwise.
>
> Endpoints found that this document does not mention at all have been added to the catalogue in §4.
>
> ✅ **API-VERIFIED — both open questions below are now answered, and the recommendation changes.** All three create schemas were read from the OpenAPI document.
>
> **`POST /api/simple-strategies/` — 9 fields, 4 required:**
>
> ```
> * name              string
> * flight_dates      object
> * market            string      ← SINGULAR
> * format            string      ← SINGULAR
>   budget            string
>   impression_target integer
>   id · is_archived · is_readonly
> ```
>
> 🔴 **This is not "the CTV variant".** That was an inference from the name and it was wrong. It is a **minimal single-market, single-format shell** — it cannot express multi-market, multi-format, deals, assets or conversions. A plan built through the agent would not fit in it.
>
> **`POST /api/automated-strategies/` — 18 fields, 6 required:**
>
> ```
> * name                 string
> * flight_dates         object
> * markets_info         [MarketInfo]
> * primary_currency     string
> * product_location     string
> * formats_and_kpis     [AutomatedStrategyFormatsAndKpis]   ← KPI restricted to 5 values
>   goals                [string]      ← PLURAL, an array
>   market_deals         [MarketDeals]
>   assets               [VowAssetMarkets]
>   conversion_types     [string]
>   asin_numbers         string
>   draft_id             string
>   pre_approved_creatives · third_party_creatives · rec_creatives
> ```
>
> **`POST /api/strategies/` — the same six required fields as automated.** This is what the product's own wizard uses.
>
> ✅ **Recommendation: the agent uses `/api/automated-strategies/`.** Three reasons drawn from the schema rather than preference:
>
> 1. It is the only one of the three that can carry the whole plan — per-market budgets, formats with KPIs, matched deals, assets and conversions
> 2. Its KPI list is **already restricted to five values**, which is evidence the endpoint was built for the automated case rather than repurposed for it
> 3. `goals` is an **array**, so a plan with more than one objective is expressible
>
> ✅ **And the strategy record proves which route was taken.** The read model carries `is_simple` and `is_automated` as booleans. On the test strategy both were `false` — it came from the wizard. So after creation the agent can confirm its own route rather than assume it.
>
> 🔴 **One correction to the paragraph above.** It says a strategy is "created through the CTV endpoint and then updated through the general one". Since the recommended endpoint is now `automated-strategies`, that asymmetry is different: `automated-strategies` is also POST-only, so reads and updates still go through `/api/strategies/{id}/`. The pattern holds; only the create endpoint changes.
>
> 🔴 **And `draft_id` is worth noting.** Draft creation was removed from this document on the grounds that "draft is just for the wizard", yet `automated-strategies` accepts a `draft_id`. So drafts are not entirely out of scope for the agent's own create call.
>
> **OPEN QUESTIONS:**
>
> - What is `draft_id` for on `automated-strategies`, given drafts were said to be wizard-only? Is it required in practice, or genuinely optional?
> - `formats_and_kpis` pairs a format with a KPI. For a CTV plan holding `streaming_tv` plus channels, is one pair sent per channel, or one pair for the plan?
> - `market_deals` implies deals are attached at create time rather than after. Does that mean the matched deals must be final before the strategy exists?
> - `strategies-sp` is a separate family with its own draft endpoints. Confirming that is sponsored products and irrelevant to CTV would close it off.

### Step 9: Upload Video Creative

CHANGED — was Step 5 "Creatives" in v1.1.0. Simplified to video only, moved to after plan approval, and duration check added.

**What was in v1.1.0:**

Browse assets and pre-approved creatives, select from table, add click-through URL

**What it is now:**

| Field | Type | Requirement | Change from v1.1.0 |
|---|---|---|---|
| Video file | Upload (direct or URL) | Required | CHANGED. For CTV, always video. No display creatives, no pre-approved selection, no responsive e-commerce |
| Click-through URL | HttpUrl | Optional | CHANGED. Nothing on a television screen can be clicked, so the field stops being required. Still validated as a URL when one is given. Recommended where the device types include mobile, tablet or desktop |
| Duration | Derived from file | Checked | NEW. Must match one of the durations in the approved plan |

**NEW — Duration match check:** If the uploaded video is 30s but the approved plan specified 15s deals, the economics change (different CPM → different impressions for the same budget). This triggers re-approval (return to Step 7 with the amended plan).

**Upload path:** `POST /api/assets/amz_assets/gen_upload_urls/` (get upload URLs) → `POST /api/assets/amz_assets/register/` (register the asset on Amazon)

REMOVED for CTV: browse existing assets (`GET /api/assets/`), pre-approved creatives (`GET /api/creatives/`), responsive e-commerce (`POST /api/creatives/recs/`), third-party tags (`POST /api/creatives/third-party/`). These are valid for Display but not for CTV scope.

> **REVIEW NOTE — the click-through URL is optional on streaming TV** (review comment on *"Required"* against Click-through URL: *"optional for streaming tv"*): A viewer holding a remote cannot click an ad, so requiring a landing page would block a trader on a field that has nothing to do on a television. The schema follows: `click_through_url: Optional[HttpUrl] = None`, still validated as a URL when one is supplied.
>
> **Recording why, so it does not get put back.** The call to action on CTV takes other forms — a QR code in the creative, a spoken or on-screen prompt to search for the brand, or simply brand recall. Measurement does not depend on the click either: it comes from the ASINs or the ad tag set up at the tracking step.
>
> **One refinement, following the device-type comment above.** Device types come from the advertiser and may include mobile, tablet or desktop — and on those screens the ad *can* be clicked. So "optional for streaming TV" is really two cases: with Connected TV alone there is nothing a URL could do, while with mobile or desktop in the mix a URL is worth having. The row above recommends it in that case rather than requiring it, which keeps the trader unblocked without quietly wasting the click-through.
>
> **OPEN QUESTIONS:**
>
> - Where the device types include mobile or desktop, should the agent actively ask for a URL, or leave it optional throughout and mention it once?
> - The staging API has a model named `MarketWithClickthroughUrl`. Is the click-through URL held **per market**? For a multi-market campaign that would matter — a German landing page is not the same as a British one — and this document currently treats it as a single value.
> - Are QR codes permitted in CTV creatives, and is there a spec for them? If that is the practical call to action, it is worth naming here rather than leaving traders to guess.

### Step 10: Platform Creative Approval

ENTIRELY NEW — did not exist in v1.1.0.

| Field | Type | Requirement | Source |
|---|---|---|---|
| Creative approval statuses | `dict[str, ApprovalStatusEnum]` | Read-only | API |

CHANGED — one entry per channel, keyed by the channels actually matched, replacing the three hard-coded rows. For example:

```json
{"Prime Video": "APPROVED", "Netflix": "PENDING", "Channel 4": "PENDING"}
```

Values per channel: PENDING → APPROVED or REJECTED

Every video must pass the platform's content and technical review before it can run. Each platform reviews its own inventory independently. A plan can be fully approved and funded and still not launch until the creative clears.

**On rejection:** the agent reports the reason and asks for a replacement (return to Step 9).

> **STILL OPEN, and it blocks more than this step:** do the per-channel review statuses surface inside VOW's API, or are they tracked externally? Nothing in the staging Swagger obviously carries a per-channel creative approval status. If these statuses are not readable, the dictionary above cannot be populated and the activation checklist cannot verify that every channel has approved — the agent can only check what it can read.

> **REVIEW NOTE — one status per channel, and the channel list is data** (review comment on the three hard-coded approval rows: *"It's just a single status for each channel not necessary netflix or disney - could be paramount or channel 4"*): The three rows become one field holding a status per channel, keyed by the channels the plan actually matched.
>
> **Why the shape matters more than the tidiness.** With a row per publisher, adding Paramount+ means changing the schema, migrating, touching the backend, the interface and the tests, and shipping a release — to add a name. As a dictionary it is a data change and nothing else. the choice of "Channel 4" is a deliberate one: it is a British broadcaster, so the list is market-specific as well as changeable — UK has ITVX and Channel 4, the US has Hulu and Peacock. Hard-coding would not merely be untidy; it would not scale past one market.
>
> **What stays fixed is the set of states.** `PENDING`, `APPROVED` and `REJECTED` are stable and the agent's logic depends on them, so those remain an enum. It is the **keys** that are data, not the values. Making everything dynamic would lose the type safety that matters.
>
> **The document already contained this rule, one section earlier.** The targeting step carries a design note that the targeting list changes often and so must be config-driven rather than hard-coded. Channels are the same kind of list. The rule was written down and then not applied here.
>
> **Naming.** The client's word is "channel". The deal schema called the same thing `provider`, and the inventory step now has a `Channel` field, which left three names for one concept. `SelectedDealSchema.provider` has been renamed to `channel`, along with the same field on `CurationRequirementsSchema` and inside `BudgetSplitSchema.by_inventory`.
>
> One caveat, since "provider" has not disappeared from this document: it still appears in the audience notes, where it means a **data** provider — Amazon 1P against a third party such as Experian. That is a different thing from a channel, and the two should not be collapsed. Channel is who shows the ad; data provider is whose audience data is being paid for.
>
> **OPEN QUESTIONS:**
>
> - Where should the channel list come from — `GET /api/admin/advertiser/get_channels_choices/`, or derived from the deals that were matched? The endpoint exists; deriving from matched deals gives only the channels in play, which may be what the interface actually needs.
> - Is the approval status held **per channel**, or per creative-and-channel pair? A plan with a 15s and a 30s creative could plausibly have one approved and the other not on the same channel.
> - Which other lists in this document should be config-driven rather than fixed in the schema? Genres, markets and device types all look like candidates, and `GET /api/strategies/choices/` may already serve some of them.

### Step 11: Tracking Setup

MOVED — ASIN validation was in Step 1 (strategy details) and ad-tag conversions were in Step 2 (goal/KPI). Both now sit here, after creative approval and before tracking is attached.

**What was in v1.1.0:**

ASINs collected in Step 1 and validated via `POST /api/contextual-targeting/{market}/asin-validation/`

Ad tag conversions selected in Step 2 via `GET /api/conversions/definitions/`

**What it is now:**

| Field | Type | Requirement | Change from v1.1.0 |
|---|---|---|---|
| Sells on Amazon? | Question | Asked here | MOVED from Step 1 |
| Product ASINs | Textarea | Required if endemic | Validation unchanged: `POST /api/contextual-targeting/{market}/asin-validation/` |
| Sells on own website? | Question | Asked here | NEW explicit question |
| Ad tag registered? | Check | Required if yes | NEW. Check whether an ad tag is already registered. If not, show setup instructions — the tag must be installed before the campaign runs (tracking only records activity after it goes live) |
| Ad tag conversions | Multi-select | Required if ad tag exists | MOVED from Step 2. 🔴 **CORRECTED — six events, not four, and they differ by market.** Via `GET /api/conversions/definitions/?selected_advertiser_id={id}` — the parameter is **required**, the endpoint 400s without it |

🔴 **API-VERIFIED — the conversion event list is market-specific.** This document listed four events and treated them as universal. There are six, and availability differs:

| Event | GB | US |
|---|---|---|
| `ADD_TO_SHOPPING_CART` | ✅ | ✅ |
| `APPLICATION` | ✅ | ✅ |
| `CHECKOUT` | ✅ | — |
| `PAGE_VIEW` | ✅ | — |
| `SEARCH` | — | ✅ |
| `OTHER` | — | ✅ |

**So a market-agnostic list offers events that do not exist in the chosen market.** `SEARCH` and `OTHER` are new to this document, and `CHECKOUT` and `PAGE_VIEW` — both listed here as though they were general — are GB-only in the data seen. The agent must filter by market before presenting these, and must never carry a selection across a market change without re-checking it.

**API calls at this step:** `POST /api/contextual-targeting/{market}/asin-validation/`, `GET /api/conversions/definitions/`

> **RESOLVED — was: the repeat of the Step 1 timing question, ending "Confirm with client".** `product_location` comes from the advertiser's settings, so the agent holds it at creation; the ASINs are sent empty and attached here through `PATCH /api/strategies/{id}/`. See the note on the ASIN row at Step 1.

> **REVIEW NOTE — a strategy can be updated after it is created** (review comment on *"Confirm with client"*: *"no they can be updated on the strategy after creation"*): The document treated creation as a point of no return, which is why the timing of the ASINs looked like a problem. It is not one. The strategy is created with what is known, and the rest is attached afterwards through `PATCH /api/strategies/{id}/` — confirmed present in the staging API, model `StrategyUpdate`.
>
> This closes the question that appeared twice in this document, at Step 1 and again here.
>
> **It is also what makes the previous comment work.** Removing the order from the creative, tracking and credit branches only makes sense if those branches can write back to a strategy that already exists. Had the strategy been fixed at creation, everything would have had to be collected beforehand and the sequence could not have been broken. So the two comments are one change seen from two sides: *no order necessary* is the behaviour, *updatable after creation* is the mechanism that permits it.
>
> **What should not be freely updatable.** The answer was about the measurement fields, and it should not be read as "anything may change". Some fields carry money:
>
> | Safely updatable | Needs a guardrail |
> |---|---|
> | `product_asins`, `product_location` | `market_budgets` — a guaranteed deal already owes the full budget |
> | Ad tag, conversions | `selected_deals` — the deal is booked |
> | Creatives | `flight_dates` — tied to the booking |
> | Targeting, frequency cap | `markets` — invalidates the whole plan |
>
> Without that distinction someone will PATCH a budget on a strategy whose Programmatic Guaranteed deal has already committed it, and the plan and the commitment will disagree.
>
> **OPEN QUESTIONS:**
>
> - **Which fields should be updatable after creation, and which fixed?** The table above is a proposal, not a confirmation. Budget and deals are the ones that matter.
> - Does "after creation" extend to **after activation**? A live campaign is a different case from one that has been created but not yet launched.
> - Does an update re-run anything — validation, or the reach forecast? If a PATCH changes the targeting, the forecast the trader was shown is no longer the forecast that applies, and the agent should say so.
> - Is `PATCH /api/strategies/{id}/` the right route for a strategy created through `automated-strategies`, given that `automated-strategies` is also POST-only?

> **REVIEW NOTE — no order, and therefore a gate** (review comment on the *"Tracking Setup"* heading: *"could be done before creatives if they are no available yet - no order necessary"*): Tracking can be set up before the creative arrives. Which sounds like a small allowance, and is not.
>
> **The numbering implied a chain that does not exist.** If tracking, creatives and the credit check can happen in any order, they are not steps 9, 10, 11 and 12 — they are three branches that run independently after the strategy is created and meet at activation. The sequence up to creation is genuinely ordered: the inventory decides the CPM, the CPM decides the impressions, the forecast needs the targeting. After creation, none of the three waits on another.
>
> **This matches how the work actually arrives.** Creatives come from an agency and are often late. An ad tag has to be installed by the advertiser's own developers, which can take days. Credit is a finance matter. Forcing an order means one late item blocks everything, when the trader could have finished the rest.
>
> **Removing the order makes a completeness check necessary.** Something has to establish that everything is in place before money is spent, which is what the join node at Step 13 now does — see the prerequisite table and `ready_to_activate` there. The document already implied this without stating it: the creative-approval step notes that *"a plan can be fully approved and funded and still not launch until the creative clears."* That is a launch gate described in prose; it is now a checklist.
>
> **Step numbers are left as they are** so the review comments stay anchored. The parallelism is recorded here and in the state machine rather than by renumbering the document.
>
> **The checklist depends on something still unresolved.** "Approved by every channel" can only be checked if those per-channel statuses are readable through the API — the open question raised at the creative-approval step. If they are tracked outside VOW, that prerequisite cannot be evaluated and activation would either block indefinitely or have to trust the trader.
>
> **OPEN QUESTIONS:**
>
> - Is the prerequisite list complete, or is there something else that must be true before a campaign can go live?
> - Is the **credit check** genuinely order-free? Its outcome can change the budget, which would argue for running it before the plan is finalised rather than alongside the creative work.
> - Can conversions be **skipped** entirely — activating with no conversion tracking at all — or is at least one always required?
> - Is there an endpoint that reports activation readiness, or is the agent expected to assemble this from the individual checks?

### Step 12: Credit Check

ENTIRELY NEW — did not exist in v1.1.0.

Credit is checked only at activation, not during planning. Everything before this point is a costless plan.

| Field | Type | Requirement |
|---|---|---|
| Account balance | Number | Read-only |
| Strategy budget | Number | Read-only |
| Sufficient | Boolean | Derived (balance ≥ budget) |

If insufficient: prompt a top-up via `POST /api/credits/` or `POST /api/credits/stripe/`.

**API call:** `GET /api/credits/summary/`

### Step 13: Activate

ENTIRELY NEW — did not exist in v1.1.0 (was implicit in "create strategy").

The single spend action in the entire flow. Everything before this was free.

NEW — **a join node, not just a step.** Because the creative, tracking and credit branches run in any order, this is where completeness is checked. Nothing launches until every prerequisite holds:

| Prerequisite | Holds when |
|---|---|
| Creatives uploaded | One per duration in the plan — a 15s and a 30s plan needs both |
| Creatives approved | Every matched channel has returned `APPROVED` |
| Ad tag registered | The advertiser does not sell on Amazon and a tag is in place |
| ASINs attached | The advertiser does sell on Amazon and the ASINs validated |
| Conversions chosen | Selected, or explicitly skipped |
| Credit sufficient | Balance ≥ strategy budget |

```python
class ActivationPrerequisitesSchema(BaseModel):
    """NEW — checked at the join node before any spend."""
    creative_uploaded: dict[str, bool] # per duration: {"15": True, "30": False}
    creative_approved: dict[str, ApprovalStatusEnum] # per channel: {"Prime Video": APPROVED}
    ad_tag_registered: Optional[bool] = None # None when not applicable
    asins_attached: Optional[bool] = None # None when not applicable
    conversions_chosen: bool = False # True if chosen or deliberately skipped
    credit_sufficient: bool = False
    spend_quantity_defined: bool = False # NEW - a budget or an impression target, per allocation_mode

    @property
    def ready_to_activate(self) -> bool:
        return (
            bool(self.creative_uploaded) and all(self.creative_uploaded.values())
            and bool(self.creative_approved)
            and all(s == ApprovalStatusEnum.APPROVED for s in self.creative_approved.values())
            and (self.ad_tag_registered is not False)
            and (self.asins_attached is not False)
            and self.conversions_chosen
            and self.credit_sufficient
            and self.spend_quantity_defined
        )
```

The agent should be able to answer "what is still outstanding?" at any point from this, rather than only discovering the gap at activation.

**API call:** `POST /api/strategies/{id}/set_status/`

🔴 **There is no `POST /api/strategies/{id}/activate/`.** It appeared in an earlier revision and does not exist. Activation is a status change through `set_status/`, which means the status vocabulary matters here. Six values are known, three of them now confirmed against live records:

```
1_delivering · 2_out_of_budget · 3_ended · 4_not_running ·
5_ready_to_deliver · 6_inactive
```

`3_ended`, `4_not_running` and `6_inactive` have been observed. The numeric prefixes are almost certainly there for sort order rather than as a state machine, so **the agent must not infer a transition from the numbering** — that a strategy can go from `4_not_running` to `1_delivering` is an assumption until confirmed.

**One prerequisite is missing from the table above.** The plan must have either a budget or an impression target, and exactly one of them can be authoritative. `allocation_mode` decides which. Activating with `allocation_mode: BUDGET` and no budget, or with `IMPRESSIONS` and no `impression_target`, is a spend action against an undefined quantity — so it belongs in the gate:

```
Budget or impressions defined    allocation_mode is BUDGET and every market has a budget,
                                 OR it is IMPRESSIONS and impression_target is set
```

After activation, VOW's outbound sync creates the Campaigns and Ad Groups on Amazon DSP.

---

## 4. API Catalogue

CHANGED — original catalogue kept, with additions, corrections and removals marked.

**Two passes were made against staging (`staging.vowmade.dev`):**

| Pass | When | What |
|---|---|---|
| Spec read | 4 August 2026 | The OpenAPI document — **192 paths, 197 definitions**. Tells us what exists |
| Live calls | 6 August 2026 | **60+ authenticated GET requests.** Tells us what actually answers, with which parameters, and what the data looks like |

The second pass matters because the spec and the running service disagree in several places. Every row below now carries a **Verified** column: ✅ called successfully, 🔴 called and it failed or contradicted the spec, ⬜ in the spec but not yet called.

### 4.1 Endpoints the agent calls

| Operation | Method | Endpoint | Verified | Notes |
|---|---|---|---|---|
| Check name uniqueness | GET | `/api/strategies/check_strategy_name_uniqueness/` | ⬜ | Unchanged |
| Strategy choices | GET | `/api/strategies/choices/` | ✅ | **The single most useful endpoint in the catalogue.** Every enum in §5 was read from here — goal, format, kpi, currency, market, product_location. Config-driven; nothing should be hard-coded that this returns |
| List deals | GET | `/api/deals/` | ✅ | **369 deals unfiltered.** Paginated. See the pagination quirk in §4.4 |
| Deal filter properties | GET | `/api/deals/filter-properties/` | ✅ | The filter vocabulary. Confirms no `channel` or `inventory_tier` filter exists |
| Inventory sources | GET | `/api/inventory-sources/` | 🔴 | **Requires all three of `goal`, `strategy_formats`, `markets`.** Returns 400 without them, so an unfiltered count is impossible. Max observed: **4** |
| CTV rate card | GET | `/api/rates/ctv/{market}/` | ✅ | Verified for GB, US, DE |
| Location search | GET | `/api/strategies/locations/{market}/` | 🔴 | **Requires `?query=` of at least two characters.** It is a search, not a list. Returns Amazon's own shape (`geoLocations`, `nextToken`) |
| Custom radius location | POST | `/api/strategies/locations/{market}/` | ⬜ | Same path, different verb. Confirms the radius facility from the location review note |
| Postcode validation | POST | `/api/strategies/postcode-validation/{market}/` | ⬜ | Confirms postcode-level geo targeting is available |
| Product categories | GET | `/api/contextual-targeting/{market}/product-categories/` | ✅ | **25,973 categories for GB.** Far too many to enumerate — this must be a search, never a list |
| ASIN validation | POST | `/api/contextual-targeting/{market}/asin-validation/` | ⬜ | Unchanged |
| Contextual targeting fees | GET | `/api/contextual-targeting/fees` | ✅ | **16 markets × 3 rates.** 🔴 This is **not** the audience fee — see §4.3 |
| Conversion definitions | GET | `/api/conversions/definitions/` | 🔴 | **Requires `?selected_advertiser_id=`.** Six event types, and they differ by market |
| List audience sets | GET | `/api/audience-sets/` | ✅ | **35 sets**, not 15. The audience fee lives on this object |
| Suggest audiences | POST | `/api/audience-sets/suggest/` | ⬜ | Unchanged |
| Audience reach forecast | POST | `/api/audience-sets/reach-forecast/` | ⬜ | Unchanged |
| Audience overlap | POST | `/api/audiences/{market}/overlapping-audiences/` | ⬜ | Detects the cross-provider case where two data fees apply |
| Strategy reach forecast | POST | `/api/strategies/reach-forecast/` | ⬜ | The forecast the whole repair loop turns on |
| List assets | GET | `/api/assets/` | ✅ | **58 assets**, not 4 |
| Upload URLs | POST | `/api/assets/amz_assets/gen_upload_urls/` | ⬜ | |
| Register asset | POST | `/api/assets/amz_assets/register/` | ⬜ | |
| List creatives | GET | `/api/creatives/` | ⬜ | |
| Set creative durations | POST | `/api/strategies/{id}/creatives/set_durations/` | ⬜ | Supports the duration match check |
| Ad tag events | GET | `/api/ad-tags/{market}/ad-tag-events/` | ⬜ | Used at the tracking step |
| Credit summary | GET | `/api/credits/summary/` | ⬜ | |
| Targeting recommendation | POST | `/api/strategies/{id}/targeting/auto-rec/` | ⬜ | May already produce the default targeting baseline |
| Brand lookup by domain | GET | `/api/brand/get_brand_by_domain/` | ⬜ | Could resolve the brand from a website named in the brief |
| Read strategy | GET | `/api/strategies/{id}/` | ✅ | **40 keys, not 20.** See §4.5 |
| Update strategy | PATCH | `/api/strategies/{id}/` | ⬜ | Model `StrategyUpdate`. How ASINs are attached at the tracking step |
| Activate strategy | POST | `/api/strategies/{id}/set_status/` | ⬜ | |

### 4.2 The three create endpoints — ✅ D5 answered

Earlier revisions asserted `/api/simple-strategies/` was "the CTV route". **That was a guess and it was wrong.** All three request schemas have now been read.

| Endpoint | Fields | Required | What it actually is |
|---|---|---|---|
| `POST /api/simple-strategies/` | 9 | 4 | A **minimal shell** — `name`, `flight_dates`, `market` (singular), `format` (singular). Cannot express multi-market or multi-format. Carries `impression_target` |
| `POST /api/automated-strategies/` | 18 | 6 | **The full planning payload** — `markets_info`, `formats_and_kpis`, `market_deals`, `assets`, `conversion_types`, `goals`, `draft_id` |
| `POST /api/strategies/` | — | 6 | Same six required fields as automated. What the product's own wizard uses |

**Recommendation: the agent should use `/api/automated-strategies/`.** Three reasons, all from the spec rather than preference:

1. It is the only one of the three that can carry everything the plan holds — deals, assets, conversions and per-market budget
2. Its KPI list is already restricted to **five** values, which is close to what an awareness CTV plan needs — evidence that this endpoint was built for the automated case
3. `goals` on this endpoint is an **array** (`goals: [string]`), not a single value — the plan can express more than one objective

🔴 **Two shape differences to note before building the payload:**

```
simple-strategies      market   (string)     format  (string)      ← singular
automated-strategies   markets_info  [MarketInfo]                  ← plural, objects
                       formats_and_kpis  [AutomatedStrategyFormatsAndKpis]
                       goals  [string]                             ← plural, array
```

✅ **And the strategy record proves which endpoint created it.** The read model carries both `is_simple` and `is_automated` as booleans. On the test strategy both were `false` — it was made through the wizard. This gives us a way to confirm, after creation, that the agent's route was taken.

### 4.3 🔴 Correction — two different fees, not one

Earlier revisions said the audience data fee is read from `GET /api/contextual-targeting/fees`. **That is wrong.** They are two unrelated fees and both can apply to one plan.

| Fee | Where it lives | Example |
|---|---|---|
| **Audience data fee** | On the **audience set object** itself | `video_fee: "1.63"`, `standard_display_fee: "0.59"`, `fee_currency: "GBP"` |
| **Contextual targeting fee** | `GET /api/contextual-targeting/fees` | GB streaming TV `0.450` GBP |

The path name is the clue that was missed: `contextual-targeting/fees` is the fee for **contextual (product-category) targeting**, not for audience targeting.

The contextual endpoint returns **16 markets**, each with three rates:

```
market  currency  display  online_video   stv
AE      AED       0.825    1.650          1.650
AU      AUD       0.300    0.450          0.450
BR      BRL       0.450    1.275          1.275
CA      CAD       0.300    0.450          0.450
DE      EUR       0.180    0.450          0.450
ES      EUR       0.108    0.450          0.450
FR      EUR       0.147    0.450          0.450
GB      GBP       0.162    0.450          0.450
```

The 1.63 GBP figure quoted throughout this document for audience fees is **correct** — only its source was mis-stated.

> **OPEN QUESTION D49:** if a plan uses both an audience and product-category targeting, do both fees apply, and do they add? At GB streaming-TV rates that is 1.63 + 0.450 = **2.08 GBP per thousand impressions** on top of the deal CPM, which changes the forecast materially.

### 4.4 Calling quirks that will bite the implementation

**Required parameters that are not obvious.** Three endpoints return 400 rather than a default:

```
/inventory-sources/            needs goal AND strategy_formats AND markets
/strategies/locations/{m}/     needs query, minimum two characters
/conversions/definitions/      needs selected_advertiser_id
```

**Pagination comes back on the wrong scheme.** The DRF `next` link is returned as `http://`, which the server then 301-redirects to `https://`. Walking pages naively costs a redirect each time and puts the session cookie on a plaintext hop. **Rewrite the scheme before following the link.**

**The advertiser header is required on every call.** `Vowmade-Advertiser-Id` selects the advertiser context. Without it the responses are empty rather than an error, which is a silent failure mode.

**Counts from the interface are not counts from the API.** Every count in earlier revisions came from a filtered UI view and every one was too low:

| Thing | Was documented | Actual |
|---|---|---|
| Deals | 83 | **369** |
| Audience sets | 15 | **35** |
| Assets | 4 | **58** |
| Markets with deals | 2 | **18** |
| Product categories | not counted | **25,973** |

### 4.5 🔴 The strategy read model is twice the size documented

`GET /api/strategies/{id}/` returns **40 keys**. This document described about 20. The fifteen that were missing are not minor — they form a **delivery-control layer** nobody has specified:

| Field | Observed | What it appears to control |
|---|---|---|
| `is_simple` / `is_automated` | `false` / `false` | Which create endpoint was used |
| `impression_target` | `null` | ✅ **D38 answered** — planning against impressions instead of budget is supported |
| `allocation_mode` | `"BUDGET"` | Budget or impressions |
| `creative_duration_allocation_mode` | `"budget"` | 🔴 Lowercase, where the one above is uppercase |
| `creative_durations` | `[]` | Durations are stored on the strategy |
| `creative_rotation_type` | `"RANDOM"` | Creative rotation |
| `content_rating_exclusions` | `[]` | Brand safety — but content **rating**, not category |
| `user_location_signal` | `"CURRENT"` | 🔴 A concept in no document so far |
| `audiences_cpm` | `null` | The audience fee, stored on the strategy |
| `planned_cpm` · `cpm_target` · `pacing_ratio` | `null` | Delivery economics |
| `can_be_extended` | `true` | Whether the flight can be extended |
| `kpis` | — | Plural |
| `last_exported` | — | Export tracking |
| `status` | `"4_not_running"` | ✅ Confirms the fourth value of the status ordering |

> **OPEN QUESTION D50:** who owns `pacing_ratio`, `planned_cpm`, `cpm_target`, `allocation_mode` and `creative_rotation_type` — does the agent set them, or does the platform? If the agent must set them they belong in the plan model and in the conversation; if the platform sets them they should be read-only in the schema. Right now they are in neither place.

### 4.6 Endpoints that do not exist, or cannot be reached

| Operation | Endpoint | What happened |
|---|---|---|
| ~~Deal matching~~ | ~~`POST /api/rate-cards/match/`~~ | **Does not exist.** Matching is `GET /api/deals/` filtered with the vocabulary from `/api/deals/filter-properties/` |
| ~~Advertiser defaults~~ | ~~`GET /api/advertisers/{id}/defaults/`~~ | **Does not exist** under that path |
| ~~Activate~~ | ~~`POST /api/strategies/{id}/activate/`~~ | **Does not exist.** Activation is `POST /api/strategies/{id}/set_status/` |
| ~~Draft create~~ | ~~`POST /api/strategies/draft/`~~ | **Removed by the client** — "draft is just for the wizard". Note however that `automated-strategies` accepts a `draft_id`, so drafts are not entirely out of the picture |
| Advertiser settings | `GET /api/admin/advertiser/{id}/` | 🔴 **403 Forbidden.** See below |

🔴 **The 403 is a blocker, not an inconvenience.** Five admin endpoints refuse the trader's session even though the session is valid:

```
403  GET /api/admin/advertiser/                                       advertiser list
403  GET /api/admin/advertiser/{id}/                                  advertiser defaults
403  GET /api/admin/advertiser/get_channels_choices/                  channel list
403  GET /api/admin/advertiser/get_deal_exchange_choices/             exchange list
403  GET /api/admin/advertiser/get_industry_and_sub_industry_choices/ industry list
```

The second of those is the endpoint the **entire advertiser-defaults concept** depends on — the frequency cap, device types, product categories and selling location that the review comment on advertiser profiles asked us to read rather than ask for. The agent cannot read it.

The third is where the channel list was supposed to come from instead of being hard-coded. It is also unreachable, which means the channel vocabulary has to be derived from deal names — the same problem the deal-matching note describes.

> **OPEN QUESTION D47 — blocking.** `GET /api/admin/advertiser/{id}/` returns 403 to a valid trader session. Two possibilities: (a) the agent needs a **service account** with admin scope, or (b) the advertiser defaults are exposed on a non-admin endpoint that has not been found. Until this is settled, every advertiser-default field in this document is unimplementable and the agent must ask the trader for values it was supposed to already know.

---

## 5. Pydantic Data Models

CHANGED — original models kept where valid, extended and restructured.

🔴 **Every enum below was read from `GET /api/strategies/choices/` on 6 August 2026.** Earlier revisions guessed at these lists and every guess was too small. The pattern of the error is the same each time: a filtered view in the interface was read as the full set.

| Enum | Was documented | Verified | Where the wrong number came from |
|---|---|---|---|
| `goal` | 3 | **15** | The three the CTV screen offers |
| `format` | 4 | **21** | The four in the CTV filter |
| `kpi` | 6 | **16** (5 on the automated endpoint) | A guess |
| `primary_currency` | 3 | **19** | The three markets we had looked at |
| `market` | 2 | **21** (18 with live deals) | The GB/US filter in the deals list |
| `conversion_type` | 4 | **6**, market-specific | Read from the GB screen only |
| `duration` | 4 | **7** | The CTV creative screen |

**Two rules follow from this**, and they apply beyond these seven fields:

1. **A narrow enum in the model is a decision, not a fact.** Where the agent restricts a field below what the API accepts, the code must say so and say why — otherwise the next person reads the short list as the platform's limit.
2. **Prefer reading `/api/strategies/choices/` at startup over hard-coding.** The lists are config-driven server-side, so a hard-coded copy is stale the moment someone edits the config. The enums below exist to document what was seen, not to be typed into the codebase verbatim.

```python
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, HttpUrl


# ==========================================
# ENUMS
# ==========================================

class ChannelTypeEnum(str, Enum):
    """UNCHANGED"""
    DSP = "dsp"
    SPONSORED = "sponsored"

class GoalEnum(str, Enum):
    """CORRECTED - the API accepts 15 values, not 3.

    Read from /api/strategies/choices/. The agent DEFAULTS to AWARENESS for CTV
    and says so; it does not restrict the field. See the goal review note at
    Step 1 - the review comment corrected FIXED to "defaulted", and fifteen
    options makes that correction more important, not less.
    """
    AWARENESS = "AWARENESS"                                   # agent default for CTV
    CONSIDERATION = "CONSIDERATION"
    CONVERSION = "CONVERSION"
    OTHER = "OTHER"
    PROSPECTING = "PROSPECTING"
    REMARKETING = "REMARKETING"
    RETENTION = "RETENTION"
    UPPER_FUNNEL_PROSPECTING = "UPPER_FUNNEL_PROSPECTING"
    CONVERSIONS_OFF_AMAZON = "CONVERSIONS_OFF_AMAZON"
    ENGAGEMENT_WITH_MY_AD = "ENGAGEMENT_WITH_MY_AD"
    CONSIDERATIONS_ON_AMAZON = "CONSIDERATIONS_ON_AMAZON"
    PURCHASES_ON_AMAZON = "PURCHASES_ON_AMAZON"
    MOBILE_APP_INSTALLS = "MOBILE_APP_INSTALLS"
    PURCHASES_ON_OFF_AMAZON = "PURCHASES_ON_OFF_AMAZON"
    MULTI_FUNNEL = "MULTI_FUNNEL"

class KPIEnum(str, Enum):
    """CORRECTED - 16 values, not 6, and the casing was wrong too.

    Earlier revisions had lowercase ("reach", "ctr"). The API uses SCREAMING_CASE
    and spells the metrics out in full.
    """
    REACH = "REACH"
    FREQUENCY = "FREQUENCY"
    COST_PER_VIDEO_COMPLETION = "COST_PER_VIDEO_COMPLETION"
    VIDEO_COMPLETION_RATE = "VIDEO_COMPLETION_RATE"
    CLICK_THROUGH_RATE = "CLICK_THROUGH_RATE"
    COST_PER_CLICK = "COST_PER_CLICK"
    COST_PER_DETAIL_PAGE_VIEW = "COST_PER_DETAIL_PAGE_VIEW"
    DETAIL_PAGE_VIEW_RATE = "DETAIL_PAGE_VIEW_RATE"
    RETURN_ON_AD_SPEND = "RETURN_ON_AD_SPEND"
    TOTAL_RETURN_ON_AD_SPEND = "TOTAL_RETURN_ON_AD_SPEND"
    COMBINED_RETURN_ON_AD_SPEND = "COMBINED_RETURN_ON_AD_SPEND"
    COST_PER_INSTALL = "COST_PER_INSTALL"
    COST_PER_ACTION = "COST_PER_ACTION"
    COST_PER_FIRST_APP_OPEN = "COST_PER_FIRST_APP_OPEN"
    COST_PER_SIGN_UP = "COST_PER_SIGN_UP"
    OTHER = "OTHER"

class AutomatedKPIEnum(str, Enum):
    """NEW - the FIVE values POST /api/automated-strategies/ accepts.

    This is the operative list for the agent, because §4.2 recommends that
    endpoint. It also partly answers the open question about goal-to-KPI mapping:
    the platform has already made that restriction for the automated case.

        REACH, FREQUENCY                                -> awareness
        COST_PER_ACTION                                 -> conversion
        RETURN_ON_AD_SPEND, TOTAL_RETURN_ON_AD_SPEND    -> conversion
    """
    REACH = "REACH"
    FREQUENCY = "FREQUENCY"
    COST_PER_ACTION = "COST_PER_ACTION"
    RETURN_ON_AD_SPEND = "RETURN_ON_AD_SPEND"
    TOTAL_RETURN_ON_AD_SPEND = "TOTAL_RETURN_ON_AD_SPEND"

class ProductLocationEnum(str, Enum):
    """UNCHANGED"""
    ON_AMAZON = "ON_AMAZON"
    NOT_SOLD_ON_AMAZON = "NOT_SOLD_ON_AMAZON"

class FormatEnum(str, Enum):
    """CORRECTED - 21 values, and TWELVE OF THEM ARE CHANNELS.

    This is the single most consequential correction in the document. The review
    comment said "Prime Video is a channel, not a format" and that is right about
    the domain - but the API does not model it that way. Its `format` enum IS the
    channel list. See the formats review note at Step 1 for how the agent holds
    both truths: the plan model keeps streaming_tv plus a channel, and the
    forecast request sends the channel as a format because that endpoint keys its
    supply lines on this field.
    """
    # Generic formats
    STANDARD_DISPLAY = "standard_display"
    AMAZON_MOBILE_DISPLAY = "amazon_mobile_display"
    AAP_MOBILE_APP = "aap_mobile_app"
    VIDEO = "video"
    DISPLAY = "display"
    ONLINE_VIDEO = "online_video"
    STREAMING_TV = "streaming_tv"           # what a CTV plan sets
    OTHER = "other"
    # Channels the API models as formats
    PRIME_VIDEO = "prime_video"
    NETFLIX = "netflix"
    DISNEY = "disney"
    PARAMOUNT = "paramount"
    CHANNEL4 = "channel4"
    PLUTO = "pluto"
    BSKYB = "bskyb"
    HULU = "hulu"
    TUBI = "tubi"
    ROKU = "roku"
    VEVO = "vevo"
    DAZN = "dazn"
    DISCOVERY = "discovery"

class CurrencyEnum(str, Enum):
    """CORRECTED - 19 values, not 3.

    This closes the open question that asked whether the enum needed extending
    for markets outside EUR/GBP/USD. It does not - NOK, SEK, DKK, INR, JPY and
    the rest are already there. A live strategy was found with primary_currency
    NOK, which is what prompted the check.
    """
    USD = "USD"; MXN = "MXN"; CAD = "CAD"; BRL = "BRL"; AED = "AED"
    SAR = "SAR"; GBP = "GBP"; EUR = "EUR"; SEK = "SEK"; TRY = "TRY"
    AUD = "AUD"; INR = "INR"; SGD = "SGD"; JPY = "JPY"; NOK = "NOK"
    DKK = "DKK"; NZD = "NZD"; CNY = "CNY"; CHF = "CHF"

class MarketEnum(str, Enum):
    """NEW - 21 markets. Earlier revisions said "GB and US only", which was the
    deals-list filter rather than the platform.

    Eighteen of the 21 have live deals:
        GB 82 · US 78 · ES 25 · DE 23 · FR 23 · IT 23 · CA 22 · MX 20
        BR 16 · AU 14 · JP 12 · NO 3 · IE 2 · AT 2 · DK 2 · FI 2 · SE 2 · NL 1

    Note that NO, IE and FI carry deals but are NOT in this enum, while BE, IN,
    NZ, SA, SG, TR and AE are in the enum with no deals. The two lists disagree
    in both directions - see the open question at the target-markets note.
    """
    AU = "AU"; AT = "AT"; BE = "BE"; BR = "BR"; CA = "CA"; FR = "FR"
    DE = "DE"; IN = "IN"; IT = "IT"; JP = "JP"; MX = "MX"; NL = "NL"
    NZ = "NZ"; SA = "SA"; SG = "SG"; ES = "ES"; SE = "SE"; TR = "TR"
    AE = "AE"; GB = "GB"; US = "US"

class ConversionTypeEnum(str, Enum):
    """NEW - 6 events, not 4, and THEY DIFFER BY MARKET.

    Availability verified per market:
        ADD_TO_SHOPPING_CART   GB, US
        APPLICATION            GB, US
        CHECKOUT               GB only
        PAGE_VIEW              GB only
        OTHER                  US only
        SEARCH                 US only

    So a market-agnostic conversion list will offer events that do not exist.
    The agent must filter by market before presenting these.
    """
    ADD_TO_SHOPPING_CART = "ADD_TO_SHOPPING_CART"
    APPLICATION = "APPLICATION"
    CHECKOUT = "CHECKOUT"
    PAGE_VIEW = "PAGE_VIEW"
    SEARCH = "SEARCH"
    OTHER = "OTHER"

class InventorySourceTypeEnum(str, Enum):
    """NEW - three types, not one.

    An earlier claim that "no non-AMAZON source was ever returned" was wrong.
    All four sources that exist, with the formats each serves:

        Amazon Publisher Direct  AMAZON_PUBLISHER_DIRECT  display, online_video
        Amazon Streaming TV      AMAZON                   streaming_tv
        Third Party Exchange     THIRD_PARTY_EXCHANGE     display, online_video
        Twitch                   AMAZON                   display, streaming_tv

    For streaming_tv there are exactly TWO sources - Amazon Streaming TV and
    Twitch. That is the whole CTV supply surface at the source level.
    """
    AMAZON = "AMAZON"
    AMAZON_PUBLISHER_DIRECT = "AMAZON_PUBLISHER_DIRECT"
    THIRD_PARTY_EXCHANGE = "THIRD_PARTY_EXCHANGE"

class DealTypeEnum(str, Enum):
    """NEW - two types in the data, though three exist in the domain.

    Counted across all 369 deals:
        PRIVATE_AUCTION          341   (92%)
        PREFERRED                 28   (8%)
        PROGRAMMATIC_GUARANTEED    0   <- none at all

    The absence of PG matters: it is the only deal type with guaranteed
    delivery, so nothing in the current inventory can promise impressions.
    Every forecast is therefore an estimate, and the agent must say so.
    """
    PRIVATE_AUCTION = "PRIVATE_AUCTION"
    PREFERRED = "PREFERRED"
    PROGRAMMATIC_GUARANTEED = "PROGRAMMATIC_GUARANTEED"   # in the domain, absent from the data

class DealPriceTypeEnum(str, Enum):
    """NEW - and this is why the bid is a real lever.

        FLOOR_RATE   341   (92%)
        FIXED_CPM     28   (8%)

    A floor rate is a minimum, not a price. On 92% of inventory the bid decides
    what is actually paid, which is the evidence behind treating base bid as a
    plannable field rather than a constant.
    """
    FLOOR_RATE = "FLOOR_RATE"
    FIXED_CPM = "FIXED_CPM"

class AllocationModeEnum(str, Enum):
    """NEW - read from the strategy record. Plan against money or impressions."""
    BUDGET = "BUDGET"
    IMPRESSIONS = "IMPRESSIONS"   # inferred; only BUDGET observed

class UserLocationSignalEnum(str, Enum):
    """NEW - a concept found on the strategy record and in no document so far.

    Only "CURRENT" was observed. The likely meaning is whether to target on the
    viewer's current location or their home location, but this is an ASSUMPTION -
    see the open question at the targeting note. Do not build against it until
    the value set is confirmed.
    """
    CURRENT = "CURRENT"

# NEW ENUMS

class DurationEnum(str, Enum):
    """CORRECTED - 7 durations, not 4."""
    SIX = "6"
    TEN = "10"
    FIFTEEN = "15"
    TWENTY = "20"
    THIRTY = "30"
    FORTY_FIVE = "45"
    SIXTY = "60"

class InventoryTierEnum(str, Enum):
    """NEW - the three inventory tiers driving the flow's primary fork.

    🔴 THIS IS OUR CONCEPT, NOT THE API'S. Verified across all 369 deals: there
    is no `inventory_tier` field, no `channel`, no `provider` and no `publisher`.
    The tier has to be DERIVED, and the only thing to derive it from is the deal
    name. See the deal-matching note at Step 2 for why that is fragile.
    """
    AMAZON_OWNED = "AMAZON_OWNED"
    THIRD_PARTY_PRECURATED = "THIRD_PARTY_PRECURATED"
    THIRD_PARTY_NEEDS_CURATION = "THIRD_PARTY_NEEDS_CURATION"

class ApprovalStatusEnum(str, Enum):
    """NEW — creative approval only; the plan uses PlanStatusEnum"""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class PlanStatusEnum(str, Enum):
    """NEW — the plan is finalised by the trader, not approved by a manager.
    Kept extensible: the review said "no manager approval required for now"."""
    DRAFT = "DRAFT"
    FINALISED = "FINALISED"

class BudgetSplitMethodEnum(str, Enum):
    """NEW — how the budget is divided"""
    EVEN_BY_BUDGET = "EVEN_BY_BUDGET"
    EVEN_BY_IMPRESSIONS = "EVEN_BY_IMPRESSIONS"
    CUSTOM = "CUSTOM"

class AudienceProfileEnum(str, Enum):
    """NEW — the three audience options"""
    NARROW = "NARROW"
    BALANCED = "BALANCED"
    WIDE = "WIDE"


# ==========================================
# COMPONENT SCHEMAS
# ==========================================

class DateRangeSchema(BaseModel):
    """UNCHANGED"""
    lower: str = Field(..., description="ISO date YYYY-MM-DD")
    upper: str = Field(..., description="ISO date YYYY-MM-DD")
    bounds: str = Field("[)", description="Interval boundary notation")

class MarketBudgetBidSchema(BaseModel):
    """UNCHANGED"""
    market: str = Field(..., description="ISO country code")
    budget: str = Field(..., description="Total budget decimal string")
    base_bid: str = Field(..., description="Base CPM bid decimal string")

class SelectedDealSchema(BaseModel):
    """CORRECTED - now separates what the API returns from what we derive.

    Verified against all 369 deals. The fields split cleanly in two, and mixing
    them was the error in earlier revisions - `channel` and `inventory_tier` were
    written as though the API supplied them.
    """
    # --- Returned by GET /api/deals/ ---
    external_deal_id: str = Field(..., description="e.g. EXT7P75718S8MNR")
    name: str = Field(..., description="Deal name - the only place the channel appears")
    deal_type: DealTypeEnum = Field(..., description="92% PRIVATE_AUCTION, 8% PREFERRED")
    deal_price_type: DealPriceTypeEnum = Field(..., description="92% FLOOR_RATE - so the bid matters")
    deal_price_amount: str = Field(..., description="Decimal string. Two deals are priced at 0")
    deal_price_currency: str = Field(
        ...,
        description="EIGHT currencies across the 369 deals: USD 156, EUR 95, GBP 35, "
                    "CAD 22, MXN 19, BRL 16, AUD 14, JPY 12. A GB plan CAN hold a "
                    "USD-priced deal - see the currency note at Step 1",
    )
    media_types: list[str] = Field(default_factory=list)
    devices: list[str] = Field(default_factory=list)
    environments: list[str] = Field(default_factory=list)
    locations: list[dict] = Field(default_factory=list, description="[{country_code, ...}]")
    genre: Optional[str] = Field(
        None,
        description="🔴 NULL on every deal inspected, INCLUDING deals whose name "
                    "carries a genre. Not usable for matching",
    )
    ad_lengths: list[str] = Field(default_factory=list, description="Supported durations")

    # --- DERIVED by the agent. Not API fields. ---
    channel: Optional[str] = Field(
        None,
        description="🔴 DERIVED by parsing `name`. There is no channel field. Eight "
                    "naming conventions exist and the casing is inconsistent "
                    "(Tubi vs TUBI), so this is best-effort and must be marked as "
                    "such wherever it is shown",
    )
    inventory_tier: Optional[InventoryTierEnum] = Field(
        None, description="🔴 DERIVED from the parsed channel. See InventoryTierEnum"
    )
    channel_confidence: Optional[str] = Field(
        None,
        description="NEW - how the channel was obtained: PARSED_CONFIDENT, "
                    "PARSED_GUESS or UNKNOWN. Required by the Stated Uncertainty "
                    "principle: a guessed channel must never read like a fact",
    )

class SelectedAudienceSetSchema(BaseModel):
    """CHANGED — added profile and effective_cpm"""
    audience_set_id: str = Field(..., description="Audience set UUID")
    name: str = Field(..., description="Audience set name")
    vcpm_fee: str = Field(..., description="VCPM fee decimal")
    profile: AudienceProfileEnum = Field(..., description="Narrow, Balanced, or Wide") # NEW
    effective_cpm: Optional[str] = Field(None, description="Deal CPM + audience VCPM") # NEW
    estimated_reach: Optional[int] = Field(None, description="If Amazon inventory") # NEW

class SelectedCreativeSchema(BaseModel):
    """CHANGED — added duration_seconds for the match check"""
    asset_id: str = Field(..., description="Registered asset ID")
    click_through_url: Optional[HttpUrl] = Field(
        None, description="Landing page URL — optional for CTV; nothing on a TV screen is clickable"
    ) # CHANGED from required
    duration_seconds: int = Field(..., description="Video length in seconds") # NEW
    upload_method: str = Field("direct", description="direct or url") # NEW

# NEW SCHEMAS

class BudgetSplitSchema(BaseModel):
    """NEW — how budget is divided across inventories and durations"""
    method: BudgetSplitMethodEnum = Field(..., description="Even by budget, even by impressions, or custom")
    by_inventory: list[dict] = Field(..., description="[{channel, budget, impressions_estimate}]")
    by_duration: list[dict] = Field(..., description="[{duration, budget, cpm, impressions_estimate}]")

class CurationRequirementsSchema(BaseModel):
    """NEW — captured for 3P-needs-curation inventory (e.g. Disney+)"""
    channel: str = Field(..., description="e.g. Disney+") # was `provider`
    genres: list[str] = Field(default_factory=list)
    durations: list[str] = Field(default_factory=list)
    targeting_preferences: Optional[str] = None
    budget: str = Field(..., description="Allocated budget for this channel")
    flight_dates: DateRangeSchema = Field(...)

class TargetingSchema(BaseModel):
    """CORRECTED - rebuilt against the review comments and the verified API.

    Four things were wrong in the previous version:
      1. `locations` was a flat list - the API has separate include and exclude
      2. Locations were treated as free text - they are opaque Amazon IDs
      3. `content_category_exclusions` - the field is content RATING, not category
      4. `mobile_environments` - the API field is the mobile OPERATING SYSTEM
    """
    # --- Location: include and exclude, both ID lists ---
    location_include: list[str] = Field(
        default_factory=list,
        description="Amazon geo location IDs. Opaque strings, NOT numeric - a real "
                    "one looks like XHvCjcKHXsKGemnCjsKQbMKX. This REPLACES the "
                    "market-level GB default when populated",
    )
    location_exclude: list[str] = Field(
        default_factory=list,
        description="Same ID space. Confirmed present in the API - the review "
                    "comment asking for exclusions was already supported",
    )

    # --- Instream position ---
    instream_positions: list[str] = Field(default_factory=list)

    # --- Brand safety: RATING, not category ---
    content_rating_exclusions: list[str] = Field(
        default_factory=list,
        description="RENAMED from content_category_exclusions. The API field on the "
                    "strategy record is content_rating_exclusions - an age or "
                    "suitability rating, which is a different control from excluding "
                    "a content category. Value set not yet confirmed",
    )

    # --- Devices ---
    device_types: list[str] = Field(
        default_factory=list,
        description="For streaming_tv, CONNECTED_TV is REQUIRED. DESKTOP and MOBILE "
                    "are optional additions. The default is either ALL or "
                    "CONNECTED_TV alone. There is NO TABLET value",
    )

    # --- Mobile OS: only meaningful if MOBILE is selected ---
    mobile_operating_systems: list[str] = Field(
        default_factory=list,
        description="RENAMED from mobile_environments. IOS and ANDROID only, and "
                    "ONLY RELEVANT IF MOBILE IS IN device_types. Setting this "
                    "without MOBILE is a validation error, not a silent no-op",
    )

    # --- New concept found on the strategy record ---
    user_location_signal: Optional[UserLocationSignalEnum] = Field(
        None,
        description="NEW and NOT UNDERSTOOD. Observed value CURRENT. Present in no "
                    "prior document. Do not set it until the value set and meaning "
                    "are confirmed",
    )

class CustomRadiusLocationSchema(BaseModel):
    """NEW - the custom radius location from the review comment, confirmed in the API.

    POST /api/strategies/locations/{market}/ takes an address plus a distance and
    returns a NEW location ID, which then goes into location_include like any
    other. So a radius is not a separate targeting mode - it is a way to mint an
    ID.
    """
    address: str = Field(..., description="Street address the radius is centred on")
    radius: float = Field(..., gt=0, description="Numeric distance")
    unit: str = Field(..., description="km or miles")

class PostcodeResolutionSchema(BaseModel):
    """NEW - answers the review question "can the user search for locations?".

    Yes, and they must. GET /api/strategies/locations/{market}/?query= is a SEARCH,
    minimum two characters, and it returns Amazon's own shape. A trader-supplied
    list of postcodes therefore has to be resolved one term at a time.

        query "SW1"  ->  {"nextToken": null, "geoLocations": [
                            {"name": "London, England, UK - SW1Y",
                             "id":   "XHvCjcKHXsKGemnCjsKQbMKX",
                             "category": "POSTAL_CODE"}, ...]}

    Three consequences the agent must handle: a postcode that resolves to
    several IDs, a postcode that resolves to none, and pagination via nextToken.
    """
    submitted: list[str] = Field(..., description="What the trader typed")
    resolved: list[dict] = Field(
        default_factory=list, description="[{submitted, amz_id, name, category}]"
    )
    ambiguous: list[dict] = Field(
        default_factory=list,
        description="[{submitted, candidates: [...]}] - more than one match. The "
                    "agent must ASK, never pick the first",
    )
    unresolved: list[str] = Field(
        default_factory=list, description="No match. Reported back verbatim, never dropped silently"
    )

class ForecastResultSchema(BaseModel):
    """CHANGED — added availability flag for the honesty rule"""
    is_available: bool = Field(..., description="False for Netflix/Disney — no reach data") # NEW
    estimated_impressions: Optional[int] = None
    estimated_unique_reach: Optional[int] = Field(None, description="Only for Amazon inventory")
    average_frequency: Optional[float] = Field(None, description="Only for Amazon inventory")
    indicative_cpm: Optional[str] = None
    reach_curve: Optional[list[dict]] = Field(None, description="[{budget, reach}] — Amazon only")

class TrackingSetupSchema(BaseModel):
    """NEW — tracking prerequisites collected at Step 11"""
    sells_on_amazon: bool = Field(...)
    validated_asins: list[dict] = Field(default_factory=list, description="[{asin, title, brand}]")
    sells_on_own_site: bool = Field(...)
    ad_tag_registered: Optional[bool] = None
    ad_tag_conversions: list[str] = Field(default_factory=list, description="Selected conversion events")


# ==========================================
# FULL STRATEGY SCHEMA
# ==========================================

class FullStrategySchema(BaseModel):
    """CHANGED — restructured from wizard steps to semantic grouping"""

    # --- Identity ---
    id: Optional[str] = Field(None, description="System-assigned strategy ID")
    advertiser_id: str = Field(..., description="Parent advertiser UUID")
    channel_type: ChannelTypeEnum = ChannelTypeEnum.DSP

    # --- Basics (Step 1) ---
    name: str = Field(..., description="Unique strategy name")
    flight_dates: DateRangeSchema = Field(...)
    markets: list[MarketEnum] = Field(..., description="ISO country codes. 21 in the enum")
    primary_currency: CurrencyEnum = Field(
        ...,
        description="CORRECTED - comes from the ADVERTISER, not from the market and "
                    "not defaulted to GBP. Observed pre-filled as EUR before any "
                    "market was chosen. The market's own currency is separate, on "
                    "market_budgets below",
    )
    durations: list[DurationEnum] = Field(..., description="Creative durations. 7 available")
    formats: list[FormatEnum] = Field(
        ...,
        description="A CTV plan sets streaming_tv. Note the enum ALSO contains 12 "
                    "channel values - see FormatEnum",
    )
    goal: GoalEnum = Field(
        GoalEnum.AWARENESS,
        description="CORRECTED - DEFAULTED for CTV, not fixed. The API accepts 15 "
                    "values and the trader may change it. The agent states the "
                    "default rather than hiding it",
    )
    kpi_target_type: KPIEnum = Field(..., description="16 values; 5 on the automated endpoint")
    target_kpi: Optional[str] = Field(
        None,
        description="CORRECTED - this is a STRING in the API, not an integer. It "
                    "holds the number the trader is aiming for (a frequency of 3, a "
                    "reach figure), and a string can carry a decimal ROAS target "
                    "that an int cannot. Renamed from kpi_target_value",
    )
    impression_target: Optional[int] = Field(
        None,
        description="NEW and API-VERIFIED. A plan can be built against impressions "
                    "INSTEAD OF budget. Mutually exclusive with the budget on "
                    "market_budgets - see allocation_mode",
    )
    allocation_mode: AllocationModeEnum = Field(
        AllocationModeEnum.BUDGET, description="NEW - which of the two above is authoritative"
    )
    product_categories: list[str] = Field(
        default_factory=list,
        description="CORRECTED - list of STRINGS, not integers. 25,973 exist for GB, "
                    "so this is always populated from a search and never from a list",
    )
    product_location: ProductLocationEnum = Field(...)
    market_budgets: list[MarketBudgetBidSchema] = Field(...)
    conversion_types: list[ConversionTypeEnum] = Field(
        default_factory=list,
        description="NEW - 6 events, and availability DIFFERS BY MARKET. Must be "
                    "filtered against the chosen market before being offered",
    )
    frequency_cap: Optional[int] = Field(None, description="Optional cap, per WEEK")
    budget_cap: Optional[str] = Field(None, description="Optional budget cap") # NEW

    # --- Inventory (Step 2) ---
    selected_deals: list[SelectedDealSchema] = Field(...) # CHANGED — enriched schema
    curation_requirements: list[CurationRequirementsSchema] = Field(default_factory=list) # NEW

    # --- Budget Split (Step 3) ---
    budget_split: Optional[BudgetSplitSchema] = None # NEW

    # --- Audiences (Step 4) ---
    audience_options: list[SelectedAudienceSetSchema] = Field(default_factory=list) # CHANGED — now carries all three
    chosen_audience_profile: Optional[AudienceProfileEnum] = None # NEW
    matching_mode: str = Field("Exact", description="Similar or Exact") # UNCHANGED

    # --- Targeting (Step 5) ---
    targeting: Optional[TargetingSchema] = None # NEW

    # --- Forecast (Step 6) ---
    forecast: Optional[ForecastResultSchema] = None # CHANGED — enriched with availability

    # --- Finalisation (Step 7) ---
    plan_status: Optional[PlanStatusEnum] = None # was approval_status
    finalised_by: Optional[str] = None # was approved_by
    finalised_at: Optional[str] = None # was approved_at

    # --- Creative (Step 9) ---
    selected_creatives: list[SelectedCreativeSchema] = Field(default_factory=list) # CHANGED — enriched
    creative_duration_match: Optional[bool] = None # NEW
    creative_approval_statuses: dict[str, ApprovalStatusEnum] = Field(
        default_factory=dict,
        description="One entry per matched channel — keys are data, not schema",
    ) # was a single creative_approval_status

    # --- Tracking (Step 11) ---
    tracking: Optional[TrackingSetupSchema] = None # NEW
    product_asins: list[str] = Field(default_factory=list) # MOVED from Step 1

    # --- Activation (Steps 12-13) ---
    credit_sufficient: Optional[bool] = None # NEW
    status: str = Field("created", description="Strategy status") # CHANGED from "draft"
    is_syncing: bool = Field(False)

    # --- Delivery controls (NEW, and OWNERSHIP UNRESOLVED) ---
    # 🔴 These were found on the live strategy record and appear in no earlier
    # revision. They are listed here so the gap is visible, NOT because the agent
    # should set them. Until D50 is answered, treat every one as read-only.
    planned_cpm: Optional[str] = Field(None, description="Observed null")
    cpm_target: Optional[str] = Field(None, description="Observed null")
    audiences_cpm: Optional[str] = Field(
        None, description="The audience fee, stored on the strategy rather than recomputed"
    )
    pacing_ratio: Optional[float] = Field(None, description="Delivery pacing. Observed null")
    creative_rotation_type: Optional[str] = Field(None, description="Observed RANDOM")
    creative_duration_allocation_mode: Optional[str] = Field(
        None,
        description="Observed 'budget' - LOWERCASE, where allocation_mode above is "
                    "uppercase BUDGET. The casing is genuinely inconsistent in the "
                    "API; do not normalise it silently",
    )
    can_be_extended: Optional[bool] = Field(None, description="Whether the flight can be extended")

    # --- Provenance (NEW) ---
    # Which create endpoint made this strategy. Useful for confirming the agent
    # took the route §4.2 recommends.
    is_simple: Optional[bool] = Field(None, description="Created via /simple-strategies/")
    is_automated: Optional[bool] = Field(None, description="Created via /automated-strategies/")


# ==========================================
# LANGGRAPH PLANNING STATE
# ==========================================

# CHANGED — restructured from wizard-step-based to semantic field names

# WAS (v1.1.0):
# class PlanningAgentState(TypedDict):
# messages: List[Dict[str, Any]]
# advertiser_id: str
# current_step: int # 0 to 5
# strategy_id: Optional[str]
# step1_details: Optional[Dict[str, Any]]
# step2_goal_kpi_bid: Optional[Dict[str, Any]]
# step3_deals: Optional[Dict[str, Any]]
# step4_audiences: Optional[Dict[str, Any]]
# step5_creatives: Optional[Dict[str, Any]]
# forecast_results: Optional[Dict[str, Any]]
# validation_errors: List[str]
# is_complete: bool

# NOW:
from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages

class PlanningAgentState(TypedDict):
    """State carried through the LangGraph planning flow.

    Named semantically, not by wizard step — the state describes
    the plan, not the UI that collected it.
    """
    # --- Conversation ---
    messages: Annotated[list, add_messages]

    # --- Session context ---
    advertiser_id: str
    session_id: str
    current_stage: str # NEW — for the adaptive canvas
    current_artifact_id: Optional[str] # NEW — for the adaptive canvas

    # --- Basics ---
    strategy_name: Optional[str]
    flight_dates: Optional[dict]
    markets: list[str]
    durations: list[str] # NEW
    primary_currency: str
    goal: str # fixed: AWARENESS for CTV
    kpi: str # reach or frequency
    market_budgets: list[dict]
    product_location: Optional[str]
    frequency_cap: Optional[int] # NEW
    budget_cap: Optional[str] # NEW

    # --- Inventory ---
    inventory_tier: Optional[str] # NEW — which tier fork we're on
    selected_deals: list[dict]
    curation_requirements: list[dict] # NEW

    # --- Budget split ---
    budget_split: Optional[dict] # NEW

    # --- Audiences ---
    audience_options: list[dict] # the three profiles
    chosen_audience: Optional[dict] # which one the trader picked

    # --- Targeting ---
    targeting: Optional[dict] # NEW

    # --- Forecast ---
    forecast: Optional[dict] # reach/impressions/CPM (with availability flag)

    # --- Finalisation ---
    plan_status: Optional[str] # DRAFT/FINALISED — was approval_status
    finalised_by: Optional[str] # was approved_by
    finalised_at: Optional[str] # was approved_at

    # --- Creative ---
    creative_id: Optional[str]
    creative_duration_match: Optional[bool] # NEW
    creative_approval_status: Optional[str] # NEW

    # --- Tracking ---
    tracking_setup: Optional[dict] # NEW
    product_asins: list[str] # MOVED

    # --- Activation ---
    credit_sufficient: Optional[bool] # NEW
    strategy_id: Optional[str]
    strategy_status: Optional[str]

    # --- Errors ---
    validation_errors: list[str]
```

---

## 5.5 Validation authorities — what every value is checked against

NEW — required by the extended Zero-Hallucination principle in §1. Nothing enters the plan unverified, so every field needs a named authority and a named failure behaviour.

### The three outcomes

Every check produces one of three results, and each has a different consequence:

| Outcome | Meaning | What the agent does |
|---|---|---|
| **VALID** | The value exists and is usable here | Accept it. Say nothing |
| **INVALID** | The value does not exist, or cannot apply in this context | **Report it and ask.** Never substitute, never drop |
| **AMBIGUOUS** | Several real values match | **Ask which.** Never take the first |

**AMBIGUOUS is the outcome most likely to be mishandled**, because taking the first match always "works" and never raises an error. A postcode that matched five London districts, resolved silently to one of them, produces a plan that runs — in the wrong place.

### The timing rule

**Validate before confirming, not after.**

```
WRONG   extract → confirm to trader → validate → discover a problem
        The trader has already agreed to something that cannot be built.
        Now the agent has to withdraw a plan it presented as understood.

RIGHT   extract → validate → confirm to trader
        The confirmation only contains values that survived verification.
```

This ordering is why validation is a distinct step in the flow rather than something folded into extraction. It also means the confirmation message can legitimately carry the phrase *"here is what I understood"* — because everything in it has been checked.

### The authority table

| Field | Authority | Check | On failure |
|---|---|---|---|
| **Strategy name** | `GET /strategies/check_strategy_name_uniqueness/` | Does this name already exist? | Report the clash and offer alternatives. **Never auto-append a suffix** — the trader may have meant to reuse an existing campaign's naming and needs to know |
| **Markets** | `market` enum (21) **and** `GET /deals/` | Is the code valid, **and** does this market have deals? | Valid-but-empty is a real case: 3 of 21 enum markets have no deals. Say which markets do |
| **Flight dates** | Business rules | Start in the future; end after start; length within limits | Report the specific problem, not "invalid dates" |
| **Budget** | `GET /credits/summary/` | Is the credit balance sufficient? | Report the shortfall as a number. This is checkable at Step 1, not only at Step 12 |
| **Primary currency** | `currency` enum (19) **and** the advertiser | Valid code, and does it match the advertiser's? | A mismatch is not an error — it is a conversion. Say the rate and which currency the arithmetic used |
| **Durations** | `duration` enum (7) **and** deal `ad_lengths` | Valid value, **and** do matched deals support it? | A 45s plan with no 45s deals is unbuyable. Report which durations the inventory supports |
| **Formats** | `format` enum (21) | Valid value | — |
| **Goal** | `goal` enum (15) | Valid value | — |
| **KPI** | `kpi` enum (16), **or the 5-value automated set** | Valid, **and permitted on the create endpoint being used** | A KPI valid on `/strategies/` may be rejected by `/automated-strategies/`. Check against the endpoint actually being called |
| **`target_kpi`** | Per-KPI range rules | Range depends on which KPI. Frequency 2–5; ROAS is a decimal | The range is conditional on the KPI, so the error message must name the KPI |
| **Channel** | `GET /deals/` + name parsing | Do deals exist for this channel in this market at these durations? | Report the count. Zero matches is the common case and must be said plainly, with what *is* available |
| **`specific_deal_id`** | `GET /deals/` | Does the deal exist, serve this market, and support these durations? | A trader naming a deal by hand is the case most likely to carry a stale ID |
| **Product categories** | `GET /contextual-targeting/{market}/product-categories/` | Does the category exist, and is it a selectable leaf? | 25,973 exist, so this is always a search. A non-leaf category cannot be selected |
| **ASINs** | `POST /contextual-targeting/{market}/asin-validation/` | Does each ASIN exist and belong to this advertiser? | Report per-ASIN, not as one pass or fail |
| **Locations / postcodes** | `GET /strategies/locations/{market}/?query=` | Does each term resolve to exactly one ID? | Three-way: resolved, **ambiguous → ask**, unresolved → report. Never drop silently |
| **Custom radius** | `POST /strategies/locations/{market}/` | Does the address resolve? Is the unit `km` or `miles`? | An unresolvable address must be reported, not approximated |
| **Audience set** | `GET /audience-sets/` | Does it exist and apply to this market? | — |
| **Conversion types** | `GET /conversions/definitions/?selected_advertiser_id=` | Valid event **for this market** | `CHECKOUT` is GB-only, `SEARCH` is US-only. A market change **re-invalidates** an existing selection |
| **Device types** | Device value set | Valid value; `CONNECTED_TV` present when `streaming_tv` | `TABLET` does not exist. **Report it — do not drop it.** The trader believes tablets are excluded |
| **Mobile OS** | `IOS` / `ANDROID` | Set only when `MOBILE` is in `device_types` | Setting it without `MOBILE` is a validation error, not a silent no-op |
| **Content rating exclusions** | Value set (unconfirmed) | — | Blocked on D51 — the field is a rating, not a category |
| **Creative duration** | Plan `durations` | Does the uploaded file's length match a planned duration? | A mismatch changes the economics and triggers re-approval (Step 9) |
| **Impression target** | `allocation_mode` | Exactly one of budget or impression target is authoritative | Both set with no `allocation_mode` is ambiguous — ask which governs |
| **Frequency cap** | Advertiser defaults | Is the advertiser's value locked? | 🔴 Blocked on **D47** — the endpoint returns 403, so a locked cap cannot currently be detected |

### What "never silently fix" rules out

Four specific behaviours, each of which would pass tests and mislead a trader:

```
Duplicate name        →  appending "-2", "(1)" or a timestamp
Invalid device value  →  dropping TABLET from the list
Ambiguous postcode    →  taking geoLocations[0]
Unknown channel       →  falling back to "run of service" or to Prime Video
```

Each of these produces a plan that builds and runs. **That is what makes them dangerous** — nothing fails, so nothing is investigated, and the trader's belief about their own campaign is wrong.

### Where validation cannot currently happen

Two authorities are unavailable, and both are open blockers:

| Field | Authority | Status |
|---|---|---|
| Frequency cap, device policy, product categories, selling location | `GET /admin/advertiser/{id}/` | 🔴 **403** — see D47 |
| Channel | A `channel` field on the deal | 🔴 **Does not exist** — parsed from the name, marked `PARSED_GUESS`. See D53 |

**Where an authority is missing, the value must be marked as unverified rather than treated as verified.** This is the point at which the Zero-Hallucination principle and the Stated Uncertainty principle meet: a value that could not be checked is not the same as a value that passed, and the plan must be able to tell the difference.

---

## 6. State Machine

CHANGED — needs complete rebuild. The original was a linear pipe. The confirmed flow has branches, loops, and interrupts.

The confirmed state machine (v5):

```
START
  → extract_fields (slot-filling from brief)
  → match_inventory_deals (CTV, three-tier fork — matched, not selected)
    → [if 3P needs curation] capture_curation_requirements
  → propose_budget_split (across inventories + durations)
  → suggest_audiences (3 options via pgvector; optional — may be declined)
  → apply_targeting (optional, configurable)
  → predict_reach
    → [if Amazon] real forecast + reach curve
    → [if 3P] CPM + derived impressions only (honest)
    → [if too narrow] REPAIR: extend audience → re-predict (loop)
  → present_plan (on the strategy card)
  → finalise_plan (status DRAFT → FINALISED — no interrupt, no manager)
  → create_strategy (POST /simple-strategies/ — the real one, not draft)

  ── from here the three branches run in any order, none waits on another ──

  ├── BRANCH A upload_creative (video, gen_upload_urls + register)
  │ → [if duration mismatch] amend plan → re-finalise (loop back)
  │ platform_creative_approval (per matched channel)
  │ → interrupt — waiting on the platform's review, not on a colleague
  │ → [if rejected] return to upload_creative
  │
  ├── BRANCH B tracking_setup (ASINs + ad tag check)
  │ → PATCH /strategies/{id}/ to attach the ASINs
  │
  └── BRANCH C credit_check (GET /credits/summary/)
                 → [if insufficient] prompt top-up (loop)

  → activate — join node. Checks ready_to_activate across all three
                  branches, then POST /strategies/{id}/set_status/
                  (the single spend action)
  → DONE
```

**Q&A side path:** at any point, the trader can ask a pricing/availability question ("what's the CPM for Netflix 30s?"). The agent answers from the rate card and resumes.

---

## 7. Brief Parsing & Edge Cases

### 7.1 Entity Normalisation

UNCHANGED — the original examples are correct. Additions:

| Input | Extraction | Status |
|---|---|---|
| August 2026 | `flight_dates: {lower: "2026-08-01", upper: "2026-08-31"}` | Original |
| UK | `markets: ["GB"], primary_currency: "GBP"` | Original |
| £10,000 | `market_budgets: [{market: "GB", budget: "10000.00"}]` | Original |
| education website | `product_location: "NOT_SOLD_ON_AMAZON"` | Original |
| 30 seconds | `durations: ["30"]` | NEW |
| UK and France | `markets: ["GB", "FR"]` | NEW |
| sports drink | Consider genre-specific deals (Sports) | NEW |
| Prime and Netflix | Multiple inventory tiers | NEW |
| SW1A, EC2, W1 | Three location searches, then IDs — **not** a single field | NEW |
| within 10 miles of Manchester | A custom radius location, which mints a new ID | NEW |
| 400,000 impressions | `impression_target: 400000`, `allocation_mode: IMPRESSIONS` | NEW |
| a frequency of 3 | `kpi_target_type: FREQUENCY`, `target_kpi: "3"` | NEW |

🔴 **Two corrections to the row for "UK".** It maps to `markets: ["GB"]`, which is right, but the currency does **not** follow from it — `primary_currency` comes from the advertiser (see the currency note at Step 1). And the extraction is incomplete: a GB market can still hold a USD-priced deal, so the market fixes the geography and nothing else about the money.

🔴 **And "Prime and Netflix" cannot be extracted to a tier.** Deals carry no channel or tier field, so what the agent actually does is search deal names for those words and mark the result as derived. See the deal-matching note at Step 2.

### 7.2 Validation Failure Protocols

UNCHANGED — duplicate name, invalid ASIN, past dates protocols all correct.

### 7.3 Repair Loop

CHANGED — concept correct, mechanism updated (see Step 6 above). Only applies to Amazon-owned inventory.

**NEW — "Did I understand correctly?" confirmation.** After extracting fields from a brief, the agent immediately shows what it understood so the trader can correct before proceeding. This is the single most important trust mechanism in the product.

---

## 8. Summary of all changes

| Category | Count | Items |
|---|---|---|
| Unchanged | ~15 | Core principles, product attribution, deal types, date validation, name uniqueness, currency, most API endpoints, brief parsing examples |
| Changed | ~12 | Step order, goal scoped to Awareness, KPI scoped to reach/frequency, deals enriched with tier, audiences suggestion-driven + renamed Wide, forecast with availability flag, state restructured, creative simplified to video |
| New | ~15 | Durations, inventory tiers, budget split, targeting, plan approval, creative duration check, platform creative approval, tracking setup (moved), credit check, activation, curation capture, effective CPM, adaptive-canvas fields |
| Removed | ~5 | Draft endpoint, product audiences, non-CTV formats (scoped out), non-awareness KPIs (scoped out), canary-check |
| **Corrected in v3.1** | **11** | Currency source, audience fee source, deal channel and tier, the create endpoint, the bid lever, inventory source types, and every count and enum in the document |

### Corrections made in v3.1, in one place

The full evidence for each sits at the step it affects. Collected here because a reader who has the earlier revision needs to know exactly what to stop relying on.

| # | Where | This document said | Correct |
|---|---|---|---|
| 1 | Step 1, §5 | Currency is derived from the market | An **advertiser** default. 19 values in the enum |
| 2 | Step 1, §5 | `goal` is FIXED for CTV | **Defaulted**, and the enum has 15 values |
| 3 | Step 1, §5 | `kpi_target_value`, an integer | **`target_kpi`, a string** — a decimal ROAS target needs it |
| 4 | Step 1, §5 | `product_categories: List[int]` | `List[str]`. 25,973 exist for GB |
| 5 | Step 1, §5 | 4 formats, 4 KPIs, 4 durations, 2 markets | **21, 16, 7 and 21** |
| 6 | Step 2, §5 | Deals carry `channel` and `inventory_tier` | **Neither field exists.** Both parsed from the name |
| 7 | Step 2 | 83 deals, one priced at zero | **369 deals, two** priced at zero |
| 8 | Step 4, §4 | The audience fee comes from `/contextual-targeting/fees` | **Two separate fees.** The audience fee is on the audience set |
| 9 | Step 6 | CTV CPMs are fixed, so no bid lever | **92% are floor-rate.** The bid is the least invasive repair |
| 10 | Step 8, §4 | `simple-strategies` is the CTV create endpoint | A minimal shell. **`automated-strategies`** carries the plan |
| 11 | Step 11, §5 | 4 conversion events, universal | **6 events, market-specific** |

---

## 9. Questions raised by the verification pass

Twenty-two `OPEN QUESTIONS` blocks sit under the relevant notes throughout the document. The eight below are new, arose from the live API pass, and are collected here because they are the ones that block work rather than refine it.

**The two blockers, in priority order:**

| # | Question | Why it blocks |
|---|---|---|
| **D47** | `GET /api/admin/advertiser/{id}/` returns **403** to a valid trader session, along with four other `/admin/` endpoints. How is the agent meant to read advertiser defaults — does it need a **service account** with admin scope, or are the defaults exposed on a non-admin endpoint we have not found? | The whole advertiser-defaults concept — frequency cap, device types, product categories, selling location — rests on this endpoint. Without it the agent must **ask the trader for values it was told not to ask for**, which contradicts a review comment |
| **D50** | The strategy record carries `pacing_ratio`, `planned_cpm`, `cpm_target`, `allocation_mode`, `creative_rotation_type` and `creative_duration_allocation_mode`. Does the agent set these, or does the platform? | If the agent sets them they belong in the plan model and in the conversation. If the platform sets them they should be read-only. Right now they are in neither place, so whichever is true, something is missing |

**The six that need an answer before the schema locks:**

| # | Question | Context |
|---|---|---|
| **D48** | What is `user_location_signal`, and what values does it take? Observed: `CURRENT` | A targeting concept in no document so far. The guess is current versus home location, but that is a guess |
| **D49** | Do the audience data fee and the contextual targeting fee **add**? | At GB streaming-TV rates that is 1.63 + 0.450 = 2.08 GBP per thousand impressions. The agent cannot state a correct effective CPM until this is settled (§4.3) |
| **D51** | `content_rating_exclusions` — is this a content **rating** (age, suitability) or a content **category**? | This document called it a category. The API calls it a rating. They are different brand-safety controls |
| **D52** | The `format` enum contains `netflix`, `disney`, `paramount` and nine other channels. How should the model reconcile that with "Prime Video is a channel, not a format"? | The domain distinction is right and the API does not make it. The current answer is at Step 1's formats note; confirmation is needed |
| **D53** | Can a controlled `channel` field be added to the deal object? | Eight naming conventions across 369 deals, with `Tubi` and `TUBI` both present. **This is the highest-value data-quality request in the document** — one field removes a whole class of silent error |
| **D54** | What did the "50+ inventory" figure count? | Inventory sources max out at **4**. The likely candidates are the 369 deals or the 21-value format enum, but this should be confirmed rather than assumed |

### Data-quality requests

Separate from the questions above, because these are asks rather than clarifications:

1. **A `channel` field on the deal object** (see D53) — the single most useful change to the data
2. **Populate `genre`** — the field exists and is null even on deals whose name states a genre
3. **Consistent casing in deal names** — `Tubi` and `TUBI` are the same channel
4. **Confirm the two zero-priced deals are intentional** — both FIFA 2026 ZA. Impressions are budget ÷ CPM, so a zero CPM is a division by zero

---

## Verification method

So that the findings can be re-checked rather than taken on trust.

| | |
|---|---|
| **When** | 6 August 2026 |
| **Against** | `staging.vowmade.dev` |
| **Spec** | Full OpenAPI document — 192 paths, 197 definitions |
| **Calls** | 60+ authenticated requests, **all GET**. Nothing was created, modified or deleted |
| **Advertiser context** | A single test advertiser, passed via the `Vowmade-Advertiser-Id` header |
| **Enum source** | `GET /api/strategies/choices/` — every enum in §5 |
| **Deal analysis** | All 369 deals fetched by walking the paginated list, then counted by market, type, price type, currency and name prefix |

Credentials were supplied through environment variables and never written into a file, so nothing sensitive was committed. Raw responses and the probe scripts are outside the repository.

**What was not verified.** Every endpoint marked ⬜ in §4.1 is POST-only or would have written data. Those rows come from the spec, not from a call, and should be treated as less certain than the ✅ rows.

---

This document is for client verification. Once confirmed, it becomes the shared contract that the agent, registry and interface teams build against.
