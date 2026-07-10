"""Check-governed sizing of the IRS design engine (spec/capabilities/irs-engine.md).

Two deterministic stages:

1. **Heuristic starting point** — the RDSO B-10152/R family proportions (slab
   ~ span/10, wall ~ governing opening/12, 300 mm floor, 50 mm rounding),
   honouring user overrides. The heuristic is documented in
   `engine.defaults` and remains the recorded starting point of every size.
2. **Check-governed loop** — the candidate design is analysed
   (`engine.analysis.analyse_frame`) and put through the IRS CBC member
   checks (`engine.checks.run_member_checks`); any AUTO-sized member failing
   flexure/shear/crack is bumped by one 50 mm constructible increment and
   the loop repeats until the design passes its own checks. The heuristic
   alone ignores fill load — at 4 m cushion the 4x3 box needs 450 mm slabs,
   not the heuristic 400 mm.

User-overridden thicknesses are NEVER bumped: a deliberate under-design flows
through to FAIL rows and a return-for-revision verdict. The thinner-override
warning compares against the FINAL check-governed auto size (what the engine
would have sized), not the raw heuristic. Every bump is a CalcStep citing the
governing IRS CBC check, and each auto-sized Assumption carries the final
check-governed value. Pure deterministic Python — no LLM, no DB, no file I/O;
the same input always produces a byte-identical result.
"""

from typing import NamedTuple

from pydantic import BaseModel

from domain.culvert import Assumption, BoxGeometry, CalcStep, CulvertParams
from engine.analysis import analyse_frame
from engine.checks import (
    ASSUMED_BAR_DIA_MM,
    CONCRETE_PERMISSIBLE,
    ChecksOutput,
    run_member_checks,
)
from engine.defaults import (
    CITATION_BOX_GEOMETRY,
    CITATION_BRIDGE_MANUAL,
    CITATION_RDSO_FAMILY,
    CITATION_USER_INPUT,
    MIN_MEMBER_THICKNESS_MM,
    SLAB_SPAN_DIVISOR,
    THICKNESS_ROUND_STEP_MM,
    WALL_OPENING_DIVISOR,
    auto_slab_thickness_mm,
    auto_wall_thickness_mm,
)
from engine.trail import TrailRecorder

_SLAB_FORMULA = (
    f"t = ceil50(max(1000 * L / {SLAB_SPAN_DIVISOR:g}, {MIN_MEMBER_THICKNESS_MM:g} mm))"
)
_WALL_FORMULA = (
    f"t = ceil50(max(1000 * max(L, H) / {WALL_OPENING_DIVISOR:g}, {MIN_MEMBER_THICKNESS_MM:g} mm))"
)

# Check-governed loop bound. Each pass is one closed-form frame solve plus the
# full IRS CBC check set (~1 ms). The heaviest VALID parameter corner (8 m
# span x 6 m height, 10 m cushion, M25/Fe415, 75 mm cover, 22 kN/m^3 fill at
# phi = 25 deg) converges in 41 passes; 60 leaves clear margin, so hitting the
# bound means the request is genuinely un-sizeable — unreachable for validated
# CulvertParams ranges, and a loud error if it ever happens.
MAX_SIZING_PASSES = 60

# A bump reacts to these failing check kinds on an auto-sized member. 'crack'
# mirrors 'flexure' (deemed-to-satisfy via stress limitation), so the named
# governing check is always a flexure or shear row.
_BUMPED_CHECK_KINDS = frozenset({"flexure", "shear", "crack"})

_MEMBER_ORDER = ("top_slab", "bottom_slab", "wall")
_MEMBER_LABELS = {"top_slab": "Top slab", "bottom_slab": "Bottom slab", "wall": "Wall"}
_MEMBER_FIELDS = {member: f"{member}_thickness_mm" for member in _MEMBER_ORDER}


class SizingResult(BaseModel):
    """Everything `engine.size_culvert` returns — geometry plus its full provenance."""

    geometry: BoxGeometry
    assumptions: list[Assumption]
    trail: list[CalcStep]
    warnings: list[str]


class _Bump(NamedTuple):
    """One check-governed 50 mm increase of an auto-sized member."""

    member: str
    governing_kind: str
    governing_clause: str
    utilisation: float
    previous_mm: float
    new_mm: float


def size_culvert(params: CulvertParams) -> SizingResult:
    """Size a single-cell box: heuristic start, check-governed thicknesses,
    external dims and barrel length — fully traced."""
    trail = TrailRecorder()
    assumptions: list[Assumption] = []
    warnings: list[str] = []

    trail.record(
        description="Clear span of the box (inside face of wall to inside face of wall)",
        formula="L = clear_span_m (user requirement)",
        inputs={"clear_span_m": params.clear_span_m},
        value=params.clear_span_m,
        unit="m",
        citation=CITATION_USER_INPUT,
    )
    trail.record(
        description="Clear height of the box (top slab soffit to bottom slab top)",
        formula="H = clear_height_m (user requirement)",
        inputs={"clear_height_m": params.clear_height_m},
        value=params.clear_height_m,
        unit="m",
        citation=CITATION_USER_INPUT,
    )
    trail.record(
        description="Cushion — fill from top of top slab to formation level",
        formula="c = cushion_m (user requirement)",
        inputs={"cushion_m": params.cushion_m},
        value=params.cushion_m,
        unit="m",
        citation=CITATION_USER_INPUT,
    )

    heuristic = _heuristic_thicknesses_mm(params)
    overrides = {m: getattr(params, _MEMBER_FIELDS[m]) for m in _MEMBER_ORDER}
    thicknesses = {
        m: overrides[m] if overrides[m] is not None else heuristic[m]
        for m in _MEMBER_ORDER
    }
    formulas = _member_formulas(params)

    for member in _MEMBER_ORDER:
        _record_starting_thickness(
            member=member,
            override_mm=overrides[member],
            heuristic_mm=heuristic[member],
            formulas=formulas,
            trail=trail,
        )

    # The check-governed loop: only auto-sized members may be bumped.
    adjustable = frozenset(m for m in _MEMBER_ORDER if overrides[m] is None)
    bumps = _check_governed_bumps(params, thicknesses, adjustable, trail)

    # Thinner-override warnings compare against the FINAL check-governed auto
    # size — what the engine would have sized had the member not been overridden.
    if adjustable == frozenset(_MEMBER_ORDER):
        reference = dict(thicknesses)
    else:
        reference = dict(heuristic)
        _check_governed_bumps(params, reference, frozenset(_MEMBER_ORDER), trail=None)

    bumps_by_member: dict[str, list[_Bump]] = {}
    for bump in bumps:
        bumps_by_member.setdefault(bump.member, []).append(bump)

    for member in _MEMBER_ORDER:
        label = f"{_MEMBER_LABELS[member]} thickness"
        if overrides[member] is None:
            assumptions.append(
                _auto_size_assumption(
                    member=member,
                    label=label,
                    heuristic_mm=heuristic[member],
                    final_mm=thicknesses[member],
                    formula=formulas[member][0],
                    member_bumps=bumps_by_member.get(member, []),
                    cushion_m=params.cushion_m,
                )
            )
        elif overrides[member] < reference[member]:
            warnings.append(
                f"{label} override {overrides[member]:g} mm is thinner than the "
                f"auto-sized {reference[member]:g} mm (check-governed; "
                f"{CITATION_RDSO_FAMILY} + IRS CBC member checks) — possible "
                "under-design; member checks will verify it."
            )

    haunch_mm = trail.record(
        description="Haunch leg size at each inside corner (45-degree, both legs equal)",
        formula="h = haunch_mm (150 mm standard detail unless specified)",
        inputs={"haunch_mm": params.haunch_mm},
        value=params.haunch_mm,
        unit="mm",
        citation=CITATION_RDSO_FAMILY,
    )

    ext_width, ext_height, fill_at_base, barrel = _external_dimensions(params, thicknesses)
    external_width_m = trail.record(
        description="External (overall) width of the box",
        formula="W_ext = L + 2 * t_wall / 1000",
        inputs={
            "clear_span_m": params.clear_span_m,
            "wall_thickness_mm": thicknesses["wall"],
        },
        value=ext_width,
        unit="m",
        citation=CITATION_BOX_GEOMETRY,
    )
    external_height_m = trail.record(
        description="External (overall) height of the box",
        formula="H_ext = H + (t_top + t_bottom) / 1000",
        inputs={
            "clear_height_m": params.clear_height_m,
            "top_slab_thickness_mm": thicknesses["top_slab"],
            "bottom_slab_thickness_mm": thicknesses["bottom_slab"],
        },
        value=ext_height,
        unit="m",
        citation=CITATION_BOX_GEOMETRY,
    )

    fill_at_base_m = trail.record(
        description="Height of fill from the underside of the box to formation level",
        formula="D = c + H_ext",
        inputs={"cushion_m": params.cushion_m, "external_height_m": external_height_m},
        value=fill_at_base,
        unit="m",
        citation=CITATION_BRIDGE_MANUAL,
    )
    barrel_length_m = trail.record(
        description="Barrel length of the box along the track axis",
        formula="L_barrel = W_formation + 2 * s * D",
        inputs={
            "formation_width_m": params.formation_width_m,
            "side_slope_h_per_v": params.side_slope_h_per_v,
            "fill_at_base_m": fill_at_base_m,
        },
        value=barrel,
        unit="m",
        citation=CITATION_BRIDGE_MANUAL,
    )
    assumptions.append(
        Assumption(
            field="barrel_length_m",
            value=barrel_length_m,
            source="engine_default",
            note=(
                f"Barrel length computed from formation width {params.formation_width_m:g} m "
                f"and {params.side_slope_h_per_v:g}H:1V side slopes over {fill_at_base_m:g} m "
                f"of fill at the box base — {CITATION_BRIDGE_MANUAL}."
            ),
        )
    )

    geometry = BoxGeometry(
        clear_span_m=params.clear_span_m,
        clear_height_m=params.clear_height_m,
        cushion_m=params.cushion_m,
        top_slab_thickness_mm=thicknesses["top_slab"],
        bottom_slab_thickness_mm=thicknesses["bottom_slab"],
        wall_thickness_mm=thicknesses["wall"],
        haunch_mm=haunch_mm,
        external_width_m=external_width_m,
        external_height_m=external_height_m,
        barrel_length_m=barrel_length_m,
    )
    return SizingResult(
        geometry=geometry, assumptions=assumptions, trail=trail.steps, warnings=warnings
    )


# --- heuristic starting point ---------------------------------------------------


def _heuristic_thicknesses_mm(params: CulvertParams) -> dict[str, float]:
    """The documented RDSO family starting point for the check-governed loop."""
    return {
        "top_slab": auto_slab_thickness_mm(params.clear_span_m),
        "bottom_slab": auto_slab_thickness_mm(params.clear_span_m),
        "wall": auto_wall_thickness_mm(params.clear_span_m, params.clear_height_m),
    }


def _member_formulas(
    params: CulvertParams,
) -> dict[str, tuple[str, dict[str, float]]]:
    """Per-member heuristic formula text + substituted inputs for the trail."""
    slab_inputs = {"clear_span_m": params.clear_span_m}
    return {
        "top_slab": (_SLAB_FORMULA, slab_inputs),
        # RDSO family practice: bottom slab matched to the top slab.
        "bottom_slab": (_SLAB_FORMULA + " (bottom slab matched to top slab)", slab_inputs),
        "wall": (
            _WALL_FORMULA,
            {
                "clear_span_m": params.clear_span_m,
                "clear_height_m": params.clear_height_m,
            },
        ),
    }


def _record_starting_thickness(
    *,
    member: str,
    override_mm: float | None,
    heuristic_mm: float,
    formulas: dict[str, tuple[str, dict[str, float]]],
    trail: TrailRecorder,
) -> None:
    label = f"{_MEMBER_LABELS[member]} thickness"
    formula, formula_inputs = formulas[member]
    if override_mm is None:
        trail.record(
            description=f"{label} — auto-sized starting point (RDSO family heuristic)",
            formula=formula,
            inputs=formula_inputs,
            value=heuristic_mm,
            unit="mm",
            citation=CITATION_RDSO_FAMILY,
        )
        return
    trail.record(
        description=f"{label} — user override (heuristic auto-size reference {heuristic_mm:g} mm)",
        formula=f"t = user override; auto-size reference: {formula}",
        inputs={**formula_inputs, "override_mm": override_mm, "auto_sized_mm": heuristic_mm},
        value=override_mm,
        unit="mm",
        citation=CITATION_RDSO_FAMILY,
    )


# --- the check-governed loop ------------------------------------------------------


def _check_governed_bumps(
    params: CulvertParams,
    thicknesses: dict[str, float],
    adjustable: frozenset[str],
    trail: TrailRecorder | None,
) -> list[_Bump]:
    """Analyse -> check -> bump each failing AUTO member by 50 mm until the
    design passes its own IRS CBC flexure/shear/crack checks.

    Mutates `thicknesses` in place; records a CalcStep per bump when a trail
    is given (None for the warning-reference pass). Bounded and loud: raises
    a clear ValueError at MAX_SIZING_PASSES — unreachable for valid inputs.
    """
    bumps: list[_Bump] = []
    if not adjustable:
        return bumps  # everything overridden — nothing the loop may touch
    for _ in range(MAX_SIZING_PASSES):
        geometry = _assemble_geometry(params, thicknesses)
        try:
            output = run_member_checks(analyse_frame(params, geometry), geometry, params)
        except ValueError:
            # A user override too thin for the cover allowance (effective depth
            # d <= 0): the member checks cannot run at all. Keep the current
            # sizes — the graph's check step raises the same loud error on
            # this design, exactly the pre-loop behaviour.
            return bumps
        failing = [
            member
            for member in _MEMBER_ORDER
            if member in adjustable and _member_fails(output, member)
        ]
        if not failing:
            return bumps
        for member in failing:
            bump = _bump_member(params, output, thicknesses, member)
            bumps.append(bump)
            if trail is not None:
                _record_bump(bump, params, trail)
    raise ValueError(
        f"check-governed sizing did not converge within {MAX_SIZING_PASSES} passes "
        f"for clear span {params.clear_span_m:g} m, clear height "
        f"{params.clear_height_m:g} m, cushion {params.cushion_m:g} m — the members "
        "cannot be sized to pass the IRS CBC checks; the request is outside the "
        "sizeable design domain"
    )


def _member_fails(output: ChecksOutput, member: str) -> bool:
    return any(
        c.member == member and c.status == "FAIL" and c.kind in _BUMPED_CHECK_KINDS
        for c in output.checks
    )


def _bump_member(
    params: CulvertParams,
    output: ChecksOutput,
    thicknesses: dict[str, float],
    member: str,
) -> _Bump:
    kind, clause, utilisation = _governing_failure(
        params, output, member, thicknesses[member]
    )
    previous = thicknesses[member]
    thicknesses[member] = previous + THICKNESS_ROUND_STEP_MM
    return _Bump(
        member=member,
        governing_kind=kind,
        governing_clause=clause,
        utilisation=utilisation,
        previous_mm=previous,
        new_mm=thicknesses[member],
    )


def _governing_failure(
    params: CulvertParams, output: ChecksOutput, member: str, thickness_mm: float
) -> tuple[str, str, float]:
    """The FAIL row that most exceeds its limit — flexure by d_req/d, shear by
    tau/tau_c ('crack' mirrors flexure, so the governor is one of these two)."""
    d_mm = thickness_mm - params.clear_cover_mm - ASSUMED_BAR_DIA_MM / 2.0
    tau_c = CONCRETE_PERMISSIBLE[params.concrete_grade].tau_c_n_mm2
    step_values = {step.step_id: step.value for step in output.trail}
    governing: tuple[float, str, str] | None = None
    for row in output.checks:
        if row.member != member or row.status != "FAIL":
            continue
        if row.kind == "flexure":
            utilisation = step_values[row.trail_ref] / d_mm  # d_req / d
        elif row.kind == "shear":
            utilisation = step_values[row.trail_ref] / tau_c  # tau / tau_c
        else:
            continue
        if governing is None or utilisation > governing[0]:
            governing = (utilisation, row.kind, row.clause)
    if governing is None:  # unreachable: 'crack' fails only when 'flexure' fails
        raise ValueError(
            f"no governing flexure/shear FAIL row found for {member!r} — "
            "cannot attribute the check-governed bump"
        )
    utilisation, kind, clause = governing
    return kind, clause, utilisation


def _record_bump(bump: _Bump, params: CulvertParams, trail: TrailRecorder) -> None:
    label = _MEMBER_LABELS[bump.member]
    trail.record(
        description=(
            f"{label} governed by {bump.governing_kind} check at "
            f"{params.cushion_m:g} m fill: {bump.previous_mm:g} → {bump.new_mm:g} mm"
        ),
        formula=f"t = t_prev + {THICKNESS_ROUND_STEP_MM:g} mm (check-governed sizing increment)",
        inputs={
            "member": bump.member,
            "previous_mm": bump.previous_mm,
            "governing_check": bump.governing_kind,
            "check_utilisation": round(bump.utilisation, 4),
        },
        value=bump.new_mm,
        unit="mm",
        citation=f"Check-governed sizing — governing check: {bump.governing_clause}",
    )


def _auto_size_assumption(
    *,
    member: str,
    label: str,
    heuristic_mm: float,
    final_mm: float,
    formula: str,
    member_bumps: list[_Bump],
    cushion_m: float,
) -> Assumption:
    if member_bumps:
        governing = " + ".join(sorted({b.governing_kind for b in member_bumps}))
        note = (
            f"Auto-sized {label.lower()}: heuristic {formula} = {heuristic_mm:g} mm, "
            f"check-governed to {final_mm:g} mm — governed by the IRS CBC {governing} "
            f"check at {cushion_m:g} m fill; heuristic per {CITATION_RDSO_FAMILY}."
        )
    else:
        note = (
            f"Auto-sized {label.lower()}: {formula} = {final_mm:g} mm, per "
            f"{CITATION_RDSO_FAMILY}; check-governed — the IRS CBC member checks "
            "pass at this thickness (no increase required)."
        )
    return Assumption(
        field=_MEMBER_FIELDS[member], value=final_mm, source="engine_default", note=note
    )


# --- geometry assembly (one source for the loop and the final result) -------------


def _external_dimensions(
    params: CulvertParams, thicknesses: dict[str, float]
) -> tuple[float, float, float, float]:
    """(W_ext, H_ext, fill at base, barrel length) — the exact rounding the
    final trail records, so the loop analyses the geometry that ships."""
    external_width_m = round(params.clear_span_m + 2 * thicknesses["wall"] / 1000.0, 3)
    external_height_m = round(
        params.clear_height_m
        + (thicknesses["top_slab"] + thicknesses["bottom_slab"]) / 1000.0,
        3,
    )
    fill_at_base_m = round(params.cushion_m + external_height_m, 3)
    barrel_length_m = round(
        params.formation_width_m + 2 * params.side_slope_h_per_v * fill_at_base_m, 2
    )
    return external_width_m, external_height_m, fill_at_base_m, barrel_length_m


def _assemble_geometry(
    params: CulvertParams, thicknesses: dict[str, float]
) -> BoxGeometry:
    external_width_m, external_height_m, _, barrel_length_m = _external_dimensions(
        params, thicknesses
    )
    return BoxGeometry(
        clear_span_m=params.clear_span_m,
        clear_height_m=params.clear_height_m,
        cushion_m=params.cushion_m,
        top_slab_thickness_mm=thicknesses["top_slab"],
        bottom_slab_thickness_mm=thicknesses["bottom_slab"],
        wall_thickness_mm=thicknesses["wall"],
        haunch_mm=params.haunch_mm,
        external_width_m=external_width_m,
        external_height_m=external_height_m,
        barrel_length_m=barrel_length_m,
    )
