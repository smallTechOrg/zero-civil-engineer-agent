"""Calc-sheet composer — the clause-cited `calc_sheet.json` artefact.

Reuses the culvert calc-sheet JSON shape so the existing frontend CalcSheet
renderer works unchanged:

    {"sections": [{"id", "title", "lines": [{"description", "value", "unit",
     "citation", "trail_ref", "status"}]}], "assumptions": [...],
     "warnings": [...], "trail": [{"step_id", "description", "formula",
     "inputs", "value", "unit", "citation"}]}

The sizing ('S'), analysis ('A') and checks ('K') trail segments carry disjoint
id namespaces, so merging them into one drill-down trail needs no re-keying.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from components.base import Assumption, CalcStep, CheckResult, coerce
from components.retaining_wall.params import RetainingWallGeometry, RetainingWallParams

CALC_SHEET_FILENAME = "calc_sheet.json"

SECTION_TITLES = {
    "design_basis": "Design Basis & Proportioning",
    "earth_pressure": "Earth Pressure & Loading",
    "stability": "Stability (Overturning / Sliding / Bearing)",
    "section_checks": "RCC Section Design (IS 456 + IRS CBC)",
}
CITATION_PARAMETER = "User design requirement / preset default (see the assumptions block)"

# Analysis-trail descriptions that belong to the Earth Pressure section (by prefix).
_EARTH_PRESSURE_PREFIXES = (
    "Earth pressure coefficient",
    "Equivalent live-load surcharge",
    "Active earth thrust",
    "Surcharge thrust",
    "Design bending moment at the stem",
    "Design shear at the stem",
)


def _line(description, value, unit, citation, trail_ref, status=None) -> dict:
    return {
        "description": description,
        "value": value,
        "unit": unit,
        "citation": citation,
        "trail_ref": trail_ref,
        "status": status,
    }


def _step_line(step: CalcStep) -> dict:
    return _line(step.description, step.value, step.unit, step.citation, step.step_id)


def _is_earth_pressure(step: CalcStep) -> bool:
    return any(step.description.startswith(p) for p in _EARTH_PRESSURE_PREFIXES)


def compose_calc_sheet(
    *,
    trail: Sequence[Sequence[CalcStep]],
    checks: Sequence[CheckResult],
    assumptions: Sequence[Assumption],
    warnings: Sequence[str],
    params: RetainingWallParams,
    geometry: RetainingWallGeometry,
    out_dir: Path,
) -> Path:
    """Compose and write `calc_sheet.json`; returns the written file's Path."""
    segments = [[coerce(CalcStep, step) for step in segment] for segment in trail]
    all_steps = [step for segment in segments for step in segment]
    sizing_steps = [s for s in all_steps if s.step_id.startswith("S")]
    analysis_steps = [s for s in all_steps if s.step_id.startswith("A")]
    check_rows = [coerce(CheckResult, c) for c in checks]

    step_ids = {s.step_id for s in all_steps}

    design_basis = [_step_line(s) for s in sizing_steps]
    design_basis.extend(
        [
            _line("Concrete grade", params.concrete_grade.value, "", CITATION_PARAMETER, None),
            _line("Steel grade", params.steel_grade.value, "", CITATION_PARAMETER, None),
            _line("Clear cover to reinforcement", f"{params.clear_cover_mm:g} mm", "", CITATION_PARAMETER, None),
            _line(
                "Backfill properties",
                f"gamma = {params.backfill_unit_weight_kn_m3:g} kN/m^3, phi = "
                f"{params.backfill_friction_angle_deg:g} deg, slope = {params.backfill_slope_deg:g} deg",
                "", CITATION_PARAMETER, None,
            ),
            _line(
                "Founding soil",
                f"SBC = {params.safe_bearing_capacity_kn_m2:g} kN/m^2, base friction mu = "
                f"{params.base_friction_coeff:g}",
                "", CITATION_PARAMETER, None,
            ),
            _line(
                "Proportioned wall",
                f"base {geometry.base_width_mm:g} mm wide x {geometry.total_height_mm:g} mm high, "
                f"stem {geometry.stem_top_thickness_mm:g}-{geometry.stem_base_thickness_mm:g} mm, "
                f"base slab {geometry.base_thickness_mm:g} mm"
                + (f", shear key {geometry.key_depth_mm:g} mm" if geometry.key_depth_mm else ""),
                "", "Proportioned geometry — see the sizing trail steps above", None,
            ),
        ]
    )

    earth_pressure = [_step_line(s) for s in analysis_steps if _is_earth_pressure(s)]
    stability = [_step_line(s) for s in analysis_steps if not _is_earth_pressure(s)]

    section_checks = []
    for check in check_rows:
        if check.trail_ref not in step_ids:
            raise ValueError(
                f"check {check.member}/{check.kind} references trail step "
                f"{check.trail_ref!r} which is not in any provided trail segment"
            )
        section_checks.append(
            _line(
                f"{check.member}: {check.requirement}",
                f"{check.computed} | limit: {check.limit}",
                "", check.clause, check.trail_ref, check.status,
            )
        )

    sections = [
        {"id": "design_basis", "title": SECTION_TITLES["design_basis"], "lines": design_basis},
        {"id": "earth_pressure", "title": SECTION_TITLES["earth_pressure"], "lines": earth_pressure},
        {"id": "stability", "title": SECTION_TITLES["stability"], "lines": stability},
        {"id": "section_checks", "title": SECTION_TITLES["section_checks"], "lines": section_checks},
    ]

    doc = {
        "sections": sections,
        "assumptions": [coerce(Assumption, a).model_dump() for a in assumptions],
        "warnings": list(warnings),
        "trail": [
            {
                "step_id": s.step_id,
                "description": s.description,
                "formula": s.formula,
                "inputs": s.inputs,
                "value": s.value,
                "unit": s.unit,
                "citation": s.citation,
            }
            for s in all_steps
        ],
    }

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    file_path = out_path / CALC_SHEET_FILENAME
    file_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return file_path
