"""The 12-item deterministic proof-check (spec/capabilities/proof-check.md).

Pinned public API (the graph slice calls exactly this):

    from proofcheck import run_checklist, ProofCheckResult
    result = run_checklist(params=..., geometry=..., analysis=..., checks=...,
                           fe=..., ga_dxf_path=..., out_dir=...)
    # evaluates the 12 items, writes out_dir/"compliance.json", returns the result

Every item evaluates deterministically — the LLM never grades. Items 1–5 are
RE-VERIFICATION, not restatement: they recompute from primary sources (the raw
EUDL tables, the CDA rule, the documented dispersal formula) and compare
against what the run recorded in ``analysis.trail`` / ``analysis.load_cases``.
Items 6–10 derive from the IRS CBC check rows; item 11 from the independent FE
comparison; item 12 measures the produced ga.dxf with ezdxf and compares the
read-back dimensions against the designed ``BoxGeometry`` (±1 mm).

Severity mapping (documented, engineering-significance based):

* Items 1–5, 11, 12 — a mismatch, a missing record, or an unreadable drawing is
  ``NON_CONFORMITY_MAJOR``: it voids the design basis or the audit trail.
* Item 1 — the POC loading tables are transcribed at an ACS level that is
  still pending verification; that honesty is graded ``OBSERVATION`` (never
  silently PASS) until the transcription is verified.
* Items 7 (flexure) and 8 (shear) — any FAIL row is ``NON_CONFORMITY_MAJOR``
  (strength).
* Item 6 (grade & cover) — a FAIL row is ``NON_CONFORMITY_MINOR`` (durability,
  not stability).
* Item 9 (minimum steel) — a FAIL row is ``NON_CONFORMITY_MINOR`` (detailing).
* Item 10 (crack / SLS) — a FAIL row is ``NON_CONFORMITY_MINOR``: it mirrors
  the working-stress breach whose strength consequence is already graded
  MAJOR under item 7.

Verdict rule (spec): any ``NON_CONFORMITY_MAJOR`` → ``return_for_revision``,
otherwise ``recommended_for_approval``.

Pure deterministic Python — no LLM, no network; the only I/O is reading
``ga.dxf`` and writing ``compliance.json``.
"""

import json
import math
from pathlib import Path
from typing import Literal

import ezdxf
from pydantic import BaseModel, Field

from domain.culvert import AnalysisResult, BoxGeometry, CalcStep, CulvertParams
from engine.checks import CONCRETE_PERMISSIBLE, MEMBER_LABELS, CheckResult
from engine.fe_check import FeComparison
from engine.loading import get_loading_standard
from engine.loads import (
    BALLAST_DEPTH_M,
    CASE_DL,
    CASE_EP_ACTIVE,
    CASE_EP_AT_REST,
    CASE_FILL,
    CASE_LL,
    CASE_LL_SURCHARGE,
    CASE_SIDL,
    CASE_WATER,
    CITATION_DISPERSAL,
    DISPERSAL_SLOPE_H_PER_V,
    MIN_LOADED_LENGTH_M,
    SLEEPER_LENGTH_M,
)

COMPLIANCE_FILENAME = "compliance.json"

VERDICT_APPROVAL = "recommended_for_approval"
VERDICT_REVISION = "return_for_revision"

Severity = Literal["PASS", "OBSERVATION", "NON_CONFORMITY_MINOR", "NON_CONFORMITY_MAJOR"]
Verdict = Literal["recommended_for_approval", "return_for_revision"]

SEVERITY_PASS: Severity = "PASS"
SEVERITY_OBSERVATION: Severity = "OBSERVATION"
SEVERITY_MINOR: Severity = "NON_CONFORMITY_MINOR"
SEVERITY_MAJOR: Severity = "NON_CONFORMITY_MAJOR"

# DXF read-back tolerance (spec: dimensions must match the geometry within ±1 mm).
DXF_TOLERANCE_MM = 1.0

# Numeric tolerance for "the recorded value equals the recomputed value" — the
# comparison is between identical deterministic arithmetic, so anything beyond
# floating-point noise is a genuine discrepancy.
_REL_TOL = 1e-6
_ABS_TOL = 1e-6

# Recorded-trail step descriptions (the audit-record contract with engine.loads —
# matched by prefix so cosmetic wording drift does not void the proof-check).
_TRAIL_LOADED_LENGTH = "LL: dispersed loaded length for EUDL"
_TRAIL_LATERAL_WIDTH = "LL: lateral distribution width"
_TRAIL_EUDL_BM = "LL: EUDL for bending moment"
_TRAIL_EUDL_SHEAR = "LL: EUDL for shear"
_TRAIL_CDA = "LL: coefficient of dynamic augment"

_CLAUSE_COMPLETENESS = (
    "IRS working-stress practice — required elementary cases (DL, fill, SIDL, LL+CDA, "
    "earth pressure at rest and active, LL surcharge) and box empty/full service "
    "combinations, per IRICEN box-culvert design examples"
)
_CLAUSE_FE = (
    "Independent proof-check practice (post-Pamban tightening) — an independent FE "
    "re-solve of the recorded load cases must agree with the closed-form analysis "
    "within the stated tolerance"
)
_CLAUSE_DRAWING = (
    "Calc-vs-drawing consistency — every dimension read back from the issued GA "
    "drawing (ga.dxf) must match the designed BoxGeometry within ±1 mm"
)

_TITLES = {
    1: "Loading standard & ACS level",
    2: "EUDL matches the cited table",
    3: "CDA incl. cushion reduction",
    4: "Load-case completeness",
    5: "Cushion dispersal",
    6: "Concrete grade & clear cover",
    7: "Flexure adequacy",
    8: "Shear adequacy",
    9: "Minimum steel & distribution",
    10: "Crack control / SLS",
    11: "Independent FE cross-check",
    12: "Calc-vs-drawing consistency",
}


class ChecklistItem(BaseModel):
    """One compliance-matrix row — exactly the pinned compliance.json item shape.

    Field order is normative: it is the JSON key order the frontend renders.
    """

    item: int = Field(description="1..12, the fixed spec order")
    title: str = Field(description="Fixed item title (spec/capabilities/proof-check.md)")
    clause: str = Field(description="Code clause / source citation the item verifies against")
    requirement: str = Field(description="What must hold, in plain language")
    computed: str = Field(description="What the proof-check found / recomputed, with units")
    limit: str = Field(description="The acceptance criterion, human-readable")
    severity: Severity
    detail: str = Field(description="Evidence and honesty notes; names failing members")


class ProofCheckResult(BaseModel):
    """run_checklist output — the 12 items, the rule-computed verdict, the FE figure.

    ``grounding_text`` carries the deterministic params/geometry reference lines so
    the narration validator can ground numbers that appear in the run record but
    not verbatim in an item row (it is NOT part of compliance.json).
    """

    items: list[ChecklistItem]
    verdict: Verdict
    fe_agreement_pct: float
    grounding_text: str = Field(
        default="", description="Deterministic reference lines for narration grounding"
    )


def reference_lines(params: CulvertParams, geometry: BoxGeometry) -> list[str]:
    """The run-record one-liners shared by the memo, the facts block and grounding."""
    return [
        (
            f"Single-cell RCC box culvert — clear span {params.clear_span_m:g} m x "
            f"clear height {params.clear_height_m:g} m, cushion {params.cushion_m:g} m, "
            f"{params.gauge.value} single track, {params.loading_standard.value} loading, "
            f"{params.concrete_grade.value} concrete / {params.steel_grade.value} steel, "
            f"clear cover {params.clear_cover_mm:g} mm."
        ),
        (
            f"Members: top slab {geometry.top_slab_thickness_mm:g} mm, bottom slab "
            f"{geometry.bottom_slab_thickness_mm:g} mm, walls {geometry.wall_thickness_mm:g} mm, "
            f"haunch {geometry.haunch_mm:g} mm; external {geometry.external_width_m:g} m x "
            f"{geometry.external_height_m:g} m; barrel length {geometry.barrel_length_m:g} m."
        ),
    ]


def _fmt(value: float, decimals: int = 4) -> str:
    return f"{round(float(value), decimals):g}"


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=_REL_TOL, abs_tol=_ABS_TOL)


def _item(number: int, *, clause: str, requirement: str, computed: str, limit: str,
          severity: Severity, detail: str) -> ChecklistItem:
    return ChecklistItem(
        item=number,
        title=_TITLES[number],
        clause=clause,
        requirement=requirement,
        computed=computed,
        limit=limit,
        severity=severity,
        detail=detail,
    )


def _trail_step(analysis: AnalysisResult, prefix: str) -> CalcStep | None:
    return next((s for s in analysis.trail if s.description.startswith(prefix)), None)


# --- items 1–5: re-verification against primary sources ------------------------


def _item_1_loading_standard(params: CulvertParams, analysis: AnalysisResult) -> ChecklistItem:
    requirement = (
        "The run must use the specified railway loading standard, registered with a "
        "source citation that states its ACS (Advance Correction Slip) level, and the "
        "live-load case must cite it."
    )
    limit = (
        f"standard '{params.loading_standard.value}' registered; citation carries an "
        "ACS correction-slip level"
    )
    try:
        standard = get_loading_standard(params.loading_standard.value)
    except ValueError as error:
        return _item(1, clause="IRS Bridge Rules — loading standard registry",
                     requirement=requirement, computed=str(error), limit=limit,
                     severity=SEVERITY_MAJOR,
                     detail="The specified loading standard is not registered — the "
                            "design basis cannot be verified.")

    clause = getattr(standard, "eudl_citation", None) or standard.citation
    problems: list[str] = []
    if standard.name != params.loading_standard.value:
        problems.append(
            f"registry returned '{standard.name}' for '{params.loading_standard.value}'"
        )
    if "ACS" not in standard.citation:
        problems.append("the standard's citation states no ACS correction-slip level")
    ll_case = next((c for c in analysis.load_cases if c.name == CASE_LL), None)
    if ll_case is None:
        problems.append("the run record has no live-load case citing the standard")
    elif not any("ACS" in citation for citation in ll_case.citations):
        problems.append("the recorded live-load case does not cite the ACS level")

    acs_text = str(getattr(standard, "acs_level", standard.citation))
    computed = (
        f"registered standard '{standard.name}'; ACS citation: {acs_text}"
    )
    if problems:
        return _item(1, clause=clause, requirement=requirement, computed=computed,
                     limit=limit, severity=SEVERITY_MAJOR, detail="; ".join(problems) + ".")

    pending = "pending verification" in standard.citation.lower()
    detail = (
        "Standard registered and cited on the live-load case. HONESTY NOTE: the "
        "transcribed tables' ACS correction-slip level is pending verification "
        "against the source PDF (IR engineer pre-review before demo day) — graded "
        "OBSERVATION, not silently passed."
        if pending
        else "Standard registered, cited on the live-load case, ACS level verified."
    )
    return _item(1, clause=clause, requirement=requirement, computed=computed, limit=limit,
                 severity=SEVERITY_OBSERVATION if pending else SEVERITY_PASS, detail=detail)


def _table_lookup(rows, loaded_length_m: float) -> float | None:
    """Independent linear interpolation over the RAW transcribed table rows."""
    if not rows or loaded_length_m < rows[0].loaded_length_m or loaded_length_m > rows[-1].loaded_length_m:
        return None
    for lower, upper in zip(rows, rows[1:]):
        if lower.loaded_length_m <= loaded_length_m <= upper.loaded_length_m:
            if upper.loaded_length_m == lower.loaded_length_m:
                return upper.eudl_kn
            fraction = (loaded_length_m - lower.loaded_length_m) / (
                upper.loaded_length_m - lower.loaded_length_m
            )
            return lower.eudl_kn + fraction * (upper.eudl_kn - lower.eudl_kn)
    return None  # unreachable given the range guard; defensive for single-row tables


def _item_2_eudl(params: CulvertParams, analysis: AnalysisResult) -> ChecklistItem:
    requirement = (
        "The EUDL values the run recorded for its loaded length must equal an "
        "independent re-lookup of the raw transcribed tables."
    )
    limit = "recorded EUDL equals the cited-table interpolation (exact re-lookup)"
    try:
        standard = get_loading_standard(params.loading_standard.value)
    except ValueError as error:
        return _item(2, clause="IRS Bridge Rules — EUDL tables", requirement=requirement,
                     computed=str(error), limit=limit, severity=SEVERITY_MAJOR,
                     detail="The loading standard is not registered — the recorded EUDL "
                            "cannot be re-verified.")
    clause = getattr(standard, "eudl_citation", None) or standard.citation

    bm_step = _trail_step(analysis, _TRAIL_EUDL_BM)
    shear_step = _trail_step(analysis, _TRAIL_EUDL_SHEAR)
    if bm_step is None or shear_step is None:
        return _item(2, clause=clause, requirement=requirement,
                     computed="the calc trail records no EUDL lookup", limit=limit,
                     severity=SEVERITY_MAJOR,
                     detail="The run record lacks the recorded EUDL trail step(s) — "
                            "an unauditable live load is a major non-conformity.")

    parts: list[str] = []
    mismatches: list[str] = []
    for label, step, table in (
        ("EUDL(BM)", bm_step, standard.eudl_bm_table()),
        ("EUDL(shear)", shear_step, standard.eudl_shear_table()),
    ):
        recorded_length = float(step.inputs.get("loaded_length_m", float("nan")))
        independent = (
            _table_lookup(table, recorded_length) if math.isfinite(recorded_length) else None
        )
        if independent is None:
            mismatches.append(
                f"{label}: recorded loaded length {_fmt(recorded_length)} m is outside "
                "the cited table range"
            )
            continue
        parts.append(
            f"{label} recorded {_fmt(step.value)} kN vs table re-lookup "
            f"{_fmt(independent)} kN at L = {_fmt(recorded_length)} m"
        )
        if not _close(step.value, independent):
            mismatches.append(
                f"{label}: recorded {_fmt(step.value)} kN does not match the cited "
                f"table's {_fmt(independent)} kN at L = {_fmt(recorded_length)} m"
            )
    computed = "; ".join(parts) if parts else "; ".join(mismatches)

    if mismatches:
        return _item(2, clause=clause, requirement=requirement, computed=computed,
                     limit=limit, severity=SEVERITY_MAJOR, detail="; ".join(mismatches) + ".")
    return _item(2, clause=clause, requirement=requirement, computed=computed, limit=limit,
                 severity=SEVERITY_PASS,
                 detail="Recorded EUDL values re-derived independently from the raw "
                        "transcribed table rows — exact match. (Table transcription "
                        "itself remains flagged for pre-demo verification; see item 1.)")


def _item_3_cda(params: CulvertParams, analysis: AnalysisResult) -> ChecklistItem:
    requirement = (
        "The recorded coefficient of dynamic augment must equal the standard's CDA "
        "rule re-applied at the recorded loaded length, including the fill/cushion "
        "reduction."
    )
    limit = "recorded CDA equals cda(L, cushion) re-computed from the rule"
    try:
        standard = get_loading_standard(params.loading_standard.value)
    except ValueError as error:
        return _item(3, clause="IRS Bridge Rules — CDA rule", requirement=requirement,
                     computed=str(error), limit=limit, severity=SEVERITY_MAJOR,
                     detail="The loading standard is not registered — the recorded CDA "
                            "cannot be re-verified.")
    clause = getattr(standard, "cda_citation", None) or standard.citation

    step = _trail_step(analysis, _TRAIL_CDA)
    if step is None:
        return _item(3, clause=clause, requirement=requirement,
                     computed="the calc trail records no CDA computation", limit=limit,
                     severity=SEVERITY_MAJOR,
                     detail="The run record lacks the recorded CDA trail step — an "
                            "unauditable dynamic augment is a major non-conformity.")

    recorded_length = float(step.inputs.get("loaded_length_m", float("nan")))
    recorded_cushion = float(step.inputs.get("cushion_m", float("nan")))
    problems: list[str] = []
    if not math.isfinite(recorded_length):
        problems.append("the CDA trail step records no loaded length")
    if not math.isfinite(recorded_cushion) or not _close(recorded_cushion, params.cushion_m):
        problems.append(
            f"the CDA trail step's cushion {_fmt(recorded_cushion)} m does not match "
            f"the run's cushion {params.cushion_m:g} m"
        )
    if problems:
        return _item(3, clause=clause, requirement=requirement, computed=step.description,
                     limit=limit, severity=SEVERITY_MAJOR, detail="; ".join(problems) + ".")

    recomputed = standard.cda(recorded_length, recorded_cushion)
    full = standard.cda(recorded_length, 0.0)
    factor = recomputed / full if full else 0.0
    computed = (
        f"recorded CDA {_fmt(step.value)} vs re-computed {_fmt(recomputed)} at "
        f"L = {_fmt(recorded_length)} m, cushion {_fmt(recorded_cushion)} m"
    )
    reduction_note = (
        f"Cushion reduction confirmed: full CDA {_fmt(full)} at zero fill x factor "
        f"{_fmt(factor)} for {_fmt(recorded_cushion)} m of fill = {_fmt(recomputed)}."
        if recorded_cushion >= 0.9
        else f"Fill below the reduction threshold — full CDA {_fmt(full)} applies unreduced."
    )
    if not _close(step.value, recomputed):
        return _item(3, clause=clause, requirement=requirement, computed=computed,
                     limit=limit, severity=SEVERITY_MAJOR,
                     detail=f"Recorded CDA {_fmt(step.value)} does not match the rule's "
                            f"{_fmt(recomputed)}. {reduction_note}")
    return _item(3, clause=clause, requirement=requirement, computed=computed, limit=limit,
                 severity=SEVERITY_PASS, detail=reduction_note)


def _item_4_completeness(analysis: AnalysisResult) -> ChecklistItem:
    requirement = (
        "All elementary load cases (dead, fill, SIDL, live+CDA, earth pressure at rest "
        "AND active, live-load surcharge) and both box-empty and box-full service "
        "combinations must be present."
    )
    limit = "DL, FILL, SIDL, LL+CDA, EP at-rest, EP active, LL surcharge; box empty & full"
    present = {case.name for case in analysis.load_cases}
    required = (
        CASE_DL, CASE_FILL, CASE_SIDL, CASE_LL, CASE_EP_AT_REST, CASE_EP_ACTIVE,
        CASE_LL_SURCHARGE,
    )
    problems = [f"missing load case '{name}'" for name in required if name not in present]

    box_empty = box_full = False
    for combination in analysis.combinations:
        active = {name for name, factor in combination.case_factors.items() if factor}
        unknown = sorted(active - present)
        if unknown:
            problems.append(
                f"combination '{combination.name}' references missing case(s): "
                + ", ".join(unknown)
            )
        if CASE_WATER in active:
            box_full = True
        else:
            box_empty = True
    if not box_empty:
        problems.append("no box-empty combination is analysed")
    if not box_full:
        problems.append(f"no box-full combination (with {CASE_WATER}) is analysed")

    computed = (
        f"{len(analysis.load_cases)} elementary cases ({', '.join(sorted(present))}); "
        f"{len(analysis.combinations)} combinations incl. box-empty and box-full"
    )
    if problems:
        return _item(4, clause=_CLAUSE_COMPLETENESS, requirement=requirement,
                     computed=computed, limit=limit, severity=SEVERITY_MAJOR,
                     detail="; ".join(problems) + ".")
    return _item(4, clause=_CLAUSE_COMPLETENESS, requirement=requirement, computed=computed,
                 limit=limit, severity=SEVERITY_PASS,
                 detail="Every required elementary case is present and every combination "
                        "resolves to recorded cases, covering box empty and box full.")


def _item_5_dispersal(params: CulvertParams, geometry: BoxGeometry,
                      analysis: AnalysisResult) -> ChecklistItem:
    requirement = (
        "The recorded loaded length and lateral width must equal the documented "
        "dispersal formula re-applied to the geometry: slope x (cushion + ballast) "
        "each side, floored/capped per the rule."
    )
    limit = "recorded loaded length and lateral width match the re-computed dispersal"
    length_step = _trail_step(analysis, _TRAIL_LOADED_LENGTH)
    width_step = _trail_step(analysis, _TRAIL_LATERAL_WIDTH)
    if length_step is None or width_step is None:
        return _item(5, clause=CITATION_DISPERSAL, requirement=requirement,
                     computed="the calc trail records no dispersal computation",
                     limit=limit, severity=SEVERITY_MAJOR,
                     detail="The run record lacks the recorded dispersal trail step(s) — "
                            "an unauditable dispersal is a major non-conformity.")

    span_c = geometry.clear_span_m + geometry.wall_thickness_mm / 1000.0
    depth = params.cushion_m + BALLAST_DEPTH_M
    expected_length = max(
        MIN_LOADED_LENGTH_M, span_c + 2.0 * DISPERSAL_SLOPE_H_PER_V * depth
    )
    expected_width = min(
        SLEEPER_LENGTH_M + 2.0 * DISPERSAL_SLOPE_H_PER_V * depth, geometry.barrel_length_m
    )
    computed = (
        f"loaded length recorded {_fmt(length_step.value)} m vs re-computed "
        f"{_fmt(expected_length)} m; lateral width recorded {_fmt(width_step.value)} m "
        f"vs re-computed {_fmt(expected_width)} m (dispersal "
        f"{DISPERSAL_SLOPE_H_PER_V:g}H:1V through {_fmt(depth)} m of cushion + ballast)"
    )
    problems: list[str] = []
    if not _close(length_step.value, expected_length):
        problems.append(
            f"recorded loaded length {_fmt(length_step.value)} m does not match the "
            f"formula's {_fmt(expected_length)} m"
        )
    if not _close(width_step.value, expected_width):
        problems.append(
            f"recorded lateral width {_fmt(width_step.value)} m does not match the "
            f"formula's {_fmt(expected_width)} m"
        )
    if problems:
        return _item(5, clause=CITATION_DISPERSAL, requirement=requirement,
                     computed=computed, limit=limit, severity=SEVERITY_MAJOR,
                     detail="; ".join(problems) + ".")
    return _item(5, clause=CITATION_DISPERSAL, requirement=requirement, computed=computed,
                 limit=limit, severity=SEVERITY_PASS,
                 detail="Dispersal re-computed from the documented formula and geometry — "
                        "both recorded values match exactly.")


# --- items 6–10: derived from the IRS CBC check rows ----------------------------


def _rows_of_kind(checks: list[CheckResult], kind: str) -> list[CheckResult]:
    return [row for row in checks if row.kind == kind]


def _label(member: str) -> str:
    return MEMBER_LABELS.get(member, member)


def _missing_rows_item(number: int, kind: str, requirement: str) -> ChecklistItem:
    return _item(
        number,
        clause="IRS Concrete Bridge Code — member checks (run record)",
        requirement=requirement,
        computed=f"the run record contains no '{kind}' check rows",
        limit="every member carries a recorded IRS CBC check row",
        severity=SEVERITY_MAJOR,
        detail=f"The run record lacks the {kind} check rows — an unauditable member "
               "check is a major non-conformity.",
    )


def _item_from_rows(number: int, kind: str, requirement: str,
                    checks: list[CheckResult], fail_severity: Severity,
                    fail_note: str, pass_note: str) -> ChecklistItem:
    rows = _rows_of_kind(checks, kind)
    if not rows:
        return _missing_rows_item(number, kind, requirement)

    failing = [row for row in rows if row.status != "PASS"]
    computed = "; ".join(f"{_label(row.member)}: {row.computed}" for row in rows)
    limit = "; ".join(f"{_label(row.member)}: {row.limit}" for row in rows)
    clause = rows[0].clause
    if failing:
        names = ", ".join(_label(row.member) for row in failing)
        detail = f"Fails on: {names}. {fail_note}"
        return _item(number, clause=clause, requirement=requirement, computed=computed,
                     limit=limit, severity=fail_severity, detail=detail)
    return _item(number, clause=clause, requirement=requirement, computed=computed,
                 limit=limit, severity=SEVERITY_PASS, detail=pass_note)


def _item_6_grade_and_cover(params: CulvertParams, checks: list[CheckResult]) -> ChecklistItem:
    requirement = (
        "The concrete grade must be an IRS CBC working-stress grade and the provided "
        "clear cover must meet the exposure minimum."
    )
    rows = _rows_of_kind(checks, "cover")
    if not rows:
        return _missing_rows_item(6, "cover", requirement)
    row = rows[0]
    grade_known = params.concrete_grade in CONCRETE_PERMISSIBLE
    computed = (
        f"{params.concrete_grade.value} concrete, {params.steel_grade.value} steel; "
        f"{row.computed}"
    )
    problems: list[str] = []
    if not grade_known:
        problems.append(
            f"concrete grade {params.concrete_grade.value} has no transcribed "
            "permissible-stress row"
        )
    if row.status != "PASS":
        problems.append("provided clear cover is below the exposure minimum")
    if problems:
        severity = SEVERITY_MAJOR if not grade_known else SEVERITY_MINOR
        return _item(6, clause=row.clause, requirement=requirement, computed=computed,
                     limit=row.limit, severity=severity,
                     detail="; ".join(problems) + ". Cover shortfalls are graded minor "
                            "(durability, not stability); an unknown grade is major.")
    return _item(6, clause=row.clause, requirement=requirement, computed=computed,
                 limit=row.limit, severity=SEVERITY_PASS,
                 detail="Grade carries transcribed permissible stresses; provided cover "
                        "meets the moderate-exposure minimum.")


def _item_7_flexure(checks: list[CheckResult]) -> ChecklistItem:
    return _item_from_rows(
        7, "flexure",
        "Working-stress flexure: the required effective depth at the governing design "
        "section must not exceed the provided effective depth on any member.",
        checks, SEVERITY_MAJOR,
        "Required effective depth exceeds provided — a strength non-conformity "
        "(graded major); see the clause and the computed-vs-limit values.",
        "All members provide more effective depth than flexure requires.",
    )


def _item_8_shear(checks: list[CheckResult]) -> ChecklistItem:
    return _item_from_rows(
        8, "shear",
        "The applied shear stress at the critical section must not exceed the "
        "permissible shear stress of concrete without shear reinforcement.",
        checks, SEVERITY_MAJOR,
        "Applied shear stress exceeds the permissible value — a strength "
        "non-conformity (graded major).",
        "Applied shear stress is within the permissible value on every member.",
    )


def _item_9_min_steel(checks: list[CheckResult]) -> ChecklistItem:
    item = _item_from_rows(
        9, "min_steel",
        "Required reinforcement must be reported against the IRS CBC minimum "
        "percentage of the gross section on every member.",
        checks, SEVERITY_MINOR,
        "Reported reinforcement falls below the code minimum — a detailing "
        "non-conformity (graded minor).",
        "Required vs minimum steel reported on every member; the governing value is "
        "quoted per member. Bar spacing and distribution-steel detailing are beyond "
        "this concrete-only sizing level and are noted, not verified.",
    )
    return item


def _item_10_crack(checks: list[CheckResult]) -> ChecklistItem:
    return _item_from_rows(
        10, "crack",
        "SLS crack control: working stresses within permissible values (deemed-to-"
        "satisfy at this level of design) on every member.",
        checks, SEVERITY_MINOR,
        "Working stresses exceed permissible — crack control is not deemed satisfied. "
        "Graded minor here (serviceability); the underlying strength breach is graded "
        "major under the flexure item.",
        "Working stresses within permissible on every member — crack control deemed "
        "satisfied.",
    )


# --- item 11: independent FE agreement ------------------------------------------


def _item_11_fe(fe: FeComparison) -> ChecklistItem:
    requirement = (
        "An independent FE re-solve of the recorded load cases must agree with the "
        "closed-form analysis within the stated tolerance — agreement is itself a "
        "check item."
    )
    agreement = round(fe.agreement_pct, 2)
    computed = (
        f"independent FE re-solve ({fe.solver}) max deviation {agreement:g}% — "
        f"governing {fe.governing}"
    )
    limit = f"within ±{fe.tolerance_pct:g}% of the closed-form analysis"
    detail = (
        f"All {len(fe.combinations_checked)} combinations re-solved independently from "
        f"the recorded load cases; support-reaction residual "
        f"{fe.reaction_residual_kn:.3g} kN proves the like-for-like load set."
    )
    if not fe.within_tolerance:
        return _item(11, clause=_CLAUSE_FE, requirement=requirement, computed=computed,
                     limit=limit, severity=SEVERITY_MAJOR,
                     detail=f"FE disagreement exceeds the tolerance. {detail}")
    return _item(11, clause=_CLAUSE_FE, requirement=requirement, computed=computed,
                 limit=limit, severity=SEVERITY_PASS, detail=detail)


# --- item 12: DXF read-back -------------------------------------------------------


def _expected_dimensions(geometry: BoxGeometry) -> tuple[dict[str, float], dict[str, float]]:
    """(core, recognised) read-back values in mm.

    Core values MUST be present as measured dimensions; recognised values are
    every geometry-derived quantity a dimension may legitimately measure — any
    measured dimension matching NONE of them is an inconsistency.
    """
    core = {
        "clear span": geometry.clear_span_m * 1000.0,
        "clear height": geometry.clear_height_m * 1000.0,
        "top slab thickness": geometry.top_slab_thickness_mm,
        "bottom slab thickness": geometry.bottom_slab_thickness_mm,
        "wall thickness": geometry.wall_thickness_mm,
        "barrel length": geometry.barrel_length_m * 1000.0,
    }
    recognised = {
        **core,
        "haunch": geometry.haunch_mm,
        "cushion": geometry.cushion_m * 1000.0,
        "external width": geometry.external_width_m * 1000.0,
        "external height": geometry.external_height_m * 1000.0,
    }
    return core, recognised


def _rendered_dimension_texts(doc) -> list[str]:
    """The dimension text strings actually printed on the sheet (geometry blocks)."""
    texts: list[str] = []
    for dimension in doc.modelspace().query("DIMENSION"):
        block_name = dimension.dxf.get("geometry", None)
        if not block_name or block_name not in doc.blocks:
            continue
        block = doc.blocks[block_name]
        for entity in block.query("TEXT"):
            texts.append(entity.dxf.text.strip())
        for entity in block.query("MTEXT"):
            texts.append(entity.plain_text().strip())
    return texts


def _parse_dimension_text(text: str) -> float | None:
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _item_12_drawing(geometry: BoxGeometry, ga_dxf_path: Path) -> ChecklistItem:
    requirement = (
        "Dimensions read back from the produced GA drawing must match the designed "
        "geometry — clear span, clear height, member thicknesses and barrel length "
        f"within ±{DXF_TOLERANCE_MM:g} mm, with no dimension measuring a value that "
        "belongs to no designed quantity."
    )
    limit = f"every read-back dimension matches the designed geometry within ±{DXF_TOLERANCE_MM:g} mm"
    core, recognised = _expected_dimensions(geometry)

    try:
        doc = ezdxf.readfile(Path(ga_dxf_path))
    except (IOError, OSError, ezdxf.DXFError) as error:
        return _item(12, clause=_CLAUSE_DRAWING, requirement=requirement,
                     computed=f"ga.dxf could not be read back: {error}", limit=limit,
                     severity=SEVERITY_MAJOR,
                     detail="The issued drawing is missing or unreadable — calc-vs-"
                            "drawing consistency cannot be verified.")

    measurements = [
        round(float(dimension.get_measurement()), 3)
        for dimension in doc.modelspace().query("DIMENSION")
    ]
    problems: list[str] = []
    if not measurements:
        problems.append("the drawing contains no measurable DIMENSION entities")

    # (a) every core quantity must be measured — duplicates (e.g. equal slab
    # thicknesses) need as many matching dimensions as quantities sharing the value.
    required_counts: dict[float, list[str]] = {}
    for name, value in core.items():
        key = next((k for k in required_counts if abs(k - value) <= DXF_TOLERANCE_MM), value)
        required_counts.setdefault(key, []).append(name)
    for value, names in required_counts.items():
        found = sum(1 for m in measurements if abs(m - value) <= DXF_TOLERANCE_MM)
        if found < len(names):
            problems.append(
                f"no dimension found for {' / '.join(names)} ({_fmt(value, 1)} mm — "
                f"{found} of {len(names)} required measurements present)"
            )

    # (b) no stray measurement: every dimension must measure a designed value.
    for measurement in measurements:
        if not any(
            abs(measurement - value) <= DXF_TOLERANCE_MM for value in recognised.values()
        ):
            problems.append(
                f"dimension measuring {_fmt(measurement, 1)} mm matches no designed value"
            )

    # (c) the printed dimension texts must show the designed values too — a text
    # override could mislead a reader even when the measured geometry is correct.
    printed = [
        value
        for value in (_parse_dimension_text(t) for t in _rendered_dimension_texts(doc))
        if value is not None
    ]
    if printed:
        for name, value in core.items():
            if not any(abs(p - value) <= DXF_TOLERANCE_MM for p in printed):
                problems.append(
                    f"no printed dimension text shows {name} ({_fmt(value, 1)} mm)"
                )
        for p in printed:
            if not any(abs(p - value) <= DXF_TOLERANCE_MM for value in recognised.values()):
                problems.append(
                    f"printed dimension text '{_fmt(p, 1)}' matches no designed value"
                )

    verified = ", ".join(f"{name} {_fmt(value, 1)} mm" for name, value in core.items())
    computed = (
        f"{len(measurements)} dimensions read back from ga.dxf via ezdxf; core values "
        f"checked: {verified}"
    )
    if problems:
        return _item(12, clause=_CLAUSE_DRAWING, requirement=requirement, computed=computed,
                     limit=limit, severity=SEVERITY_MAJOR, detail="; ".join(problems) + ".")
    return _item(12, clause=_CLAUSE_DRAWING, requirement=requirement, computed=computed,
                 limit=limit, severity=SEVERITY_PASS,
                 detail="Every measured dimension and every printed dimension text "
                        "matches the designed geometry within the tolerance.")


# --- assembly ---------------------------------------------------------------------


def run_checklist(
    *,
    params: CulvertParams,
    geometry: BoxGeometry,
    analysis: AnalysisResult,
    checks: list[CheckResult],
    fe: FeComparison,
    ga_dxf_path: Path,
    out_dir: Path,
) -> ProofCheckResult:
    """Evaluate the 12 items deterministically and write ``compliance.json``.

    The verdict is computed by rule — any NON_CONFORMITY_MAJOR returns the
    design for revision. Never raises on a bad *record* (an unverifiable record
    is itself a major finding); only programming errors propagate.
    """
    items = [
        _item_1_loading_standard(params, analysis),
        _item_2_eudl(params, analysis),
        _item_3_cda(params, analysis),
        _item_4_completeness(analysis),
        _item_5_dispersal(params, geometry, analysis),
        _item_6_grade_and_cover(params, checks),
        _item_7_flexure(checks),
        _item_8_shear(checks),
        _item_9_min_steel(checks),
        _item_10_crack(checks),
        _item_11_fe(fe),
        _item_12_drawing(geometry, ga_dxf_path),
    ]
    verdict: Verdict = (
        VERDICT_REVISION
        if any(item.severity == SEVERITY_MAJOR for item in items)
        else VERDICT_APPROVAL
    )
    result = ProofCheckResult(
        items=items,
        verdict=verdict,
        fe_agreement_pct=round(fe.agreement_pct, 2),
        grounding_text="\n".join(reference_lines(params, geometry)),
    )
    _write_compliance(result, Path(out_dir))
    return result


def _write_compliance(result: ProofCheckResult, out_dir: Path) -> Path:
    """Write the PINNED compliance.json shape — exactly items/verdict/fe_agreement_pct."""
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "items": [item.model_dump() for item in result.items],
        "verdict": result.verdict,
        "fe_agreement_pct": result.fe_agreement_pct,
    }
    path = out_dir / COMPLIANCE_FILENAME
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path
