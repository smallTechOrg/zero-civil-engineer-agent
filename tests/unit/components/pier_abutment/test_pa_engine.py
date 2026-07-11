"""Sizing + analysis + checks engine — pier, abutment, and the under-design case."""

import pytest

from components.pier_abutment.analysis import analyse_substructure, compute_stability
from components.pier_abutment.checks import run_substructure_checks
from components.pier_abutment.params import PierAbutmentParams
from components.pier_abutment.sizing import (
    FOS_OVERTURNING_MIN,
    FOS_SLIDING_MIN,
    size_substructure,
)

PIER = PierAbutmentParams(
    pier_height_m=9.0, superstructure_reaction_kn=5000.0,
    safe_bearing_capacity_kn_m2=300.0, component_kind="pier",
)
ABUTMENT = PierAbutmentParams(
    pier_height_m=9.0, superstructure_reaction_kn=5000.0,
    safe_bearing_capacity_kn_m2=300.0, component_kind="abutment",
)


def _run(params):
    g = size_substructure(params).geometry
    a = analyse_substructure(params, g)
    c = run_substructure_checks(a, g, params)
    return g, a, c


@pytest.mark.parametrize("params", [PIER, ABUTMENT], ids=["pier", "abutment"])
def test_auto_sized_substructure_passes_its_own_checks(params):
    g, a, c = _run(params)
    # An auto-sized substructure is check-governed: every row PASSes.
    assert all(row.status == "PASS" for row in c.checks), [
        (r.kind, r.status) for r in c.checks
    ]
    assert a.fos_overturning >= FOS_OVERTURNING_MIN
    assert a.fos_sliding >= FOS_SLIDING_MIN
    assert a.max_base_pressure_kn_m2 <= params.safe_bearing_capacity_kn_m2 + 1e-6
    assert a.min_base_pressure_kn_m2 >= -1e-6
    assert a.pier_direct_stress_n_mm2 <= a.permissible_direct_stress_n_mm2
    # The footing is wider than the pier in both directions.
    assert g.footing_length_mm >= g.pier_width_mm
    assert g.footing_width_mm >= g.pier_length_mm


def test_abutment_adds_earth_pressure_and_surcharge_a_pier_does_not():
    _gp, ap, _cp = _run(PIER)
    _ga, aa, _ca = _run(ABUTMENT)
    # A pier carries only the longitudinal (braking) force horizontally.
    assert ap.earth_thrust_kn == 0.0
    assert ap.surcharge_thrust_kn == 0.0
    assert ap.retained_height_m == 0.0
    # An abutment adds Rankine active earth pressure + a track surcharge.
    assert aa.earth_thrust_kn > 0.0
    assert aa.surcharge_thrust_kn > 0.0
    assert aa.ka == pytest.approx(1.0 / 3.0, rel=1e-3)  # phi 30 deg -> Ka = 1/3
    assert aa.total_horizontal_kn > ap.total_horizontal_kn


def test_check_rows_reference_recorded_trail_steps():
    _g, _a, c = _run(PIER)
    step_ids = {s.step_id for s in c.trail}
    assert step_ids, "the checks trail must record steps"
    for row in c.checks:
        assert row.trail_ref in step_ids, f"{row.kind} references missing step {row.trail_ref}"
        assert row.trail_ref.startswith("K")


def test_analysis_trail_and_stability_core_agree():
    g = size_substructure(ABUTMENT).geometry
    a = analyse_substructure(ABUTMENT, g)
    core = compute_stability(ABUTMENT, g)
    # The rehydratable analysis model equals the pure numeric core (within rounding).
    assert a.fos_overturning == pytest.approx(core.fos_overturning, rel=1e-3)
    assert a.max_base_pressure_kn_m2 == pytest.approx(core.max_base_pressure_kn_m2, rel=1e-3)
    assert a.trail and all(s.step_id.startswith("A") for s in a.trail)


def test_under_designed_footing_fails_bearing_and_overturning():
    # A heavy reaction on weak soil with a deliberately small footing override —
    # the overrides are never grown, so the checks FAIL (the under-design case).
    under = PierAbutmentParams(
        pier_height_m=9.0, superstructure_reaction_kn=8000.0,
        safe_bearing_capacity_kn_m2=200.0,
        footing_length_mm=2600.0, footing_width_mm=2600.0,
    )
    g, a, c = _run(under)
    statuses = {row.kind: row.status for row in c.checks}
    assert statuses["bearing"] == "FAIL"
    assert statuses["overturning"] == "FAIL"
    assert a.max_base_pressure_kn_m2 > under.safe_bearing_capacity_kn_m2
    # The sizing surfaces the under-design as a warning.
    assert any("smaller than the auto-sized" in w for w in size_substructure(under).warnings)


def test_weak_soil_auto_grows_a_larger_footing():
    weak = PierAbutmentParams(
        pier_height_m=8.0, superstructure_reaction_kn=4000.0, safe_bearing_capacity_kn_m2=120.0
    )
    strong = PierAbutmentParams(
        pier_height_m=8.0, superstructure_reaction_kn=4000.0, safe_bearing_capacity_kn_m2=400.0
    )
    gw = size_substructure(weak).geometry
    gs = size_substructure(strong).geometry
    # Weaker soil demands a wider spread footing to keep p_max within the SBC.
    assert gw.footing_length_mm > gs.footing_length_mm
    aw = analyse_substructure(weak, gw)
    assert aw.max_base_pressure_kn_m2 <= weak.safe_bearing_capacity_kn_m2 + 1e-6
