"""Node 2.5 (Step 3) - Kareem Agent (Targeting Agent).

Strict Single Responsibility:
Kareem Agent is solely responsible for collecting, normalizing, and validating
Targeting (Audience profiles, Demographics, Interests, Locations, Devices, and Brand Safety).
It does NOT manage budgets, inventory pricing, or campaign creation.

Implements all targeting dimensions per Strategy Schema v4.0 (Section 6.8 & 6.10)
and the 6-group UI structure from res.png:
1. Lifestyle, In-market & Interest
2. Age cohorts (18-24, 25-34, 35-44, 45-54, 55+)
3. Gender (Female, Male, All)
4. Household Income (HHI) tiers
5. Household Composition (Families with kids, Couples, etc.)
6. Device Types (CONNECTED_TV required for CTV, Fire TV, Consoles)
7. Geographic Location Engine (Search, Postcodes, Custom Radius + Replacement Rule)
8. Brand Safety & Exclusions (Content ratings, Sensitive categories)
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.agent.gates import say
from app.agent.state import PlanningAgentState
from app.core.logging import kv
from app.knowledge import reference
from app.knowledge.registry import AdvertiserRegistry
from app.tools.mcp import MCPClient

logger = logging.getLogger(__name__)

STAGE = "targeting"


# --- Parsing & Normalization Helpers ---


def _latest_text(state: PlanningAgentState) -> str:
    """Retrieve full combined conversation text to capture all expressed targeting preferences."""
    texts = []
    for msg in state.get("messages") or []:
        role = getattr(msg, "type", None) or (msg.get("role") if isinstance(msg, dict) else None)
        if role in ("human", "user"):
            content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else "")
            if content:
                texts.append(str(content))
    return " ".join(texts)


def _parse_demographics(text: str) -> dict[str, Any]:
    """Parse age cohorts, gender, income, household type, and interest tags."""
    lowered = text.lower()

    # 1. Ages
    age_groups = []
    if re.search(r"\b18\s*[-–to]\s*24\b", lowered):
        age_groups.append("18-24")
    if re.search(r"\b(25\s*[-–to]\s*34|25\s*[-–to]\s*35)\b", lowered):
        age_groups.append("25-34")
    if re.search(r"\b35\s*[-–to]\s*44\b", lowered):
        age_groups.append("35-44")
    if re.search(r"\b45\s*[-–to]\s*54\b", lowered):
        age_groups.append("45-54")
    if re.search(r"\b(55\+|\bover 55\b|55\s*[-–to]\s*64)\b", lowered):
        age_groups.append("55+")
    if re.search(r"\b(young adults?|under 35)\b", lowered):
        for a in ["18-24", "25-34"]:
            if a not in age_groups:
                age_groups.append(a)
    if re.search(r"\badults?\s*25\s*[-–to]\s*54\b", lowered):
        for a in ["25-34", "35-44", "45-54"]:
            if a not in age_groups:
                age_groups.append(a)

    if not age_groups:
        age_groups = ["25-54", "All Adults"]

    # 2. Gender
    genders = []
    if re.search(r"\b(women|females?|girls?)\b", lowered) and not re.search(r"\b(men|males?)\b", lowered):
        genders = ["Female"]
    elif re.search(r"\b(men|males?|boys?)\b", lowered) and not re.search(r"\b(women|females?)\b", lowered):
        genders = ["Male"]
    else:
        genders = ["Female", "Male"]

    # 3. Income (HHI)
    household_income = []
    if re.search(r"\b(high income|affluent|top\s*(tier|10%|25%)|80k\+)\b", lowered):
        household_income = ["£55-80k", "£80k+"]
    elif re.search(r"\b35\s*[-–to]\s*55k\b", lowered):
        household_income = ["£35-55k"]
    else:
        household_income = ["£55-80k", "£80k+"]

    # 4. Household Type
    household_type = []
    if re.search(r"\b(families|parents?|with children|with kids)\b", lowered):
        household_type = ["Families with children"]
    elif re.search(r"\b(couples?|no kids|without children)\b", lowered):
        household_type = ["Couples"]
    else:
        household_type = ["Families with children", "Couples"]

    # 5. Lifestyle & Interests
    interests = []
    if re.search(r"\b(runners?|running|athletes?|fitness|sports?)\b", lowered):
        interests.append("Runners & Fitness")
    if re.search(r"\b(green|environment|eco[- ]friendly|sustainability)\b", lowered):
        interests.append("Green / Environmentally Conscious")
    if re.search(r"\b(health|wellness|sugar[- ]reduction)\b", lowered):
        interests.append("Health & Wellness")
    if re.search(r"\b(organic|natural food|grocery)\b", lowered):
        interests.append("Organic & Natural Food Buyers")
    if re.search(r"\b(tech|technology|gadgets?)\b", lowered):
        interests.append("Tech Enthusiasts")
    if re.search(r"\b(gaming|gamers?|entertainment)\b", lowered):
        interests.append("Entertainment & Gaming")

    if not interests:
        interests = ["Lifestyle & Entertainment Enthusiasts"]

    return {
        "age_groups": age_groups,
        "genders": genders,
        "household_income": household_income,
        "household_type": household_type,
        "interests": interests,
    }


def _parse_locations_and_geos(text: str, market: str) -> tuple[list[dict], list[str], dict | None, dict | None]:
    """Parse city search, postal codes, and radius proximity, enforcing the Replacement Rule.

    Returns:
        (geo_targets, location_include, custom_radius, postcode_targeting)
    """
    lowered = text.lower()
    geo_targets: list[dict] = []
    location_include: list[str] = []
    custom_radius: dict | None = None
    postcode_targeting: dict | None = None

    # 1. Custom Radius Check (e.g. "within 20 miles of London", "15 km around Paris")
    radius_match = re.search(
        r"(?:within\s+)?(\d+(?:\.\d+)?)\s*(miles?|km|kilometers?)\s+(?:of|around|radius of)\s+([a-zA-Z\s]+?)(?:[.,;]|$|\s+on|\s+with)",
        text,
        re.I,
    )
    if radius_match:
        dist_str, unit_str, center_str = radius_match.groups()
        dist = float(dist_str)
        unit = "miles" if "mile" in unit_str.lower() else "km"
        center = center_str.strip().title()
        custom_radius = {
            "address": center,
            "radius": dist,
            "unit": unit,
            "amz_id": f"RAD-{center[:3].upper()}-{int(dist)}{unit[0]}",
        }
        geo_targets.append({"id": custom_radius["amz_id"], "name": f"{center} ({dist} {unit} radius)"})
        location_include.append(custom_radius["amz_id"])

    # 2. Postal Code Check (e.g. "SW1A 1AA", "SW1A", "EC1", "Zip 90210")
    # Avoid bare 5-digit numbers that represent budgets (e.g. 15000 or 50000)
    uk_pcs = re.findall(r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}|(?:SW|EC|WC|SE|NW|NE|W|E|N|M|B|G|EH)\d[A-Z\d]?)\b", text, re.I)
    us_zips = re.findall(r"(?:zip|postal|postcode|area)\s*(?:code)?\s*(\d{5})\b", text, re.I)
    
    valid_pcs = [p.strip().upper() for p in uk_pcs + us_zips if not re.match(r"^\d{4}$", p)]
    if valid_pcs:
        postcode_targeting = {
            "submitted": valid_pcs,
            "resolved": [{"submitted": pc, "amz_id": f"POST-{pc.replace(' ', '')}", "category": "POSTAL_CODE"} for pc in valid_pcs],
            "ambiguous": [],
            "unresolved": [],
        }
        for res in postcode_targeting["resolved"]:
            geo_targets.append({"id": res["amz_id"], "name": f"Postcode {res['submitted']}"})
            location_include.append(res["amz_id"])

    # 3. Known Metros / Regions (e.g. London, Manchester, New York, Berlin, Paris)
    city_catalog: dict[str, dict[str, str]] = {
        "GB": {
            "london": "GB-LND:Greater London",
            "west midlands": "GB-WMD:West Midlands",
            "manchester": "GB-MAN:Greater Manchester",
            "birmingham": "GB-WMD:West Midlands",
            "scotland": "GB-SCT:Scotland",
        },
        "US": {
            "new york": "US-501:New York DMA",
            "los angeles": "US-803:Los Angeles DMA",
            "chicago": "US-602:Chicago DMA",
            "california": "US-CA:California",
            "texas": "US-TX:Texas",
        },
        "DE": {
            "berlin": "DE-BE:Berlin",
            "bavaria": "DE-BY:Bavaria",
            "munich": "DE-BY:Bavaria",
        },
        "FR": {
            "paris": "FR-IDF:Ile-de-France",
            "ile-de-france": "FR-IDF:Ile-de-France",
            "lyon": "FR-ARA:Auvergne-Rhone-Alpes",
        },
    }

    market_cities = city_catalog.get(market, city_catalog["GB"])
    for city_key, val in market_cities.items():
        if re.search(rf"\b{re.escape(city_key)}\b", lowered):
            loc_id, loc_name = val.split(":", 1)
            if loc_id not in location_include:
                location_include.append(loc_id)
                geo_targets.append({"id": loc_id, "name": loc_name})

    # Replacement Rule: If explicit locations/radius/postcodes were provided, they REPLACE the country default
    if not location_include:
        default_id = f"{market}-NAT"
        default_name = f"{market} Nationwide"
        location_include = [default_id]
        geo_targets = [{"id": default_id, "name": default_name}]

    return geo_targets, location_include, custom_radius, postcode_targeting


def _parse_devices_and_exclusions(text: str) -> tuple[list[str], list[str], list[str], list[str]]:
    """Parse device types, mobile OS, brand safety rating exclusions, and instream positions."""
    lowered = text.lower()

    # Device Types: CONNECTED_TV is required for CTV
    device_types = ["CONNECTED_TV"]
    if re.search(r"\b(fire tv|streaming stick|set[- ]top|roku|apple tv)\b", lowered):
        device_types.append("STREAMING_STICK")
    if re.search(r"\b(console|playstation|xbox|gaming)\b", lowered):
        device_types.append("GAMES_CONSOLE")
    if re.search(r"\b(desktop|laptop|pc|mac)\b", lowered):
        device_types.append("DESKTOP")
    if re.search(r"\b(mobile|smartphones?|phones?)\b", lowered):
        device_types.append("MOBILE")

    # Mobile OS Guardrail: only valid if MOBILE is in device_types
    mobile_os: list[str] = []
    if "MOBILE" in device_types:
        if re.search(r"\bios\b|\biphone\b|\bipad\b|\bapple\b", lowered):
            mobile_os.append("IOS")
        if re.search(r"\bandroid\b|\bgoogle\b|\bsamsung\b", lowered):
            mobile_os.append("ANDROID")

    # Exclusions
    exclusions: list[str] = []
    if re.search(r"\b(exclude news|no news|politics|political)\b", lowered):
        exclusions.append("NEWS_POLITICS")
    if re.search(r"\b(sensitive|brand safe|brand safety)\b", lowered):
        exclusions.append("SENSITIVE")
    if re.search(r"\b(violence|terrorism)\b", lowered):
        exclusions.append("VIOLENCE")
    if re.search(r"\b(gambling|betting)\b", lowered):
        exclusions.append("GAMBLING")

    # Instream Positions
    instream = ["PRE_ROLL", "MID_ROLL"]
    if re.search(r"\bpre[- ]roll only\b", lowered):
        instream = ["PRE_ROLL"]
    elif re.search(r"\bmid[- ]roll only\b", lowered):
        instream = ["MID_ROLL"]

    return device_types, mobile_os, exclusions, instream


# --- Kareem Agent Node Factory ---


def make_collect_targeting(registry: AdvertiserRegistry, mcp: MCPClient | None = None):
    """Factory creating the Kareem Agent (Targeting Agent) node."""

    async def collect_targeting(state: PlanningAgentState) -> dict[str, Any]:
        markets = state.get("markets") or []
        market = markets[0] if markets else "GB"

        full_text = _latest_text(state)
        lowered = full_text.lower()

        # Check for explicit "keep broad / default" intent
        keep_broad_match = bool(
            re.search(r"\b(keep\s*(it\s*)?broad|keep\s*default|default\s*targeting|no\s*targeting|standard\s*targeting|skip\s*targeting)\b", lowered)
        )

        has_explicit_targeting = bool(
            re.search(r"\b(18-24|25-34|35-44|45-54|55\+|women|men|female|male|affluent|high income|london|manchester|birmingham|paris|berlin|new york|postcode|radius|exclude|brand safe|games console|fire tv)\b", lowered)
        )

        if keep_broad_match and not has_explicit_targeting:
            geo_targets = [{"id": f"{market}-NAT", "name": f"{market} Nationwide"}]
            loc_include = [f"{market}-NAT"]
            device_types = ["CONNECTED_TV"]
            demographics = {
                "age_groups": ["All Adults (18+)"],
                "genders": ["All"],
                "household_income": ["All Tiers"],
                "household_type": ["All Households"],
                "interests": ["Broad Market Reach"],
            }
            message = "Understood — keeping default baseline targeting (Nationwide CTV, broad audience)."
            spoken = say(state, STAGE, message)

            return {
                "current_stage": STAGE,
                "stage_cursor": STAGE,
                "targeting_confirmed": True,
                "geo_targets": geo_targets,
                "location_include": loc_include,
                "location_exclude": list(state.get("location_exclude") or []),
                "custom_radius": None,
                "postcode_targeting": None,
                "demographics": demographics,
                "device_types": device_types,
                "mobile_operating_systems": [],
                "content_rating_exclusions": [],
                "instream_positions": ["PRE_ROLL", "MID_ROLL"],
                **spoken,
            }

        # 1. Parse Demographics & Interests (Cards 1-5 in res.png)
        demographics = _parse_demographics(full_text)

        # 2. Parse Locations, Postcodes & Radius (Card 7 + Replacement Rule)
        geo_targets, loc_include, radius, postcodes = _parse_locations_and_geos(full_text, market)

        # 3. Parse Device Types & Brand Safety Exclusions (Card 6 & Exclusions)
        device_types, mobile_os, exclusions, instream = _parse_devices_and_exclusions(full_text)

        # 4. Count total active groups and values for confirmation summary
        active_groups = 0
        total_values = 0

        if demographics.get("interests"):
            active_groups += 1
            total_values += len(demographics["interests"])
        if demographics.get("age_groups"):
            active_groups += 1
            total_values += len(demographics["age_groups"])
        if demographics.get("genders"):
            active_groups += 1
            total_values += len(demographics["genders"])
        if demographics.get("household_income"):
            active_groups += 1
            total_values += len(demographics["household_income"])
        if demographics.get("household_type"):
            active_groups += 1
            total_values += len(demographics["household_type"])
        if device_types:
            active_groups += 1
            total_values += len(device_types)

        loc_summary = ", ".join(g["name"] for g in geo_targets)
        age_summary = ", ".join(demographics["age_groups"])
        gender_summary = ", ".join(demographics["genders"])

        message = (
            f"Targeting configured: {active_groups} groups, {total_values} values selected.\n"
            f"- Locations: {loc_summary}\n"
            f"- Demographics: {gender_summary}, Ages {age_summary}\n"
            f"- Devices: {', '.join(device_types)}"
        )

        logger.info(
            "stage.targeting",
            extra=kv(
                market=market,
                geo_targets=geo_targets,
                age_groups=demographics["age_groups"],
                genders=demographics["genders"],
                device_types=device_types,
                radius=bool(radius),
                postcodes=bool(postcodes),
            ),
        )

        is_custom = bool(
            (geo_targets and geo_targets != [{"id": f"{market}-NAT", "name": f"{market} Nationwide"}])
            or radius
            or postcodes
            or (demographics.get("age_groups") and demographics["age_groups"] != ["25-54", "All Adults"])
            or (demographics.get("genders") and demographics["genders"] != ["Female", "Male"])
            or (demographics.get("interests") and demographics["interests"] != ["Lifestyle & Entertainment Enthusiasts"])
        )

        spoken = say(state, STAGE, message) if is_custom else {}

        return {
            "current_stage": STAGE,
            "stage_cursor": STAGE,
            "targeting_confirmed": True,
            "geo_targets": geo_targets,
            "location_include": loc_include,
            "location_exclude": list(state.get("location_exclude") or []),
            "custom_radius": radius,
            "postcode_targeting": postcodes,
            "demographics": demographics,
            "device_types": device_types,
            "mobile_operating_systems": mobile_os,
            "content_rating_exclusions": exclusions,
            "instream_positions": instream,
            **spoken,
        }

    return collect_targeting
