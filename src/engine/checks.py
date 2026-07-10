"""IRS Concrete Bridge Code member checks — working-stress basis (Phase 2, irs-engine.md).

Pinned public API (later slices import exactly this):

    from engine.checks import run_checks, CheckResult
    checks: list[CheckResult] = run_checks(analysis, geometry, params)

Rich API (the calc-sheet composer consumes the check trail and assumptions):

    from engine.checks import run_member_checks, ChecksOutput
    output = run_member_checks(analysis, geometry, params)
    # output.checks / output.trail / output.assumptions

The engine sizes concrete only (no rebar detailing), so every check is
formulated the working-stress way that needs no provided-steel input:

* Flexure — required effective depth d_req = sqrt(M / (Q*b)) from the balanced
  working-stress constant Q (sigma_cbc per grade; m = 280/(3*sigma_cbc); k, j,
  Q derived and recorded as CalcSteps) vs provided d = t - cover - bar_dia/2.
* Shear — applied tau = V/(b*d) at the haunch-face critical section
  (conservative vs the d-from-face rule) vs the permissible shear stress of
  concrete without shear reinforcement, per grade.
* Minimum steel — required As = M/(sigma_st*j*d) vs the IRS CBC minimum
  percentage of the gross section (informational; PASS with the governing
  value quoted).
* Clear cover — provided vs the IRS CBC minimum for moderate exposure.
* Crack control (SLS) — deemed-to-satisfy via working-stress stress
  limitation: satisfied exactly when the member's flexure check passes.

TRANSCRIPTION FOR DEMO — the permissible-stress constants below are encoded
from IRS working-stress bridge practice; verify each value and its clause/table
number against the IRS Concrete Bridge Code before demo day (IR engineer
pre-review required per spec). Envelope forces come from `analysis.envelopes`
(design sign convention: positive moment = tension on the inside face).
Pure deterministic Python — no LLM, no I/O, no network.
"""

import math
from typing import Literal, NamedTuple

from pydantic import BaseModel, Field

from domain.culvert import (
    AnalysisResult,
    Assumption,
    BoxGeometry,
    CalcStep,
    ConcreteGrade,
    CulvertParams,
    SectionEnvelope,
    SteelGrade,
)

# --- transcribed permissible-stress tables (IRS Concrete Bridge Code) ----------

VERIFY_BANNER = (
    "TRANSCRIPTION FOR DEMO — verify each value against the cited source PDF before "
    "demo day (IR engineer pre-review required per spec)"
)
CBC_DOCUMENT = (
    "IRS Concrete Bridge Code — Code of Practice for Plain, Reinforced and Prestressed "
    "Concrete for General Bridge Construction, Government of India, Ministry of Railways "
    "(official PDF: iricen.gov.in)"
)
CBC_ACS_LEVEL = (
    "ACS (Advance Correction Slip) level: reprint incorporating correction slips — "
    "slip level pending verification against the source PDF"
)


class ConcretePermissible(NamedTuple):
    """Working-stress permissible stresses for one concrete grade, N/mm^2.

    `needs_verification` follows the loading-table honesty discipline — True
    until checked digit-for-digit against the IRS Concrete Bridge Code tables.
    """

    grade: str
    sigma_cbc_n_mm2: float  # permissible flexural compressive stress
    tau_c_n_mm2: float  # permissible shear stress, no shear reinforcement
    needs_verification: bool


class SteelPermissible(NamedTuple):
    """Working-stress permissible tensile stress for one steel grade, N/mm^2."""

    grade: str
    sigma_st_n_mm2: float
    needs_verification: bool


CONCRETE_PERMISSIBLE: dict[ConcreteGrade, ConcretePermissible] = {
    ConcreteGrade.M25: ConcretePermissible("M25", 8.5, 0.50, True),
    ConcreteGrade.M30: ConcretePermissible("M30", 10.0, 0.60, True),
    ConcreteGrade.M35: ConcretePermissible("M35", 11.5, 0.70, True),
}
STEEL_PERMISSIBLE: dict[SteelGrade, SteelPermissible] = {
    SteelGrade.FE415: SteelPermissible("Fe415", 200.0, True),
    SteelGrade.FE500: SteelPermissible("Fe500", 240.0, True),
}

# IRS CBC minimum reinforcement — percentage of the gross section for HYSD bars.
MIN_STEEL_PCT_GROSS = 0.12
# IRS CBC minimum clear cover for moderate exposure, mm.
MIN_CLEAR_COVER_MM = 40.0
# Assumed main-bar diameter for the effective depth: d = t - cover - dia/2.
ASSUMED_BAR_DIA_MM = 20.0
ANALYSIS_STRIP_WIDTH_M = 1.0


def _clause(text: str) -> str:
    return f"{text} — {CBC_DOCUMENT}; {CBC_ACS_LEVEL}. {VERIFY_BANNER}."


CLAUSE_FLEXURE = _clause(
    "IRS Concrete Bridge Code, permissible stresses in concrete (working-stress basis): "
    "sigma_cbc table and modular ratio m = 280/(3*sigma_cbc) [clause/table number pending "
    "verification]"
)
CLAUSE_STEEL = _clause(
    "IRS Concrete Bridge Code, permissible tensile stress in reinforcement sigma_st "
    "(working-stress basis) [clause/table number pending verification]"
)
CLAUSE_SHEAR = _clause(
    "IRS Concrete Bridge Code, permissible shear stress in concrete without shear "
    "reinforcement (working-stress basis) [clause/table number pending verification]; "
    "critical section taken at the haunch face — conservative relative to the "
    "d-from-face rule"
)
CLAUSE_MIN_STEEL = _clause(
    "IRS Concrete Bridge Code, minimum reinforcement — "
    f"{MIN_STEEL_PCT_GROSS:g}% of the gross section for HYSD bars [clause pending "
    "verification]"
)
CLAUSE_COVER = _clause(
    "IRS Concrete Bridge Code, minimum clear cover to reinforcement for moderate "
    f"exposure — {MIN_CLEAR_COVER_MM:g} mm [clause pending verification]"
)
CLAUSE_CRACK = _clause(
    "IRS Concrete Bridge Code, SLS crack control — deemed-to-satisfy via working-stress "
    "stress limitation (stresses within permissible imply acceptable crack widths at "
    "this level of detail) [clause pending verification]"
)

# The calc-sheet composer resolves any string input of the form "ref:<step_id>"
# to the ref-form {"ref": step_id, "value": ...} in calc_sheet.json.
TRAIL_REF_INPUT_PREFIX = "ref:"

MEMBER_LABELS = {"top_slab": "Top slab", "bottom_slab": "Bottom slab", "wall": "Wall"}
# Design sections per member: corner peaks are relieved by the 45-degree haunch,
# so flexure/shear are checked at the haunch faces and at mid-length.
FLEXURE_SECTIONS = {
    "top_slab": ("haunch_face", "midspan"),
    "bottom_slab": ("haunch_face", "midspan"),
    "wall": ("bottom_haunch_face", "midheight", "top_haunch_face"),
}
SHEAR_SECTIONS = {
    "top_slab": ("haunch_face",),
    "bottom_slab": ("haunch_face",),
    "wall": ("bottom_haunch_face", "top_haunch_face"),
}

CheckStatus = Literal["PASS", "FAIL"]


class CheckResult(BaseModel):
    """One member-check row — exactly the spec/api.md `checks[]` shape plus extras."""

    clause: str = Field(description="IRS Concrete Bridge Code citation (with ACS level)")
    requirement: str = Field(description="What the code requires, in plain language")
    computed: str = Field(description="The computed value(s), human-readable with units")
    limit: str = Field(description="The permissible/limit value, human-readable")
    status: CheckStatus
    member: str = Field(description="'top_slab' | 'bottom_slab' | 'wall' | 'all'")
    kind: str = Field(description="'flexure' | 'shear' | 'min_steel' | 'cover' | 'crack'")
    trail_ref: str = Field(description="CalcStep id of the governing computation")
    severity_hint: str = Field(description="'critical' for FAIL rows, 'info' otherwise")


class ChecksOutput(BaseModel):
    """Everything `run_member_checks` returns — rows plus their full provenance."""

    checks: list[CheckResult]
    trail: list[CalcStep] = Field(description="Check CalcSteps (ids K01..; ref-form inputs)")
    assumptions: list[Assumption]


class _CheckTrail:
    """CalcStep recorder with a 'K' id namespace so check steps never collide
    with the sizing/analysis trails (which both use 'S' ids)."""

    def __init__(self) -> None:
        self._steps: list[CalcStep] = []

    def record(
        self,
        *,
        description: str,
        formula: str,
        inputs: dict[str, float | int | str],
        value: float,
        unit: str,
        citation: str,
    ) -> str:
        step_id = f"K{len(self._steps) + 1:02d}"
        self._steps.append(
            CalcStep(
                step_id=step_id,
                description=description,
                formula=formula,
                inputs=inputs,
                value=value,
                unit=unit,
                citation=citation,
            )
        )
        return step_id

    def value(self, step_id: str) -> float:
        return next(s.value for s in self._steps if s.step_id == step_id)

    @property
    def steps(self) -> list[CalcStep]:
        return list(self._steps)


def _ref(step_id: str) -> str:
    return f"{TRAIL_REF_INPUT_PREFIX}{step_id}"


class _Envelopes:
    """Envelope lookup that fails loudly when a member/section is missing."""

    def __init__(self, analysis: AnalysisResult) -> None:
        self._by_key = {(e.member, e.section): e for e in analysis.envelopes}
        self._trail = analysis.trail

    def at(self, member: str, section: str) -> SectionEnvelope:
        envelope = self._by_key.get((member, section))
        if envelope is None:
            raise ValueError(
                f"analysis result lacks the envelope for {member!r} at section "
                f"{section!r} — cannot run the IRS CBC member checks"
            )
        return envelope

    def step_ref(self, member: str, section: str, quantity: str) -> str | None:
        """'ref:<id>' for the envelope CalcStep recorded by analyse_frame, if present."""
        description = f"Envelope: {member} {section} {quantity}"
        step = next((s for s in self._trail if s.description == description), None)
        return _ref(step.step_id) if step is not None else None


class _GradeConstants(NamedTuple):
    """Recorded working-stress constants shared by every member check."""

    sigma_cbc_id: str
    sigma_st_id: str
    j_id: str
    q_id: str
    tau_c_id: str
    sigma_st: float
    j: float
    q_n_mm2: float
    tau_c: float


def _record_grade_constants(
    params: CulvertParams, trail: _CheckTrail
) -> _GradeConstants:
    concrete = CONCRETE_PERMISSIBLE[params.concrete_grade]
    steel = STEEL_PERMISSIBLE[params.steel_grade]

    sigma_cbc_id = trail.record(
        description=f"Permissible flexural compressive stress in concrete, {concrete.grade}",
        formula="sigma_cbc = table({grade})".format(grade=concrete.grade),
        inputs={"concrete_grade": concrete.grade},
        value=concrete.sigma_cbc_n_mm2,
        unit="N/mm^2",
        citation=CLAUSE_FLEXURE,
    )
    sigma_st_id = trail.record(
        description=f"Permissible tensile stress in reinforcement, {steel.grade}",
        formula="sigma_st = table({grade})".format(grade=steel.grade),
        inputs={"steel_grade": steel.grade},
        value=steel.sigma_st_n_mm2,
        unit="N/mm^2",
        citation=CLAUSE_STEEL,
    )
    m = 280.0 / (3.0 * concrete.sigma_cbc_n_mm2)
    m_id = trail.record(
        description="Modular ratio",
        formula="m = 280 / (3 * sigma_cbc)",
        inputs={"sigma_cbc_n_mm2": _ref(sigma_cbc_id)},
        value=m,
        unit="-",
        citation=CLAUSE_FLEXURE,
    )
    k = m * concrete.sigma_cbc_n_mm2 / (m * concrete.sigma_cbc_n_mm2 + steel.sigma_st_n_mm2)
    k_id = trail.record(
        description="Neutral-axis depth factor of the balanced working-stress section",
        formula="k = m*sigma_cbc / (m*sigma_cbc + sigma_st)",
        inputs={
            "m": _ref(m_id),
            "sigma_cbc_n_mm2": _ref(sigma_cbc_id),
            "sigma_st_n_mm2": _ref(sigma_st_id),
        },
        value=k,
        unit="-",
        citation=CLAUSE_FLEXURE,
    )
    j = 1.0 - k / 3.0
    j_id = trail.record(
        description="Lever-arm factor of the balanced working-stress section",
        formula="j = 1 - k/3",
        inputs={"k": _ref(k_id)},
        value=j,
        unit="-",
        citation=CLAUSE_FLEXURE,
    )
    q = 0.5 * concrete.sigma_cbc_n_mm2 * k * j
    q_id = trail.record(
        description="Balanced working-stress moment-of-resistance constant",
        formula="Q = 0.5 * sigma_cbc * k * j",
        inputs={"sigma_cbc_n_mm2": _ref(sigma_cbc_id), "k": _ref(k_id), "j": _ref(j_id)},
        value=q,
        unit="N/mm^2",
        citation=CLAUSE_FLEXURE,
    )
    tau_c_id = trail.record(
        description=f"Permissible shear stress of concrete, no shear reinforcement, {concrete.grade}",
        formula="tau_c = table({grade})".format(grade=concrete.grade),
        inputs={"concrete_grade": concrete.grade},
        value=concrete.tau_c_n_mm2,
        unit="N/mm^2",
        citation=CLAUSE_SHEAR,
    )
    return _GradeConstants(
        sigma_cbc_id=sigma_cbc_id,
        sigma_st_id=sigma_st_id,
        j_id=j_id,
        q_id=q_id,
        tau_c_id=tau_c_id,
        sigma_st=steel.sigma_st_n_mm2,
        j=j,
        q_n_mm2=q,
        tau_c=concrete.tau_c_n_mm2,
    )


def _member_thickness_mm(member: str, geometry: BoxGeometry) -> float:
    return {
        "top_slab": geometry.top_slab_thickness_mm,
        "bottom_slab": geometry.bottom_slab_thickness_mm,
        "wall": geometry.wall_thickness_mm,
    }[member]


def _governing_moment(
    member: str, envelopes: _Envelopes
) -> tuple[float, str, str]:
    """(|M| kN*m/m, section, envelope quantity name) at the governing design section."""
    candidates: list[tuple[float, str, str]] = []
    for section in FLEXURE_SECTIONS[member]:
        envelope = envelopes.at(member, section)
        candidates.append((abs(envelope.max_moment_knm), section, "maximum design moment"))
        candidates.append((abs(envelope.min_moment_knm), section, "minimum design moment"))
    return max(candidates, key=lambda c: c[0])


def _governing_shear(member: str, envelopes: _Envelopes) -> tuple[float, str]:
    candidates = [
        (envelopes.at(member, section).max_abs_shear_kn, section)
        for section in SHEAR_SECTIONS[member]
    ]
    return max(candidates, key=lambda c: c[0])


def _severity(status: CheckStatus) -> str:
    return "critical" if status == "FAIL" else "info"


def _check_member(
    member: str,
    geometry: BoxGeometry,
    params: CulvertParams,
    envelopes: _Envelopes,
    constants: _GradeConstants,
    trail: _CheckTrail,
) -> list[CheckResult]:
    label = MEMBER_LABELS[member]
    thickness_mm = _member_thickness_mm(member, geometry)
    d_mm = thickness_mm - params.clear_cover_mm - ASSUMED_BAR_DIA_MM / 2.0
    if d_mm <= 0:
        raise ValueError(
            f"{label} effective depth is non-positive ({d_mm:g} mm) — thickness "
            f"{thickness_mm:g} mm cannot accommodate cover {params.clear_cover_mm:g} mm"
        )
    d_id = trail.record(
        description=f"{member}: provided effective depth",
        formula="d = t - cover - bar_dia/2",
        inputs={
            "thickness_mm": thickness_mm,
            "clear_cover_mm": params.clear_cover_mm,
            "assumed_bar_dia_mm": ASSUMED_BAR_DIA_MM,
        },
        value=d_mm,
        unit="mm",
        citation=CLAUSE_COVER,
    )

    # --- flexure -------------------------------------------------------------
    moment_knm, moment_section, moment_quantity = _governing_moment(member, envelopes)
    envelope_ref = envelopes.step_ref(member, moment_section, moment_quantity)
    moment_inputs: dict[str, float | int | str] = {
        "member": member,
        "governing_section": moment_section,
    }
    moment_inputs["envelope_moment_knm"] = (
        envelope_ref if envelope_ref is not None else moment_knm
    )
    moment_id = trail.record(
        description=f"{member}: design bending moment (envelope, governing design section)",
        formula="M = max |M| over design sections (haunch faces + mid-length)",
        inputs=moment_inputs,
        value=moment_knm,
        unit="kN*m/m",
        citation=CLAUSE_FLEXURE,
    )
    d_req_mm = 1000.0 * math.sqrt(
        moment_knm / (constants.q_n_mm2 * 1000.0 * ANALYSIS_STRIP_WIDTH_M)
    )
    d_req_id = trail.record(
        description=f"{member}: required effective depth for flexure",
        formula="d_req = sqrt(M / (Q * b))",
        inputs={
            "M_knm_per_m": _ref(moment_id),
            "Q_n_mm2": _ref(constants.q_id),
            "b_m": ANALYSIS_STRIP_WIDTH_M,
        },
        value=d_req_mm,
        unit="mm",
        citation=CLAUSE_FLEXURE,
    )
    utilisation = d_req_mm / d_mm
    utilisation_id = trail.record(
        description=f"{member}: flexural depth utilisation",
        formula="u = d_req / d",
        inputs={"d_req_mm": _ref(d_req_id), "d_mm": _ref(d_id)},
        value=utilisation,
        unit="-",
        citation=CLAUSE_FLEXURE,
    )
    flexure_status: CheckStatus = "PASS" if d_req_mm <= d_mm else "FAIL"
    flexure = CheckResult(
        clause=CLAUSE_FLEXURE,
        requirement=f"Flexure (working stress): required effective depth within provided ({label})",
        computed=(
            f"d_req = {d_req_mm:.0f} mm for M = {moment_knm:.1f} kN*m/m "
            f"at {moment_section}"
        ),
        limit=f"d = {d_mm:.0f} mm provided (t = {thickness_mm:g} mm)",
        status=flexure_status,
        member=member,
        kind="flexure",
        trail_ref=d_req_id,
        severity_hint=_severity(flexure_status),
    )

    # --- shear ----------------------------------------------------------------
    shear_kn, shear_section = _governing_shear(member, envelopes)
    shear_ref = envelopes.step_ref(member, shear_section, "maximum shear")
    shear_inputs: dict[str, float | int | str] = {
        "member": member,
        "critical_section": shear_section,
    }
    shear_inputs["envelope_shear_kn"] = shear_ref if shear_ref is not None else shear_kn
    shear_id = trail.record(
        description=f"{member}: design shear at the critical section (haunch face)",
        formula="V = max |V| over shear critical sections",
        inputs=shear_inputs,
        value=shear_kn,
        unit="kN/m",
        citation=CLAUSE_SHEAR,
    )
    tau = shear_kn / (ANALYSIS_STRIP_WIDTH_M * d_mm)  # kN/m over mm depth == N/mm^2
    tau_id = trail.record(
        description=f"{member}: applied shear stress",
        formula="tau = V / (b * d)",
        inputs={"V_kn_per_m": _ref(shear_id), "d_mm": _ref(d_id), "b_m": ANALYSIS_STRIP_WIDTH_M},
        value=tau,
        unit="N/mm^2",
        citation=CLAUSE_SHEAR,
    )
    shear_status: CheckStatus = "PASS" if tau <= constants.tau_c else "FAIL"
    shear = CheckResult(
        clause=CLAUSE_SHEAR,
        requirement=f"Shear: applied stress within permissible, no shear reinforcement ({label})",
        computed=f"tau = {tau:.3f} N/mm^2 for V = {shear_kn:.1f} kN/m at {shear_section}",
        limit=f"tau_c = {constants.tau_c:.2f} N/mm^2 ({params.concrete_grade.value})",
        status=shear_status,
        member=member,
        kind="shear",
        trail_ref=tau_id,
        severity_hint=_severity(shear_status),
    )

    # --- minimum steel (informational) -----------------------------------------
    as_req_mm2 = moment_knm * 1e6 / (constants.sigma_st * constants.j * d_mm)
    as_req_id = trail.record(
        description=f"{member}: required steel area (informational — concrete-only sizing)",
        formula="As_req = M / (sigma_st * j * d)",
        inputs={
            "M_knm_per_m": _ref(moment_id),
            "sigma_st_n_mm2": _ref(constants.sigma_st_id),
            "j": _ref(constants.j_id),
            "d_mm": _ref(d_id),
        },
        value=as_req_mm2,
        unit="mm^2/m",
        citation=CLAUSE_STEEL,
    )
    as_min_mm2 = MIN_STEEL_PCT_GROSS / 100.0 * 1000.0 * thickness_mm
    trail.record(
        description=f"{member}: minimum reinforcement of the gross section",
        formula="As_min = pct/100 * b * t",
        inputs={"min_steel_pct": MIN_STEEL_PCT_GROSS, "thickness_mm": thickness_mm},
        value=as_min_mm2,
        unit="mm^2/m",
        citation=CLAUSE_MIN_STEEL,
    )
    min_governs = as_min_mm2 > as_req_mm2
    min_steel = CheckResult(
        clause=CLAUSE_MIN_STEEL,
        requirement=f"Minimum reinforcement: required steel vs code minimum ({label})",
        computed=(
            f"As_req = {as_req_mm2:.0f} mm^2/m"
            + (" — minimum governs" if min_governs else " — required steel governs")
        ),
        limit=f"As_min = {as_min_mm2:.0f} mm^2/m ({MIN_STEEL_PCT_GROSS:g}% gross)",
        status="PASS",
        member=member,
        kind="min_steel",
        trail_ref=as_req_id,
        severity_hint="info",
    )

    # --- crack control (SLS, deemed-to-satisfy) ---------------------------------
    crack = CheckResult(
        clause=CLAUSE_CRACK,
        requirement=f"Crack control (SLS): deemed-to-satisfy via stress limitation ({label})",
        computed=(
            f"flexural depth utilisation d_req/d = {utilisation:.2f} "
            f"({'within' if flexure_status == 'PASS' else 'EXCEEDS'} permissible stresses)"
        ),
        limit="working stresses within permissible == crack width deemed satisfied",
        status=flexure_status,
        member=member,
        kind="crack",
        trail_ref=utilisation_id,
        severity_hint=_severity(flexure_status),
    )
    return [flexure, shear, min_steel, crack]


def _check_cover(params: CulvertParams, trail: _CheckTrail) -> CheckResult:
    cover_id = trail.record(
        description="Clear cover to reinforcement, provided",
        formula="cover = clear_cover_mm (user/preset parameter)",
        inputs={"clear_cover_mm": params.clear_cover_mm},
        value=params.clear_cover_mm,
        unit="mm",
        citation=CLAUSE_COVER,
    )
    trail.record(
        description="Minimum clear cover for moderate exposure",
        formula="cover_min = table(exposure)",
        inputs={"exposure_condition": "moderate"},
        value=MIN_CLEAR_COVER_MM,
        unit="mm",
        citation=CLAUSE_COVER,
    )
    status: CheckStatus = "PASS" if params.clear_cover_mm >= MIN_CLEAR_COVER_MM else "FAIL"
    return CheckResult(
        clause=CLAUSE_COVER,
        requirement="Clear cover: provided cover at least the code minimum (all members)",
        computed=f"cover = {params.clear_cover_mm:g} mm provided",
        limit=f"cover_min = {MIN_CLEAR_COVER_MM:g} mm (moderate exposure)",
        status=status,
        member="all",
        kind="cover",
        trail_ref=cover_id,
        severity_hint=_severity(status),
    )


def _check_assumptions() -> list[Assumption]:
    return [
        Assumption(
            field="effective_depth_bar_allowance",
            value=f"{ASSUMED_BAR_DIA_MM:g} mm bar diameter",
            source="engine_default",
            note=(
                f"Effective depth taken as d = t - clear cover - {ASSUMED_BAR_DIA_MM:g}/2 mm "
                "(assumed main-bar diameter; no rebar detailing at this level of design)."
            ),
        ),
        Assumption(
            field="exposure_condition",
            value="moderate",
            source="engine_default",
            note=(
                f"Moderate exposure assumed for the cover check — minimum clear cover "
                f"{MIN_CLEAR_COVER_MM:g} mm per {CBC_DOCUMENT} [clause pending verification]."
            ),
        ),
        Assumption(
            field="check_design_sections",
            value="haunch faces + mid-length",
            source="engine_default",
            note=(
                "Flexure and shear checked at the haunch-face and mid-length sections; the "
                "corner moment peak is relieved by the 45-degree haunch (IRICEN box-culvert "
                "practice). Shear at the haunch face is conservative vs the d-from-face rule."
            ),
        ),
        Assumption(
            field="wall_axial_in_flexure_check",
            value="neglected",
            source="engine_default",
            note=(
                "Wall axial compression is neglected in the working-stress flexure check — "
                "conservative (axial compression reduces the flexural tension demand)."
            ),
        ),
        Assumption(
            field="shear_reinforcement",
            value="none assumed",
            source="engine_default",
            note=(
                "Permissible shear stress taken on the no-shear-reinforcement basis, "
                "grade-only — conservative for detailed designs that add stirrups."
            ),
        ),
    ]


def run_member_checks(
    analysis: AnalysisResult, geometry: BoxGeometry, params: CulvertParams
) -> ChecksOutput:
    """All IRS CBC member checks with their CalcStep trail and assumptions."""
    trail = _CheckTrail()
    envelopes = _Envelopes(analysis)
    constants = _record_grade_constants(params, trail)

    checks: list[CheckResult] = []
    for member in ("top_slab", "bottom_slab", "wall"):
        checks.extend(_check_member(member, geometry, params, envelopes, constants, trail))
    checks.append(_check_cover(params, trail))

    return ChecksOutput(checks=checks, trail=trail.steps, assumptions=_check_assumptions())


def run_checks(
    analysis: AnalysisResult, geometry: BoxGeometry, params: CulvertParams
) -> list[CheckResult]:
    """Pinned API — the spec/api.md `checks[]` rows for one analysed design."""
    return run_member_checks(analysis, geometry, params).checks
