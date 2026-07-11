"""Proof-check spine for the fabricated rolling-stock member.

The SAME IR-protocol review as the other components: a deterministic checklist
grades every finding, an independent cross-check re-solves the section modulus and
the bending / shear / axial stresses from scratch, a rule computes the verdict
(any major non-conformity -> return_for_revision), and a grounded memo narrates
ONLY from the deterministic facts (no number in the memo may be absent from the
results; only the declared RDSO Specifications / IS 800 codes may be cited — IS 456
concrete and IRC road codes are forbidden).

Reuses the shared `ChecklistItem` / severity / verdict / compliance-filename
constants (`proofcheck.checklist`) so the frontend compliance matrix renders the
member review unchanged. Writes `compliance.json` and a bending-moment/shear
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
from components.rolling_stock_member._engine_common import (
    STEEL_PERMISSIBLE,
    STEEL_UNIT_WEIGHT_KN_M3,
    VERTICAL_IMPACT_FACTOR,
    permissible,
    section_properties,
)
from components.rolling_stock_member.analysis import RollingStockMemberAnalysis
from components.rolling_stock_member.params import (
    RollingStockMemberGeometry,
    RollingStockMemberParams,
    member_kind_label,
)
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

# The rolling-stock member declares RDSO Specifications + IS 800. Concrete (IS 456)
# and road-congress (IRC) citations are defects. Patterns are assembled by
# concatenation so this file never greps as a violation.
_FORBIDDEN_CITATION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (r"\bI" + r"S\s*[:.\-]?\s*456\b", r"\bI" + r"RC\b")
)


class SectionCrossCheck(BaseModel):
    """Independent re-solve of the section modulus + stresses vs the recorded analysis."""

    method: str = Field(description="Independent recomputation method")
    section_modulus_cm3: float
    max_bending_stress_mpa: float
    max_shear_stress_mpa: float
    max_axial_stress_mpa: float
    agreement_pct: float = Field(description="100 - worst relative deviation, %")
    tolerance_pct: float
    within_tolerance: bool


class RSMProofResult(BaseModel):
    """run_proof_check output — graded items, rule-computed verdict, cross-check, grounding."""

    items: list[ChecklistItem]
    verdict: str
    agreement_pct: float
    cross_check: SectionCrossCheck
    grounding_text: str = ""


# --------------------------------------------------------------------------- reference / facts
def reference_lines(
    params: RollingStockMemberParams,
    geometry: RollingStockMemberGeometry,
    analysis: RollingStockMemberAnalysis,
) -> list[str]:
    return [
        (
            f"Fabricated rolling-stock member ({member_kind_label(geometry.member_kind)}) — "
            f"length {geometry.member_length_mm:g} mm, overall depth "
            f"{geometry.overall_depth_mm:g} mm, web {geometry.web_depth_mm:g} x "
            f"{geometry.web_thickness_mm:g} mm, flanges {geometry.flange_width_mm:g} x "
            f"{geometry.flange_thickness_mm:g} mm, {geometry.weld_size_mm:g} mm fillet welds, "
            f"{params.steel_grade} steel."
        ),
        (
            f"RDSO load cases per member: vertical design moment {analysis.design_moment_knm:g} "
            f"kN*m (dead {analysis.dead_moment_knm:g}, payload+impact {analysis.live_moment_knm:g}, "
            f"impact factor {analysis.impact_factor:g}), design shear {analysis.design_shear_kn:g} "
            f"kN; longitudinal buffing load {analysis.buffing_load_kn:g} kN; section modulus "
            f"{analysis.section_modulus_cm3:g} cm^3."
        ),
        (
            f"Stresses: bending {analysis.max_bending_stress_mpa:g} N/mm^2 (permissible "
            f"{analysis.permissible_bending_stress_mpa:g}), web shear "
            f"{analysis.max_shear_stress_mpa:g} N/mm^2 (permissible "
            f"{analysis.permissible_shear_stress_mpa:g}), axial {analysis.max_axial_stress_mpa:g} "
            f"N/mm^2 (permissible {analysis.permissible_axial_stress_mpa:g}); combined interaction "
            f"{analysis.interaction_ratio:g} (limit {analysis.interaction_limit:g}); governing case "
            f"{analysis.governing_load_case}."
        ),
    ]


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
    params: RollingStockMemberParams,
    geometry: RollingStockMemberGeometry,
    analysis: RollingStockMemberAnalysis,
) -> SectionCrossCheck:
    """Recompute the section modulus + stresses independently from the geometry."""
    section = section_properties(
        web_depth_mm=geometry.web_depth_mm,
        web_thickness_mm=geometry.web_thickness_mm,
        flange_width_mm=geometry.flange_width_mm,
        flange_thickness_mm=geometry.flange_thickness_mm,
    )
    z_cm3 = section.section_modulus_mm3 / 1000.0
    bending = analysis.design_moment_knm * 1e6 / section.section_modulus_mm3
    web_area = geometry.web_depth_mm * geometry.web_thickness_mm
    shear = analysis.design_shear_kn * 1e3 / web_area
    axial = analysis.buffing_load_kn * 1e3 / section.area_mm2

    pairs = [
        (analysis.section_modulus_cm3, z_cm3),
        (analysis.max_bending_stress_mpa, bending),
        (analysis.max_shear_stress_mpa, shear),
        (analysis.max_axial_stress_mpa, axial),
    ]
    worst = 0.0
    for recorded, recomputed in pairs:
        if abs(recorded) > 1e-9:
            worst = max(worst, abs(recomputed - recorded) / abs(recorded) * 100.0)
    return SectionCrossCheck(
        method="Independent re-solve of the welded-I section modulus and the M/Z, V/(d*t), P/A stresses",
        section_modulus_cm3=round(z_cm3, 2),
        max_bending_stress_mpa=round(bending, 3),
        max_shear_stress_mpa=round(shear, 3),
        max_axial_stress_mpa=round(axial, 3),
        agreement_pct=round(100.0 - worst, 3),
        tolerance_pct=TOLERANCE_PCT,
        within_tolerance=worst <= TOLERANCE_PCT,
    )


def _build_items(
    params: RollingStockMemberParams,
    geometry: RollingStockMemberGeometry,
    analysis: RollingStockMemberAnalysis,
    checks: list[CheckResult],
    cross: SectionCrossCheck,
    ga_dxf_path: Path,
) -> list[ChecklistItem]:
    items: list[ChecklistItem] = []

    # 1 — design basis & transcription honesty
    grade_known = params.steel_grade in STEEL_PERMISSIBLE
    perm = permissible(params.steel_grade) if grade_known else None
    items.append(_item(
        1, "Design basis & code transcription",
        "RDSO Specifications / IS 800",
        "The member must be designed to RDSO wagon-design load cases with IS 800 "
        "working-stress section practice, with a stated, verifiable basis for the "
        "permissible stresses and the RDSO design loads.",
        f"{params.steel_grade} steel: permissible bending {perm.sigma_bending_n_mm2:g}, shear "
        f"{perm.sigma_shear_n_mm2:g}, axial {perm.sigma_axial_n_mm2:g} N/mm^2; RDSO vertical "
        f"impact factor {VERTICAL_IMPACT_FACTOR:g}, buffing load {analysis.buffing_load_kn:g} kN."
        if perm else f"steel grade {params.steel_grade} has no transcribed permissible-stress row.",
        "grade carries transcribed permissible stresses; RDSO load basis cited",
        SEVERITY_OBSERVATION if grade_known else SEVERITY_MAJOR,
        "HONESTY NOTE: the IS 800 working-stress permissible bending (~0.66 fy), shear "
        "(~0.40 fy) and axial (~0.60 fy) stresses and the RDSO wagon-design vertical "
        "dynamic-augment factor and buffing-load magnitudes are transcribed for the POC and "
        "pending digit-for-digit verification against the source RDSO specification and IS 800 "
        "(IR engineer pre-review before demo day) — graded OBSERVATION, not silently passed."
        if grade_known else
        f"Steel grade {params.steel_grade} has no transcribed permissible-stress row.",
    ))

    # 2 — RDSO load-case re-derivation
    items.append(_load_case_item(params, geometry, analysis))

    # 3 — bending stress adequacy
    bending = _find(checks, kind="bending")
    items.append(_item(
        3, "Bending stress adequacy", bending.clause if bending else "IS 800",
        "Extreme-fibre bending stress (vertical payload case) within the permissible bending stress.",
        bending.computed if bending else "no recorded bending row",
        bending.limit if bending else "-",
        _severity_from_check(bending, on_fail=SEVERITY_MAJOR),
        "Bending stress is within the permissible value." if bending and bending.status == "PASS"
        else "The extreme-fibre bending stress exceeds the permissible value — a strength "
             "non-conformity in the MEMBER flanges (under-designed section modulus).",
    ))

    # 4 — shear stress adequacy
    shear = _find(checks, kind="shear")
    items.append(_item(
        4, "Web shear adequacy", shear.clause if shear else "IS 800",
        "Average web shear stress (vertical payload case) within the permissible shear stress.",
        shear.computed if shear else "no recorded shear row",
        shear.limit if shear else "-",
        _severity_from_check(shear, on_fail=SEVERITY_MAJOR),
        "Web shear stress is within the permissible value." if shear and shear.status == "PASS"
        else "The average web shear stress exceeds the permissible value — a strength "
             "non-conformity in the WEB (under-designed web thickness).",
    ))

    # 5 — axial (buffing) adequacy
    axial = _find(checks, kind="axial")
    items.append(_item(
        5, "Axial buffing adequacy", axial.clause if axial else "IS 800",
        "Gross-section axial stress (longitudinal buffing case) within the permissible axial stress.",
        axial.computed if axial else "no recorded axial row",
        axial.limit if axial else "-",
        _severity_from_check(axial, on_fail=SEVERITY_MAJOR),
        "Axial buffing stress is within the permissible value." if axial and axial.status == "PASS"
        else "The gross-section axial (buffing) stress exceeds the permissible value — a strength "
             "non-conformity in the MEMBER (under-designed cross-sectional area).",
    ))

    # 6 — combined axial + bending interaction
    combined = _find(checks, kind="combined")
    items.append(_item(
        6, "Combined axial + bending interaction", combined.clause if combined else "IS 800",
        "Combined axial+bending interaction ratio within the unity (1.0) limit.",
        combined.computed if combined else "no recorded combined row",
        combined.limit if combined else "-",
        _severity_from_check(combined, on_fail=SEVERITY_MAJOR),
        "The combined interaction ratio is within unity." if combined and combined.status == "PASS"
        else "The combined axial+bending interaction ratio exceeds unity — the section is "
             "inadequate for simultaneous vertical payload and longitudinal buffing (a strength "
             "non-conformity in the MEMBER).",
    ))

    # 7 — welds & fatigue (observation)
    fatigue = _find(checks, kind="weld_fatigue")
    items.append(_item(
        7, "Welds & fatigue of welded details", fatigue.clause if fatigue else "RDSO Specifications",
        "The fillet welds and welded details require detailed sizing and a fatigue (S-N) assessment.",
        fatigue.computed if fatigue else "welds/fatigue not evaluated",
        fatigue.limit if fatigue else "-",
        SEVERITY_OBSERVATION,
        "HONESTY NOTE: detailed fillet-weld sizing / length and a full fatigue assessment of the "
        "welded details (stress range vs the S-N detail category) under repeated wagon loading are "
        "beyond this POC scope — flagged as an observation for the detailed design stage, not "
        "silently passed.",
    ))

    # 8 — independent section cross-check
    items.append(_item(
        8, "Independent section cross-check", cross.method,
        "An independent re-solve of the section modulus and the M/Z, V/(d*t), P/A stresses must "
        "agree with the recorded analysis within the stated tolerance.",
        f"independent Z {_fmt(cross.section_modulus_cm3, 1)} cm^3, bending "
        f"{_fmt(cross.max_bending_stress_mpa, 1)} N/mm^2, shear "
        f"{_fmt(cross.max_shear_stress_mpa, 1)} N/mm^2, axial "
        f"{_fmt(cross.max_axial_stress_mpa, 1)} N/mm^2; agreement {_fmt(cross.agreement_pct, 2)} %",
        f"within +/-{TOLERANCE_PCT:g}% of the recorded analysis",
        SEVERITY_PASS if cross.within_tolerance else SEVERITY_MAJOR,
        "The independent re-solve reproduces the recorded section modulus and stresses."
        if cross.within_tolerance
        else "The independent re-solve disagrees with the recorded section modulus / stresses.",
    ))

    # 9 — calc-vs-drawing (DXF read-back)
    items.append(_dxf_item(geometry, ga_dxf_path))
    return items


def _load_case_item(
    params: RollingStockMemberParams,
    geometry: RollingStockMemberGeometry,
    analysis: RollingStockMemberAnalysis,
) -> ChecklistItem:
    requirement = (
        "The recorded vertical design moment/shear and the longitudinal buffing load must equal "
        "an independent re-derivation from the member geometry, the design loads and the RDSO "
        "vertical impact factor."
    )
    limit = "recorded vertical M / V and buffing P equal the independent re-derivation (exact)"
    clause = (
        "RDSO Specifications — wagon vertical (payload + dynamic augment) and longitudinal "
        "buffing / draft load cases"
    )
    span_m = geometry.member_length_mm / 1000.0
    section = section_properties(
        web_depth_mm=geometry.web_depth_mm,
        web_thickness_mm=geometry.web_thickness_mm,
        flange_width_mm=geometry.flange_width_mm,
        flange_thickness_mm=geometry.flange_thickness_mm,
    )
    self_weight = section.area_mm2 * 1e-6 * STEEL_UNIT_WEIGHT_KN_M3
    m_indep = (
        self_weight * span_m**2 / 8.0
        + VERTICAL_IMPACT_FACTOR * params.design_vertical_load_kn * span_m / 8.0
    )
    v_indep = (
        self_weight * span_m / 2.0
        + VERTICAL_IMPACT_FACTOR * params.design_vertical_load_kn / 2.0
    )
    p_indep = params.design_buffing_load_kn

    problems: list[str] = []
    for label, recorded, recomputed in (
        ("vertical M", analysis.design_moment_knm, m_indep),
        ("vertical V", analysis.design_shear_kn, v_indep),
        ("buffing P", analysis.buffing_load_kn, p_indep),
    ):
        if not math.isclose(recorded, recomputed, rel_tol=1e-3, abs_tol=1e-3):
            problems.append(f"{label} recorded {_fmt(recorded, 2)} vs re-derived {_fmt(recomputed, 2)}")
    computed = (
        f"re-derived vertical M {_fmt(m_indep, 1)} kN*m, V {_fmt(v_indep, 1)} kN "
        f"(impact {VERTICAL_IMPACT_FACTOR:g}), buffing P {_fmt(p_indep, 1)} kN"
    )
    if problems:
        return _item(2, "RDSO load-case re-derivation", clause, requirement, computed, limit,
                     SEVERITY_MAJOR, "; ".join(problems) + ".")
    return _item(2, "RDSO load-case re-derivation", clause, requirement, computed, limit,
                 SEVERITY_PASS,
                 "Recorded vertical moment/shear and the buffing load re-derived independently "
                 "from the geometry, the design loads and the RDSO impact factor — match. (The "
                 "transcribed RDSO magnitudes themselves remain flagged for pre-demo verification; "
                 "see item 1.)")


def _dxf_item(geometry: RollingStockMemberGeometry, ga_dxf_path: Path) -> ChecklistItem:
    requirement = (
        "Dimensions read back from the produced fabrication drawing must match the designed "
        f"geometry — at least the member length and overall depth within +/-{DXF_TOLERANCE_MM:g} mm."
    )
    limit = f"principal dimensions match within +/-{DXF_TOLERANCE_MM:g} mm"
    clause = "Calc-vs-drawing consistency — every issued dimension matches the designed geometry"
    core = {
        "member length": geometry.member_length_mm,
        "overall depth": geometry.overall_depth_mm,
    }
    try:
        doc = ezdxf.readfile(Path(ga_dxf_path))
    except (IOError, OSError, ezdxf.DXFError) as error:
        return _item(9, "Calc-vs-drawing consistency", clause, requirement,
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
        return _item(9, "Calc-vs-drawing consistency", clause, requirement, computed, limit,
                     SEVERITY_MAJOR, "; ".join(problems) + ".")
    return _item(9, "Calc-vs-drawing consistency", clause, requirement, computed, limit,
                 SEVERITY_PASS, "Member length and overall depth read back from ga.dxf match the design.")


# --------------------------------------------------------------------------- assembly
def run_proof_check(
    *,
    params: RollingStockMemberParams,
    geometry: RollingStockMemberGeometry,
    analysis: RollingStockMemberAnalysis,
    checks: list[CheckResult],
    ga_dxf_path: Path,
    out_dir: Path,
) -> RSMProofResult:
    """Grade the checklist, run the cross-check, write compliance.json + bmd.svg."""
    params = coerce(RollingStockMemberParams, params)
    geometry = coerce(RollingStockMemberGeometry, geometry)
    analysis = coerce(RollingStockMemberAnalysis, analysis)
    check_rows = [coerce(CheckResult, c) for c in checks]

    cross = _cross_check(params, geometry, analysis)
    items = _build_items(params, geometry, analysis, check_rows, cross, ga_dxf_path)
    verdict = (
        VERDICT_REVISION
        if any(i.severity == SEVERITY_MAJOR for i in items)
        else VERDICT_APPROVAL
    )
    result = RSMProofResult(
        items=items,
        verdict=verdict,
        agreement_pct=cross.agreement_pct,
        cross_check=cross,
        grounding_text="\n".join(reference_lines(params, geometry, analysis)),
    )
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_compliance(result, out_dir)
    _write_bmd_diagram(analysis, out_dir)
    return result


def _write_compliance(result: RSMProofResult, out_dir: Path) -> Path:
    payload = {
        "items": [item.model_dump() for item in result.items],
        "verdict": result.verdict,
        "fe_agreement_pct": result.agreement_pct,
    }
    path = out_dir / COMPLIANCE_FILENAME
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _write_bmd_diagram(analysis: RollingStockMemberAnalysis, out_dir: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    span = analysis.member_length_m
    m_mid = analysis.design_moment_knm
    v_end = analysis.design_shear_kn

    xs = [i * span / 20.0 for i in range(21)]
    # parabolic BM shape scaled to the design mid-span moment (vertical payload case)
    moments = [4.0 * m_mid * x * (span - x) / span**2 if span else 0.0 for x in xs]
    # linear SF shape scaled to the design end shear
    shears = [v_end * (1.0 - 2.0 * x / span) if span else 0.0 for x in xs]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.0, 4.0))
    ax1.fill_between(xs, moments, color="#1565c0", alpha=0.25)
    ax1.plot(xs, moments, color="#1565c0")
    ax1.plot([0.0, span], [0.0, 0.0], color="black", linewidth=1)
    ax1.set_title("Bending moment (vertical payload case)")
    ax1.set_xlabel("distance along member, m")
    ax1.set_ylabel("moment, kN*m")
    ax1.annotate(f"M_max = {m_mid:.0f}", (span / 2.0, m_mid))
    ax2.fill_between(xs, shears, color="#c62828", alpha=0.25)
    ax2.plot(xs, shears, color="#c62828")
    ax2.plot([0.0, span], [0.0, 0.0], color="black", linewidth=1)
    ax2.set_title("Shear force (vertical payload case)")
    ax2.set_xlabel("distance along member, m")
    ax2.set_ylabel("shear, kN")
    ax2.annotate(f"V_end = {v_end:.0f}", (0.0, v_end))
    fig.tight_layout()
    path = out_dir / BMD_FILENAME
    fig.savefig(path, format="svg")
    plt.close(fig)
    return path


# --------------------------------------------------------------------------- memo grounding
def _allowed_values(result: RSMProofResult, extra_facts: str | None) -> list[float]:
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
    narration_md: str, result: RSMProofResult, *, extra_facts: str | None = None
) -> list[str]:
    """Grounding problems in ``narration_md`` — an empty list means it may be embedded."""
    if not narration_md or not narration_md.strip():
        return ["narration is empty"]
    problems: list[str] = []
    for pattern in _FORBIDDEN_CITATION_PATTERNS:
        match = pattern.search(narration_md)
        if match:
            problems.append(f"forbidden non-declared-code citation '{match.group(0)}'")
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
    result: RSMProofResult,
    *,
    params: RollingStockMemberParams,
    geometry: RollingStockMemberGeometry,
    analysis: RollingStockMemberAnalysis,
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
        f"- independent section cross-check agreement: {result.agreement_pct:g} %",
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
    result: RSMProofResult,
    narration: str | None = None,
    *,
    params: RollingStockMemberParams,
    geometry: RollingStockMemberGeometry,
    analysis: RollingStockMemberAnalysis,
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
        f"Deterministic {len(result.items)}-item proof-check of the submitted rolling-stock "
        "member design, covering:",
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
            "carry observations only; the independent section cross-check agrees with the "
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
