# VOW Platform — Strategy Schema (Revised v2.0)
## Aligned to the confirmed CTV-first agentic flow (v5)

**Original version:** 1.1.0 by Kareem
**This revision:** 2.0.0 — reordered, scoped to CTV, and extended with client-confirmed corrections
**Status:** For client verification

> **How to read this document.** Every section is marked:
> - ✅ **UNCHANGED** — kept exactly as Kareem wrote it
> - 🔄 **CHANGED** — the concept existed but is modified (original shown for comparison)
> - ➕ **NEW** — did not exist in v1.1.0, added from client feedback
> - ❌ **REMOVED** — existed in v1.1.0 but dropped for CTV scope (kept as future scope)
>
> The document follows the **confirmed agentic flow order**, not the existing wizard order.

---

## 1. Core Principles

✅ **UNCHANGED** — all three kept exactly as written.

1. **Zero-Hallucination Policy**: The agent NEVER invents strategy parameters, metrics, targeting criteria, or deal IDs. It only populates values verified against the VOW database and REST APIs.
2. **Self-Filling Form Paradigm**: The agent operates as a stateful slot-filling engine backed by LangGraph. Inputs via chat or uploaded briefs are parsed into registered Pydantic slot schemas.
3. **API-Driven Tool Execution**: Every step maps to official VOW API endpoints.

---

## 2. Business Logic

### 2.1 Product Attribution & Selling Locations

✅ **UNCHANGED**

- **On Amazon (`ON_AMAZON`) [Endemic]**: ASINs **required**. Enables DPV, ATC, Purchase, ROAS tracking.
- **Off Amazon (`NOT_SOLD_ON_AMAZON`) [Non-Endemic]**: ASINs **optional** (monitors halo sales). Ad tag conversions required for site event tracking.

### 2.2 Attribution Window

✅ **UNCHANGED** — 14-day post-view and post-click.

### 2.3 Deal Types

🔄 **CHANGED** — deal types unchanged, but **inventory tiers added**.

**Original deal types (kept):**

| Type | Price | Commitment | Can pause? |
|---|---|---|---|
| **Programmatic Guaranteed (PG)** | Fixed CPM, guaranteed volume | Full budget owed | No |
| **Preferred Deals** | Fixed CPM | None | Yes |
| **Private Auctions** | Floor CPM, competitive | None | Yes |

➕ **NEW — Three inventory tiers** (the primary fork in the CTV flow):

*Every deal now carries an inventory tier. This classification drives most of the downstream branching — whether reach can be forecast, whether Amazon audiences apply, and whether the deal is selectable now.*

| Tier | Examples | Deals | Reach forecast | Audiences |
|---|---|---|---|---|
| **Amazon owned** | Prime Video | Pre-curated, selectable now | ✅ Available | Amazon audiences |
| **3P pre-curated** | Netflix, Hulu, others | Pre-curated, selectable now | ❌ Not available | Their own targeting (adds CPM) |
| **3P needs curation** | Disney+, others | Rate-card CPM only; VOW curates the deal after the IO is signed | ❌ Not available | Their own targeting (adds CPM) |

**Why this matters:** a plan spanning Prime + Netflix + Disney has three portions, each with different capabilities. The agent must handle them differently — and be honest about what it can and cannot forecast.

### 2.4 Audience Set Profiles

🔄 **CHANGED** — renamed "Broad" to "Wide" per client vocabulary; added fee consequence.

| Profile | Was (v1.1.0) | Now |
|---|---|---|
| 1 | Narrow (High Precision) | **Narrow** — highly targeted, elevated intent, **higher audience fee**, risk of underdelivery |
| 2 | Balanced (Recommended) | **Balanced** — optimal blend, the usual recommendation |
| 3 | Broad (Maximum Scale) | **Wide** — broad demographic/interest reach, **lower fee**, less precision |

➕ **NEW note:** the audience fee (VCPM) stacks on top of the deal CPM. A narrow audience is both smaller **and** more expensive per impression. The agent should surface the **effective CPM** (deal + audience fee), not just the deal price.

➕ **NEW:** audiences are **mandatory** and **suggestion-driven**. The agent always suggests three options using VOW's existing pgvector + OpenAI feature (`POST /audience-sets/suggest/`). Nobody browses the ~3,400 segments manually.

❌ **REMOVED for CTV:** product audiences (not applicable per client). AMC audiences are **conditional** — available only when the advertiser has prior campaign data (retargeting tactic).

---

## 3. The Agentic Flow — Step by Step

🔄 **CHANGED — entirely reordered.** The original followed the 6-step UI wizard. This follows the client-confirmed CTV-first agentic flow (v5).

### Comparison: old order vs new order

| Old (v1.1.0 wizard) | New (v2.0 agentic, confirmed) |
|---|---|
| 1. Strategy details | 1. Basics (+ **durations**) |
| 2. Goal, KPI & bid | *(goal/KPI/bid folded into Basics)* |
| 3. Deals | 2. CTV inventory (**three-tier fork**) |
| — | 3. **Budget split** ➕ NEW |
| 4. Audiences | 4. Audiences (mandatory, suggestion-driven) |
| — | 5. **Targeting** ➕ NEW |
| *(forecast was a sub-step)* | 6. Predict reach (**Amazon only**; repair loop) |
| — | 7. **Plan approval** ➕ NEW |
| *(create was at the end)* | 8. Create the **real** strategy |
| 5. Creatives | 9. Upload video creative (+ **duration check**) |
| — | 10. **Platform creative approval** ➕ NEW |
| *(ASINs were in step 1)* | 11. **Tracking setup** (ASINs + ad tag) 🔄 MOVED |
| — | 12. **Credit check** ➕ NEW |
| 6. Summary → create | 13. **Activate** ➕ NEW |

---

### Step 1: Basics

🔄 **CHANGED** — merged original Steps 1 and 2 (strategy details + goal/KPI/bid), added durations, scoped to CTV.

**What was in v1.1.0 (Step 1 + Step 2):**
- Strategy name, flight dates, target markets, primary currency, formats (all four), product categories, selling location, ASINs
- Goal (three choices), KPI (six choices), ad tag conversions, market budgets, base bids

**What it is now:**

| Field | Type | Requirement | Change from v1.1.0 |
|---|---|---|---|
| **Strategy name** | String | Required | ✅ Unchanged. Validated via `GET /api/strategies/check_strategy_name_uniqueness/` |
| **Flight dates** | Date range | Required | ✅ Unchanged. `lower` ≥ today, `upper` > `lower` |
| **Target markets** | Multi-select | Required | ✅ Unchanged. ISO country codes (GB, US, DE) |
| **Primary currency** | Dropdown | Required | ✅ Unchanged. EUR, GBP, USD |
| **Creative durations** | Multi-select | **Required** | ➕ **NEW.** Values: `10`, `15`, `20`, `30` (seconds). Determines which deals are available and what CPM applies |
| **Goal** | Fixed | Required | 🔄 **CHANGED.** For CTV, **always Awareness**. Client: "CTV is typically used as an Awareness goal as it's hard to track anything further down the funnel" |
| **KPI** | Select | Required | 🔄 **CHANGED.** For CTV, **reach or frequency only**. Was six choices; others scoped out |
| **Market budgets** | Table | Required | ✅ Unchanged. Per-market budget, must be > 0 |
| **Base bids** | Table | Required | ✅ Unchanged. Per-market base CPM bid |
| **Frequency cap** | Number | **Optional** | ➕ **NEW.** Was absent; client confirmed optional |
| **Budget cap** | Number | **Optional** | ➕ **NEW.** Was absent; client confirmed optional |
| **Formats** | Fixed | Required | 🔄 **CHANGED.** For M1, **streaming_tv and prime_video only**. Display and online_video removed from scope |
| **Product categories** | Multi-select | Required for video | ✅ Unchanged. Fetched via `GET /api/contextual-targeting/{market}/product-categories/` |
| **Selling location** | Radio | Required | ✅ Unchanged. `ON_AMAZON` or `NOT_SOLD_ON_AMAZON` |
| **Product ASINs** | Textarea | Conditional | 🔄 **MOVED.** Still required if ON_AMAZON, but the **validation and collection** now happens at Step 11 (tracking setup). See open question below |

**API calls at this step:** `GET /api/strategies/check_strategy_name_uniqueness/`, `GET /api/contextual-targeting/{market}/product-categories/`

❌ **REMOVED from this step:** ad tag conversions (moved to Step 11), the three non-CTV format options (Display, Online Video — future scope), the four non-awareness KPIs (CTR, CPC, CPA, CPDPV — future scope)

⚠️ **Open question:** `product_location` and `asin_numbers` are fields in the `POST /strategies/` payload called at Step 8. If ASINs are collected at Step 11 (after Step 8), they'd need to be patched onto the strategy afterwards. Alternatively, the ASIN question stays early (it's a plan field) and only the ad-tag check moves late. **Confirm with client.**

---

### Step 2: CTV Inventory (the tier fork)

🔄 **CHANGED** — was Step 3 "Deals" in v1.1.0. Now comes **before audiences**, and introduces the three-tier fork.

**What was in v1.1.0:**
- A flat deals table filtered by market and format, with checkbox selection

**What it is now:**

| Field | Type | Requirement | Change from v1.1.0 |
|---|---|---|---|
| **Selected deals** | Checkbox table | Required | ✅ Core concept unchanged. Fetched via `GET /api/deals/?markets={market}&formats=streaming_tv` |
| **Inventory tier** (per deal) | Enum | Derived | ➕ **NEW.** Each deal classified as `AMAZON_OWNED`, `THIRD_PARTY_PRECURATED`, or `THIRD_PARTY_NEEDS_CURATION` |
| **CTV rate card** | Reference | Read | ➕ **NEW.** `GET /api/rates/ctv/{market}/` — channels, durations, CPMs |

➕ **NEW — Genre upsell logic:**
The client asked: "based on the brief we can suggest whether a specific available genre would be a better match at a slightly higher CPM." Example: Prime Video ROS at $18.22 vs Action at $22.07 — the agent should recommend when the brief implies a genre match.

➕ **NEW — Curation capture (for 3P-needs-curation tier):**
When deals can't be selected yet (Disney+ etc.), the agent captures what VOW needs to curate later: genres, durations, targeting preferences, budget, flight dates.

| Field | Type | Requirement |
|---|---|---|
| **Curation: genres** | Multi-select | Required for curation tier |
| **Curation: durations** | Multi-select | Required for curation tier |
| **Curation: targeting prefs** | Text | Optional |
| **Curation: budget** | Number | Required for curation tier |
| **Curation: flight dates** | Date range | Required for curation tier |

**API calls at this step:** `GET /api/deals/`, `GET /api/deals/filter-properties/`, `GET /api/rates/ctv/{market}/`

---

### Step 3: Budget Split

➕ **ENTIRELY NEW** — did not exist in v1.1.0. Added per client requirement.

*"We will need to support the suggested budget split across inventories or creative durations."*

The agent proposes how the total budget is divided across inventories (Prime / Netflix / Disney) and across creative durations (15s / 30s). This is genuinely hard — different durations have different CPMs, and there's no reach data for Netflix/Disney to optimise against.

| Field | Type | Requirement |
|---|---|---|
| **Split by inventory** | Allocation (%) | Required when multiple inventories selected |
| **Split by duration** | Allocation (%) | Required when multiple durations selected |
| **Split method** | Enum | Agent states its assumption |

**Split method options:**
- `EVEN_BY_BUDGET` — same £ per inventory/duration; **uneven impressions** (higher CPM = fewer impressions)
- `EVEN_BY_IMPRESSIONS` — same impression count; **uneven £** (higher CPM = more spend)

The agent must **state which it chose and why**, so the trader can adjust. Example: "I've split evenly by impressions, which weights spend toward the 30s at its higher CPM."

**No API call** — this is agent-side logic. The resulting budgets feed into the `market_budgets` field at strategy creation.

---

### Step 4: Audiences

🔄 **CHANGED** — was Step 4 in v1.1.0 and optional. Now mandatory, suggestion-driven, and positioned after the budget split.

**What was in v1.1.0:**
- Browse/search audience sets, checkbox selection, Similar/Exact toggle

**What it is now:**

| Field | Type | Requirement | Change from v1.1.0 |
|---|---|---|---|
| **Audience options** | 3 profiles | **Required** | 🔄 **CHANGED from optional to mandatory.** Agent always generates narrow / balanced / wide |
| **Chosen option** | Select one | Required | ➕ **NEW.** Trader picks one of the three |
| **Matching mode** | Toggle | Required | ✅ Unchanged. Similar vs Exact |
| **Effective CPM** (per option) | Display | Read-only | ➕ **NEW.** Deal CPM + audience VCPM fee, shown per option so the trader sees the real cost |

**Constraints for CTV:**
- Amazon audiences **only apply to Amazon-owned inventory**. For Netflix/Disney, their own targeting applies
- ❌ Product audiences **not applicable** to CTV (removed)
- AMC audiences are **conditional** — only when the advertiser has prior campaign data
- **Nobody browses** — the agent uses `POST /api/audience-sets/suggest/` exclusively
- The audience set does **not** need to be created before forecasting — it's created later at strategy creation via a simplified CTV endpoint

**API calls at this step:** `POST /api/audience-sets/suggest/` → `GET /api/audience-sets/suggest/{id}/`

⚠️ **Open question:** the suggest endpoint's response shape. v1.1.0 assumed it returns `bundles.narrow/balanced/broad`. The real endpoint may return a flat list that we group ourselves. **Confirm against the real API.**

---

### Step 5: Targeting

➕ **ENTIRELY NEW** — did not exist in v1.1.0.

| Field | Type | Requirement |
|---|---|---|
| **Location** | Multi-select | Optional |
| **Instream position** | Select | Optional |
| **Content-category exclusions** | Multi-select | Optional |
| **Device type** | Multi-select | Optional |
| **Mobile environment** | Select | Optional |

**Critical design note from the client:** *"This targeting list frequently changes so it should be easy to add new targeting types."* — the implementation must be **config-driven**, not hard-coded. Adding a new targeting type should be a configuration change, not a code change.

**Not supported by VOW today** (future scope): genre exclusions, day-parting, language.

**API calls at this step:** `POST /api/contextual-targeting/{market}/products/`, `GET /api/strategies/locations/{market}/`

---

### Step 6: Predict Reach

🔄 **CHANGED** — was embedded in the original flow. Now a first-class step with the tier-based honesty rule.

| Field | Type | Requirement | Change from v1.1.0 |
|---|---|---|---|
| **Reach curve** | Chart | Read-only (Amazon only) | 🔄 **CHANGED.** Only available for Amazon-owned inventory. For 3P, **state honestly that reach is unavailable** |
| **Estimated impressions** | Number | Read-only | ✅ Unchanged |
| **Estimated unique reach** | Number | Read-only (Amazon only) | 🔄 **CHANGED.** Not available for Netflix/Disney |
| **Average frequency** | Number | Read-only (Amazon only) | 🔄 **CHANGED.** Not available for Netflix/Disney |
| **Indicative CPM** | Number | Read-only | ✅ Unchanged |

➕ **NEW — the honesty rule for 3P inventory:**
For Netflix/Disney, the agent shows: rate-card CPM and **derived impressions** (budget ÷ CPM × 1,000). It explicitly states that reach is unavailable and why. **Never invent a reach number.**

➕ **NEW — consequences:**
- The **repair loop** (too narrow → widen → re-forecast) applies **only to the Amazon portion**
- **Total reach cannot be summed** across providers (no cross-platform deduplication)

**Repair loop** (v1.1.0 §7.1 — ✅ concept correct, 🔄 mechanism updated):

| Was (v1.1.0) | Now |
|---|---|
| If `estimated_unique_reach == 0`, switch from Narrow to Balanced/Broad | If reach is insufficient, **extend the audience** (not necessarily switch profiles — could add segments within the chosen profile) |
| Also adjust base CPM bid upward | ✅ Still valid as Action 2 |
| Re-run forecast | ✅ Unchanged |

**API calls at this step:** `POST /api/audience-sets/reach-forecast/` (or the simplified CTV endpoint, name TBC)

---

### Step 7: Plan Approval

➕ **ENTIRELY NEW** — did not exist in v1.1.0.

*The client confirmed: approval gates the **plan**, before it is finalised. Not before launch. Optionally routes to a manager.*

| Field | Type | Requirement |
|---|---|---|
| **Approval status** | Enum | Required |
| **Approved by** | String (user) | Set on approval |
| **Approved at** | Timestamp | Set on approval |
| **Manager required** | Boolean | Configurable (possibly budget-threshold-based) |
| **Rejection reason** | Text | Required on reject |

**Values:** `PENDING` → `APPROVED` or `REJECTED`

**Implementation:** LangGraph `interrupt()`. The graph physically stops and persists state. It cannot proceed until a human sends approve or reject. The budget is locked at this moment — nothing launches that a person hasn't approved.

**On rejection:** the flow returns to Step 4 (audiences) so the trader can adjust the plan.

**No API call** — this is agent-internal. The approval is logged in the audit trail.

---

### Step 8: Create the Real Strategy

🔄 **CHANGED** — was "Summary & Create" (Step 6) in v1.1.0. Key change: create the **real** strategy, not a draft.

**What was in v1.1.0:**
- Summary view → `POST /api/strategies/` or `POST /api/strategies/draft/` → returns `status: "draft"`

**What it is now:**

| Field | Change |
|---|---|
| **Endpoint** | 🔄 `POST /api/strategies/` — **not** `/strategies/draft/`. Client: "don't need to create draft strategy; draft is just for the wizard creation" |
| **Audience set** | ➕ Created at this step via the simplified CTV endpoint (not before forecasting) |
| **All slots** | All filled slots from Steps 1–7 are assembled into the creation payload |

**API calls at this step:** `POST /api/strategies/`, audience-set creation via CTV endpoint

⚠️ **Open question:** what status does the created strategy land in? If it's still "draft" by default, activation via `set_status` remains a separate step. **Confirm with client.**

---

### Step 9: Upload Video Creative

🔄 **CHANGED** — was Step 5 "Creatives" in v1.1.0. Simplified to video only, moved to after plan approval, and duration check added.

**What was in v1.1.0:**
- Browse assets and pre-approved creatives, select from table, add click-through URL

**What it is now:**

| Field | Type | Requirement | Change from v1.1.0 |
|---|---|---|---|
| **Video file** | Upload (direct or URL) | Required | 🔄 **CHANGED.** For CTV, **always video**. No display creatives, no pre-approved selection, no responsive e-commerce |
| **Click-through URL** | URL | Required | ✅ Unchanged |
| **Duration** | Derived from file | Checked | ➕ **NEW.** Must match one of the durations in the approved plan |

➕ **NEW — Duration match check:**
If the uploaded video is 30s but the approved plan specified 15s deals, the economics change (different CPM → different impressions for the same budget). This triggers **re-approval** (return to Step 7 with the amended plan).

**Upload path:** `POST /api/assets/amz_assets/gen_upload_urls/` (get upload URLs) → `POST /api/assets/amz_assets/register/` (register the asset on Amazon)

❌ **REMOVED for CTV:** browse existing assets (`GET /api/assets/`), pre-approved creatives (`GET /api/creatives/`), responsive e-commerce (`POST /api/creatives/recs/`), third-party tags (`POST /api/creatives/third-party/`). These are valid for Display but not for CTV scope.

---

### Step 10: Platform Creative Approval

➕ **ENTIRELY NEW** — did not exist in v1.1.0.

| Field | Type | Requirement |
|---|---|---|
| **Amazon approval status** | Enum | Read-only |
| **Netflix approval status** | Enum | Read-only (if Netflix inventory) |
| **Disney approval status** | Enum | Read-only (if Disney inventory) |

**Values:** `PENDING` → `APPROVED` or `REJECTED`

Every video must pass the platform's content and technical review before it can run. Each platform reviews its own inventory independently. A plan can be fully approved and funded and still not launch until the creative clears.

**On rejection:** the agent reports the reason and asks for a replacement (return to Step 9).

⚠️ **Open question:** do Netflix/Disney review statuses surface inside VOW's API, or is that tracked externally? **Confirm with client.**

---

### Step 11: Tracking Setup

🔄 **MOVED** — ASIN validation was in Step 1 (strategy details) and ad-tag conversions were in Step 2 (goal/KPI). Both now sit here, after creative approval and before tracking is attached.

**What was in v1.1.0:**
- ASINs collected in Step 1 and validated via `POST /api/contextual-targeting/{market}/asin-validation/`
- Ad tag conversions selected in Step 2 via `GET /api/conversions/definitions/`

**What it is now:**

| Field | Type | Requirement | Change from v1.1.0 |
|---|---|---|---|
| **Sells on Amazon?** | Question | Asked here | 🔄 **MOVED** from Step 1 |
| **Product ASINs** | Textarea | Required if endemic | ✅ Validation unchanged: `POST /api/contextual-targeting/{market}/asin-validation/` |
| **Sells on own website?** | Question | Asked here | ➕ **NEW explicit question** |
| **Ad tag registered?** | Check | Required if yes | ➕ **NEW.** Check whether an ad tag is already registered. If not, show setup instructions — the tag must be installed before the campaign runs (tracking only records activity after it goes live) |
| **Ad tag conversions** | Multi-select | Required if ad tag exists | 🔄 **MOVED** from Step 2. Events: Page view, Add to cart, Checkout, Application. Via `GET /api/conversions/definitions/` |

**API calls at this step:** `POST /api/contextual-targeting/{market}/asin-validation/`, `GET /api/conversions/definitions/`

⚠️ **Open question (repeated from Step 1):** since `product_location` and `asin_numbers` are fields in `POST /strategies/` (called at Step 8), they may need to be collected before Step 8 and only the ad-tag check moves here. **Confirm with client.**

---

### Step 12: Credit Check

➕ **ENTIRELY NEW** — did not exist in v1.1.0.

Credit is checked **only at activation**, not during planning. Everything before this point is a costless plan.

| Field | Type | Requirement |
|---|---|---|
| **Account balance** | Number | Read-only |
| **Strategy budget** | Number | Read-only |
| **Sufficient** | Boolean | Derived (balance ≥ budget) |

If insufficient: prompt a top-up via `POST /api/credits/` or `POST /api/credits/stripe/`.

**API call:** `GET /api/credits/summary/`

---

### Step 13: Activate

➕ **ENTIRELY NEW** — did not exist in v1.1.0 (was implicit in "create strategy").

**The single spend action in the entire flow.** Everything before this was free.

**API call:** `POST /api/strategies/{id}/set_status/`

After activation, VOW's outbound sync creates the Campaigns and Ad Groups on Amazon DSP.

---

## 4. API Catalogue

🔄 **CHANGED** — original catalogue kept, with additions and removals marked.

| Operation | Method | Endpoint | Status |
|---|---|---|---|
| Check name uniqueness | `GET` | `/api/strategies/check_strategy_name_uniqueness/` | ✅ Unchanged |
| ASIN validation | `POST` | `/api/contextual-targeting/{market}/asin-validation/` | ✅ Unchanged |
| Product categories | `GET` | `/api/contextual-targeting/{market}/product-categories/` | ✅ Unchanged |
| Conversion definitions | `GET` | `/api/conversions/definitions/` | ✅ Unchanged |
| List deals | `GET` | `/api/deals/` | ✅ Unchanged |
| Deal filter properties | `GET` | `/api/deals/filter-properties/` | ✅ Unchanged |
| List audience sets | `GET` | `/api/audience-sets/` | ✅ Unchanged |
| Suggest audiences | `POST` | `/api/audience-sets/suggest/` | ✅ Unchanged |
| Audience reach forecast | `POST` | `/api/audience-sets/reach-forecast/` | ✅ Unchanged |
| Strategy reach forecast | `POST` | `/api/strategies/reach-forecast/` | ✅ Unchanged |
| List assets | `GET` | `/api/assets/` | ✅ Unchanged |
| List creatives | `GET` | `/api/creatives/` | ✅ Unchanged |
| Create strategy | `POST` | `/api/strategies/` | ✅ Unchanged |
| Read strategy | `GET` | `/api/strategies/{id}/` | ✅ Unchanged |
| **CTV rate card** | `GET` | `/api/rates/ctv/{market}/` | ➕ **NEW** |
| **Inventory sources** | `GET` | `/api/inventory-sources/` | ➕ **NEW** |
| **Activate strategy** | `POST` | `/api/strategies/{id}/set_status/` | ➕ **NEW** |
| **Credit summary** | `GET` | `/api/credits/summary/` | ➕ **NEW** |
| **Upload URLs** | `POST` | `/api/assets/amz_assets/gen_upload_urls/` | ➕ **NEW** |
| **Register asset** | `POST` | `/api/assets/amz_assets/register/` | ➕ **NEW** |
| **Locations** | `GET` | `/api/strategies/locations/{market}/` | ➕ **NEW** |
| Draft create | `POST` | `/api/strategies/draft/` | ❌ **REMOVED** — client: "draft is just for the wizard" |

---

## 5. Pydantic Data Models

🔄 **CHANGED** — original models kept where valid, extended and restructured.

```python
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, HttpUrl


# ==========================================
# ENUMS
# ==========================================

class ChannelTypeEnum(str, Enum):
    """✅ UNCHANGED"""
    DSP = "dsp"
    SPONSORED = "sponsored"

class GoalEnum(str, Enum):
    """🔄 CHANGED — kept all values, but for CTV M1 only AWARENESS is used"""
    AWARENESS = "AWARENESS"
    CONSIDERATION = "CONSIDERATION"  # future scope
    CONVERSION = "CONVERSION"        # future scope

class KPIEnum(str, Enum):
    """🔄 CHANGED — kept all values, but for CTV M1 only reach and frequency"""
    REACH = "reach"
    FREQUENCY = "frequency"
    CTR = "ctr"          # future scope
    CPC = "cpc"          # future scope
    CPA = "cpa"          # future scope
    CPDPV = "cpdpv"      # future scope

class ProductLocationEnum(str, Enum):
    """✅ UNCHANGED"""
    ON_AMAZON = "ON_AMAZON"
    NOT_SOLD_ON_AMAZON = "NOT_SOLD_ON_AMAZON"

class FormatEnum(str, Enum):
    """🔄 CHANGED — kept all values, but for CTV M1 only streaming_tv and prime_video"""
    DISPLAY = "display"              # future scope
    ONLINE_VIDEO = "online_video"    # future scope
    STREAMING_TV = "streaming_tv"
    PRIME_VIDEO = "prime_video"

class CurrencyEnum(str, Enum):
    """✅ UNCHANGED"""
    EUR = "EUR"
    GBP = "GBP"
    USD = "USD"

# ➕ NEW ENUMS

class DurationEnum(str, Enum):
    """➕ NEW — creative durations for CTV"""
    TEN = "10"
    FIFTEEN = "15"
    TWENTY = "20"
    THIRTY = "30"

class InventoryTierEnum(str, Enum):
    """➕ NEW — the three inventory tiers driving the flow's primary fork"""
    AMAZON_OWNED = "AMAZON_OWNED"
    THIRD_PARTY_PRECURATED = "THIRD_PARTY_PRECURATED"
    THIRD_PARTY_NEEDS_CURATION = "THIRD_PARTY_NEEDS_CURATION"

class ApprovalStatusEnum(str, Enum):
    """➕ NEW — for plan approval and creative approval"""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class BudgetSplitMethodEnum(str, Enum):
    """➕ NEW — how the budget is divided"""
    EVEN_BY_BUDGET = "EVEN_BY_BUDGET"
    EVEN_BY_IMPRESSIONS = "EVEN_BY_IMPRESSIONS"
    CUSTOM = "CUSTOM"

class AudienceProfileEnum(str, Enum):
    """➕ NEW — the three audience options"""
    NARROW = "NARROW"
    BALANCED = "BALANCED"
    WIDE = "WIDE"


# ==========================================
# COMPONENT SCHEMAS
# ==========================================

class DateRangeSchema(BaseModel):
    """✅ UNCHANGED"""
    lower: str = Field(..., description="ISO date YYYY-MM-DD")
    upper: str = Field(..., description="ISO date YYYY-MM-DD")
    bounds: str = Field("[)", description="Interval boundary notation")

class MarketBudgetBidSchema(BaseModel):
    """✅ UNCHANGED"""
    market: str = Field(..., description="ISO country code")
    budget: str = Field(..., description="Total budget decimal string")
    base_bid: str = Field(..., description="Base CPM bid decimal string")

class SelectedDealSchema(BaseModel):
    """🔄 CHANGED — added inventory_tier, genre, ad_lengths, provider"""
    deal_id: str = Field(..., description="External deal ID e.g. EXT7P75718S8MNR")
    name: str = Field(..., description="Deal name")
    cpm: str = Field(..., description="Fixed or floor CPM price")
    inventory_tier: InventoryTierEnum = Field(..., description="Which tier this deal belongs to")  # ➕ NEW
    provider: str = Field(..., description="e.g. Prime Video, Netflix, Disney+")  # ➕ NEW
    genre: Optional[str] = Field(None, description="Genre if genre-specific deal")  # ➕ NEW
    ad_lengths: list[str] = Field(default_factory=list, description="Supported durations")  # ➕ NEW
    deal_type: str = Field(..., description="PG, Preferred, or Private Auction")  # ➕ NEW

class SelectedAudienceSetSchema(BaseModel):
    """🔄 CHANGED — added profile and effective_cpm"""
    audience_set_id: str = Field(..., description="Audience set UUID")
    name: str = Field(..., description="Audience set name")
    vcpm_fee: str = Field(..., description="VCPM fee decimal")
    profile: AudienceProfileEnum = Field(..., description="Narrow, Balanced, or Wide")  # ➕ NEW
    effective_cpm: Optional[str] = Field(None, description="Deal CPM + audience VCPM")  # ➕ NEW
    estimated_reach: Optional[int] = Field(None, description="If Amazon inventory")  # ➕ NEW

class SelectedCreativeSchema(BaseModel):
    """🔄 CHANGED — added duration_seconds for the match check"""
    asset_id: str = Field(..., description="Registered asset ID")
    click_through_url: HttpUrl = Field(..., description="Landing page URL")
    duration_seconds: int = Field(..., description="Video length in seconds")  # ➕ NEW
    upload_method: str = Field("direct", description="direct or url")  # ➕ NEW

# ➕ NEW SCHEMAS

class BudgetSplitSchema(BaseModel):
    """➕ NEW — how budget is divided across inventories and durations"""
    method: BudgetSplitMethodEnum = Field(..., description="Even by budget, even by impressions, or custom")
    by_inventory: list[dict] = Field(..., description="[{provider, budget, impressions_estimate}]")
    by_duration: list[dict] = Field(..., description="[{duration, budget, cpm, impressions_estimate}]")

class CurationRequirementsSchema(BaseModel):
    """➕ NEW — captured for 3P-needs-curation inventory (e.g. Disney+)"""
    provider: str = Field(..., description="e.g. Disney+")
    genres: list[str] = Field(default_factory=list)
    durations: list[str] = Field(default_factory=list)
    targeting_preferences: Optional[str] = None
    budget: str = Field(..., description="Allocated budget for this provider")
    flight_dates: DateRangeSchema = Field(...)

class TargetingSchema(BaseModel):
    """➕ NEW — CTV targeting options (config-driven, extensible)"""
    locations: list[str] = Field(default_factory=list)
    instream_positions: list[str] = Field(default_factory=list)
    content_category_exclusions: list[str] = Field(default_factory=list)
    device_types: list[str] = Field(default_factory=list)
    mobile_environments: list[str] = Field(default_factory=list)

class ForecastResultSchema(BaseModel):
    """🔄 CHANGED — added availability flag for the honesty rule"""
    is_available: bool = Field(..., description="False for Netflix/Disney — no reach data")  # ➕ NEW
    estimated_impressions: Optional[int] = None
    estimated_unique_reach: Optional[int] = Field(None, description="Only for Amazon inventory")
    average_frequency: Optional[float] = Field(None, description="Only for Amazon inventory")
    indicative_cpm: Optional[str] = None
    reach_curve: Optional[list[dict]] = Field(None, description="[{budget, reach}] — Amazon only")

class TrackingSetupSchema(BaseModel):
    """➕ NEW — tracking prerequisites collected at Step 11"""
    sells_on_amazon: bool = Field(...)
    validated_asins: list[dict] = Field(default_factory=list, description="[{asin, title, brand}]")
    sells_on_own_site: bool = Field(...)
    ad_tag_registered: Optional[bool] = None
    ad_tag_conversions: list[str] = Field(default_factory=list, description="Selected conversion events")


# ==========================================
# FULL STRATEGY SCHEMA
# ==========================================

class FullStrategySchema(BaseModel):
    """🔄 CHANGED — restructured from wizard steps to semantic grouping"""

    # --- Identity ---
    id: Optional[str] = Field(None, description="System-assigned strategy ID")
    advertiser_id: str = Field(..., description="Parent advertiser UUID")
    channel_type: ChannelTypeEnum = ChannelTypeEnum.DSP

    # --- Basics (Step 1) ---
    name: str = Field(..., description="Unique strategy name")
    flight_dates: DateRangeSchema = Field(...)
    markets: list[str] = Field(..., description="ISO country codes")
    primary_currency: CurrencyEnum = Field(CurrencyEnum.GBP)
    durations: list[DurationEnum] = Field(..., description="Creative durations")  # ➕ NEW
    formats: list[FormatEnum] = Field(...)
    goal: GoalEnum = Field(GoalEnum.AWARENESS, description="Fixed for CTV")  # 🔄 CHANGED default
    kpi_target_type: KPIEnum = Field(...)
    product_categories: list[int] = Field(default_factory=list)
    product_location: ProductLocationEnum = Field(...)
    market_budgets: list[MarketBudgetBidSchema] = Field(...)
    frequency_cap: Optional[int] = Field(None, description="Optional weekly cap")  # ➕ NEW
    budget_cap: Optional[str] = Field(None, description="Optional budget cap")  # ➕ NEW

    # --- Inventory (Step 2) ---
    selected_deals: list[SelectedDealSchema] = Field(...)  # 🔄 CHANGED — enriched schema
    curation_requirements: list[CurationRequirementsSchema] = Field(default_factory=list)  # ➕ NEW

    # --- Budget Split (Step 3) ---
    budget_split: Optional[BudgetSplitSchema] = None  # ➕ NEW

    # --- Audiences (Step 4) ---
    audience_options: list[SelectedAudienceSetSchema] = Field(default_factory=list)  # 🔄 CHANGED — now carries all three
    chosen_audience_profile: Optional[AudienceProfileEnum] = None  # ➕ NEW
    matching_mode: str = Field("Exact", description="Similar or Exact")  # ✅ UNCHANGED

    # --- Targeting (Step 5) ---
    targeting: Optional[TargetingSchema] = None  # ➕ NEW

    # --- Forecast (Step 6) ---
    forecast: Optional[ForecastResultSchema] = None  # 🔄 CHANGED — enriched with availability

    # --- Approval (Step 7) ---
    approval_status: Optional[ApprovalStatusEnum] = None  # ➕ NEW
    approved_by: Optional[str] = None  # ➕ NEW
    approved_at: Optional[str] = None  # ➕ NEW

    # --- Creative (Step 9) ---
    selected_creatives: list[SelectedCreativeSchema] = Field(default_factory=list)  # 🔄 CHANGED — enriched
    creative_duration_match: Optional[bool] = None  # ➕ NEW
    creative_approval_status: Optional[ApprovalStatusEnum] = None  # ➕ NEW

    # --- Tracking (Step 11) ---
    tracking: Optional[TrackingSetupSchema] = None  # ➕ NEW
    product_asins: list[str] = Field(default_factory=list)  # 🔄 MOVED from Step 1

    # --- Activation (Steps 12-13) ---
    credit_sufficient: Optional[bool] = None  # ➕ NEW
    status: str = Field("created", description="Strategy status")  # 🔄 CHANGED from "draft"
    is_syncing: bool = Field(False)


# ==========================================
# LANGGRAPH PLANNING STATE
# ==========================================

# 🔄 CHANGED — restructured from wizard-step-based to semantic field names

# WAS (v1.1.0):
#   class PlanningAgentState(TypedDict):
#       messages: List[Dict[str, Any]]
#       advertiser_id: str
#       current_step: int  # 0 to 5
#       strategy_id: Optional[str]
#       step1_details: Optional[Dict[str, Any]]
#       step2_goal_kpi_bid: Optional[Dict[str, Any]]
#       step3_deals: Optional[Dict[str, Any]]
#       step4_audiences: Optional[Dict[str, Any]]
#       step5_creatives: Optional[Dict[str, Any]]
#       forecast_results: Optional[Dict[str, Any]]
#       validation_errors: List[str]
#       is_complete: bool

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
    current_stage: str                              # ➕ NEW — for the adaptive canvas
    current_artifact_id: Optional[str]              # ➕ NEW — for the adaptive canvas

    # --- Basics ---
    strategy_name: Optional[str]
    flight_dates: Optional[dict]
    markets: list[str]
    durations: list[str]                            # ➕ NEW
    primary_currency: str
    goal: str                                       # fixed: AWARENESS for CTV
    kpi: str                                        # reach or frequency
    market_budgets: list[dict]
    product_location: Optional[str]
    frequency_cap: Optional[int]                    # ➕ NEW
    budget_cap: Optional[str]                       # ➕ NEW

    # --- Inventory ---
    inventory_tier: Optional[str]                   # ➕ NEW — which tier fork we're on
    selected_deals: list[dict]
    curation_requirements: list[dict]               # ➕ NEW

    # --- Budget split ---
    budget_split: Optional[dict]                    # ➕ NEW

    # --- Audiences ---
    audience_options: list[dict]                    # the three profiles
    chosen_audience: Optional[dict]                 # which one the trader picked

    # --- Targeting ---
    targeting: Optional[dict]                       # ➕ NEW

    # --- Forecast ---
    forecast: Optional[dict]                        # reach/impressions/CPM (with availability flag)

    # --- Approval ---
    approval_status: Optional[str]                  # ➕ NEW — PENDING/APPROVED/REJECTED
    approved_by: Optional[str]                      # ➕ NEW
    approved_at: Optional[str]                      # ➕ NEW

    # --- Creative ---
    creative_id: Optional[str]
    creative_duration_match: Optional[bool]         # ➕ NEW
    creative_approval_status: Optional[str]         # ➕ NEW

    # --- Tracking ---
    tracking_setup: Optional[dict]                  # ➕ NEW
    product_asins: list[str]                        # 🔄 MOVED

    # --- Activation ---
    credit_sufficient: Optional[bool]               # ➕ NEW
    strategy_id: Optional[str]
    strategy_status: Optional[str]

    # --- Errors ---
    validation_errors: list[str]
```

---

## 6. State Machine

🔄 **CHANGED — needs complete rebuild.** The original was a linear pipe. The confirmed flow has branches, loops, and interrupts.

**The confirmed state machine (v5):**

```
START
  → extract_fields (slot-filling from brief)
  → select_inventory (CTV, three-tier fork)
    → [if 3P needs curation] capture_curation_requirements
  → propose_budget_split (across inventories + durations)
  → suggest_audiences (3 options via pgvector; mandatory)
  → apply_targeting (optional, configurable)
  → predict_reach
    → [if Amazon] real forecast + reach curve
    → [if 3P] CPM + derived impressions only (honest)
    → [if too narrow] REPAIR: extend audience → re-predict (loop)
  → present_plan (on the strategy card)
  → ⏸ PLAN APPROVAL (interrupt — optionally a manager)
    → [if rejected] return to suggest_audiences
  → create_strategy (POST /strategies/ — the real one, not draft)
  → upload_creative (video, gen_upload_urls + register)
    → [if duration mismatch] amend plan → RE-APPROVE (loop back)
  → platform_creative_approval (Amazon / Netflix / Disney review)
    → [if rejected] return to upload_creative
  → tracking_setup (ASINs + ad tag check)
  → credit_check (GET /credits/summary/)
    → [if insufficient] prompt top-up (loop)
  → activate (POST /strategies/{id}/set_status/ — the single spend action)
  → DONE
```

**Q&A side path:** at any point, the trader can ask a pricing/availability question ("what's the CPM for Netflix 30s?"). The agent answers from the rate card and resumes.

---

## 7. Brief Parsing & Edge Cases

### 7.1 Entity Normalisation

✅ **UNCHANGED** — the original examples are correct. **Additions:**

| Input | Extraction | Status |
|---|---|---|
| `August 2026` | `flight_dates: {lower: "2026-08-01", upper: "2026-08-31"}` | ✅ Original |
| `UK` | `markets: ["GB"]`, `primary_currency: "GBP"` | ✅ Original |
| `£10,000` | `market_budgets: [{market: "GB", budget: "10000.00"}]` | ✅ Original |
| `education website` | `product_location: "NOT_SOLD_ON_AMAZON"` | ✅ Original |
| `30 seconds` | `durations: ["30"]` | ➕ **NEW** |
| `UK and France` | `markets: ["GB", "FR"]` | ➕ **NEW** |
| `sports drink` | Consider genre-specific deals (Sports) | ➕ **NEW** |
| `Prime and Netflix` | Multiple inventory tiers | ➕ **NEW** |

### 7.2 Validation Failure Protocols

✅ **UNCHANGED** — duplicate name, invalid ASIN, past dates protocols all correct.

### 7.3 Repair Loop

🔄 **CHANGED** — concept correct, mechanism updated (see Step 6 above). Only applies to Amazon-owned inventory.

➕ **NEW — "Did I understand correctly?" confirmation.** After extracting fields from a brief, the agent immediately shows what it understood so the trader can correct before proceeding. This is the single most important trust mechanism in the product.

---

## 8. Summary of all changes

| Category | Count | Items |
|---|---|---|
| ✅ Unchanged | ~15 | Core principles, product attribution, deal types, date validation, name uniqueness, currency, most API endpoints, brief parsing examples |
| 🔄 Changed | ~12 | Step order, goal scoped to Awareness, KPI scoped to reach/frequency, deals enriched with tier, audiences mandatory + renamed Wide, forecast with availability flag, state restructured, creative simplified to video |
| ➕ New | ~15 | Durations, inventory tiers, budget split, targeting, plan approval, creative duration check, platform creative approval, tracking setup (moved), credit check, activation, curation capture, effective CPM, adaptive-canvas fields |
| ❌ Removed | ~5 | Draft endpoint, product audiences, non-CTV formats (scoped out), non-awareness KPIs (scoped out), canary-check |

---

**This document is for client verification.** Once confirmed, it becomes the shared contract that Wajahat (state + graph), Vishal (registry), and Basil (adaptive canvas) build against.
