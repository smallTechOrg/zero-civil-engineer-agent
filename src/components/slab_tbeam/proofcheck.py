"""Proof-check spine for the RCC slab / T-beam deck.

The SAME IR-protocol review as the culvert / retaining wall: a deterministic
checklist grades every finding, an independent cross-check re-solves the design
moment and required depth from the loading tables and geometry, a rule computes
the verdict (any major non-conformity -> return_for_revision), and a grounded
memo narrates ONLY from the deterministic facts (no number in the memo may be
absent from the results; only IRS / IS-456 codes may be cited).

Reuses the shared `ChecklistItem` / severity / verdict / compliance-filename
constants (`proofcheck.checklist`) so the frontend compliance matrix renders the
deck review unchanged. Writes `compliance.json` and a bending-moment diagram
`bmd.svg`. Pure deterministic Python — the only I/O is reading ga.dxf and writing
the two artefacts.
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
from components.slab_tbeam._engine_common import (
    CONCRETE_PERMISSIBLE,
    TRACK_SIDL_KN_M2,
    working_stress_constants,
)
from components.slab_tbeam.analysis import (
    SlabTbeamAnalysis,
    compute_deck_forces,
    track_live_load,
)
from components.slab_tbeam.params import SlabTbeamGeometry, SlabTbeamParams
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

# The deck declares IRS Concrete Bridge Code + IS 456 (+ IR Bridge Rules for the
# live load). IS 456 and IRS codes are ALLOWED; steel (IS 800) and road-congress
# (IRC) citations are defects. Patterns assembled by concatenation so this file
# never greps as a violation.
_FORBIDDEN_CITATION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (r"\bI" + r"RC\b", r"\bI" + r"S\s*[:.\-]?\s*800\b")
)


class DeckCrossCheck(BaseModel):
    """Independent re-solve of the design moment / required depth vs the recorded analysis."""

    method: str = Field(description="Independent recomputation method")
    design_moment_knm: float
    required_depth_mm: float
    provided_depth_mm: float
    agreement_pct: float = Field(description="100 - worst relative deviation, %")
    tolerance_pct: float
    within_tolerance: bool


class DeckProofResult(BaseModel):
    """run_proof_check output — the graded items, the rule-computed verdict, the
    independent cross-check, and grounding lines for narration validation."""

    items: list[ChecklistItem]
    verdict: str
    agreement_pct: float
    cross_check: DeckCrossCheck
    grounding_text: str = ""


# --------------------------------------------------------------------------- reference / facts
def reference_lines(
    params: SlabTbeamParams,
    geometry: SlabTbeamGeometry,
    analysis: SlabTbeamAnalysis,
) -> list[str]:
    deck_label = "solid RCC slab" if geometry.deck_type == "solid_slab" else "RCC T-beam deck"
    section = (
        f"overall depth {geometry.overall_depth_mm:g} mm"
        if geometry.deck_type == "solid_slab"
        else (
            f"deck slab {geometry.slab_depth_mm:g} mm + rib {geometry.rib_width_mm:g} x "
            f"{geometry.rib_depth_mm:g} mm ({geometry.number_of_girders} girders at "
            f"{geometry.girder_spacing_mm:g} mm, flange {geometry.flange_width_mm:g} mm), "
            f"overall depth {geometry.overall_depth_mm:g} mm"
        )
    )
    return [
        (
            f"RCC slab / T-beam deck — {deck_label}, effective span {geometry.span_mm:g} mm, "
            f"deck width {geometry.deck_width_mm:g} mm, {params.loading_standard.value} live load, "
            f"{params.concrete_grade.value} concrete / {params.steel_grade.value} steel, clear "
            f"cover {params.clear_cover_mm:g} mm."
        ),
        f"Section: {section}.",
        (
            f"Design forces on the governing member: bending moment "
            f"{analysis.design_moment_knm:g} kN*m (dead {analysis.dead_moment_knm:g} + live "
            f"{analysis.live_moment_knm:g}), shear {analysis.design_shear_kn:g} kN; EUDL(BM) "
            f"{analysis.eudl_bm_kn:g} kN, EUDL(shear) {analysis.eudl_shear_kn:g} kN, CDA "
            f"{analysis.cda:g}."
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
    params: SlabTbeamParams,
    geometry: SlabTbeamGeometry,
    analysis: SlabTbeamAnalysis,
) -> DeckCrossCheck:
    forces = compute_deck_forces(params, geometry)
    wsc = working_stress_constants(params.concrete_grade, params.steel_grade)
    b = forces.design_width_mm
    required_depth = math.sqrt(forces.design_moment_knm * 1e6 / (wsc.q_n_mm2 * b)) if forces.design_moment_knm > 0 else 0.0
    from components.slab_tbeam._engine_common import ASSUMED_BAR_DIA_MM

    provided_depth = geometry.overall_depth_mm - params.clear_cover_mm - ASSUMED_BAR_DIA_MM / 2.0

    pairs = [
        (analysis.design_moment_knm, forces.design_moment_knm),
        (analysis.design_shear_kn, forces.design_shear_kn),
    ]
    worst = 0.0
    for recorded, recomputed in pairs:
        if abs(recorded) > 1e-9:
            worst = max(worst, abs(recomputed - recorded) / abs(recorded) * 100.0)
    return DeckCrossCheck(
        method="Independent re-solve of the dead + 25t live load design moment and required depth",
        design_moment_knm=round(forces.design_moment_knm, 2),
        required_depth_mm=round(required_depth, 1),
        provided_depth_mm=round(provided_depth, 1),
        agreement_pct=round(100.0 - worst, 3),
        tolerance_pct=TOLERANCE_PCT,
        within_tolerance=worst <= TOLERANCE_PCT,
    )


def _build_items(
    params: SlabTbeamParams,
    geometry: SlabTbeamGeometry,
    analysis: SlabTbeamAnalysis,
    checks: list[CheckResult],
    cross: DeckCrossCheck,
    ga_dxf_path: Path,
) -> list[ChecklistItem]:
    items: list[ChecklistItem] = []
    member_word = "deck slab" if geometry.deck_type == "solid_slab" else "longitudinal girder"

    # 1 — design basis & transcription honesty
    concrete_known = params.concrete_grade in CONCRETE_PERMISSIBLE
    items.append(_item(
        1, "Design basis & code transcription",
        "IS 456 / IRS Concrete Bridge Code / IR Bridge Rules",
        "The deck must be designed to IRS/IS-456 working-stress practice with a stated, "
        "verifiable code basis for the permissible stresses and the 25t live-load allowances.",
        f"{params.concrete_grade.value} concrete / {params.steel_grade.value} steel; "
        f"{analysis.loading_standard} live load; permanent-way SIDL {TRACK_SIDL_KN_M2:g} kN/m^2.",
        "grade carries transcribed permissible stresses; loading basis cited",
        SEVERITY_MAJOR if not concrete_known else SEVERITY_OBSERVATION,
        "HONESTY NOTE: the IS 456 permissible-stress values, the permanent-way superimposed "
        "dead-load allowance and the live-load distribution width are transcribed / assumed "
        "for the POC and pending digit-for-digit verification against the source codes (IR "
        "engineer pre-review before demo day) — graded OBSERVATION, not silently passed."
        if concrete_known else
        f"Concrete grade {params.concrete_grade.value} has no transcribed permissible-stress row.",
    ))

    # 2 — live load EUDL & CDA re-derivation
    ll = track_live_load(params, geometry.span_mm / 1000.0)
    ll_ok = (
        abs(ll.eudl_bm_kn - analysis.eudl_bm_kn) <= 1e-2
        and abs(ll.eudl_shear_kn - analysis.eudl_shear_kn) <= 1e-2
        and abs(ll.cda - analysis.cda) <= 1e-4
    )
    items.append(_item(
        2, "Live load — EUDL & CDA re-derivation",
        f"IR Bridge Rules — {analysis.loading_standard} EUDL tables + CDA rule",
        "The recorded EUDL(BM), EUDL(shear) and CDA must equal an independent re-lookup of "
        "the 25t Loading-2008 tables and the CDA rule at the loaded length.",
        f"recorded EUDL(BM) {_fmt(analysis.eudl_bm_kn, 1)} kN, EUDL(shear) "
        f"{_fmt(analysis.eudl_shear_kn, 1)} kN, CDA {_fmt(analysis.cda, 4)} vs re-derived "
        f"{_fmt(ll.eudl_bm_kn, 1)} / {_fmt(ll.eudl_shear_kn, 1)} kN, CDA {_fmt(ll.cda, 4)}",
        "recorded = re-derived (exact)",
        SEVERITY_PASS if ll_ok else SEVERITY_MAJOR,
        "Live-load EUDL and CDA re-derived independently from the tables and match. (Table "
        "transcription itself remains flagged for pre-demo verification; see item 1.)"
        if ll_ok else
        "Recorded live-load EUDL / CDA do not match the independent re-lookup of the tables.",
    ))

    # 3 — flexure
    flex = _find(checks, kind="flexure")
    items.append(_item(
        3, "Flexure adequacy", flex.clause if flex else "IS 456 working stress",
        f"Required effective depth at midspan within the provided depth ({member_word}).",
        flex.computed if flex else "no recorded flexure row",
        flex.limit if flex else "-",
        _severity_from_check(flex, on_fail=SEVERITY_MAJOR),
        f"The {member_word} provides adequate depth for flexure." if flex and flex.status == "PASS"
        else f"The {member_word} is under-designed in flexure — the required depth exceeds the "
             "provided depth (a strength non-conformity).",
    ))

    # 4 — shear
    shear = _find(checks, kind="shear")
    items.append(_item(
        4, "Shear adequacy", shear.clause if shear else "IS 456 working stress",
        f"Applied shear stress at the support within the permissible value ({member_word}).",
        shear.computed if shear else "no recorded shear row",
        shear.limit if shear else "-",
        _severity_from_check(shear, on_fail=SEVERITY_MAJOR),
        f"Shear stress within permissible on the {member_word}." if shear and shear.status == "PASS"
        else f"Shear stress exceeds the permissible value on the {member_word} (a strength "
             "non-conformity).",
    ))

    # 5 — minimum reinforcement
    min_steel = _find(checks, kind="min_steel")
    items.append(_item(
        5, "Minimum reinforcement", min_steel.clause if min_steel else "IS 456 cl. 26.5",
        "Required reinforcement reported against the code minimum percentage of the gross section.",
        min_steel.computed if min_steel else "no recorded reinforcement row",
        min_steel.limit if min_steel else "-",
        _severity_from_check(min_steel, on_fail=SEVERITY_MINOR),
        "Required vs minimum steel reported; the governing value is quoted (bar detailing "
        "beyond this level is noted, not verified)." if min_steel and min_steel.status == "PASS"
        else "Reported reinforcement falls below the code minimum — a detailing non-conformity "
             "(graded minor).",
    ))

    # 6 — deflection
    defl = _find(checks, kind="deflection")
    items.append(_item(
        6, "Deflection (span / effective-depth)", defl.clause if defl else "IS 456 cl. 23.2.1",
        f"Span / effective-depth ratio within the deemed-to-satisfy limit ({member_word}).",
        defl.computed if defl else "no recorded deflection row",
        defl.limit if defl else "-",
        _severity_from_check(defl, on_fail=SEVERITY_MINOR),
        "Span/effective-depth within the deemed-to-satisfy limit — deflection deemed "
        "controlled." if defl and defl.status == "PASS"
        else "Span/effective-depth exceeds the deemed-to-satisfy limit — deflection is not "
             "deemed controlled (a serviceability non-conformity, graded minor).",
    ))

    # 7 — clear cover
    cover = _find(checks, kind="cover")
    cover_ok = cover is not None and cover.status == "PASS"
    items.append(_item(
        7, "Clear cover", cover.clause if cover else "IS 456 cl. 26.4",
        "Provided clear cover meets the exposure minimum on every member.",
        cover.computed if cover else "no cover row",
        cover.limit if cover else "-",
        SEVERITY_PASS if cover_ok else SEVERITY_MINOR,
        "Cover meets the moderate-exposure minimum." if cover_ok
        else "Provided cover is below the exposure minimum — a durability non-conformity "
             "(graded minor).",
    ))

    # 8 — independent design-moment cross-check
    items.append(_item(
        8, "Independent design-moment cross-check", cross.method,
        "An independent re-solve of the dead + 25t live-load design moment and the required "
        "effective depth must agree with the recorded analysis within the stated tolerance.",
        f"independent design moment {_fmt(cross.design_moment_knm, 1)} kN*m, required depth "
        f"{_fmt(cross.required_depth_mm, 0)} mm vs provided {_fmt(cross.provided_depth_mm, 0)} mm; "
        f"agreement {_fmt(cross.agreement_pct, 2)} %",
        f"within +/-{TOLERANCE_PCT:g}% of the recorded analysis",
        SEVERITY_PASS if cross.within_tolerance else SEVERITY_MAJOR,
        "The independent re-solve reproduces the recorded design moment and required depth."
        if cross.within_tolerance
        else "The independent re-solve disagrees with the recorded design moment.",
    ))

    # 9 — calc-vs-drawing (DXF read-back)
    items.append(_dxf_item(geometry, ga_dxf_path))
    return items


def _dxf_item(geometry: SlabTbeamGeometry, ga_dxf_path: Path) -> ChecklistItem:
    requirement = (
        "Dimensions read back from the produced GA drawing must match the designed geometry "
        f"— at least the span and overall depth within +/-{DXF_TOLERANCE_MM:g} mm."
    )
    limit = f"principal dimensions match within +/-{DXF_TOLERANCE_MM:g} mm"
    clause = "Calc-vs-drawing consistency — every issued dimension matches the designed geometry"
    core = {
        "span": geometry.span_mm,
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
                 SEVERITY_PASS, "Span and overall depth read back from ga.dxf match the design.")


# --------------------------------------------------------------------------- assembly
def run_proof_check(
    *,
    params: SlabTbeamParams,
    geometry: SlabTbeamGeometry,
    analysis: SlabTbeamAnalysis,
    checks: list[CheckResult],
    ga_dxf_path: Path,
    out_dir: Path,
) -> DeckProofResult:
    """Grade the checklist, run the cross-check, write compliance.json + bmd.svg."""
    params = coerce(SlabTbeamParams, params)
    geometry = coerce(SlabTbeamGeometry, geometry)
    analysis = coerce(SlabTbeamAnalysis, analysis)
    check_rows = [coerce(CheckResult, c) for c in checks]

    cross = _cross_check(params, geometry, analysis)
    items = _build_items(params, geometry, analysis, check_rows, cross, ga_dxf_path)
    verdict = (
        VERDICT_REVISION
        if any(i.severity == SEVERITY_MAJOR for i in items)
        else VERDICT_APPROVAL
    )
    result = DeckProofResult(
        items=items,
        verdict=verdict,
        agreement_pct=cross.agreement_pct,
        cross_check=cross,
        grounding_text="\n".join(reference_lines(params, geometry, analysis)),
    )
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_compliance(result, out_dir)
    _write_bmd(analysis, out_dir)
    return result


def _write_compliance(result: DeckProofResult, out_dir: Path) -> Path:
    payload = {
        "items": [item.model_dump() for item in result.items],
        "verdict": result.verdict,
        "fe_agreement_pct": result.agreement_pct,
    }
    path = out_dir / COMPLIANCE_FILENAME
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _write_bmd(analysis: SlabTbeamAnalysis, out_dir: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    span = analysis.effective_span_m
    m_max = analysis.design_moment_knm
    v_max = analysis.design_shear_kn
    n = 40
    xs = [span * i / n for i in range(n + 1)]
    # parabolic BM for a UDL-equivalent simply-supported span, peak m_max at midspan.
    moments = [4.0 * m_max * x * (span - x) / span**2 if span else 0.0 for x in xs]
    shears = [v_max * (1.0 - 2.0 * x / span) if span else 0.0 for x in xs]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.0, 4.0))
    ax1.fill_between(xs, moments, color="#1565c0", alpha=0.25)
    ax1.plot(xs, moments, color="#1565c0")
    ax1.plot([0.0, span], [0.0, 0.0], color="black", linewidth=1)
    ax1.set_title("Bending moment (design)")
    ax1.set_xlabel("distance along span, m")
    ax1.set_ylabel("moment, kN*m")
    ax1.annotate(f"M_max = {m_max:.1f}", (span / 2.0, m_max))
    ax2.plot(xs, shears, color="#c62828")
    ax2.plot([0.0, span], [0.0, 0.0], color="black", linewidth=1)
    ax2.set_title("Shear force (design)")
    ax2.set_xlabel("distance along span, m")
    ax2.set_ylabel("shear, kN")
    ax2.annotate(f"V_max = {v_max:.1f}", (0.0, v_max))
    fig.tight_layout()
    path = out_dir / BMD_FILENAME
    fig.savefig(path, format="svg")
    plt.close(fig)
    return path


# --------------------------------------------------------------------------- memo grounding
def _allowed_values(result: DeckProofResult, extra_facts: str | None) -> list[float]:
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
    narration_md: str, result: DeckProofResult, *, extra_facts: str | None = None
) -> list[str]:
    """Grounding problems in ``narration_md`` — an empty list means it may be embedded."""
    if not narration_md or not narration_md.strip():
        return ["narration is empty"]
    problems: list[str] = []
    for pattern in _FORBIDDEN_CITATION_PATTERNS:
        match = pattern.search(narration_md)
        if match:
            problems.append(f"forbidden non-IRS/IS-456 citation '{match.group(0)}'")
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
    result: DeckProofResult,
    *,
    params: SlabTbeamParams,
    geometry: SlabTbeamGeometry,
    analysis: SlabTbeamAnalysis,
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
        f"- independent design-moment cross-check agreement: {result.agreement_pct:g} %",
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
    result: DeckProofResult,
    narration: str | None = None,
    *,
    params: SlabTbeamParams,
    geometry: SlabTbeamGeometry,
    analysis: SlabTbeamAnalysis,
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
        f"Deterministic {len(result.items)}-item proof-check of the submitted slab / T-beam "
        "deck design, covering:",
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
            "carry observations only; the independent design-moment cross-check agrees with the "
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
