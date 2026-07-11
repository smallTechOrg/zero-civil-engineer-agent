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
from components.rolling_stock_member.params import (
    RollingStockMemberGeometry,
    RollingStockMemberParams,
    member_kind_label,
)

CALC_SHEET_FILENAME = "calc_sheet.json"

SECTION_TITLES = {
    "design_basis": "Design Basis & Proportioning",
    "loading": "RDSO Load Cases (Vertical Payload + Longitudinal Buffing)",
    "section_analysis": "Section Properties, Stresses & Interaction",
    "section_checks": "Strength & Interaction Checks (RDSO Specifications / IS 800)",
}
CITATION_PARAMETER = "User design requirement / preset default (see the assumptions block)"

# Analysis-trail descriptions that belong to the Loading section (by prefix).
_LOADING_PREFIXES = (
    "Member self-weight",
    "Vertical payload case:",
    "Longitudinal buffing case:",
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


def compose_calc_sheet(
    *,
    trail: Sequence[Sequence[CalcStep]],
    checks: Sequence[CheckResult],
    assumptions: Sequence[Assumption],
    warnings: Sequence[str],
    params: RollingStockMemberParams,
    geometry: RollingStockMemberGeometry,
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
        _line("Member kind", member_kind_label(params.member_kind), "", CITATION_PARAMETER, None),
        _line("Steel grade", params.steel_grade, "", CITATION_PARAMETER, None),
        _line("Design vertical load", params.design_vertical_load_kn, "kN", CITATION_PARAMETER, None),
        _line("Design buffing load", params.design_buffing_load_kn, "kN", CITATION_PARAMETER, None),
        _line(
            "Proportioned member",
            f"length {geometry.member_length_mm:g} mm, overall depth {geometry.overall_depth_mm:g} mm, "
            f"web {geometry.web_depth_mm:g} x {geometry.web_thickness_mm:g} mm, "
            f"flanges {geometry.flange_width_mm:g} x {geometry.flange_thickness_mm:g} mm, "
            f"fillet welds {geometry.weld_size_mm:g} mm",
            "", "Proportioned geometry — see the sizing trail steps above", None,
        ),
    ])

    loading = [_step_line(s) for s in analysis_steps if _is_loading(s)]
    section_analysis = [_step_line(s) for s in analysis_steps if not _is_loading(s)]

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
        {"id": "loading", "title": SECTION_TITLES["loading"], "lines": loading},
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
