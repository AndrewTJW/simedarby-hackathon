import pytest

from ffsa.config import ConfigError, load_config, split_provenance


def test_base_config_loads_with_placeholders_allowed():
    cfg, prov = load_config(allow_placeholders=True)
    assert cfg.thresholds.car_float_m == 0.30
    assert "damage.per_car_rm" in prov["_placeholders_in_use"]


def test_placeholders_fail_loudly():
    with pytest.raises(ConfigError, match="per_car_rm"):
        load_config()


def test_override_of_placeholder_clears_it():
    cfg, prov = load_config(overrides={"damage.per_car_rm": 1.0})
    assert prov["_placeholders_in_use"] == []


def test_every_leaf_needs_provenance():
    with pytest.raises(ConfigError):
        split_provenance({"a": {"value": 1}})


def test_unknown_override_rejected():
    with pytest.raises(ConfigError):
        load_config(overrides={"sensors.nope": 1}, allow_placeholders=True)
