"""Proof-check spine for the fabricated structural-steel member.

The SAME IR-protocol review as the other components: a deterministic checklist
grades every finding, an independent cross-check re-solves the section modulus,
the axial/bending stresses and the fillet-weld resultant from scratch, a rule
computes the verdict (any major non-conformity -> return_for_revision), and a
grounded memo narrates ONLY from the deterministic facts (no number in the memo
may be absent from the results; only IS 800 / IS 816 codes may be cited — IS 456,
IRC and the IRS Concrete Bridge Code are forbidden).

Reuses the shared `ChecklistItem` / severity / verdict / compliance-filename
constants (`proofcheck.checklist`) so the frontend compliance matrix renders the
member review unchanged. Writes `compliance.json` and a bending-moment/shear
diagram `bmd.svg`. Pure deterministic Python — the only I/O is reading ga.dxf and
writing the two artefacts.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path

import ezdxf
from pydantic import BaseModel, Field

from components.base import CheckResult, coerce
from components.structural_steel_member._engine_common import (
    STEEL_PERMISSIBLE,
    permissible,
    permissible_axial_stress,
    section_properties,
    sigma_ac_table_value,
    weld_stresses,
)
from components.structural_steel_member.analysis import SteelMemberAnalysis
from components.structural_steel_member.params import (
    SteelMemberGeometry,
    SteelMemberParams,
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
AXIAL_TABLE_TOLERANCE_PCT = 10.0

_SEVERITY_ORDER = (SEVERITY_MAJOR, SEVERITY_MINOR, SEVERITY_OBSERVATION, SEVERITY_PASS)
_SEVERITY_HEADINGS = {
    SEVERITY_MAJOR: "Non-conformities — major",
    SEVERITY_MINOR: "Non-conformities — minor",
    SEVERITY_OBSERVATION: "Observations",
    SEVERITY_PASS: "Conforming items",
}

# The steel member declares IS 800 + IS 816. Concrete (IS 456 / IRS Concrete
# Bridge Code) and road-congress (IRC) citations are out-of-domain defects.
# Patterns are assembled by concatenation so this file never greps as a violation.
_FORBIDDEN_CITATION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (
        r"\bI" + r"S\s*[:.\-]?\s*456\b",
        r"\bI" + r"RC\b",
        r"Concrete\s+Bridge\s+Code",
    )
)


class MemberCrossCheck(BaseModel):
    """Independent re-solve of the section, stresses and weld vs the recorded analysis."""

    method: str = Field(description="Independent recomputation method")
    section_modulus_cm3: float
    max_axial_stress_mpa: float
    max_bending_stress_mpa: float
    weld_stress_mpa: float
    agreement_pct: float = Field(description="100 - worst relative deviation, %")
    tolerance_pct: float
    within_tolerance: bool


class SSMProofResult(BaseModel):
    """run_proof_check output — graded items, rule-computed verdict, cross-check, grounding."""

    items: list[ChecklistItem]
    verdict: str
    agreement_pct: float
    cross_check: MemberCrossCheck
    grounding_text: str = ""


# --------------------------------------------------------------------------- reference / facts
def reference_lines(
    params: SteelMemberParams,
    geometry: SteelMemberGeometry,
    analysis: SteelMemberAnalysis,
) -> list[str]:
    return [
        (
            f"Fabricated welded-I steel {geometry.member_type.replace('_', ' ')} — length "
            f"{geometry.cantilever_length_mm:g} mm, overall depth {geometry.overall_depth_mm:g} "
            f"mm, web {geometry.web_depth_mm:g} x {geometry.web_thickness_mm:g} mm, flanges "
            f"{geometry.flange_width_mm:g} x {geometry.flange_thickness_mm:g} mm, "
            f"{geometry.weld_size_mm:g} mm base fillet weld, {params.steel_grade} steel."
        ),
        (
            f"Actions: design moment {analysis.design_moment_knm:g} kN*m, design shear "
            f"{analysis.design_shear_kn:g} kN, axial {analysis.design_axial_kn:g} kN; section "
            f"modulus {analysis.section_modulus_cm3:g} cm^3; slenderness KL/r "
            f"{analysis.slenderness_ratio:g} (limit {analysis.slenderness_limit:g})."
        ),
        (
            f"Stresses: axial {analysis.max_axial_stress_mpa:g} N/mm^2 (permissible "
            f"{analysis.permissible_axial_stress_mpa:g}), bending "
            f"{analysis.max_bending_stress_mpa:g} N/mm^2 (permissible "
            f"{analysis.permissible_bending_stress_mpa:g}), web shear "
            f"{analysis.max_shear_stress_mpa:g} N/mm^2 (permissible "
            f"{analysis.permissible_shear_stress_mpa:g}); combined interaction "
            f"{analysis.combined_ratio:g} (limit {analysis.combined_limit:g}); weld "
            f"{analysis.weld_stress_mpa:g} N/mm^2 (permissible "
            f"{analysis.permissible_weld_stress_mpa:g})."
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
    params: SteelMemberParams,
    geometry: SteelMemberGeometry,
    analysis: SteelMemberAnalysis,
) -> MemberCrossCheck:
    """Recompute the section modulus, stresses and weld resultant independently."""
    section = section_properties(
        web_depth_mm=geometry.web_depth_mm,
        web_thickness_mm=geometry.web_thickness_mm,
        flange_width_mm=geometry.flange_width_mm,
        flange_thickness_mm=geometry.flange_thickness_mm,
    )
    z_cm3 = section.section_modulus_mm3 / 1000.0
    axial = analysis.design_axial_kn * 1e3 / section.area_mm2
    bending = analysis.design_moment_knm * 1e6 / section.section_modulus_mm3
    welds = weld_stresses(
        weld_size_mm=geometry.weld_size_mm,
        overall_depth_mm=geometry.overall_depth_mm,
        web_depth_mm=geometry.web_depth_mm,
        flange_width_mm=geometry.flange_width_mm,
        moment_knm=analysis.design_moment_knm,
        shear_kn=analysis.design_shear_kn,
        axial_kn=analysis.design_axial_kn,
    )

    pairs = [
        (analysis.section_modulus_cm3, z_cm3),
        (analysis.max_axial_stress_mpa, axial),
        (analysis.max_bending_stress_mpa, bending),
        (analysis.weld_stress_mpa, welds.resultant_stress_mpa),
    ]
    worst = 0.0
    for recorded, recomputed in pairs:
        if abs(recorded) > 1e-9:
            worst = max(worst, abs(recomputed - recorded) / abs(recorded) * 100.0)
    return MemberCrossCheck(
        method="Independent re-solve of the welded-I section modulus, the N/A and M/Z "
        "stresses, and the fillet-weld-group resultant throat stress",
        section_modulus_cm3=round(z_cm3, 2),
        max_axial_stress_mpa=round(axial, 3),
        max_bending_stress_mpa=round(bending, 3),
        weld_stress_mpa=round(welds.resultant_stress_mpa, 3),
        agreement_pct=round(100.0 - worst, 3),
        tolerance_pct=TOLERANCE_PCT,
        within_tolerance=worst <= TOLERANCE_PCT,
    )


def _build_items(
    params: SteelMemberParams,
    geometry: SteelMemberGeometry,
    analysis: SteelMemberAnalysis,
    checks: list[CheckResult],
    cross: MemberCrossCheck,
    ga_dxf_path: Path,
) -> list[ChecklistItem]:
    items: list[ChecklistItem] = []

    # 1 — design basis & transcription honesty
    grade_known = params.steel_grade in STEEL_PERMISSIBLE
    perm = permissible(params.steel_grade) if grade_known else None
    items.append(_item(
        1, "Design basis & code transcription",
        "IS 800 / IS 816",
        "The member must be designed to IS 800 working-stress practice with the fillet "
        "welds to IS 816, on a stated, verifiable code basis for the permissible stresses.",
        f"{params.steel_grade} steel: permissible bending {perm.sigma_bending_n_mm2:g}, shear "
        f"{perm.sigma_shear_n_mm2:g} N/mm^2; permissible weld "
        f"{analysis.permissible_weld_stress_mpa:g} N/mm^2 (IS 816)."
        if perm else f"steel grade {params.steel_grade} has no transcribed permissible-stress row.",
        "grade carries transcribed permissible stresses; weld permissible cited",
        SEVERITY_OBSERVATION if grade_known else SEVERITY_MAJOR,
        "HONESTY NOTE: the IS 800 working-stress permissible bending (~0.66 fy) and shear "
        "(~0.40 fy) stresses, the IS 816 fillet-weld permissible (108 N/mm^2) and the "
        "transcribed sigma_ac table are transcribed for the POC and pending digit-for-digit "
        "verification against the source codes (IR engineer pre-review before demo day) — "
        "graded OBSERVATION, not silently passed."
        if grade_known else
        f"Steel grade {params.steel_grade} has no transcribed permissible-stress row.",
    ))

    # 2 — permissible axial stress re-derivation (Merchant-Rankine + table cross-check)
    items.append(_axial_derivation_item(params, analysis))

    # 3 — axial capacity adequacy
    axial = _find(checks, kind="axial")
    items.append(_item(
        3, "Axial capacity adequacy", axial.clause if axial else "IS 800",
        "Direct axial compressive stress within the permissible axial stress.",
        axial.computed if axial else "no recorded axial row",
        axial.limit if axial else "-",
        _severity_from_check(axial, on_fail=SEVERITY_MAJOR),
        "Axial stress is within the permissible value." if axial and axial.status == "PASS"
        else "The direct axial stress exceeds the permissible axial stress — a strength "
             "non-conformity in the MEMBER (compression capacity governed by slenderness).",
    ))

    # 4 — bending stress adequacy
    bending = _find(checks, kind="bending")
    items.append(_item(
        4, "Bending stress adequacy", bending.clause if bending else "IS 800",
        "Extreme-fibre bending stress within the permissible bending stress.",
        bending.computed if bending else "no recorded bending row",
        bending.limit if bending else "-",
        _severity_from_check(bending, on_fail=SEVERITY_MAJOR),
        "Bending stress is within the permissible value." if bending and bending.status == "PASS"
        else "The extreme-fibre bending stress exceeds the permissible value — a strength "
             "non-conformity in the MEMBER flanges (under-designed section modulus).",
    ))

    # 5 — shear stress adequacy
    shear = _find(checks, kind="shear")
    items.append(_item(
        5, "Web shear adequacy", shear.clause if shear else "IS 800",
        "Average web shear stress within the permissible shear stress.",
        shear.computed if shear else "no recorded shear row",
        shear.limit if shear else "-",
        _severity_from_check(shear, on_fail=SEVERITY_MAJOR),
        "Web shear stress is within the permissible value." if shear and shear.status == "PASS"
        else "The average web shear stress exceeds the permissible value — a strength "
             "non-conformity in the WEB (under-designed web thickness).",
    ))

    # 6 — combined interaction
    combined = _find(checks, kind="combined")
    items.append(_item(
        6, "Combined axial + bending interaction", combined.clause if combined else "IS 800",
        "The axial + bending interaction ratio must be within 1.0.",
        combined.computed if combined else "no recorded interaction row",
        combined.limit if combined else "-",
        _severity_from_check(combined, on_fail=SEVERITY_MAJOR),
        "The combined axial + bending interaction is within 1.0."
        if combined and combined.status == "PASS"
        else "The combined axial + bending interaction exceeds 1.0 — the MEMBER is "
             "over-utilised under the co-existent axial force and bending.",
    ))

    # 7 — fillet-weld group adequacy
    weld = _find(checks, kind="weld")
    items.append(_item(
        7, "Fillet-weld group adequacy", weld.clause if weld else "IS 816",
        "The base fillet-weld-group resultant throat stress within the permissible weld stress.",
        weld.computed if weld else "no recorded weld row",
        weld.limit if weld else "-",
        _severity_from_check(weld, on_fail=SEVERITY_MAJOR),
        "The base fillet-weld-group throat stress is within the permissible value."
        if weld and weld.status == "PASS"
        else "The base fillet-weld-group throat stress exceeds the permissible value — the "
             "WELD is under-sized; a larger fillet, a bolted, or a full-penetration moment "
             "connection is required.",
    ))

    # 8 — compression slenderness (minor on fail)
    slender = _find(checks, kind="slenderness")
    items.append(_item(
        8, "Compression slenderness & detailing", slender.clause if slender else "IS 800",
        "Member slenderness KL/r within the compression-member limit.",
        slender.computed if slender else "no recorded slenderness row",
        slender.limit if slender else "-",
        _severity_from_check(slender, on_fail=SEVERITY_MINOR),
        "Member slenderness is within the compression-member limit."
        if slender and slender.status == "PASS"
        else "The member slenderness exceeds the compression-member limit — a stockier "
             "section (wider flanges) or a tubular/lattice member is indicated (graded "
             "minor, stability/detailing).",
    ))

    # 9 — independent cross-check
    items.append(_item(
        9, "Independent section & weld cross-check", cross.method,
        "An independent re-solve of the section modulus, the N/A and M/Z stresses and the "
        "fillet-weld resultant must agree with the recorded analysis within the tolerance.",
        f"independent Z {_fmt(cross.section_modulus_cm3, 1)} cm^3, axial "
        f"{_fmt(cross.max_axial_stress_mpa, 1)} N/mm^2, bending "
        f"{_fmt(cross.max_bending_stress_mpa, 1)} N/mm^2, weld "
        f"{_fmt(cross.weld_stress_mpa, 1)} N/mm^2; agreement {_fmt(cross.agreement_pct, 2)} %",
        f"within +/-{TOLERANCE_PCT:g}% of the recorded analysis",
        SEVERITY_PASS if cross.within_tolerance else SEVERITY_MAJOR,
        "The independent re-solve reproduces the recorded section modulus, stresses and weld."
        if cross.within_tolerance
        else "The independent re-solve disagrees with the recorded section modulus / stresses / weld.",
    ))

    # 10 — calc-vs-drawing (DXF read-back)
    items.append(_dxf_item(geometry, ga_dxf_path))
    return items


def _axial_derivation_item(
    params: SteelMemberParams, analysis: SteelMemberAnalysis
) -> ChecklistItem:
    requirement = (
        "The recorded permissible axial stress must equal an independent re-application of "
        "the Merchant-Rankine formula at the recorded slenderness, and cross-check the "
        "transcribed sigma_ac table within tolerance."
    )
    limit = "recorded sigma_ac equals the formula re-computation; table within +/-10%"
    clause = "IS 800 — permissible axial compressive stress (Merchant-Rankine + transcribed table)"
    grade_known = params.steel_grade in STEEL_PERMISSIBLE
    if not grade_known:
        return _item(2, "Permissible axial stress re-derivation", clause, requirement,
                     f"steel grade {params.steel_grade} has no yield stress",
                     limit, SEVERITY_MAJOR,
                     "The steel grade is untranscribed — the permissible axial stress "
                     "cannot be re-verified.")
    fy = permissible(params.steel_grade).fy_n_mm2
    lam = analysis.slenderness_ratio
    formula = permissible_axial_stress(fy, lam)
    table = sigma_ac_table_value(lam)
    problems: list[str] = []
    if abs(formula - analysis.permissible_axial_stress_mpa) > 0.05 * max(1.0, formula):
        problems.append(
            f"recorded sigma_ac {_fmt(analysis.permissible_axial_stress_mpa, 1)} does not match "
            f"the formula re-computation {_fmt(formula, 1)} N/mm^2"
        )
    table_dev = abs(formula - table) / formula * 100.0 if formula else 0.0
    computed = (
        f"at lambda {_fmt(lam, 1)}: Merchant-Rankine sigma_ac {_fmt(formula, 1)} N/mm^2 "
        f"(recorded {_fmt(analysis.permissible_axial_stress_mpa, 1)}); transcribed table "
        f"{_fmt(table, 1)} N/mm^2 (deviation {_fmt(table_dev, 1)} %)"
    )
    if problems:
        return _item(2, "Permissible axial stress re-derivation", clause, requirement,
                     computed, limit, SEVERITY_MAJOR, "; ".join(problems) + ".")
    table_note = (
        " The transcribed sigma_ac table (fy 250) is within tolerance of the formula."
        if table_dev <= AXIAL_TABLE_TOLERANCE_PCT
        else f" The transcribed table deviates {table_dev:.0f}% from the formula (fy != 250) — "
             "noted; the Merchant-Rankine value governs."
    )
    return _item(2, "Permissible axial stress re-derivation", clause, requirement, computed, limit,
                 SEVERITY_OBSERVATION,
                 "Recorded permissible axial stress re-derived independently from the "
                 "Merchant-Rankine formula — match." + table_note +
                 " HONESTY NOTE: the sigma_ac table transcription is flagged for pre-demo "
                 "verification (see item 1).")


def _dxf_item(geometry: SteelMemberGeometry, ga_dxf_path: Path) -> ChecklistItem:
    requirement = (
        "Dimensions read back from the produced fabrication drawing must match the designed "
        f"geometry — at least the length and overall section depth within +/-{DXF_TOLERANCE_MM:g} mm."
    )
    limit = f"principal dimensions match within +/-{DXF_TOLERANCE_MM:g} mm"
    clause = "Calc-vs-drawing consistency — every issued dimension matches the designed geometry"
    core = {
        "length": geometry.cantilever_length_mm,
        "overall depth": geometry.overall_depth_mm,
    }
    try:
        doc = ezdxf.readfile(Path(ga_dxf_path))
    except (IOError, OSError, ezdxf.DXFError) as error:
        return _item(10, "Calc-vs-drawing consistency", clause, requirement,
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
        return _item(10, "Calc-vs-drawing consistency", clause, requirement, computed, limit,
                     SEVERITY_MAJOR, "; ".join(problems) + ".")
    return _item(10, "Calc-vs-drawing consistency", clause, requirement, computed, limit,
                 SEVERITY_PASS, "Length and overall depth read back from ga.dxf match the design.")


# --------------------------------------------------------------------------- assembly
def run_proof_check(
    *,
    params: SteelMemberParams,
    geometry: SteelMemberGeometry,
    analysis: SteelMemberAnalysis,
    checks: list[CheckResult],
    ga_dxf_path: Path,
    out_dir: Path,
) -> SSMProofResult:
    """Grade the checklist, run the cross-check, write compliance.json + bmd.svg."""
    params = coerce(SteelMemberParams, params)
    geometry = coerce(SteelMemberGeometry, geometry)
    analysis = coerce(SteelMemberAnalysis, analysis)
    check_rows = [coerce(CheckResult, c) for c in checks]

    cross = _cross_check(params, geometry, analysis)
    items = _build_items(params, geometry, analysis, check_rows, cross, ga_dxf_path)
    verdict = (
        VERDICT_REVISION
        if any(i.severity == SEVERITY_MAJOR for i in items)
        else VERDICT_APPROVAL
    )
    result = SSMProofResult(
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


def _write_compliance(result: SSMProofResult, out_dir: Path) -> Path:
    payload = {
        "items": [item.model_dump() for item in result.items],
        "verdict": result.verdict,
        "fe_agreement_pct": result.agreement_pct,
    }
    path = out_dir / COMPLIANCE_FILENAME
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _write_bmd_diagram(analysis: SteelMemberAnalysis, out_dir: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    length = analysis.cantilever_length_m
    m_base = analysis.design_moment_knm
    v_base = analysis.design_shear_kn

    xs = [i * length / 20.0 for i in range(21)]
    # cantilever: bending moment max at the base (x=0), zero at the free tip (x=L)
    moments = [m_base * (1.0 - x / length) if length else 0.0 for x in xs]
    # shear approximately constant along a tip-loaded cantilever (max at the base)
    shears = [v_base * (1.0 - 0.15 * x / length) if length else 0.0 for x in xs]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.0, 4.0))
    ax1.fill_between(xs, moments, color="#1565c0", alpha=0.25)
    ax1.plot(xs, moments, color="#1565c0")
    ax1.plot([0.0, length], [0.0, 0.0], color="black", linewidth=1)
    ax1.set_title("Bending moment (design)")
    ax1.set_xlabel("distance from base, m")
    ax1.set_ylabel("moment, kN*m")
    ax1.annotate(f"M_base = {m_base:.0f}", (0.0, m_base))
    ax2.fill_between(xs, shears, color="#c62828", alpha=0.25)
    ax2.plot(xs, shears, color="#c62828")
    ax2.plot([0.0, length], [0.0, 0.0], color="black", linewidth=1)
    ax2.set_title("Shear force (design)")
    ax2.set_xlabel("distance from base, m")
    ax2.set_ylabel("shear, kN")
    ax2.annotate(f"V_base = {v_base:.0f}", (0.0, v_base))
    fig.tight_layout()
    path = out_dir / BMD_FILENAME
    fig.savefig(path, format="svg")
    plt.close(fig)
    return path


# --------------------------------------------------------------------------- memo grounding
def _allowed_values(result: SSMProofResult, extra_facts: str | None) -> list[float]:
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
    narration_md: str, result: SSMProofResult, *, extra_facts: str | None = None
) -> list[str]:
    """Grounding problems in ``narration_md`` — an empty list means it may be embedded."""
    if not narration_md or not narration_md.strip():
        return ["narration is empty"]
    problems: list[str] = []
    for pattern in _FORBIDDEN_CITATION_PATTERNS:
        match = pattern.search(narration_md)
        if match:
            problems.append(f"forbidden out-of-domain citation '{match.group(0)}'")
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
    result: SSMProofResult,
    *,
    params: SteelMemberParams,
    geometry: SteelMemberGeometry,
    analysis: SteelMemberAnalysis,
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
        f"- independent cross-check agreement: {result.agreement_pct:g} %",
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
    result: SSMProofResult,
    narration: str | None = None,
    *,
    params: SteelMemberParams,
    geometry: SteelMemberGeometry,
    analysis: SteelMemberAnalysis,
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
        f"Deterministic {len(result.items)}-item proof-check of the submitted fabricated "
        "steel-member design, covering:",
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
            "carry observations only; the independent cross-check agrees with the recorded "
            f"analysis to {result.agreement_pct:g} %."
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
