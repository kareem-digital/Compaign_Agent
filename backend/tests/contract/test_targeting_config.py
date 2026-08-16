"""The config-driven targeting requirement, expressed as tests.

`VOW_Strategy_Schema_v2.md` section 3 step 5 quotes the client directly: *"This
targeting list frequently changes so it should be easy to add new targeting
types"*, and requires the implementation be *"config-driven, not hard-coded"*.

`test_a_new_targeting_type_needs_no_python` is that requirement. It adds a sixth
type to a copy of the declaration and pushes it through ingest, snapshot and
validator without touching a line of application code. If a future change makes
targeting types into model fields again, that test is what fails.

The rest guard the cost of the trade-off. Declaring types in JSON means mypy
cannot check a key, so a typo becomes a runtime miss - these checks are what
replaces the type checker.
"""

import json

import pytest

from app.config import get_settings
from app.core.exceptions import ConfigurationError
from app.knowledge.registry.ingestion import RegistryIngestor
from app.knowledge.registry.targeting import (
    _PACKAGED_CONFIG,
    REQUIRED_KEYS,
    load_config_from,
    load_targeting_types,
    to_strategy_payload,
)
from app.knowledge.registry.validate import StepwiseCTVValidator
from app.tools.mcp import VowTools, mock_data
from app.tools.mcp.mock import MockMCPClient

# The five section 5 lines 601-607 gives `TargetingSchema`. A declared type must
# map onto one of these to be submittable.
STRATEGY_SCHEMA_FIELDS = {
    "locations",
    "instream_positions",
    "content_category_exclusions",
    "device_types",
    "mobile_environments",
}


# --- the shipped declaration -------------------------------------------------


def test_the_packaged_config_is_valid() -> None:
    """It ships with the package, so a malformed file is a broken release."""
    config = load_config_from(_PACKAGED_CONFIG)
    assert config.config_version == 1
    assert len(config.types) == 5


def test_the_five_types_the_schema_mandates_are_present() -> None:
    keys = {spec.key for spec in load_targeting_types().types}
    assert set(REQUIRED_KEYS) <= keys


def test_every_declared_source_names_a_real_tool() -> None:
    """A typo in `source.tool` would degrade every market silently.

    This is the check that replaces the type checker mypy cannot run over JSON.
    """
    known = set(VowTools.all())
    for spec in load_targeting_types().types:
        assert spec.source.tool in known, f"{spec.key} names an unknown tool"


def test_every_declared_type_maps_onto_a_vow_strategy_field() -> None:
    """Offerable is free; submittable needs a VOW field to put the value in."""
    for spec in load_targeting_types().types:
        assert spec.strategy_field in STRATEGY_SCHEMA_FIELDS, spec.key


def test_market_scoped_sources_template_the_market() -> None:
    """`{market}` is the only templating supported, and it has to be applied."""
    config = load_targeting_types().by_key()
    resolved = config["location"].source.resolved_args("GB")

    assert resolved["market"] == "GB"


# --- the requirement itself --------------------------------------------------


@pytest.fixture
def declared_config(tmp_path, monkeypatch):
    """Point the registry at a declaration written by the test.

    Goes through `registry_targeting_config_path` rather than patching the loader,
    because that setting is the documented way to change the targeting list
    without a release - so the test exercises the mechanism it is describing.
    Both caches are cleared on the way in and out, since `get_settings` and
    `load_targeting_types` are process-wide.
    """

    def _apply(declaration: dict):
        path = tmp_path / "targeting_types.json"
        path.write_text(json.dumps(declaration))

        monkeypatch.setenv("REGISTRY_TARGETING_CONFIG_PATH", str(path))
        get_settings.cache_clear()
        load_targeting_types.cache_clear()
        return path

    yield _apply

    monkeypatch.undo()
    get_settings.cache_clear()
    load_targeting_types.cache_clear()


async def test_a_new_targeting_type_needs_no_python(declared_config, monkeypatch) -> None:
    """Section 3 step 5's requirement, end to end.

    A sixth type is declared, and the mock server is taught to serve values for
    it. Nothing in app/ changes, and the type reaches the snapshot and validates
    like the other five. If targeting types ever become model fields again, this
    is what fails.
    """
    declaration = json.loads(_PACKAGED_CONFIG.read_text())
    declaration["types"].append(
        {
            "key": "audio_volume",
            "label": "Audio volume",
            "cardinality": "single",
            "required": False,
            "strategy_field": None,
            "source": {
                "tool": VowTools.TARGETING_OPTIONS,
                "args": {"type": "audio_volume", "market": "{market}"},
                "values_path": "results",
                "id_field": "id",
                "label_field": "label",
            },
        }
    )
    declared_config(declaration)

    monkeypatch.setitem(
        mock_data.TARGETING_OPTIONS,
        "audio_volume",
        [{"id": "MUTED", "label": "Muted"}, {"id": "AUDIBLE", "label": "Audible"}],
    )

    mcp = MockMCPClient(advertiser_id="adv-config")
    snapshot = await RegistryIngestor(mcp).sync(markets=["GB"])
    options = snapshot.data.targeting("GB").options

    assert "audio_volume" in options
    assert options["audio_volume"].label == "Audio volume"
    assert options["audio_volume"].cardinality == "single"
    assert options["audio_volume"].value_ids() == {"MUTED", "AUDIBLE"}

    validator = StepwiseCTVValidator(snapshot, mcp)
    assert validator.validate_targeting("GB", {"audio_volume": ["MUTED"]}).is_valid
    assert validator.validate_targeting("GB", {"audio_volume": ["LOUD"]}).blocks


async def test_a_declared_type_the_server_cannot_serve_degrades(declared_config) -> None:
    """Declared but unserved is the day-one state of any new type.

    It drops out of the market rather than failing the sync, because targeting is
    optional and a type nobody can supply values for is not an outage.
    """
    declaration = json.loads(_PACKAGED_CONFIG.read_text())
    declaration["types"].append(
        {
            "key": "weather",
            "label": "Weather",
            "cardinality": "multi",
            "required": False,
            "strategy_field": None,
            "source": {
                "tool": VowTools.TARGETING_OPTIONS,
                "args": {"type": "weather", "market": "{market}"},
                "values_path": "results",
                "id_field": "id",
                "label_field": "label",
            },
        }
    )
    declared_config(declaration)

    mcp = MockMCPClient(advertiser_id="adv-config")
    snapshot = await RegistryIngestor(mcp).sync(markets=["GB"])

    assert "weather" not in snapshot.data.targeting("GB").options
    assert len(snapshot.data.targeting("GB").options) == 5


# --- the submit boundary -----------------------------------------------------


def test_selections_map_onto_the_strategy_payload_fields() -> None:
    payload = to_strategy_payload(
        {"device_type": ["CONNECTED_TV"], "instream_position": ["PRE_ROLL"]}
    )

    assert payload == {
        "device_types": ["CONNECTED_TV"],
        "instream_positions": ["PRE_ROLL"],
    }


def test_a_type_with_no_vow_field_is_dropped_and_warned_about(caplog) -> None:
    """Collected but unsubmittable is a legitimate state, and worth saying.

    Whoever added the type needs to know VOW has nowhere to put the value, rather
    than discovering it from a strategy that launched without the targeting.
    """
    with caplog.at_level("WARNING"):
        payload = to_strategy_payload({"day_parting": ["EVENING"]})

    assert payload == {}
    assert any(r.message == "registry.targeting_unmappable" for r in caplog.records)


# --- malformed declarations --------------------------------------------------


def test_a_config_missing_a_mandated_type_is_rejected(tmp_path) -> None:
    """Missing one of the five is a config error, not a degraded source."""
    declaration = json.loads(_PACKAGED_CONFIG.read_text())
    declaration["types"] = [t for t in declaration["types"] if t["key"] != "device_type"]

    path = tmp_path / "incomplete.json"
    path.write_text(json.dumps(declaration))

    with pytest.raises(ConfigurationError, match="missing"):
        load_config_from(path)


def test_duplicate_keys_are_rejected(tmp_path) -> None:
    """Two declarations of one key means the second silently wins."""
    declaration = json.loads(_PACKAGED_CONFIG.read_text())
    declaration["types"].append(dict(declaration["types"][0]))

    path = tmp_path / "duplicated.json"
    path.write_text(json.dumps(declaration))

    with pytest.raises(ConfigurationError, match="duplicate"):
        load_config_from(path)


def test_an_unparseable_config_fails_with_the_path_named(tmp_path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json")

    with pytest.raises(ConfigurationError, match="not valid JSON"):
        load_config_from(path)


def test_an_unknown_field_in_a_declaration_is_rejected(tmp_path) -> None:
    """extra="forbid", so a typo'd key name fails rather than being ignored."""
    declaration = json.loads(_PACKAGED_CONFIG.read_text())
    declaration["types"][0]["cardinallity"] = "multi"

    path = tmp_path / "typo.json"
    path.write_text(json.dumps(declaration))

    with pytest.raises(ConfigurationError, match="malformed"):
        load_config_from(path)
