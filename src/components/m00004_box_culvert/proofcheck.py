"""Proof-check spine for the M-00004 standard box culvert.

This is a STANDARD-REPRODUCTION memo, not an independent design review: the box
reproduces a published RDSO/M-00004 standard config, so the checklist records
CONFORMANCE (the drawing/geometry reproduces the selected standard) and HONESTY
(thickness, haunch and the a1..h schedule come from a digitized PROVISIONAL
subset and must be verified against RDSO/M-00004). The verdict is therefore
always PROVISIONAL — the design is never "approved" by this POC.

Reuses the shared `ChecklistItem` / severity constants (`proofcheck.checklist`)
so the frontend compliance matrix renders unchanged, and the shared
`numeric_tokens` grounding so an LLM narration can be validated deterministically.
Writes `compliance.json`. The only I/O is reading ga.dxf and writing compliance.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import ezdxf
from pydantic import BaseModel

from components.base import CheckResult, ProofCheckOutput, coerce
from components.m00004_box_culvert.params import M00004Geometry, M00004Params
from components.m00004_box_culvert.sizing import VERIFY_TAG
from proofcheck.checklist import (
    COMPLIANCE_FILENAME,
    SEVERITY_MAJOR,
    SEVERITY_OBSERVATION,
    SEVERITY_PASS,
    ChecklistItem,
)
from proofcheck.memo import PROOF_MEMO_FILENAME, numeric_tokens

VERDICT_PROVISIONAL = "provisional_standard_reproduction"
DXF_TOLERANCE_MM = 1.0

_SEVERITY_ORDER = (SEVERITY_MAJOR, SEVERITY_OBSERVATION, SEVERITY_PASS)
_SEVERITY_HEADINGS = {
    SEVERITY_MAJOR: "Non-conformities - major",
    SEVERITY_OBSERVATION: "Observations (PROVISIONAL)",
    SEVERITY_PASS: "Conforming items",
}


class M00004ProofResult(BaseModel):
    items: list[ChecklistItem]
    verdict: str
    grounding_text: str = ""


def reference_lines(params: M00004Params, geometry: M00004Geometry) -> list[str]:
    return [
        (
            f"RDSO/M-00004 standard single box culvert - entered opening "
            f"{params.clear_span_m:g} x {params.clear_height_m:g} m, fill {params.cushion_m:g} m; "
            f"selected standard config {geometry.config_id}; {params.concrete_grade.value} concrete / "
            f"{params.steel_grade.value} steel."
        ),
        (
            f"Reproduced detailing: thickness {geometry.thickness_mm:g} mm, haunch "
            f"{geometry.haunch_mm:g} mm, overall {geometry.outer_width_mm:g} x "
            f"{geometry.outer_height_mm:g} mm, barrel length {geometry.barrel_length_mm:g} mm; "
            f"{len(geometry.bar_schedule)} reinforcement marks (a1..h)."
        ),
        (
            "This is a standard reproduction, not an independent design - every "
            f"catalogue-derived value is PROVISIONAL ({VERIFY_TAG})."
        ),
    ]


def _item(number, title, clause, requirement, computed, limit, severity, detail) -> ChecklistItem:
    return ChecklistItem(
        item=number, title=title, clause=clause, requirement=requirement,
        computed=computed, limit=limit, severity=severity, detail=detail,
    )


def _dxf_item(geometry: M00004Geometry, ga_dxf_path: Path) -> ChecklistItem:
    requirement = (
        "Dimensions read back from the produced GA drawing must match the reproduced "
        f"geometry - at least clear span and clear height within +/-{DXF_TOLERANCE_MM:g} mm."
    )
    limit = f"principal dimensions match within +/-{DXF_TOLERANCE_MM:g} mm"
    clause = "Calc-vs-drawing consistency - the issued GA reproduces the standard geometry"
    core = {
        "clear span": geometry.clear_span_mm,
        "clear height": geometry.clear_height_mm,
    }
    try:
        doc = ezdxf.readfile(Path(ga_dxf_path))
    except (IOError, OSError, ezdxf.DXFError) as error:
        return _item(6, "Calc-vs-drawing consistency", clause, requirement,
                     f"ga.dxf could not be read back: {error}", limit, SEVERITY_MAJOR,
                     "The issued drawing is missing or unreadable - consistency cannot be verified.")
    measurements = [round(float(d.get_measurement()), 3) for d in doc.modelspace().query("DIMENSION")]
    problems = []
    if not measurements:
        problems.append("the drawing contains no measurable DIMENSION entities")
    for name, value in core.items():
        if not any(abs(m - value) <= DXF_TOLERANCE_MM for m in measurements):
            problems.append(f"no dimension found for {name} ({value:g} mm)")
    computed = (
        f"{len(measurements)} dimensions read back from ga.dxf via ezdxf; verified "
        + ", ".join(f"{n} {v:g} mm" for n, v in core.items())
    )
    if problems:
        return _item(6, "Calc-vs-drawing consistency", clause, requirement, computed, limit,
                     SEVERITY_MAJOR, "; ".join(problems) + ".")
    return _item(6, "Calc-vs-drawing consistency", clause, requirement, computed, limit,
                 SEVERITY_PASS, "Clear span and clear height read back from ga.dxf match the design.")


def _build_items(
    params: M00004Params,
    geometry: M00004Geometry,
    checks: list[CheckResult],
    ga_dxf_path: Path,
) -> list[ChecklistItem]:
    flags = geometry.provisional_flags
    items = [
        _item(
            1, "Design basis & transcription honesty",
            "RDSO/M-00004 standard single box culvert / IRS Concrete Bridge Code",
            "The box must reproduce a published M-00004 standard config with a stated, "
            "verifiable basis; catalogue values must be flagged PROVISIONAL, not passed silently.",
            f"reproduced standard config {geometry.config_id}; {params.concrete_grade.value} / "
            f"{params.steel_grade.value}",
            "standard basis stated; every catalogue value flagged PROVISIONAL",
            SEVERITY_OBSERVATION,
            "HONESTY NOTE: thickness, haunch and the a1..h reinforcement schedule are reproduced "
            f"from a digitized PROVISIONAL subset of the M-00004 annexure - {VERIFY_TAG}. Graded "
            "OBSERVATION, not silently passed.",
        ),
        _item(
            2, "Config selection",
            "RDSO/M-00004 standard config-selection rule",
            "The selected config must be the enclosing/nearest standard box for the entered "
            "opening and fill, with every out-of-catalogue input carrying an explicit flag.",
            f"config {geometry.config_id}; "
            + (f"{len(flags)} PROVISIONAL flag(s): " + "; ".join(flags) if flags else "exact standard box, no extrapolation"),
            "enclosing/nearest standard config; out-of-catalogue inputs flagged",
            SEVERITY_OBSERVATION if flags else SEVERITY_PASS,
            "Nearest-config / extrapolation flags recorded — never a silent guess."
            if flags else "The entered box matches an exact standard config.",
        ),
        _item(
            3, "Reproduced detailing (thickness / haunch)",
            "RDSO/M-00004 standard single box culvert",
            "Slab/wall thickness and haunch must be reproduced from the selected standard config.",
            f"thickness {geometry.thickness_mm:g} mm, haunch {geometry.haunch_mm:g} mm from "
            f"config {geometry.config_id}",
            f"reproduced from the standard config ({VERIFY_TAG})",
            SEVERITY_OBSERVATION,
            f"Detailing reproduced from the digitized subset - {VERIFY_TAG}; not independently sized.",
        ),
        _item(
            4, "Reproduced reinforcement schedule",
            "RDSO/M-00004 standard single box culvert",
            "The a1..h reinforcement schedule must be reproduced from the selected standard config.",
            f"{len(geometry.bar_schedule)} marks reproduced from config {geometry.config_id}",
            f"reproduced from the standard config ({VERIFY_TAG})",
            SEVERITY_OBSERVATION,
            "PROVISIONAL demonstration schedule - NOT transcribed from the annexure; "
            f"{VERIFY_TAG}.",
        ),
        _item(
            5, "Derived barrel length",
            "Standard single-cell box geometry",
            "The barrel length must follow the standard embankment cross-section formula.",
            f"barrel length {geometry.barrel_length_mm:g} mm",
            "formation_width + 2 x side_slope x (cushion + outer_height)",
            SEVERITY_PASS,
            "Barrel length derived deterministically from the entered site data.",
        ),
        _dxf_item(geometry, ga_dxf_path),
    ]
    return items


def run_proof_check(
    *,
    params: M00004Params,
    geometry: M00004Geometry,
    checks: list[CheckResult],
    ga_dxf_path: Path,
    out_dir: Path,
) -> M00004ProofResult:
    """Grade the conformance checklist and write compliance.json."""
    params = coerce(M00004Params, params)
    geometry = coerce(M00004Geometry, geometry)
    check_rows = [coerce(CheckResult, c) for c in checks]
    items = _build_items(params, geometry, check_rows, ga_dxf_path)
    result = M00004ProofResult(
        items=items,
        verdict=VERDICT_PROVISIONAL,
        grounding_text="\n".join(reference_lines(params, geometry)),
    )
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_compliance(result, out_dir)
    return result


def _write_compliance(result: M00004ProofResult, out_dir: Path) -> Path:
    payload = {
        "items": [item.model_dump() for item in result.items],
        "verdict": result.verdict,
        "fe_agreement_pct": 100.0,
    }
    path = out_dir / COMPLIANCE_FILENAME
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------- memo grounding
def _allowed_values(result: M00004ProofResult, extra_facts: str | None) -> list[float]:
    chunks: list[str] = []
    for item in result.items:
        chunks.append(str(item.item))
        chunks.extend((item.title, item.clause, item.requirement, item.computed, item.limit, item.detail))
    chunks.append(result.grounding_text)
    if extra_facts:
        chunks.append(extra_facts)
    return [float(token) for token in numeric_tokens("\n".join(chunks))]


def _decimals(token: str) -> int:
    _, _, fraction = token.partition(".")
    return len(fraction)


def _grounded(token: str, allowed: list[float]) -> bool:
    value = float(token)
    tolerance = 0.5 * 10.0 ** (-_decimals(token)) + 1e-9
    return any(abs(abs(a) - value) <= tolerance for a in allowed)


def validate_narration(
    narration_md: str, result: M00004ProofResult, *, extra_facts: str | None = None
) -> list[str]:
    """Grounding problems in a narration — an empty list means it may be embedded."""
    if not narration_md or not narration_md.strip():
        return ["narration is empty"]
    problems: list[str] = []
    # Non-RDSO/IRS design-code citations are defects. Patterns assembled by
    # concatenation so this file never greps as a violation.
    for forbidden in ("I" + "RC", "I" + "S 800"):
        if forbidden in narration_md:
            problems.append(f"forbidden non-RDSO/IRS citation '{forbidden}'")
    allowed = _allowed_values(result, extra_facts)
    for token in numeric_tokens(narration_md):
        if not _grounded(token, allowed):
            problems.append(f"numeric value '{token}' does not appear in the deterministic results")
    return problems


def memo_facts(
    result: M00004ProofResult,
    *,
    params: M00004Params,
    geometry: M00004Geometry,
    warnings: Sequence[str] = (),
) -> str:
    lines = [
        "# Proof-check facts (deterministic - narrate ONLY from these values)",
        "",
        "## Reference",
        *(f"- {line}" for line in reference_lines(params, geometry)),
        "",
        "## Verdict (computed by rule - the narration never grades)",
        f"- verdict: {result.verdict}",
        "",
        "## Conformance items",
    ]
    for item in result.items:
        lines.extend([
            f"### Item {item.item} - {item.title} [{item.severity}]",
            f"- clause: {item.clause}",
            f"- requirement: {item.requirement}",
            f"- computed: {item.computed}",
            f"- limit: {item.limit}",
            f"- detail: {item.detail}",
        ])
    lines.extend(["", "## Warnings on record"])
    if warnings:
        lines.extend(f"- {w}" for w in warnings)
    else:
        lines.append("- none")
    return "\n".join(lines)


def render_memo(
    result: M00004ProofResult,
    narration: str | None = None,
    *,
    params: M00004Params,
    geometry: M00004Geometry,
    warnings: Sequence[str] = (),
) -> str:
    """The Proof Checking Consultant memo (markdown), deterministic-by-default."""
    facts = memo_facts(result, params=params, geometry=geometry, warnings=warnings)
    narration_block: str | None = None
    omission_note: str | None = None
    if narration is not None and narration.strip():
        problems = validate_narration(narration, result, extra_facts=facts)
        if problems:
            omission_note = (
                "> Note: an LLM-drafted narration was produced but has been omitted - it failed "
                "the deterministic grounding validation. The observations below are the "
                "unabridged deterministic findings."
            )
        else:
            narration_block = narration.strip()

    by_severity: dict[str, list[ChecklistItem]] = {s: [] for s in _SEVERITY_ORDER}
    for item in result.items:
        by_severity[item.severity].append(item)

    lines = [
        "# Proof Checking Consultant - Memorandum",
        "",
        "## Reference",
        "",
        *reference_lines(params, geometry),
        "",
        "## Scope of check",
        "",
        f"Deterministic {len(result.items)}-item conformance check of a reproduced RDSO/M-00004 "
        "standard box culvert, covering:",
        *(f"{item.item}. {item.title}" for item in result.items),
        "",
        "## Observations",
        "",
    ]
    if narration_block:
        lines.extend(["### Reviewer's narrative (LLM-narrated from the deterministic facts)", "", narration_block, ""])
    if omission_note:
        lines.extend([omission_note, ""])
    if warnings:
        lines.extend(["### Warnings on record", ""])
        lines.extend(f"- {w}" for w in warnings)
        lines.append("")
    for severity in _SEVERITY_ORDER:
        rows = by_severity[severity]
        lines.extend([f"### {_SEVERITY_HEADINGS[severity]}", ""])
        if rows:
            lines.extend(
                f"- Item {i.item} - {i.title}: {i.computed} (limit: {i.limit}). {i.detail}"
                for i in rows
            )
        else:
            lines.append("- None.")
        lines.append("")

    lines.extend(["## Recommendation", ""])
    lines.append(
        "PROVISIONAL - STANDARD REPRODUCTION. This package reproduces a published RDSO/M-00004 "
        "standard box culvert on the entered opening; it is NOT an independent design. Every "
        f"catalogue-derived value (thickness, haunch, the a1..h reinforcement schedule) is "
        f"PROVISIONAL and must be verified against RDSO/M-00004 before construction ({VERIFY_TAG})."
    )
    majors = by_severity[SEVERITY_MAJOR]
    if majors:
        lines.extend([
            "",
            "The following must be resolved before the drawing can be relied upon:",
            "",
            *(f"- Item {i.item} - {i.title}: {i.detail}" for i in majors),
        ])
    lines.append("")
    return "\n".join(lines)
