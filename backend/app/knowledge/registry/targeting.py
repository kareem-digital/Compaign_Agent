"""Targeting types, declared in data rather than in code.

`VOW_Strategy_Schema_v2.md` section 3 step 5 carries an explicit instruction from
the client: *"This targeting list frequently changes so it should be easy to add
new targeting types"* - and adds that the implementation *"must be config-driven,
not hard-coded"*. So the five known types live in `data/targeting_types.json`,
each declaring which tool supplies its values and how to read them. The ingestor
iterates the declaration; nothing here knows what "device type" means.

Adding a type the server already serves is one JSON entry and no Python.
`tests/contract/test_targeting_config.py` proves that by pushing a synthetic
sixth type through ingest, snapshot and validator.

**The boundary is deliberately two-sided.** What the agent may *offer* a trader
is free to change, because it is only data. What it may *submit* is not: section
5's `TargetingSchema` has five named fields, and a value can only be sent if a
VOW field exists to hold it. `strategy_field` in the declaration is that mapping,
and `to_strategy_payload` is the one place it is applied. A new type becomes
offerable with a config change, and becomes submittable when VOW grows a field
for it. Anything else would be pretending.

Honest cost of the trade: mypy cannot check a targeting key, so a typo in the
JSON is a runtime miss rather than a type error. Mitigated by validating the
shipped file against `TargetingTypeSpec` in a contract test, and by the `KEY_*`
constants below for code that references a known type by name.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.core.exceptions import ConfigurationError
from app.core.logging import kv

logger = logging.getLogger(__name__)

_PACKAGED_CONFIG = Path(__file__).parent / "data" / "targeting_types.json"

# For code that names a known type. Dynamic code uses strings; these exist so a
# node or a test does not carry a bare literal that a rename would miss.
KEY_LOCATION = "location"
KEY_INSTREAM_POSITION = "instream_position"
KEY_CONTENT_CATEGORY_EXCLUSION = "content_category_exclusion"
KEY_DEVICE_TYPE = "device_type"
KEY_MOBILE_ENVIRONMENT = "mobile_environment"

# The five section 3 step 5 mandates. A config missing one of these is a config
# error, not a degraded source - the flow's targeting step would be incomplete.
REQUIRED_KEYS = (
    KEY_LOCATION,
    KEY_INSTREAM_POSITION,
    KEY_CONTENT_CATEGORY_EXCLUSION,
    KEY_DEVICE_TYPE,
    KEY_MOBILE_ENVIRONMENT,
)


class TargetingSourceSpec(BaseModel):
    """Where one targeting type's values come from.

    `args` values may contain `{market}`, substituted at fetch time - that is the
    only templating supported, on purpose. A declaration format that can express
    arbitrary computation stops being configuration.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool: str
    args: dict[str, str] = Field(default_factory=dict)
    values_path: str = "results"
    id_field: str = "id"
    label_field: str = "label"

    def resolved_args(self, market: str) -> dict[str, str]:
        return {key: value.replace("{market}", market) for key, value in self.args.items()}


class TargetingTypeSpec(BaseModel):
    """One declared targeting type."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    label: str
    cardinality: Literal["single", "multi"] = "multi"
    required: bool = False
    # The section 5 `TargetingSchema` field this maps onto. None means the type
    # can be offered and collected but not yet submitted, because VOW has no
    # field for it. That is a legitimate state, and better stated than hidden.
    strategy_field: str | None = None
    source: TargetingSourceSpec


class TargetingTypeConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    config_version: int
    types: tuple[TargetingTypeSpec, ...]

    def by_key(self) -> dict[str, TargetingTypeSpec]:
        return {spec.key: spec for spec in self.types}


def load_config_from(path: Path) -> TargetingTypeConfig:
    """Parse and validate a targeting declaration. Raises on anything wrong.

    Kept separate from the cached `load_targeting_types` so tests can load an
    alternative file without fighting the cache.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigurationError(f"Cannot read targeting config at {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Targeting config at {path} is not valid JSON: {exc}") from exc

    try:
        config = TargetingTypeConfig.model_validate(raw)
    except Exception as exc:
        raise ConfigurationError(f"Targeting config at {path} is malformed: {exc}") from exc

    keys = [spec.key for spec in config.types]
    duplicates = {key for key in keys if keys.count(key) > 1}
    if duplicates:
        raise ConfigurationError(
            f"Targeting config at {path} declares duplicate keys: {sorted(duplicates)}"
        )

    missing = [key for key in REQUIRED_KEYS if key not in keys]
    if missing:
        raise ConfigurationError(
            f"Targeting config at {path} is missing the types schema v2 section 3 "
            f"step 5 requires: {missing}"
        )

    return config


@lru_cache
def load_targeting_types() -> TargetingTypeConfig:
    """The active targeting declaration.

    Cached because it is read once per fetch and never changes within a process.
    `registry_targeting_config_path` overrides the packaged file so ops can
    hot-patch the list without a release.
    """
    settings = get_settings()
    path = Path(settings.registry_targeting_config_path or _PACKAGED_CONFIG)

    config = load_config_from(path)
    logger.info(
        "registry.targeting_config",
        extra=kv(
            path=str(path),
            config_version=config.config_version,
            types=[spec.key for spec in config.types],
        ),
    )
    return config


def to_strategy_payload(selections: dict[str, list[str]]) -> dict[str, list[str]]:
    """Map the trader's selections onto section 5's `TargetingSchema` fields.

    The one place the config-driven world meets VOW's fixed payload. A selected
    type with no `strategy_field` is dropped with a warning rather than silently:
    it means the agent collected something the platform has nowhere to put, and
    whoever added the type needs to know.
    """
    config = load_targeting_types().by_key()
    payload: dict[str, list[str]] = {}
    unmappable: list[str] = []

    for key, values in selections.items():
        spec = config.get(key)
        if spec is None or not spec.strategy_field:
            unmappable.append(key)
            continue
        payload[spec.strategy_field] = list(values)

    if unmappable:
        logger.warning(
            "registry.targeting_unmappable",
            extra=kv(
                keys=sorted(unmappable),
                reason="declared as offerable but no VOW strategy field to submit it in",
            ),
        )

    return payload
