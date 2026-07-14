"""Calc-sheet composer — the standard-basis `calc_sheet.json` artefact.

Reuses the shared calc-sheet JSON shape (sections / assumptions / warnings /
trail) so the existing frontend CalcSheet renderer works unchanged. The M-00004
sheet documents the STANDARD BASIS — config selection, thickness/haunch source,
barrel-length derivation and the reproduced bar schedule — every catalogue value
carrying a PROVISIONAL marking. No load analysis appears (there is none).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from components.base import Assumption, CalcStep, CheckResult, coerce
from components.m00004_box_culvert.params import M00004Geometry, M00004Params
from components.m00004_box_culvert.sizing import VERIFY_TAG

CALC_SHEET_FILENAME = "calc_sheet.json"

_SECTION_TITLES = {
    "standard_basis": "Standard Basis (RDSO/M-00004) - PROVISIONAL",
    "config_selection": "Config Selection & Reproduced Detailing",
    "reinforcement": "Reinforcement Schedule (a1..h) - PROVISIONAL",
    "conformance": "Standard-Conformance Checks",
}
_CITATION_PARAMETER = "User design requirement / standard default (see the assumptions block)"


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


def compose_calc_sheet(
    *,
    trail: Sequence[Sequence[CalcStep]],
    checks: Sequence[CheckResult],
    assumptions: Sequence[Assumption],
    warnings: Sequence[str],
    params: M00004Params,
    geometry: M00004Geometry,
    out_dir: Path,
) -> Path:
    """Compose and write `calc_sheet.json`; returns the written file's Path."""
    params = coerce(M00004Params, params)
    geometry = coerce(M00004Geometry, geometry)
    segments = [[coerce(CalcStep, step) for step in segment] for segment in trail]
    all_steps = [step for segment in segments for step in segment]
    sizing_steps = [s for s in all_steps if s.step_id.startswith("S")]
    check_rows = [coerce(CheckResult, c) for c in checks]

    grade_citation = (
        _CITATION_PARAMETER
        if params.concrete_grade is not None
        else f"derived per exposure/size (PROVISIONAL) - {VERIFY_TAG}"
    )
    standard_basis = [_step_line(s) for s in sizing_steps]
    standard_basis.extend(
        [
            _line(
                "Concrete grade (resolved)",
                geometry.concrete_grade_resolved,
                "",
                grade_citation,
                None,
            ),
            _line("Exposure condition", params.exposure.value, "", _CITATION_PARAMETER, None),
            _line("Steel grade", params.steel_grade.value, "", _CITATION_PARAMETER, None),
            _line(
                "Entered opening",
                f"{params.clear_span_m:g} x {params.clear_height_m:g} m, fill {params.cushion_m:g} m",
                "", _CITATION_PARAMETER, None,
            ),
            _line(
                "Standard-driven basis",
                "thickness / haunch / reinforcement reproduced from the selected standard "
                f"config - {VERIFY_TAG}; NO load analysis performed",
                "", "RDSO/M-00004 standard box culvert", None,
            ),
        ]
    )

    config_selection = [
        _line(
            "Selected standard config",
            geometry.config_id,
            "", f"RDSO/M-00004 digitized subset - {VERIFY_TAG}", None,
        ),
        _line("Slab/wall thickness", f"{geometry.thickness_mm:g}", "mm",
              f"reproduced from config {geometry.config_id} - {VERIFY_TAG}", None),
        _line("Haunch leg", f"{geometry.haunch_mm:g}", "mm",
              f"reproduced from config {geometry.config_id} - {VERIFY_TAG}", None),
        _line("Overall size", f"{geometry.outer_width_mm:g} x {geometry.outer_height_mm:g}", "mm",
              "clear opening + 2 x thickness", None),
        _line("Derived barrel length", f"{geometry.barrel_length_mm:g}", "mm",
              "formation_width + 2 x side_slope x (cushion + outer_height)", None),
        _line("HFL above bed (derived)", f"{geometry.hfl_above_bed_mm:g}", "mm",
              f"0.75 x clear height - PROVISIONAL, hydraulics not verified - {VERIFY_TAG}", None),
        _line("Return-wall base width (derived)", f"{geometry.return_wall_base_width_mm:g}", "mm",
              f"0.5 x outer height, taper to top = thickness - PROVISIONAL - {VERIFY_TAG}", None),
        _line("Drop-wall depth below bed", f"{geometry.drop_wall_depth_mm:g}", "mm",
              f"fixed GA-detail constant - PROVISIONAL - {VERIFY_TAG}", None),
    ]
    for flag in geometry.provisional_flags:
        config_selection.append(_line("PROVISIONAL flag", flag, "", VERIFY_TAG, None))

    reinforcement = [
        _line(
            f"Mark {mark}",
            f"{int(bar['dia_mm'])} dia @ {int(bar['spacing_mm'])} mm c/c",
            "", f"reproduced bar schedule (PROVISIONAL) - {VERIFY_TAG}", None,
        )
        for mark, bar in geometry.bar_schedule.items()
    ]

    conformance = [
        _line(
            f"{row.member}: {row.requirement}",
            f"{row.computed} | limit: {row.limit}",
            "", row.clause, row.trail_ref, row.status,
        )
        for row in check_rows
    ]

    sections = [
        {"id": "standard_basis", "title": _SECTION_TITLES["standard_basis"], "lines": standard_basis},
        {"id": "config_selection", "title": _SECTION_TITLES["config_selection"], "lines": config_selection},
        {"id": "reinforcement", "title": _SECTION_TITLES["reinforcement"], "lines": reinforcement},
        {"id": "conformance", "title": _SECTION_TITLES["conformance"], "lines": conformance},
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
