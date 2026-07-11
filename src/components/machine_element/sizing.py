"""Deterministic proportioning of the machine element.

Mirroring the platform's check-governed philosophy, the element is sized so an
auto-sized design passes its own checks:

* **shaft** — the governing diameter is the larger of the static combined-stress
  demand (d from tau = 16 Te/(pi d^3) <= tau_perm) and the rotating-shaft fatigue
  demand (the Soderberg diameter at the required fatigue FoS), rounded up to a
  preferred step; the journals, shoulder fillet and keyway follow standard
  proportions.
* **welded_joint** — the fillet leg is sized from the circular-weld torsional
  strength, floored at a minimum practical leg.

User overrides are never grown: a deliberately thin shaft diameter (or weld leg)
flows through to a FAIL row and a return-for-revision verdict (the under-design
demo case). Pure deterministic Python — no LLM, no I/O.
"""

from __future__ import annotations

from typing import NamedTuple

from pydantic import BaseModel

from components.base import Assumption, CalcStep
from components.machine_element._engine_common import (
    CITATION_PROPORTIONING,
    CITATION_USER_INPUT,
    DIAMETER_STEP_MM,
    MAX_WELD_SIZE_MM,
    MIN_SHAFT_DIAMETER_MM,
    MIN_WELD_SIZE_MM,
    REQUIRED_FATIGUE_FOS,
    TRANSVERSE_LOAD_FACTOR,
    Trail,
    corrected_endurance_mpa,
    equivalent_twisting_moment_nmm,
    fatigue_diameter_mm,
    material,
    permissible_shear_mpa,
    round_up,
    solid_shaft_diameter_mm,
    tangential_force_n,
    torque_nmm,
    weld_size_for_torque_mm,
    weld_throat_mm,
)
from components.machine_element.params import (
    MachineElementGeometry,
    MachineElementParams,
)


class MachineElementSizingResult(BaseModel):
    """Everything `size_element` returns — geometry plus its full provenance."""

    geometry: MachineElementGeometry
    assumptions: list[Assumption]
    trail: list[CalcStep]
    warnings: list[str]


class _SizedShaft(NamedTuple):
    diameter_mm: float
    diameter_auto_mm: float
    diameter_static_mm: float
    diameter_fatigue_mm: float
    step_diameter_mm: float
    step_length_mm: float
    length_mm: float
    fillet_radius_mm: float
    keyway_width_mm: float
    keyway_depth_mm: float


class _SizedWeld(NamedTuple):
    weld_size_mm: float
    weld_size_auto_mm: float
    weld_throat_mm: float
    hub_diameter_mm: float
    plate_thickness_mm: float
    length_mm: float


def size_element(params: MachineElementParams) -> MachineElementSizingResult:
    """Proportion the element and return the geometry with its full provenance."""
    if params.element_kind == "welded_joint":
        return _size_weld(params)
    return _size_shaft(params)


# --------------------------------------------------------------------------- shaft
def _proportion_shaft(params: MachineElementParams) -> _SizedShaft:
    mat = material(params.material_grade)
    perm = permissible_shear_mpa(mat.yield_mpa, params.required_factor_of_safety)
    endurance = corrected_endurance_mpa(mat.ultimate_mpa)

    torque = torque_nmm(params.power_kw, params.speed_rpm)
    f_t = tangential_force_n(torque, params.mounting_pcd_mm)
    moment = TRANSVERSE_LOAD_FACTOR * f_t * params.overhang_mm
    te = equivalent_twisting_moment_nmm(
        params.bending_shock_factor, moment, params.torsion_shock_factor, torque
    )

    d_static = solid_shaft_diameter_mm(te, perm)
    d_fatigue = fatigue_diameter_mm(
        moment_nmm=moment, torque_value_nmm=torque, endurance_mpa=endurance,
        yield_mpa=mat.yield_mpa, required_fatigue_fos=REQUIRED_FATIGUE_FOS,
    )
    d_auto = round_up(max(d_static, d_fatigue, MIN_SHAFT_DIAMETER_MM), DIAMETER_STEP_MM)
    diameter = params.diameter_mm if params.diameter_mm is not None else d_auto

    step_diameter = max(MIN_SHAFT_DIAMETER_MM, round_up(0.85 * diameter, DIAMETER_STEP_MM) - DIAMETER_STEP_MM)
    if step_diameter >= diameter:
        step_diameter = max(MIN_SHAFT_DIAMETER_MM, diameter - DIAMETER_STEP_MM)
    step_length = round_up(1.5 * diameter, 5.0)
    central_length = round_up(max(3.0 * diameter, params.overhang_mm), 5.0)
    length = central_length + 2.0 * step_length
    fillet_radius = max(1.0, round(0.08 * diameter))
    if params.has_keyway:
        keyway_width = max(2.0, round(0.25 * diameter))
        keyway_depth = max(1.0, round(keyway_width / 2.0))
    else:
        keyway_width = keyway_depth = 0.0

    return _SizedShaft(
        diameter_mm=diameter, diameter_auto_mm=d_auto,
        diameter_static_mm=d_static, diameter_fatigue_mm=d_fatigue,
        step_diameter_mm=step_diameter, step_length_mm=step_length, length_mm=length,
        fillet_radius_mm=fillet_radius, keyway_width_mm=keyway_width, keyway_depth_mm=keyway_depth,
    )


def _size_shaft(params: MachineElementParams) -> MachineElementSizingResult:
    s = _proportion_shaft(params)
    trail = Trail("S")
    assumptions: list[Assumption] = []
    warnings: list[str] = []

    trail.record(
        description="Transmitted power (design requirement)",
        formula="P = power_kw at N = speed_rpm",
        inputs={"power_kw": params.power_kw, "speed_rpm": params.speed_rpm},
        value=params.power_kw, unit="kW", citation=CITATION_USER_INPUT,
    )
    trail.record(
        description="Shaft diameter — static combined-stress demand",
        formula="d_static = (16 Te / (pi tau_perm))^(1/3)",
        inputs={"required_fos": params.required_factor_of_safety},
        value=round(s.diameter_static_mm, 2), unit="mm", citation=CITATION_PROPORTIONING,
    )
    trail.record(
        description="Shaft diameter — rotating-shaft fatigue demand (Soderberg)",
        formula="d_fatigue from 1/n = sigma_a/sigma_e' + sqrt(3) tau_m/fy",
        inputs={"required_fatigue_fos": params.required_factor_of_safety},
        value=round(s.diameter_fatigue_mm, 2), unit="mm", citation=CITATION_PROPORTIONING,
    )
    if params.diameter_mm is None:
        trail.record(
            description="Governing shaft diameter — auto-sized",
            formula="d = ceil5(max(d_static, d_fatigue, d_min))",
            inputs={"d_static_mm": round(s.diameter_static_mm, 2), "d_fatigue_mm": round(s.diameter_fatigue_mm, 2)},
            value=round(s.diameter_mm, 1), unit="mm", citation=CITATION_PROPORTIONING,
        )
    else:
        trail.record(
            description=f"Governing shaft diameter — user override (auto-size reference {s.diameter_auto_mm:g} mm)",
            formula="d = user override",
            inputs={"override_mm": params.diameter_mm, "auto_sized_mm": round(s.diameter_auto_mm, 1)},
            value=round(s.diameter_mm, 1), unit="mm", citation=CITATION_USER_INPUT,
        )
    trail.record(
        description="Journal (stepped) diameter",
        formula="d_journal ~ 0.85 d (bounded)",
        inputs={"d_mm": s.diameter_mm},
        value=round(s.step_diameter_mm, 1), unit="mm", citation=CITATION_PROPORTIONING,
    )
    trail.record(
        description="Overall shaft length",
        formula="L = central + 2 x journal length",
        inputs={"central_mm": round(s.length_mm - 2 * s.step_length_mm, 1), "journal_mm": s.step_length_mm},
        value=round(s.length_mm, 1), unit="mm", citation=CITATION_PROPORTIONING,
    )
    trail.record(
        description="Shoulder fillet radius (stress-concentration feature)",
        formula="r ~ 0.08 d",
        inputs={"d_mm": s.diameter_mm},
        value=round(s.fillet_radius_mm, 1), unit="mm", citation=CITATION_PROPORTIONING,
    )
    if params.has_keyway:
        trail.record(
            description="Keyway (keyseat) proportions",
            formula="width ~ d/4, depth ~ width/2",
            inputs={"d_mm": s.diameter_mm},
            value=round(s.keyway_width_mm, 1), unit="mm", citation=CITATION_PROPORTIONING,
        )

    geometry = MachineElementGeometry(
        element_kind="shaft",
        diameter_mm=s.diameter_mm, length_mm=s.length_mm,
        step_diameter_mm=s.step_diameter_mm, step_length_mm=s.step_length_mm,
        fillet_radius_mm=s.fillet_radius_mm,
        keyway_width_mm=s.keyway_width_mm, keyway_depth_mm=s.keyway_depth_mm,
        hub_diameter_mm=0.0, weld_size_mm=0.0, weld_throat_mm=0.0, plate_thickness_mm=0.0,
    )

    if params.diameter_mm is None:
        assumptions.append(_auto_assumption("diameter_mm", "shaft diameter", s.diameter_auto_mm))
    elif params.diameter_mm < s.diameter_auto_mm:
        warnings.append(
            f"Shaft diameter override {params.diameter_mm:g} mm is smaller than the auto-sized "
            f"{s.diameter_auto_mm:g} mm (strength/fatigue-governed) — possible under-design; the "
            "checks will verify it."
        )
    assumptions.append(Assumption(
        field="stepped_shaft_proportions", value="journals ~0.85 d, fillet ~0.08 d",
        source="engine_default",
        note=("Journal diameters, fillet radius, keyway and lengths follow standard stepped-shaft "
              "proportions — a layout assumption; detailed bearing/coupling design beyond this POC scope."),
    ))
    return MachineElementSizingResult(
        geometry=geometry, assumptions=assumptions, trail=trail.steps, warnings=warnings
    )


# --------------------------------------------------------------------------- welded joint
def _proportion_weld(params: MachineElementParams) -> _SizedWeld:
    mat = material(params.material_grade)
    perm = permissible_shear_mpa(mat.yield_mpa, params.required_factor_of_safety)
    torque = torque_nmm(params.power_kw, params.speed_rpm)

    s_strength = weld_size_for_torque_mm(torque, params.hub_diameter_mm, perm)
    s_auto = min(MAX_WELD_SIZE_MM, round_up(max(s_strength, MIN_WELD_SIZE_MM), 1.0))
    size = params.weld_size_mm if params.weld_size_mm is not None else s_auto

    plate_thickness = round_up(max(1.4 * size, 6.0), 1.0)
    length = round_up(1.8 * params.hub_diameter_mm, 10.0)
    return _SizedWeld(
        weld_size_mm=size, weld_size_auto_mm=s_auto, weld_throat_mm=weld_throat_mm(size),
        hub_diameter_mm=params.hub_diameter_mm, plate_thickness_mm=plate_thickness, length_mm=length,
    )


def _size_weld(params: MachineElementParams) -> MachineElementSizingResult:
    s = _proportion_weld(params)
    trail = Trail("S")
    assumptions: list[Assumption] = []
    warnings: list[str] = []

    trail.record(
        description="Transmitted power (design requirement)",
        formula="P = power_kw at N = speed_rpm",
        inputs={"power_kw": params.power_kw, "speed_rpm": params.speed_rpm},
        value=params.power_kw, unit="kW", citation=CITATION_USER_INPUT,
    )
    trail.record(
        description="Welded hub diameter (design requirement / preset)",
        formula="D = hub_diameter_mm",
        inputs={"hub_diameter_mm": params.hub_diameter_mm},
        value=round(s.hub_diameter_mm, 1), unit="mm", citation=CITATION_USER_INPUT,
    )
    if params.weld_size_mm is None:
        trail.record(
            description="Fillet-weld leg size — auto-sized",
            formula="s = ceil1(max(T/(0.707 (pi D^2/2) tau_perm), s_min))",
            inputs={"required_fos": params.required_factor_of_safety, "D_mm": s.hub_diameter_mm},
            value=round(s.weld_size_mm, 1), unit="mm", citation=CITATION_PROPORTIONING,
        )
    else:
        trail.record(
            description=f"Fillet-weld leg size — user override (auto-size reference {s.weld_size_auto_mm:g} mm)",
            formula="s = user override",
            inputs={"override_mm": params.weld_size_mm, "auto_sized_mm": round(s.weld_size_auto_mm, 1)},
            value=round(s.weld_size_mm, 1), unit="mm", citation=CITATION_USER_INPUT,
        )
    trail.record(
        description="Fillet-weld effective throat",
        formula="t = 0.707 s",
        inputs={"s_mm": s.weld_size_mm},
        value=round(s.weld_throat_mm, 2), unit="mm", citation=CITATION_PROPORTIONING,
    )
    trail.record(
        description="Backing-plate thickness",
        formula="t_plate = ceil1(max(1.4 s, 6 mm))",
        inputs={"s_mm": s.weld_size_mm},
        value=round(s.plate_thickness_mm, 1), unit="mm", citation=CITATION_PROPORTIONING,
    )

    geometry = MachineElementGeometry(
        element_kind="welded_joint",
        diameter_mm=0.0, length_mm=s.length_mm,
        step_diameter_mm=0.0, step_length_mm=0.0, fillet_radius_mm=0.0,
        keyway_width_mm=0.0, keyway_depth_mm=0.0,
        hub_diameter_mm=s.hub_diameter_mm, weld_size_mm=s.weld_size_mm,
        weld_throat_mm=s.weld_throat_mm, plate_thickness_mm=s.plate_thickness_mm,
    )

    if params.weld_size_mm is None:
        assumptions.append(_auto_assumption("weld_size_mm", "fillet-weld leg size", s.weld_size_auto_mm))
    elif params.weld_size_mm < s.weld_size_auto_mm:
        warnings.append(
            f"Fillet-weld leg override {params.weld_size_mm:g} mm is smaller than the auto-sized "
            f"{s.weld_size_auto_mm:g} mm (strength-governed) — possible under-design; the checks "
            "will verify it."
        )
    assumptions.append(Assumption(
        field="weld_plate_proportions", value="plate ~1.4 s, plate size ~1.8 D",
        source="engine_default",
        note=("Backing-plate thickness and size follow standard fillet-weld detailing proportions "
              "— a layout assumption; connection edge distances beyond this POC scope."),
    ))
    return MachineElementSizingResult(
        geometry=geometry, assumptions=assumptions, trail=trail.steps, warnings=warnings
    )


def _auto_assumption(field: str, label: str, value: float) -> Assumption:
    return Assumption(
        field=field, value=round(value, 2), source="engine_default",
        note=f"Auto-sized {label} = {value:g} mm — {CITATION_PROPORTIONING}",
    )
