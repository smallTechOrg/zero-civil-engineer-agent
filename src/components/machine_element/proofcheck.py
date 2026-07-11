"""Proof-check spine for the machine element (shaft / welded joint).

The SAME IR-protocol review as the other components: a deterministic checklist
grades every finding, an independent cross-check re-solves the governing stress and
the factor of safety from scratch (closed-form recompute — no FE needed for a
shaft/weld), a rule computes the verdict (any major non-conformity ->
return_for_revision), and a grounded memo narrates ONLY from the deterministic
facts (no number in the memo may be absent from the results; only the declared
machine-design basis / IS 816 may be cited — bridge/road/concrete codes IRC,
IS 456 and IRS Concrete Bridge Code are forbidden).

Reuses the shared `ChecklistItem` / severity / verdict / compliance-filename
constants (`proofcheck.checklist`) so the frontend compliance matrix renders the
machine-element review unchanged. Writes `compliance.json` and a stress/FoS
diagram `bmd.svg`. Pure deterministic Python — the only I/O is reading ga.dxf and
writing the two artefacts.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Sequence
from pathlib import Path

import ezdxf
from pydantic import BaseModel, Field

from components.base import CheckResult, coerce
from components.machine_element._engine_common import (
    MACHINE_MATERIALS,
    SHEAR_YIELD_RATIO,
    TORQUE_CONSTANT_NMM,
    TRANSVERSE_LOAD_FACTOR,
    WELD_THROAT_FACTOR,
    material,
)
from components.machine_element.analysis import MachineElementAnalysis
from components.machine_element.params import MachineElementGeometry, MachineElementParams
from proofcheck.checklist import (
    COMPLIANCE_FILENAME,
    SEVERITY_MAJOR,
    SEVERITY_MINOR,
    SEVERITY_OBSERVATION,
    SEVERITY_PASS,
    VERDICT_APPROVAL,
    VERDICT_REVISION,
    ChecklistItem,
)
from proofcheck.memo import numeric_tokens

BMD_FILENAME = "bmd.svg"
DXF_TOLERANCE_MM = 1.0
TOLERANCE_PCT = 5.0

_SEVERITY_ORDER = (SEVERITY_MAJOR, SEVERITY_MINOR, SEVERITY_OBSERVATION, SEVERITY_PASS)
_SEVERITY_HEADINGS = {
    SEVERITY_MAJOR: "Non-conformities — major",
    SEVERITY_MINOR: "Non-conformities — minor",
    SEVERITY_OBSERVATION: "Observations",
    SEVERITY_PASS: "Conforming items",
}

# The machine element declares standard machine-design methods + IS 816 (weld). A
# machine element is MECHANICAL: bridge/road/concrete codes are out-of-domain
# defects. Patterns are assembled by concatenation so this file never greps as a
# violation.
_FORBIDDEN_CITATION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (
        r"\bI" + r"S\s*[:.\-]?\s*456\b",
        r"\bI" + r"RC\b",
        r"\bI" + r"RS\s+Concrete\s+Bridge\s+Code\b",
    )
)


class ElementCrossCheck(BaseModel):
    """Independent re-solve of the governing stress + factor of safety."""

    method: str = Field(description="Independent recomputation method")
    max_stress_mpa: float
    factor_of_safety: float
    agreement_pct: float = Field(description="100 - worst relative deviation, %")
    tolerance_pct: float
    within_tolerance: bool


class MEProofResult(BaseModel):
    """run_proof_check output — graded items, rule-computed verdict, cross-check, grounding."""

    items: list[ChecklistItem]
    verdict: str
    agreement_pct: float
    cross_check: ElementCrossCheck
    grounding_text: str = ""


# --------------------------------------------------------------------------- reference / facts
def reference_lines(
    params: MachineElementParams,
    geometry: MachineElementGeometry,
    analysis: MachineElementAnalysis,
) -> list[str]:
    if analysis.element_kind == "welded_joint":
        geo = (
            f"Machine element — WELDED JOINT (fillet-welded hub), {params.power_kw:g} kW at "
            f"{params.speed_rpm:g} rpm, {params.material_grade} steel, hub diameter "
            f"{geometry.hub_diameter_mm:g} mm, fillet leg {geometry.weld_size_mm:g} mm "
            f"(throat {geometry.weld_throat_mm:g} mm) on a {geometry.plate_thickness_mm:g} mm plate."
        )
        actions = (
            f"Actions: transmitted torque {analysis.torque_nmm:g} N.mm carried in torsion by the "
            "circular weld group."
        )
        strength = (
            f"Strength: weld throat shear {analysis.max_stress_mpa:g} N/mm^2 (permissible "
            f"{analysis.permissible_stress_mpa:g}); factor of safety {analysis.factor_of_safety:g} "
            f"(required {analysis.required_fos:g})."
        )
        return [geo, actions, strength]
    geo = (
        f"Machine element — transmission SHAFT, {params.power_kw:g} kW at {params.speed_rpm:g} rpm, "
        f"{params.material_grade} steel, diameter {geometry.diameter_mm:g} mm x length "
        f"{geometry.length_mm:g} mm, journals {geometry.step_diameter_mm:g} mm, keyway "
        f"{geometry.keyway_width_mm:g} x {geometry.keyway_depth_mm:g} mm."
    )
    actions = (
        f"Actions: torque {analysis.torque_nmm:g} N.mm, overhung bending moment "
        f"{analysis.bending_moment_nmm:g} N.mm, equivalent twisting moment "
        f"{analysis.equiv_twisting_moment_nmm:g} N.mm."
    )
    strength = (
        f"Strength: maximum shear stress {analysis.max_stress_mpa:g} N/mm^2 (permissible "
        f"{analysis.permissible_stress_mpa:g}); static factor of safety {analysis.factor_of_safety:g} "
        f"(required {analysis.required_fos:g}); fatigue factor of safety {analysis.fatigue_fos:g} "
        f"(required {analysis.required_fatigue_fos:g}); endurance limit {analysis.endurance_limit_mpa:g} N/mm^2."
    )
    return [geo, actions, strength]


def _fmt(value: float, decimals: int = 3) -> str:
    return f"{round(float(value), decimals):g}"


# --------------------------------------------------------------------------- items
def _find(checks: list[CheckResult], **kw) -> CheckResult | None:
    for row in checks:
        if all(getattr(row, k) == v for k, v in kw.items()):
            return row
    return None


def _item(number, title, clause, requirement, computed, limit, severity, detail) -> ChecklistItem:
    return ChecklistItem(
        item=number, title=title, clause=clause, requirement=requirement,
        computed=computed, limit=limit, severity=severity, detail=detail,
    )


def _severity_from_check(row: CheckResult | None, *, on_fail: str) -> str:
    if row is None:
        return SEVERITY_MAJOR
    return SEVERITY_PASS if row.status == "PASS" else on_fail


def _cross_check(
    params: MachineElementParams,
    geometry: MachineElementGeometry,
    analysis: MachineElementAnalysis,
) -> ElementCrossCheck:
    """Recompute the governing stress + FoS independently (inline closed form)."""
    mat = material(params.material_grade)
    tau_y = SHEAR_YIELD_RATIO * mat.yield_mpa
    torque = TORQUE_CONSTANT_NMM * params.power_kw / params.speed_rpm

    if geometry.element_kind == "welded_joint":
        d_hub = geometry.hub_diameter_mm
        throat = WELD_THROAT_FACTOR * geometry.weld_size_mm
        stress = torque / (math.pi * d_hub**2 / 2.0 * throat)
        method = "Independent re-solve of the circular fillet-weld torsional shear (weld-as-a-line)"
    else:
        d = geometry.diameter_mm
        f_t = torque / (params.mounting_pcd_mm / 2.0)
        moment = TRANSVERSE_LOAD_FACTOR * f_t * params.overhang_mm
        te = math.hypot(params.bending_shock_factor * moment, params.torsion_shock_factor * torque)
        stress = 16.0 * te / (math.pi * d**3)
        method = "Independent re-solve of the equivalent twisting moment and 16 Te/(pi d^3) shear stress"
    fos = tau_y / stress if stress > 0 else float("inf")

    worst = 0.0
    for recorded, recomputed in (
        (analysis.max_stress_mpa, stress),
        (analysis.factor_of_safety, fos),
    ):
        if abs(recorded) > 1e-9:
            worst = max(worst, abs(recomputed - recorded) / abs(recorded) * 100.0)
    return ElementCrossCheck(
        method=method,
        max_stress_mpa=round(stress, 3),
        factor_of_safety=round(fos, 3),
        agreement_pct=round(100.0 - worst, 3),
        tolerance_pct=TOLERANCE_PCT,
        within_tolerance=worst <= TOLERANCE_PCT,
    )


def _build_items(
    params: MachineElementParams,
    geometry: MachineElementGeometry,
    analysis: MachineElementAnalysis,
    checks: list[CheckResult],
    cross: ElementCrossCheck,
    ga_dxf_path: Path,
) -> list[ChecklistItem]:
    is_weld = analysis.element_kind == "welded_joint"

    # 1 — design basis & material transcription honesty
    grade_known = params.material_grade in MACHINE_MATERIALS
    items = [_item(
        1, "Design basis & material transcription",
        "Machine Design Code (Shigley / PSG / Design Data Book)",
        "The element must be designed to standard machine-design practice with a stated, "
        "verifiable basis for the material strengths and the permissible stresses.",
        f"{params.material_grade} steel: yield {analysis.yield_mpa:g}, ultimate {analysis.ultimate_mpa:g} "
        f"N/mm^2; permissible shear {analysis.permissible_stress_mpa:g} N/mm^2 (FoS {analysis.required_fos:g})."
        if grade_known else f"material grade {params.material_grade} has no transcribed strength row.",
        "grade carries transcribed yield/ultimate strengths; permissible-stress basis cited",
        SEVERITY_OBSERVATION if grade_known else SEVERITY_MAJOR,
        "HONESTY NOTE: the material yield / ultimate strengths and the endurance / stress-"
        "concentration factors are transcribed from the Design Data Book for the POC and are "
        "pending verification against the source (engineer pre-review before demo day) — graded "
        "OBSERVATION, not silently passed."
        if grade_known else f"Material grade {params.material_grade} has no transcribed strength row.",
    )]

    # 2 — torque re-derivation from power & speed
    items.append(_torque_item(params, analysis))

    # 3 — governing strength adequacy
    if is_weld:
        strength = _find(checks, kind="weld_shear")
        strength_title = "Weld shear adequacy"
        strength_req = "Fillet-weld throat shear stress within the permissible weld shear stress."
        fail_detail = ("The weld throat shear stress exceeds the permissible value — a strength "
                       "non-conformity in the WELD (under-sized fillet leg).")
    else:
        strength = _find(checks, kind="combined_stress")
        strength_title = "Combined-stress adequacy"
        strength_req = ("Combined bending + torsion maximum shear stress within the permissible "
                        "shear stress (static factor of safety against shear yield).")
        fail_detail = ("The maximum shear stress exceeds the permissible value — a strength "
                       "non-conformity in the SHAFT (under-sized diameter).")
    items.append(_item(
        3, strength_title, strength.clause if strength else "Machine Design Code",
        strength_req,
        strength.computed if strength else "no recorded strength row",
        strength.limit if strength else "-",
        _severity_from_check(strength, on_fail=SEVERITY_MAJOR),
        "The governing stress is within the permissible value." if strength and strength.status == "PASS"
        else fail_detail,
    ))

    # 4 — fatigue / endurance adequacy
    if is_weld:
        items.append(_item(
            4, "Fatigue of the welded joint",
            "Machine Design Code (Shigley / PSG / Design Data Book)",
            "Fluctuating-torque fatigue of the fillet weld requires a detail-category assessment.",
            "fatigue not evaluated — flagged for a full welded-joint fatigue assessment",
            "stress range within the weld detail-category endurance",
            SEVERITY_OBSERVATION,
            "HONESTY NOTE: a full fatigue assessment of the fillet weld under fluctuating torque "
            "is beyond this POC scope — flagged as an observation, not silently passed.",
        ))
    else:
        fatigue = _find(checks, kind="fatigue")
        items.append(_item(
            4, "Fatigue (rotating-shaft endurance)", fatigue.clause if fatigue else "Machine Design Code",
            "Rotating-shaft fatigue factor of safety (Soderberg, reversed bending + steady torsion) "
            "within the required endurance factor of safety.",
            fatigue.computed if fatigue else "no recorded fatigue row",
            fatigue.limit if fatigue else "-",
            _severity_from_check(fatigue, on_fail=SEVERITY_MAJOR),
            "The fatigue factor of safety meets the required value." if fatigue and fatigue.status == "PASS"
            else "The rotating-shaft fatigue factor of safety is below the required value — a fatigue "
                 "non-conformity in the SHAFT (endurance governs; a larger diameter or better surface "
                 "finish is indicated).",
        ))

    # 5 — stress-concentration / weld-detail observation
    if is_weld:
        detail_row = _find(checks, kind="weld_detail")
        items.append(_item(
            5, "Weld detailing", detail_row.clause if detail_row else "IS 816",
            "Fillet-weld leg / throat and edge detailing per IS 816.",
            detail_row.computed if detail_row else "weld detailing not recorded",
            detail_row.limit if detail_row else "-",
            SEVERITY_OBSERVATION,
            "Weld leg, throat and plate detailing recorded per IS 816; edge distances and end returns "
            "to be confirmed at the detailed-design stage (observation).",
        ))
    else:
        sc_row = _find(checks, kind="stress_concentration")
        items.append(_item(
            5, "Stress concentration (fillet / keyway)",
            sc_row.clause if sc_row else "Machine Design Code",
            "The shoulder-fillet and keyway stress concentration must be accounted for in fatigue.",
            sc_row.computed if sc_row else "stress concentration not recorded",
            sc_row.limit if sc_row else "-",
            SEVERITY_OBSERVATION,
            "HONESTY NOTE: the stress-concentration factor is a transcribed approximation applied to "
            "the reversed bending; a detailed Kt from the actual fillet-radius/keyway geometry is to "
            "be confirmed (observation).",
        ))

    # 6 — independent strength cross-check
    items.append(_item(
        6, "Independent strength cross-check", cross.method,
        "An independent re-solve of the governing stress and factor of safety must agree with the "
        "recorded analysis within the stated tolerance.",
        f"independent stress {_fmt(cross.max_stress_mpa, 1)} N/mm^2, FoS {_fmt(cross.factor_of_safety, 2)}; "
        f"agreement {_fmt(cross.agreement_pct, 2)} %",
        f"within +/-{TOLERANCE_PCT:g}% of the recorded analysis",
        SEVERITY_PASS if cross.within_tolerance else SEVERITY_MAJOR,
        "The independent re-solve reproduces the recorded governing stress and factor of safety."
        if cross.within_tolerance
        else "The independent re-solve disagrees with the recorded governing stress / factor of safety.",
    ))

    # 7 — calc-vs-drawing (DXF read-back)
    items.append(_dxf_item(geometry, ga_dxf_path))
    return items


def _torque_item(params: MachineElementParams, analysis: MachineElementAnalysis) -> ChecklistItem:
    requirement = (
        "The recorded transmitted torque must equal an independent re-derivation from the power "
        "and speed, T = 9550 * P / N."
    )
    limit = "recorded torque equals 9550 * P[kW] / N[rpm] (exact re-derivation)"
    clause = "Machine Design Code (Shigley / PSG / Design Data Book) — torque from transmitted power"
    recomputed = TORQUE_CONSTANT_NMM * params.power_kw / params.speed_rpm
    computed = (
        f"recorded T {_fmt(analysis.torque_nmm, 1)} N.mm vs re-derived {_fmt(recomputed, 1)} N.mm "
        f"at P = {params.power_kw:g} kW, N = {params.speed_rpm:g} rpm"
    )
    if not math.isclose(analysis.torque_nmm, recomputed, rel_tol=1e-4, abs_tol=1e-3):
        return _item(2, "Torque re-derivation", clause, requirement, computed, limit,
                     SEVERITY_MAJOR,
                     "The recorded torque does not match the power/speed re-derivation — the design "
                     "basis cannot be verified.")
    return _item(2, "Torque re-derivation", clause, requirement, computed, limit, SEVERITY_PASS,
                 "The recorded transmitted torque is re-derived independently from the power and "
                 "speed — exact match.")


def _core_dimensions(geometry: MachineElementGeometry) -> dict[str, float]:
    if geometry.element_kind == "welded_joint":
        return {"hub diameter": geometry.hub_diameter_mm, "plate size": geometry.length_mm}
    return {"major diameter": geometry.diameter_mm, "overall length": geometry.length_mm}


def _dxf_item(geometry: MachineElementGeometry, ga_dxf_path: Path) -> ChecklistItem:
    requirement = (
        "Dimensions read back from the produced detail drawing must match the designed geometry "
        f"— at least the principal dimensions within +/-{DXF_TOLERANCE_MM:g} mm."
    )
    limit = f"principal dimensions match within +/-{DXF_TOLERANCE_MM:g} mm"
    clause = "Calc-vs-drawing consistency — every issued dimension matches the designed geometry"
    core = _core_dimensions(geometry)
    try:
        doc = ezdxf.readfile(Path(ga_dxf_path))
    except (IOError, OSError, ezdxf.DXFError) as error:
        return _item(7, "Calc-vs-drawing consistency", clause, requirement,
                     f"ga.dxf could not be read back: {error}", limit, SEVERITY_MAJOR,
                     "The issued drawing is missing or unreadable — consistency cannot be verified.")
    measurements = [round(float(d.get_measurement()), 3) for d in doc.modelspace().query("DIMENSION")]
    problems = []
    if not measurements:
        problems.append("the drawing contains no measurable DIMENSION entities")
    for name, value in core.items():
        if not any(abs(m - value) <= DXF_TOLERANCE_MM for m in measurements):
            problems.append(f"no dimension found for {name} ({_fmt(value, 0)} mm)")
    computed = (
        f"{len(measurements)} dimensions read back from ga.dxf via ezdxf; verified "
        + ", ".join(f"{n} {_fmt(v, 0)} mm" for n, v in core.items())
    )
    if problems:
        return _item(7, "Calc-vs-drawing consistency", clause, requirement, computed, limit,
                     SEVERITY_MAJOR, "; ".join(problems) + ".")
    return _item(7, "Calc-vs-drawing consistency", clause, requirement, computed, limit,
                 SEVERITY_PASS, "The principal dimensions read back from ga.dxf match the design.")


# --------------------------------------------------------------------------- assembly
def run_proof_check(
    *,
    params: MachineElementParams,
    geometry: MachineElementGeometry,
    analysis: MachineElementAnalysis,
    checks: list[CheckResult],
    ga_dxf_path: Path,
    out_dir: Path,
) -> MEProofResult:
    """Grade the checklist, run the cross-check, write compliance.json + bmd.svg."""
    params = coerce(MachineElementParams, params)
    geometry = coerce(MachineElementGeometry, geometry)
    analysis = coerce(MachineElementAnalysis, analysis)
    check_rows = [coerce(CheckResult, c) for c in checks]

    cross = _cross_check(params, geometry, analysis)
    items = _build_items(params, geometry, analysis, check_rows, cross, ga_dxf_path)
    verdict = (
        VERDICT_REVISION
        if any(i.severity == SEVERITY_MAJOR for i in items)
        else VERDICT_APPROVAL
    )
    result = MEProofResult(
        items=items,
        verdict=verdict,
        agreement_pct=cross.agreement_pct,
        cross_check=cross,
        grounding_text="\n".join(reference_lines(params, geometry, analysis)),
    )
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_compliance(result, out_dir)
    _write_diagram(analysis, out_dir)
    return result


def _write_compliance(result: MEProofResult, out_dir: Path) -> Path:
    payload = {
        "items": [item.model_dump() for item in result.items],
        "verdict": result.verdict,
        "fe_agreement_pct": result.agreement_pct,
    }
    path = out_dir / COMPLIANCE_FILENAME
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _write_diagram(analysis: MachineElementAnalysis, out_dir: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.0, 4.0))
    ax1.bar(["max stress", "permissible"],
            [analysis.max_stress_mpa, analysis.permissible_stress_mpa],
            color=["#c62828", "#1565c0"], alpha=0.7)
    ax1.set_title("Governing stress vs permissible")
    ax1.set_ylabel("stress, N/mm^2")

    labels = ["FoS", "required"]
    values = [analysis.factor_of_safety, analysis.required_fos]
    if analysis.fatigue_applicable:
        labels += ["fatigue FoS", "required"]
        values += [analysis.fatigue_fos, analysis.required_fatigue_fos]
    ax2.bar(labels, values, color=["#2e7d32", "#1565c0"] * 2, alpha=0.7)
    ax2.set_title("Factor of safety vs required")
    ax2.set_ylabel("factor of safety")

    fig.tight_layout()
    path = out_dir / BMD_FILENAME
    fig.savefig(path, format="svg")
    plt.close(fig)
    return path


# --------------------------------------------------------------------------- memo grounding
def _allowed_values(result: MEProofResult, extra_facts: str | None) -> list[float]:
    chunks: list[str] = []
    for item in result.items:
        chunks.append(str(item.item))
        chunks.extend((item.title, item.clause, item.requirement, item.computed, item.limit, item.detail))
    chunks.append(f"{result.agreement_pct}")
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
    narration_md: str, result: MEProofResult, *, extra_facts: str | None = None
) -> list[str]:
    """Grounding problems in ``narration_md`` — an empty list means it may be embedded."""
    if not narration_md or not narration_md.strip():
        return ["narration is empty"]
    problems: list[str] = []
    for pattern in _FORBIDDEN_CITATION_PATTERNS:
        match = pattern.search(narration_md)
        if match:
            problems.append(f"forbidden out-of-domain (bridge/road/concrete) citation '{match.group(0)}'")
    lowered = " ".join(narration_md.lower().split())
    opposite = (
        "recommended for approval" if result.verdict != VERDICT_APPROVAL else "return for revision"
    )
    if opposite in lowered:
        problems.append(
            f"narration states '{opposite}' but the rule-computed verdict is "
            f"'{result.verdict}' — the narration never grades or decides"
        )
    allowed = _allowed_values(result, extra_facts)
    for token in numeric_tokens(narration_md):
        if not _grounded(token, allowed):
            problems.append(f"numeric value '{token}' does not appear in the deterministic results")
    return problems


def memo_facts(
    result: MEProofResult,
    *,
    params: MachineElementParams,
    geometry: MachineElementGeometry,
    analysis: MachineElementAnalysis,
    warnings: Sequence[str] = (),
) -> str:
    counts = {s: 0 for s in _SEVERITY_ORDER}
    for item in result.items:
        counts[item.severity] = counts.get(item.severity, 0) + 1
    lines = [
        "# Proof-check facts (deterministic — narrate ONLY from these values)",
        "",
        "## Reference",
        *(f"- {line}" for line in reference_lines(params, geometry, analysis)),
        "",
        "## Verdict (computed by rule — the narration never grades)",
        f"- verdict: {result.verdict}",
        f"- independent strength cross-check agreement: {result.agreement_pct:g} %",
        (
            f"- items: {len(result.items)} total — {counts[SEVERITY_PASS]} pass, "
            f"{counts[SEVERITY_OBSERVATION]} observation, {counts[SEVERITY_MINOR]} minor, "
            f"{counts[SEVERITY_MAJOR]} major non-conformity"
        ),
        "",
        "## Checklist items",
    ]
    for item in result.items:
        lines.extend([
            f"### Item {item.item} — {item.title} [{item.severity}]",
            f"- clause: {item.clause}",
            f"- requirement: {item.requirement}",
            f"- computed: {item.computed}",
            f"- limit: {item.limit}",
            f"- detail: {item.detail}",
        ])
    lines.extend(["", "## Warnings on record"])
    lines.extend(f"- {w}" for w in warnings) if warnings else lines.append("- none")
    return "\n".join(lines)


def _clause_lead(clause: str) -> str:
    return clause.split(" — ")[0].strip()


def render_memo(
    result: MEProofResult,
    narration: str | None = None,
    *,
    params: MachineElementParams,
    geometry: MachineElementGeometry,
    analysis: MachineElementAnalysis,
    warnings: Sequence[str] = (),
) -> str:
    """The Proof Checking Consultant memo (markdown), deterministic-by-default."""
    facts = memo_facts(result, params=params, geometry=geometry, analysis=analysis, warnings=warnings)
    narration_block: str | None = None
    omission_note: str | None = None
    if narration is not None and narration.strip():
        problems = validate_narration(narration, result, extra_facts=facts)
        if problems:
            omission_note = (
                "> Note: an LLM-drafted narration was produced but has been omitted — it failed "
                "the deterministic grounding validation. The observations below are the "
                "unabridged deterministic findings."
            )
        else:
            narration_block = narration.strip()

    by_severity: dict[str, list[ChecklistItem]] = {s: [] for s in _SEVERITY_ORDER}
    for item in result.items:
        by_severity[item.severity].append(item)

    lines = [
        "# Proof Checking Consultant — Memorandum",
        "",
        "## Reference",
        "",
        *reference_lines(params, geometry, analysis),
        "",
        "## Scope of check",
        "",
        f"Deterministic {len(result.items)}-item proof-check of the submitted machine-element "
        "design, covering:",
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
                f"- Item {i.item} — {i.title}: {i.computed} (limit: {i.limit}). {i.detail}"
                for i in rows
            )
        else:
            lines.append("- None.")
        lines.append("")

    lines.extend(["## Recommendation", ""])
    if result.verdict == VERDICT_APPROVAL:
        lines.append(
            f"RECOMMENDED FOR APPROVAL — all {len(result.items)} checklist items conform or "
            "carry observations only; the independent strength cross-check agrees with the "
            f"recorded analysis to {result.agreement_pct:g} %."
        )
    else:
        majors = by_severity[SEVERITY_MAJOR]
        lines.append(
            "RETURN FOR REVISION — the design must not be taken forward until the following "
            "major non-conformities are resolved:"
        )
        lines.append("")
        lines.extend(
            f"- Item {i.item} — {i.title} ({_clause_lead(i.clause)}): {i.detail}" for i in majors
        )
    lines.append("")
    return "\n".join(lines)
