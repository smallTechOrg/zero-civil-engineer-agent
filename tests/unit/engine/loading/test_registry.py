"""Pluggable LoadingStandard registry — standards resolve by name so DFC 32.5t can
slot in later without touching the engine (irs-engine.md business rule)."""

import pytest

from engine.loading import (
    LoadingStandard,
    get_loading_standard,
    register_loading_standard,
)


def test_get_loading_standard_returns_the_25t_2008_singleton():
    std = get_loading_standard("25t-2008")

    assert isinstance(std, LoadingStandard)
    assert std.name == "25t-2008"
    assert get_loading_standard("25t-2008") is std


def test_unknown_standard_name_raises_value_error_naming_known_standards():
    with pytest.raises(ValueError, match="25t-2008"):
        get_loading_standard("no-such-standard")


def test_abstract_loading_standard_cannot_be_instantiated():
    with pytest.raises(TypeError):
        LoadingStandard()


class _Dfc325Stub(LoadingStandard):
    """Minimal future-standard stand-in proving the layer is pluggable."""

    name = "test-dfc-32.5t-stub"

    def eudl_bm_kn(self, loaded_length_m: float) -> float:
        return 1.0

    def eudl_shear_kn(self, loaded_length_m: float) -> float:
        return 1.0

    def eudl_bm_table(self):
        return ()

    def eudl_shear_table(self):
        return ()

    def cda(self, loaded_length_m: float, cushion_m: float = 0.0) -> float:
        return 0.0

    @property
    def citation(self) -> str:
        return "test stub — not a real standard"


def test_a_new_standard_registers_and_resolves_without_touching_the_engine():
    from engine.loading import base

    stub = _Dfc325Stub()
    register_loading_standard(stub)
    try:
        assert get_loading_standard(stub.name) is stub
    finally:
        base._REGISTRY.pop(stub.name, None)


def test_registering_a_different_instance_under_an_existing_name_raises():
    class Impostor(_Dfc325Stub):
        name = "25t-2008"

    with pytest.raises(ValueError, match="already registered"):
        register_loading_standard(Impostor())
