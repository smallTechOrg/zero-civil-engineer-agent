"""Calc-sheet composer — the clause-cited `calc_sheet.json` artefact (calc-sheet.md).

Pinned public API (the graph slice calls exactly this; the frontend renders
exactly the JSON shape below):

    from engine.calcsheet import compose_calc_sheet
    path = compose_calc_sheet(
        trail=[sizing.trail, analysis.trail, checks_output.trail],
        checks=checks_output.checks,
        assumptions=[*sizing.assumptions, *analysis.assumptions, *checks_output.assumptions],
        warnings=sizing.warnings,
        params=params,
        geometry=geometry,
        out_dir=artifacts_dir,
    )   # writes out_dir/"calc_sheet.json", returns its Path

JSON shape (pinned):
    {"sections": [{"id", "title", "lines": [{"description", "value", "unit",
     "citation", "trail_ref", "status"}]}], "assumptions": [...],
     "warnings": [...], "trail": [{"step_id", "description", "formula",
     "inputs", "value", "unit", "citation"}]}
Section ids are exactly design_basis / loading / analysis / member_checks;
`status` is only meaningful ("PASS"/"FAIL") on member_checks lines; trail
`inputs` values are plain scalars or {"ref": step_id, "value": n} when the
input is itself a computed step (recursive drill-down).

Merging: `trail` takes the CalcStep segments in engine order (sizing,
analysis, checks). Segments are merged into ONE trail with unique step ids —
colliding ids are re-keyed with a letter suffix (S07 -> S07b) that can never
steal another original id. Explicit refs written as the string "ref:<id>"
(see `engine.checks.TRAIL_REF_INPUT_PREFIX`) resolve segment-locally first,
then across segments in order; landed sizing/analysis steps carry plain
scalar inputs, which are promoted to ref-form only on an exact, UNIQUE
value match against an earlier step (never fuzzy, never ambiguous).

This module is the only place in the engine that touches the filesystem.
"""

import json
import string
from collections.abc import Sequence
from pathlib import Path

from domain.culvert import Assumption, BoxGeometry, CalcStep, CulvertParams
from engine.checks import TRAIL_REF_INPUT_PREFIX, CheckResult
from engine.loads import (
    CASE_DL,
    CASE_EP_ACTIVE,
    CASE_EP_AT_REST,
    CASE_FILL,
    CASE_LL_SURCHARGE,
    CASE_LL_SURCHARGE_ACTIVE,
    CASE_SIDL,
    CASE_WATER,
)

CALC_SHEET_FILENAME = "calc_sheet.json"
SECTION_TITLES = {
    "design_basis": "Design Basis",
    "loading": "Loading",
    "analysis": "Analysis",
    "member_checks": "Member Checks (IRS Concrete Bridge Code)",
}
# Trail steps whose description starts with one of these belong to the Loading
# section. The LL+CDA case records its steps under the shorter "LL:" prefix.
LOADING_STEP_PREFIXES = (
    f"{CASE_DL}:",
    f"{CASE_FILL}:",
    f"{CASE_SIDL}:",
    "LL:",
    f"{CASE_EP_AT_REST}:",
    f"{CASE_EP_ACTIVE}:",
    f"{CASE_LL_SURCHARGE}:",
    f"{CASE_LL_SURCHARGE_ACTIVE}:",
    f"{CASE_WATER}:",
    "Earth pressure coefficient",
    "Active earth pressure coefficient",
    "Fill depth from formation",
    "Equivalent live-load surcharge",
)
CITATION_PARAMETER = "User design requirement / preset default (see the assumptions block)"
# Auto ref-promotion skips these trivially common values — a 0 or 1 input must
# never be linked to an unrelated step that merely happens to share the value.
AUTO_REF_EXCLUDED_VALUES = (0.0, 1.0)


class _MergedStep:
    """One trail step after merging: final id, source segment, resolved inputs."""

    def __init__(self, step: CalcStep, final_id: str, segment_index: int, role: str) -> None:
        self.step = step
        self.final_id = final_id
        self.segment_index = segment_index
        self.role = role
        self.inputs: dict[str, object] = {}


def compose_calc_sheet(
    *,
    trail: Sequence[Sequence[CalcStep]] | Sequence[CalcStep],
    checks: Sequence[CheckResult],
    assumptions: Sequence[Assumption],
    warnings: Sequence[str],
    params: CulvertParams,
    geometry: BoxGeometry,
    out_dir: Path,
) -> Path:
    """Compose and write `calc_sheet.json`; returns the written file's Path."""
    segments = _normalise_segments(trail)
    merged, maps = _merge_segments(segments)
    _resolve_all_inputs(merged, maps)
    by_final_id = {m.final_id: m for m in merged}

    sections = [
        {
            "id": "design_basis",
            "title": SECTION_TITLES["design_basis"],
            "lines": _design_basis_lines(merged, params, geometry),
        },
        {
            "id": "loading",
            "title": SECTION_TITLES["loading"],
            "lines": _loading_lines(merged, params),
        },
        {
            "id": "analysis",
            "title": SECTION_TITLES["analysis"],
            "lines": _analysis_lines(merged),
        },
        {
            "id": "member_checks",
            "title": SECTION_TITLES["member_checks"],
            "lines": _member_check_lines(checks, maps, by_final_id),
        },
    ]

    doc = {
        "sections": sections,
        "assumptions": [assumption.model_dump() for assumption in assumptions],
        "warnings": list(warnings),
        "trail": [
            {
                "step_id": m.final_id,
                "description": m.step.description,
                "formula": m.step.formula,
                "inputs": m.inputs,
                "value": m.step.value,
                "unit": m.step.unit,
                "citation": m.step.citation,
            }
            for m in merged
        ],
    }
    _validate_line_refs(doc)

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    file_path = out_path / CALC_SHEET_FILENAME
    file_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return file_path


# --- merging -------------------------------------------------------------------


def _normalise_segments(
    trail: Sequence[Sequence[CalcStep]] | Sequence[CalcStep],
) -> list[list[CalcStep]]:
    items = list(trail)
    if items and isinstance(items[0], CalcStep):
        return [items]  # a flat single trail — treated as one segment
    return [list(segment) for segment in items]


def _segment_roles(segments: list[list[CalcStep]]) -> list[str]:
    """Content-based roles: a 'K'-id segment is the checks trail; the first
    other segment is the sizing trail; the rest are analysis trails."""
    roles: list[str] = []
    saw_sizing = False
    for segment in segments:
        if segment and all(step.step_id.startswith("K") for step in segment):
            roles.append("checks")
        elif not saw_sizing:
            roles.append("sizing")
            saw_sizing = True
        else:
            roles.append("analysis")
    return roles


def _next_free_id(original: str, used: set[str]) -> str:
    for suffix in string.ascii_lowercase[1:]:
        candidate = f"{original}{suffix}"
        if candidate not in used:
            return candidate
    counter = 2
    while f"{original}-{counter}" in used:
        counter += 1
    return f"{original}-{counter}"


def _merge_segments(
    segments: list[list[CalcStep]],
) -> tuple[list[_MergedStep], list[dict[str, str]]]:
    """One flat trail with unique ids; per-segment original-id -> final-id maps."""
    roles = _segment_roles(segments)
    merged: list[_MergedStep] = []
    maps: list[dict[str, str]] = []
    used: set[str] = set()
    for segment_index, segment in enumerate(segments):
        segment_map: dict[str, str] = {}
        for step in segment:
            if step.step_id in segment_map:
                raise ValueError(
                    f"duplicate step id {step.step_id!r} within one trail segment"
                )
            final_id = step.step_id
            if final_id in used:
                final_id = _next_free_id(step.step_id, used)
            used.add(final_id)
            segment_map[step.step_id] = final_id
            merged.append(_MergedStep(step, final_id, segment_index, roles[segment_index]))
        maps.append(segment_map)
    return merged, maps


def _resolve_ref(original_id: str, segment_index: int, maps: list[dict[str, str]]) -> str:
    local = maps[segment_index].get(original_id)
    if local is not None:
        return local
    for segment_map in maps:
        if original_id in segment_map:
            return segment_map[original_id]
    raise ValueError(
        f"trail ref {original_id!r} does not resolve to any step in any trail segment"
    )


def _resolve_all_inputs(merged: list[_MergedStep], maps: list[dict[str, str]]) -> None:
    """Translate CalcStep inputs to the JSON ref-form, in merged order.

    Explicit "ref:<id>" strings always resolve (or fail loudly); plain numeric
    inputs on sizing/analysis steps are promoted to ref-form only when exactly
    one EARLIER step carries the identical value. Refs therefore always point
    backwards — the trail is acyclic by construction.
    """
    position = {m.final_id: i for i, m in enumerate(merged)}
    value_by_final = {m.final_id: m.step.value for m in merged}
    earlier_values: dict[float, list[str]] = {}

    for index, m in enumerate(merged):
        for key, value in m.step.inputs.items():
            if isinstance(value, str) and value.startswith(TRAIL_REF_INPUT_PREFIX):
                original_id = value[len(TRAIL_REF_INPUT_PREFIX) :]
                final_id = _resolve_ref(original_id, m.segment_index, maps)
                if position[final_id] >= index:
                    raise ValueError(
                        f"trail ref {original_id!r} in step {m.final_id} points forward "
                        "— the drill-down trail must be acyclic"
                    )
                m.inputs[key] = {"ref": final_id, "value": value_by_final[final_id]}
            elif (
                m.role != "checks"
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
                and float(value) not in AUTO_REF_EXCLUDED_VALUES
            ):
                candidates = earlier_values.get(float(value), [])
                if len(candidates) == 1:
                    m.inputs[key] = {"ref": candidates[0], "value": value}
                else:
                    m.inputs[key] = value
            else:
                m.inputs[key] = value
        earlier_values.setdefault(float(m.step.value), []).append(m.final_id)


# --- sections --------------------------------------------------------------------


def _line(
    description: str,
    value: float | int | str,
    unit: str,
    citation: str,
    trail_ref: str | None,
    status: str | None = None,
) -> dict:
    return {
        "description": description,
        "value": value,
        "unit": unit,
        "citation": citation,
        "trail_ref": trail_ref,
        "status": status,
    }


def _step_line(m: _MergedStep) -> dict:
    return _line(m.step.description, m.step.value, m.step.unit, m.step.citation, m.final_id)


def _design_basis_lines(
    merged: list[_MergedStep], params: CulvertParams, geometry: BoxGeometry
) -> list[dict]:
    lines = [_step_line(m) for m in merged if m.role == "sizing"]
    lines.extend(
        [
            _line("Concrete grade", params.concrete_grade.value, "", CITATION_PARAMETER, None),
            _line("Steel grade", params.steel_grade.value, "", CITATION_PARAMETER, None),
            _line(
                "Loading standard",
                params.loading_standard.value,
                "",
                CITATION_PARAMETER,
                None,
            ),
            _line(
                "Track configuration",
                f"{params.gauge.value}, {params.tracks} track",
                "",
                CITATION_PARAMETER,
                None,
            ),
            _line(
                "Clear cover to reinforcement",
                f"{params.clear_cover_mm:g} mm",
                "",
                CITATION_PARAMETER,
                None,
            ),
            _line(
                "Fill properties",
                f"{params.soil_unit_weight_kn_m3:g} kN/m^3, phi = "
                f"{params.angle_of_friction_deg:g} deg",
                "",
                CITATION_PARAMETER,
                None,
            ),
            _line(
                "Overall box (sized)",
                f"{geometry.external_width_m:g} x {geometry.external_height_m:g} m, "
                f"barrel {geometry.barrel_length_m:g} m",
                "",
                "Sized geometry — see the thickness and barrel-length trail steps above",
                None,
            ),
        ]
    )
    return lines


def _is_loading_step(step: CalcStep) -> bool:
    return any(step.description.startswith(prefix) for prefix in LOADING_STEP_PREFIXES)


def _acs_suffix(params: CulvertParams) -> str:
    from engine.loading import get_loading_standard

    standard = get_loading_standard(params.loading_standard.value)
    acs = getattr(standard, "acs_level", None) or standard.citation
    return f" [Loading standard {standard.name}, transcribed at {acs}]"


def _loading_lines(merged: list[_MergedStep], params: CulvertParams) -> list[dict]:
    suffix = _acs_suffix(params)
    lines = []
    for m in merged:
        if m.role == "analysis" and _is_loading_step(m.step):
            line = _step_line(m)
            if "ACS" not in line["citation"]:
                line["citation"] += suffix
            lines.append(line)
    return lines


def _analysis_lines(merged: list[_MergedStep]) -> list[dict]:
    return [
        _step_line(m)
        for m in merged
        if m.role == "analysis" and not _is_loading_step(m.step)
    ]


def _member_check_lines(
    checks: Sequence[CheckResult],
    maps: list[dict[str, str]],
    by_final_id: dict[str, _MergedStep],
) -> list[dict]:
    lines = []
    for check in checks:
        final_ref = None
        for segment_map in maps:
            if check.trail_ref in segment_map:
                final_ref = segment_map[check.trail_ref]
                break
        if final_ref is None or final_ref not in by_final_id:
            raise ValueError(
                f"check {check.member}/{check.kind} references trail step "
                f"{check.trail_ref!r} which is not in any provided trail segment"
            )
        lines.append(
            _line(
                f"{check.member}: {check.requirement}",
                f"{check.computed} | limit: {check.limit}",
                "",
                check.clause,
                final_ref,
                check.status,
            )
        )
    return lines


def _validate_line_refs(doc: dict) -> None:
    step_ids = {step["step_id"] for step in doc["trail"]}
    if len(step_ids) != len(doc["trail"]):
        raise ValueError("merged trail contains duplicate step ids")
    for section in doc["sections"]:
        for line in section["lines"]:
            if line["trail_ref"] is not None and line["trail_ref"] not in step_ids:
                raise ValueError(
                    f"line {line['description']!r} in section {section['id']!r} "
                    f"references unknown trail step {line['trail_ref']!r}"
                )
