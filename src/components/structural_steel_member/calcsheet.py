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
from components.structural_steel_member.params import (
    SteelMemberGeometry,
    SteelMemberParams,
)

CALC_SHEET_FILENAME = "calc_sheet.json"

SECTION_TITLES = {
    "design_basis": "Design Basis & Proportioning",
    "actions": "Design Actions (Transverse + Axial, Self-weight)",
    "section_analysis": "Section Properties, Slenderness & Stresses",
    "section_checks": "Strength & Connection Checks (IS 800 / IS 816)",
}
CITATION_PARAMETER = "User design requirement / preset default (see the assumptions block)"

# Analysis-trail descriptions that belong to the Actions section (by prefix).
_ACTIONS_PREFIXES = (
    "Member self-weight",
    "Design bending moment",
    "Design shear",
    "Design axial",
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


def _is_action(step: CalcStep) -> bool:
    return any(step.description.startswith(p) for p in _ACTIONS_PREFIXES)


def compose_calc_sheet(
    *,
    trail: Sequence[Sequence[CalcStep]],
    checks: Sequence[CheckResult],
    assumptions: Sequence[Assumption],
    warnings: Sequence[str],
    params: SteelMemberParams,
    geometry: SteelMemberGeometry,
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
        _line("Member type", params.member_type, "", CITATION_PARAMETER, None),
        _line("Steel grade", params.steel_grade, "", CITATION_PARAMETER, None),
        _line("Design method", "working stress (IS 800) / fillet welds (IS 816)", "",
              CITATION_PARAMETER, None),
        _line(
            "Proportioned member",
            f"length {geometry.cantilever_length_mm:g} mm, overall depth "
            f"{geometry.overall_depth_mm:g} mm, web {geometry.web_depth_mm:g} x "
            f"{geometry.web_thickness_mm:g} mm, flanges {geometry.flange_width_mm:g} x "
            f"{geometry.flange_thickness_mm:g} mm, {geometry.weld_size_mm:g} mm fillet weld",
            "", "Proportioned geometry — see the sizing trail steps above", None,
        ),
    ])

    actions = [_step_line(s) for s in analysis_steps if _is_action(s)]
    section_analysis = [_step_line(s) for s in analysis_steps if not _is_action(s)]

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
        {"id": "actions", "title": SECTION_TITLES["actions"], "lines": actions},
        {"id": "section_analysis", "title": SECTION_TITLES["section_analysis"], "lines": section_analysis},
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
