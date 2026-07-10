"""Proof-check spine for the RCC cantilever retaining wall.

The SAME IR-protocol review as the culvert: a deterministic checklist grades
every finding, an independent cross-check re-solves the stability factors, a rule
computes the verdict (any major non-conformity -> return_for_revision), and a
grounded memo narrates ONLY from the deterministic facts (no number in the memo
may be absent from the results; only IRS / IS-456 codes may be cited).

Reuses the shared `ChecklistItem` / severity / verdict / compliance-filename
constants (`proofcheck.checklist`) so the frontend compliance matrix renders the
retaining-wall review unchanged. Writes `compliance.json` and a pressure diagram
`bmd.svg`. Pure deterministic Python — the only I/O is reading ga.dxf and writing
the two artefacts.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path

import ezdxf
from pydantic import BaseModel, Field

from components.base import CheckResult, coerce
from components.retaining_wall._engine_common import (
    CONCRETE_PERMISSIBLE,
    TRACK_SURCHARGE_EQUIVALENT_HEIGHT_M,
    active_coefficient,
    rankine_kp,
)
from components.retaining_wall.analysis import (
    RetainingWallAnalysis,
    compute_stability,
)
from components.retaining_wall.params import RetainingWallGeometry, RetainingWallParams
from components.retaining_wall.sizing import FOS_OVERTURNING_MIN, FOS_SLIDING_MIN
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

# Non-IRS/IS-456 design-code citations are defects. IS 456 and IRS codes are
# ALLOWED for a retaining wall; road-congress (IRC) and steel (IS 800) are not.
# Patterns assembled by concatenation so this file never greps as a violation.
_FORBIDDEN_CITATION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (r"\bI" + r"RC\b", r"\bI" + r"S\s*[:.\-]?\s*800\b")
)


class StabilityCrossCheck(BaseModel):
    """Independent re-solve of the stability factors vs the recorded analysis."""

    method: str = Field(description="Independent recomputation method")
    fos_overturning: float
    fos_sliding: float
    max_pressure_kn_m2: float
    agreement_pct: float = Field(description="100 - worst relative deviation, %")
    tolerance_pct: float
    within_tolerance: bool


class RWProofResult(BaseModel):
    """run_proof_check output — the graded items, the rule-computed verdict, the
    independent cross-check, and grounding lines for narration validation."""

    items: list[ChecklistItem]
    verdict: str
    agreement_pct: float
    cross_check: StabilityCrossCheck
    grounding_text: str = ""


# --------------------------------------------------------------------------- reference / facts
def reference_lines(
    params: RetainingWallParams,
    geometry: RetainingWallGeometry,
    analysis: RetainingWallAnalysis,
) -> list[str]:
    return [
        (
            f"RCC cantilever retaining wall — retained height {geometry.total_height_mm:g} mm, "
            f"base width {geometry.base_width_mm:g} mm, SBC {params.safe_bearing_capacity_kn_m2:g} "
            f"kN/m^2, backfill phi {params.backfill_friction_angle_deg:g} deg (slope "
            f"{params.backfill_slope_deg:g} deg), {params.concrete_grade.value} concrete / "
            f"{params.steel_grade.value} steel, clear cover {params.clear_cover_mm:g} mm."
        ),
        (
            f"Sections: stem {geometry.stem_top_thickness_mm:g}-{geometry.stem_base_thickness_mm:g} mm, "
            f"base slab {geometry.base_thickness_mm:g} mm, toe {geometry.toe_length_mm:g} mm, "
            f"heel {geometry.heel_length_mm:g} mm"
            + (f", shear key {geometry.key_depth_mm:g} mm" if geometry.key_depth_mm else "")
            + "."
        ),
        (
            f"Stability: FoS overturning {analysis.fos_overturning:g} (>= {FOS_OVERTURNING_MIN:g}), "
            f"FoS sliding {analysis.fos_sliding:g} (>= {FOS_SLIDING_MIN:g}), maximum base pressure "
            f"{analysis.max_base_pressure_kn_m2:g} kN/m^2, minimum {analysis.min_base_pressure_kn_m2:g} "
            f"kN/m^2; Ka {analysis.ka:g}, Kp {analysis.kp:g}."
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


def _rows(checks: list[CheckResult], **kw) -> list[CheckResult]:
    return [row for row in checks if all(getattr(row, k) == v for k, v in kw.items())]


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
    params: RetainingWallParams,
    geometry: RetainingWallGeometry,
    analysis: RetainingWallAnalysis,
) -> StabilityCrossCheck:
    core = compute_stability(params, geometry)
    pairs = [
        (analysis.fos_overturning, core.fos_overturning),
        (analysis.fos_sliding, core.fos_sliding),
        (analysis.max_base_pressure_kn_m2, core.max_base_pressure_kn_m2),
    ]
    worst = 0.0
    for recorded, recomputed in pairs:
        if abs(recorded) > 1e-9:
            worst = max(worst, abs(recomputed - recorded) / abs(recorded) * 100.0)
    return StabilityCrossCheck(
        method="Independent re-solve of the earth-pressure + stability equations",
        fos_overturning=round(core.fos_overturning, 3),
        fos_sliding=round(core.fos_sliding, 3),
        max_pressure_kn_m2=round(core.max_base_pressure_kn_m2, 2),
        agreement_pct=round(100.0 - worst, 3),
        tolerance_pct=TOLERANCE_PCT,
        within_tolerance=worst <= TOLERANCE_PCT,
    )


def _build_items(
    params: RetainingWallParams,
    geometry: RetainingWallGeometry,
    analysis: RetainingWallAnalysis,
    checks: list[CheckResult],
    cross: StabilityCrossCheck,
    ga_dxf_path: Path,
) -> list[ChecklistItem]:
    items: list[ChecklistItem] = []

    # 1 — design basis & transcription honesty
    concrete_known = params.concrete_grade in CONCRETE_PERMISSIBLE
    items.append(_item(
        1, "Design basis & code transcription",
        "IS 456 / IRS Concrete Bridge Code / IR Bridge Rules",
        "The wall must be designed to IRS/IS-456 working-stress practice with a stated, "
        "verifiable code basis for the permissible stresses and the track surcharge.",
        f"{params.concrete_grade.value} concrete / {params.steel_grade.value} steel; "
        f"track surcharge {'on' if params.track_surcharge else 'off'} "
        f"({TRACK_SURCHARGE_EQUIVALENT_HEIGHT_M:g} m equivalent fill).",
        "grade carries transcribed permissible stresses; surcharge basis cited",
        SEVERITY_MAJOR if not concrete_known else SEVERITY_OBSERVATION,
        "HONESTY NOTE: the IS 456 permissible-stress values and the IR Bridge Rules track "
        "surcharge equivalent height are transcribed for the POC and pending digit-for-digit "
        "verification against the source codes (IR engineer pre-review before demo day) — "
        "graded OBSERVATION, not silently passed."
        if concrete_known else
        f"Concrete grade {params.concrete_grade.value} has no transcribed permissible-stress row.",
    ))

    # 2 — earth-pressure coefficients re-derived
    ka_ind, method, _cit = active_coefficient(params.backfill_friction_angle_deg, params.backfill_slope_deg)
    kp_ind = rankine_kp(params.backfill_friction_angle_deg)
    ka_ok = abs(ka_ind - analysis.ka) <= 1e-3 and abs(kp_ind - analysis.kp) <= 1e-3
    items.append(_item(
        2, "Earth-pressure coefficients", method,
        "The recorded active/passive coefficients must equal an independent re-derivation "
        "from phi and the backfill slope.",
        f"recorded Ka {_fmt(analysis.ka, 4)}, Kp {_fmt(analysis.kp, 4)} vs re-derived "
        f"Ka {_fmt(ka_ind, 4)}, Kp {_fmt(kp_ind, 4)} ({method})",
        "recorded = re-derived (exact)",
        SEVERITY_PASS if ka_ok else SEVERITY_MAJOR,
        "Coefficients re-derived independently and match." if ka_ok else
        "Recorded coefficients do not match the independent re-derivation.",
    ))

    # 3-6 — stability
    for number, title, kind, req in (
        (3, "Overturning stability", "overturning",
         f"Factor of safety against overturning >= {FOS_OVERTURNING_MIN:g}."),
        (4, "Sliding stability", "sliding",
         f"Factor of safety against sliding >= {FOS_SLIDING_MIN:g} (friction + passive/key)."),
        (5, "Bearing pressure", "bearing",
         "Maximum toe pressure within the safe bearing capacity."),
        (6, "No tension under base", "bearing_tension",
         "Heel pressure non-negative — no tension under the base (e <= B/6)."),
    ):
        row = _find(checks, kind=kind)
        items.append(_item(
            number, title, row.clause if row else "IRS Bridge Substructure & Foundation Code",
            req,
            row.computed if row else "no recorded stability row",
            row.limit if row else "-",
            _severity_from_check(row, on_fail=SEVERITY_MAJOR),
            "Conforms." if row and row.status == "PASS"
            else f"Stability non-conformity: {title.lower()} fails its limit.",
        ))

    # 7 — stem flexure, 8 — stem shear
    stem_flex = _find(checks, member="stem", kind="flexure")
    items.append(_item(
        7, "Stem flexure", stem_flex.clause if stem_flex else "IS 456 working stress",
        "Required effective depth at the stem base within the provided depth.",
        stem_flex.computed if stem_flex else "no recorded stem flexure row",
        stem_flex.limit if stem_flex else "-",
        _severity_from_check(stem_flex, on_fail=SEVERITY_MAJOR),
        "Stem provides adequate depth for flexure." if stem_flex and stem_flex.status == "PASS"
        else "Stem is under-designed in flexure — the required depth exceeds the provided "
             "depth (a strength non-conformity in the STEM).",
    ))
    stem_shear = _find(checks, member="stem", kind="shear")
    items.append(_item(
        8, "Stem shear", stem_shear.clause if stem_shear else "IS 456 working stress",
        "Applied shear stress at the stem base within the permissible value.",
        stem_shear.computed if stem_shear else "no recorded stem shear row",
        stem_shear.limit if stem_shear else "-",
        _severity_from_check(stem_shear, on_fail=SEVERITY_MAJOR),
        "Stem shear within permissible." if stem_shear and stem_shear.status == "PASS"
        else "Stem shear stress exceeds the permissible value (a strength non-conformity in "
             "the STEM).",
    ))

    # 9 — heel & toe flexure
    slab_rows = [r for r in _rows(checks, kind="flexure") if r.member in ("heel", "toe")]
    slab_fail = [r for r in slab_rows if r.status != "PASS"]
    items.append(_item(
        9, "Heel & toe flexure",
        slab_rows[0].clause if slab_rows else "IS 456 working stress",
        "The heel and toe cantilevers must provide the depth their design moments require.",
        "; ".join(f"{r.member}: {r.computed}" for r in slab_rows) or "no recorded slab rows",
        "; ".join(f"{r.member}: {r.limit}" for r in slab_rows) or "-",
        SEVERITY_MAJOR if (slab_fail or not slab_rows) else SEVERITY_PASS,
        "Heel and toe provide adequate depth." if slab_rows and not slab_fail
        else f"Base-slab flexure non-conformity on: {', '.join(r.member for r in slab_fail)}.",
    ))

    # 10 — reinforcement minimum & cover
    cover = _find(checks, kind="cover")
    min_steel_rows = _rows(checks, kind="min_steel")
    cover_ok = cover is not None and cover.status == "PASS"
    items.append(_item(
        10, "Reinforcement minimum & cover",
        cover.clause if cover else "IS 456 cl. 26.4/26.5",
        "Provided clear cover meets the exposure minimum and required steel is reported "
        "against the code minimum on every member.",
        (cover.computed if cover else "no cover row")
        + f"; {len(min_steel_rows)} member reinforcement rows reported",
        cover.limit if cover else "-",
        SEVERITY_PASS if cover_ok else SEVERITY_MINOR,
        "Cover meets the minimum; reinforcement reported per member (bar detailing beyond "
        "this level is noted, not verified)." if cover_ok
        else "Provided cover is below the exposure minimum — a durability non-conformity "
             "(graded minor).",
    ))

    # 11 — independent stability cross-check
    items.append(_item(
        11, "Independent stability cross-check", cross.method,
        "An independent re-solve of the earth-pressure + stability equations must agree "
        "with the recorded analysis within the stated tolerance.",
        f"independent FoS overturning {_fmt(cross.fos_overturning, 2)}, sliding "
        f"{_fmt(cross.fos_sliding, 2)}, p_max {_fmt(cross.max_pressure_kn_m2, 1)} kN/m^2; "
        f"agreement {_fmt(cross.agreement_pct, 2)} %",
        f"within +/-{TOLERANCE_PCT:g}% of the recorded analysis",
        SEVERITY_PASS if cross.within_tolerance else SEVERITY_MAJOR,
        "The independent re-solve reproduces the recorded stability factors."
        if cross.within_tolerance
        else "The independent re-solve disagrees with the recorded stability factors.",
    ))

    # 12 — calc-vs-drawing (DXF read-back)
    items.append(_dxf_item(geometry, ga_dxf_path))
    return items


def _dxf_item(geometry: RetainingWallGeometry, ga_dxf_path: Path) -> ChecklistItem:
    requirement = (
        "Dimensions read back from the produced GA drawing must match the designed geometry "
        f"— at least the retained height and base width within +/-{DXF_TOLERANCE_MM:g} mm."
    )
    limit = f"principal dimensions match within +/-{DXF_TOLERANCE_MM:g} mm"
    clause = "Calc-vs-drawing consistency — every issued dimension matches the designed geometry"
    core = {
        "retained height": geometry.total_height_mm,
        "base width": geometry.base_width_mm,
    }
    try:
        doc = ezdxf.readfile(Path(ga_dxf_path))
    except (IOError, OSError, ezdxf.DXFError) as error:
        return _item(12, "Calc-vs-drawing consistency", clause, requirement,
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
        return _item(12, "Calc-vs-drawing consistency", clause, requirement, computed, limit,
                     SEVERITY_MAJOR, "; ".join(problems) + ".")
    return _item(12, "Calc-vs-drawing consistency", clause, requirement, computed, limit,
                 SEVERITY_PASS, "Retained height and base width read back from ga.dxf match the design.")


# --------------------------------------------------------------------------- assembly
def run_proof_check(
    *,
    params: RetainingWallParams,
    geometry: RetainingWallGeometry,
    analysis: RetainingWallAnalysis,
    checks: list[CheckResult],
    ga_dxf_path: Path,
    out_dir: Path,
) -> RWProofResult:
    """Grade the checklist, run the cross-check, write compliance.json + bmd.svg."""
    params = coerce(RetainingWallParams, params)
    geometry = coerce(RetainingWallGeometry, geometry)
    analysis = coerce(RetainingWallAnalysis, analysis)
    check_rows = [coerce(CheckResult, c) for c in checks]

    cross = _cross_check(params, geometry, analysis)
    items = _build_items(params, geometry, analysis, check_rows, cross, ga_dxf_path)
    verdict = (
        VERDICT_REVISION
        if any(i.severity == SEVERITY_MAJOR for i in items)
        else VERDICT_APPROVAL
    )
    result = RWProofResult(
        items=items,
        verdict=verdict,
        agreement_pct=cross.agreement_pct,
        cross_check=cross,
        grounding_text="\n".join(reference_lines(params, geometry, analysis)),
    )
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_compliance(result, out_dir)
    _write_pressure_diagram(analysis, geometry, out_dir)
    return result


def _write_compliance(result: RWProofResult, out_dir: Path) -> Path:
    payload = {
        "items": [item.model_dump() for item in result.items],
        "verdict": result.verdict,
        "fe_agreement_pct": result.agreement_pct,
    }
    path = out_dir / COMPLIANCE_FILENAME
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _write_pressure_diagram(
    analysis: RetainingWallAnalysis, geometry: RetainingWallGeometry, out_dir: Path
) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    b = geometry.base_width_mm / 1000.0
    h = geometry.total_height_mm / 1000.0
    p_max = analysis.max_base_pressure_kn_m2
    p_min = analysis.min_base_pressure_kn_m2
    # Lateral active-soil pressure ordinate at the base: Ka*gamma*H = 2*Pa/H.
    p_base_lateral = 2.0 * analysis.active_thrust_kn / h if h else 0.0

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.0, 4.0))
    # base pressure (toe -> heel)
    ax1.fill_between([0.0, b], [p_max, p_min], color="#c62828", alpha=0.25)
    ax1.plot([0.0, b], [p_max, p_min], color="#c62828")
    ax1.plot([0.0, b], [0.0, 0.0], color="black", linewidth=1)
    ax1.set_title("Base pressure (toe -> heel)")
    ax1.set_xlabel("base width, m")
    ax1.set_ylabel("pressure, kN/m^2")
    ax1.annotate(f"p_max = {p_max:.1f}", (0.0, p_max))
    ax1.annotate(f"p_min = {p_min:.1f}", (b, p_min))
    # active earth pressure over height (triangle)
    ax2.fill_betweenx([0.0, h], [p_base_lateral, 0.0], color="#1565c0", alpha=0.25)
    ax2.plot([p_base_lateral, 0.0], [0.0, h], color="#1565c0")
    ax2.set_title("Active earth pressure")
    ax2.set_xlabel("pressure, kN/m^2")
    ax2.set_ylabel("height above base, m")
    fig.tight_layout()
    path = out_dir / BMD_FILENAME
    fig.savefig(path, format="svg")
    plt.close(fig)
    return path


# --------------------------------------------------------------------------- memo grounding
def _allowed_values(result: RWProofResult, extra_facts: str | None) -> list[float]:
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
    narration_md: str, result: RWProofResult, *, extra_facts: str | None = None
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
    result: RWProofResult,
    *,
    params: RetainingWallParams,
    geometry: RetainingWallGeometry,
    analysis: RetainingWallAnalysis,
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
        f"- independent stability cross-check agreement: {result.agreement_pct:g} %",
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
    result: RWProofResult,
    narration: str | None = None,
    *,
    params: RetainingWallParams,
    geometry: RetainingWallGeometry,
    analysis: RetainingWallAnalysis,
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
        f"Deterministic {len(result.items)}-item proof-check of the submitted retaining-wall "
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
            "carry observations only; the independent stability cross-check agrees with the "
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
