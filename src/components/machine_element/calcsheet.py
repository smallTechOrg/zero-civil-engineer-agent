"""Calc-sheet composer — the clause-cited `calc_sheet.json` artefact.

Reuses the shared calc-sheet JSON shape so the existing frontend CalcSheet
renderer works unchanged:

    {"sections": [{"id", "title", "lines": [{"description", "value", "unit",
     "citation", "trail_ref", "status"}]}], "assumptions": [...],
     "warnings": [...], "trail": [...]}

The sizing ('S'), analysis ('A') and checks ('K') trail segments carry disjoint
id namespaces, so merging them into one drill-down trail needs no re-keying.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from components.base import Assumption, CalcStep, CheckResult, coerce
from components.machine_element.params import MachineElementGeometry, MachineElementParams

CALC_SHEET_FILENAME = "calc_sheet.json"

SECTION_TITLES = {
    "design_basis": "Design Basis & Proportioning",
    "loading": "Driving Actions (Torque & Bending)",
    "strength": "Stresses, Factors of Safety & Fatigue",
    "element_checks": "Strength Checks (Machine-Design Practice / IS 816)",
}
CITATION_PARAMETER = "User design requirement / preset default (see the assumptions block)"

# Analysis-trail descriptions that belong to the Loading section (by prefix).
_LOADING_PREFIXES = (
    "Transmitted torque",
    "Tangential force",
    "Net transverse",
    "Overhung bending",
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


def _is_loading(step: CalcStep) -> bool:
    return any(step.description.startswith(p) for p in _LOADING_PREFIXES)


def _element_summary(geometry: MachineElementGeometry) -> str:
    if geometry.element_kind == "welded_joint":
        return (
            f"welded joint — hub dia {geometry.hub_diameter_mm:g} mm, fillet leg "
            f"{geometry.weld_size_mm:g} mm (throat {geometry.weld_throat_mm:g} mm), "
            f"plate {geometry.plate_thickness_mm:g} mm"
        )
    return (
        f"shaft — dia {geometry.diameter_mm:g} mm x length {geometry.length_mm:g} mm, "
        f"journals {geometry.step_diameter_mm:g} mm, fillet r {geometry.fillet_radius_mm:g} mm, "
        f"keyway {geometry.keyway_width_mm:g} x {geometry.keyway_depth_mm:g} mm"
    )


def compose_calc_sheet(
    *,
    trail: Sequence[Sequence[CalcStep]],
    checks: Sequence[CheckResult],
    assumptions: Sequence[Assumption],
    warnings: Sequence[str],
    params: MachineElementParams,
    geometry: MachineElementGeometry,
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
    design_basis.extend([
        _line("Element kind", params.element_kind, "", CITATION_PARAMETER, None),
        _line("Material grade", params.material_grade, "", CITATION_PARAMETER, None),
        _line("Speed", params.speed_rpm, "rpm", CITATION_PARAMETER, None),
        _line("Required factor of safety", params.required_factor_of_safety, "", CITATION_PARAMETER, None),
        _line(
            "Proportioned element", _element_summary(geometry), "",
            "Proportioned geometry — see the sizing trail steps above", None,
        ),
    ])

    loading = [_step_line(s) for s in analysis_steps if _is_loading(s)]
    strength = [_step_line(s) for s in analysis_steps if not _is_loading(s)]

    element_checks = []
    for check in check_rows:
        if check.trail_ref not in step_ids:
            raise ValueError(
                f"check {check.member}/{check.kind} references trail step "
                f"{check.trail_ref!r} which is not in any provided trail segment"
            )
        element_checks.append(
            _line(
                f"{check.member}: {check.requirement}",
                f"{check.computed} | limit: {check.limit}",
                "", check.clause, check.trail_ref, check.status,
            )
        )

    sections = [
        {"id": "design_basis", "title": SECTION_TITLES["design_basis"], "lines": design_basis},
        {"id": "loading", "title": SECTION_TITLES["loading"], "lines": loading},
        {"id": "strength", "title": SECTION_TITLES["strength"], "lines": strength},
        {"id": "element_checks", "title": SECTION_TITLES["element_checks"], "lines": element_checks},
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
