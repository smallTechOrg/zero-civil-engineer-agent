"""Closed-form rigid-frame analysis of the single-cell box (Phase 2, irs-engine.md).

Public API (pinned — later slices import exactly this):

    from engine.analysis import analyse_frame
    result: AnalysisResult = analyse_frame(params, geometry)

Method: exact stiffness (slope-deflection) solution of the symmetric closed
rectangular frame — the closed-form equivalent of moment distribution, with no
iteration residue. All load cases here are symmetric about the vertical axis,
so the frame reduces to two unknown corner rotations (top, bottom):

    joint A (top):    (a + 2k) * theta_A + k * theta_B = -(FEM_A_slab + FEM_A_wall)
    joint B (bottom):  k * theta_A + (b + 2k) * theta_B = -(FEM_B_slab + FEM_B_wall)

with a = 2*E*I_top/L (symmetric far end), b = 2*E*I_bottom/L, k = 2*E*I_wall/H
(carry-over between the corners along the wall). E cancels — only stiffness
ratios matter. Sign conventions are normative in `domain.culvert`.

Pure deterministic Python — no LLM, no I/O, well under the 2 s budget.
"""

from pydantic import BaseModel, Field

from domain.culvert import (
    AnalysisResult,
    Assumption,
    BoxGeometry,
    CombinationForces,
    CulvertParams,
    FrameModel,
    LoadCase,
    LoadCombination,
    MemberForces,
    SectionEnvelope,
)
from engine.loads import build_load_cases, frame_centreline_dimensions
from engine.trail import TrailRecorder

CITATION_FRAME_METHOD = (
    "Slope-deflection (exact stiffness) solution of the closed rectangular frame — "
    "moment-distribution equivalent; IRICEN box-culvert design course / Reynolds & "
    "Steedman closed-frame tables"
)
CITATION_ENVELOPE = (
    "Design envelope — extreme of the analysed IRS working-stress combinations at the section"
)

MEMBER_TOP_SLAB = "top_slab"
MEMBER_BOTTOM_SLAB = "bottom_slab"
MEMBER_WALL = "wall"

SIGN_CONVENTION = (
    "Design moments positive = tension on the inside face; member locals: slabs left->right, "
    "walls bottom->top; loads toward the interior positive; kN*m/m and kN/m per 1 m strip"
)
BOUNDARY_NOTE = (
    "Closed frame on centreline dimensions; rigid-base uniform reaction; symmetric loads "
    "(no sway); axial deformation and haunches neglected in member stiffness"
)
MODULUS_NOTE = "Relative stiffness only — Young's modulus cancels in the closed frame"


class FrameSolution(BaseModel):
    """One symmetric closed-frame solve: corner design moments, member forces, residuals."""

    m_top_corner_knm: float = Field(
        description="Design moment shared by the top-slab end and wall top (tension-inside +)"
    )
    m_bottom_corner_knm: float = Field(
        description="Design moment shared by the bottom-slab end and wall bottom"
    )
    residual_top_knm: float = Field(
        description="Top-corner joint moment residual (exact solve: ~machine epsilon)"
    )
    residual_bottom_knm: float = Field(description="Bottom-corner joint moment residual")
    members: list[MemberForces] = Field(
        description="End/mid design forces for top_slab, bottom_slab, wall"
    )


def build_frame_model(params: CulvertParams, geometry: BoxGeometry) -> FrameModel:
    """The 1 m-strip centreline frame the solver (and any FE re-solve) analyses."""
    span_c, height_c = frame_centreline_dimensions(geometry)
    return FrameModel(
        span_centreline_m=span_c,
        height_centreline_m=height_c,
        strip_width_m=1.0,
        top_slab_thickness_mm=geometry.top_slab_thickness_mm,
        bottom_slab_thickness_mm=geometry.bottom_slab_thickness_mm,
        wall_thickness_mm=geometry.wall_thickness_mm,
        i_top_m4=(geometry.top_slab_thickness_mm / 1000.0) ** 3 / 12.0,
        i_bottom_m4=(geometry.bottom_slab_thickness_mm / 1000.0) ** 3 / 12.0,
        i_wall_m4=(geometry.wall_thickness_mm / 1000.0) ** 3 / 12.0,
        modulus_note=MODULUS_NOTE,
        boundary_note=BOUNDARY_NOTE,
        sign_convention=SIGN_CONVENTION,
    )


def _beam_moment_shear(
    x: float, length: float, m_start: float, m_end: float, uniform: float, triangle: float
) -> tuple[float, float]:
    """Design moment and shear at x on a member in its design-local frame.

    `uniform` is the constant inward load; `triangle` the linearly varying part with
    its maximum at the local origin (x = 0) and zero at x = length.
    """
    v0 = (m_end - m_start) / length + uniform * length / 2.0 + triangle * length / 3.0
    moment = (
        m_start
        + v0 * x
        - uniform * x * x / 2.0
        - triangle * (x * x / 2.0 - x**3 / (6.0 * length))
    )
    shear = v0 - uniform * x - triangle * (x - x * x / (2.0 * length))
    return moment, shear


def solve_closed_frame(
    frame: FrameModel,
    w_top_kn_m2: float,
    w_bottom_kn_m2: float,
    p_wall_top_kn_m2: float,
    p_wall_bottom_kn_m2: float,
) -> FrameSolution:
    """Exact symmetric solve for one set of combined member loads.

    Loads follow the LoadCase conventions: `w_top` down on the top slab, `w_bottom`
    up on the bottom slab (net of the base reaction), wall trapezoid inward-positive
    between the top and bottom node pressures, applied on both walls.
    """
    length, height = frame.span_centreline_m, frame.height_centreline_m
    a = 2.0 * frame.i_top_m4 / length
    b = 2.0 * frame.i_bottom_m4 / length
    k = 2.0 * frame.i_wall_m4 / height

    uniform = p_wall_top_kn_m2
    triangle = p_wall_bottom_kn_m2 - p_wall_top_kn_m2

    # Fixed-end moments, counterclockwise-positive on the member ends.
    fem_a_slab = -w_top_kn_m2 * length**2 / 12.0
    fem_b_slab = +w_bottom_kn_m2 * length**2 / 12.0
    fem_b_wall = -(uniform * height**2 / 12.0 + triangle * height**2 / 20.0)
    fem_a_wall = +(uniform * height**2 / 12.0 + triangle * height**2 / 30.0)

    a11, a12, r1 = a + 2.0 * k, k, -(fem_a_slab + fem_a_wall)
    a21, a22, r2 = k, b + 2.0 * k, -(fem_b_slab + fem_b_wall)
    determinant = a11 * a22 - a12 * a21
    theta_a = (r1 * a22 - a12 * r2) / determinant
    theta_b = (a11 * r2 - a21 * r1) / determinant

    m_a_slab = a * theta_a + fem_a_slab
    m_a_wall = k * (2.0 * theta_a + theta_b) + fem_a_wall
    m_b_slab = b * theta_b + fem_b_slab
    m_b_wall = k * (2.0 * theta_b + theta_a) + fem_b_wall

    m_top = m_a_slab  # design convention: shared corner moment (== -m_a_wall)
    m_bottom = m_b_wall  # == -m_b_slab

    members = [
        _slab_forces(MEMBER_TOP_SLAB, length, m_top, w_top_kn_m2),
        _slab_forces(MEMBER_BOTTOM_SLAB, length, m_bottom, w_bottom_kn_m2),
        _wall_forces(height, m_bottom, m_top, uniform, triangle),
    ]
    return FrameSolution(
        m_top_corner_knm=m_top,
        m_bottom_corner_knm=m_bottom,
        residual_top_knm=m_a_slab + m_a_wall,
        residual_bottom_knm=m_b_slab + m_b_wall,
        members=members,
    )


def _slab_forces(member: str, length: float, m_corner: float, w_inward: float) -> MemberForces:
    m_mid, _ = _beam_moment_shear(length / 2.0, length, m_corner, m_corner, w_inward, 0.0)
    _, v_start = _beam_moment_shear(0.0, length, m_corner, m_corner, w_inward, 0.0)
    _, v_end = _beam_moment_shear(length, length, m_corner, m_corner, w_inward, 0.0)
    return MemberForces(
        member=member,
        end_moment_start_knm=m_corner,
        end_moment_end_knm=m_corner,
        midspan_moment_knm=m_mid,
        end_shear_start_kn=v_start,
        end_shear_end_kn=v_end,
    )


def _wall_forces(
    height: float, m_bottom: float, m_top: float, uniform: float, triangle: float
) -> MemberForces:
    m_mid, _ = _beam_moment_shear(height / 2.0, height, m_bottom, m_top, uniform, triangle)
    _, v_bottom = _beam_moment_shear(0.0, height, m_bottom, m_top, uniform, triangle)
    _, v_top = _beam_moment_shear(height, height, m_bottom, m_top, uniform, triangle)
    return MemberForces(
        member=MEMBER_WALL,
        end_moment_start_knm=m_bottom,
        end_moment_end_knm=m_top,
        midspan_moment_knm=m_mid,
        end_shear_start_kn=v_bottom,
        end_shear_end_kn=v_top,
    )


def analyse_frame(
    params: CulvertParams,
    geometry: BoxGeometry,
    *,
    loading_standard=None,
) -> AnalysisResult:
    """Load cases + closed-form rigid-frame analysis + envelopes, fully traced.

    `loading_standard` follows the pinned `engine.loading` interface; None resolves
    the standard named by `params.loading_standard` (the production path).
    """
    trail = TrailRecorder()
    frame = build_frame_model(params, geometry)
    build = build_load_cases(
        params, geometry, loading_standard=loading_standard, trail=trail
    )

    for label, value, unit in (
        ("top slab", frame.i_top_m4, "m^4/m"),
        ("bottom slab", frame.i_bottom_m4, "m^4/m"),
        ("wall", frame.i_wall_m4, "m^4/m"),
    ):
        trail.record(
            description=f"Frame stiffness: second moment of area of the {label} (1 m strip)",
            formula="I = (t / 1000)^3 / 12",
            inputs={"member": label},
            value=value,
            unit=unit,
            citation=CITATION_FRAME_METHOD,
        )

    cases_by_name = {case.name: case for case in build.cases}
    member_forces: list[CombinationForces] = []
    combined_loads: dict[str, tuple[float, float, float, float]] = {}
    for combination in build.combinations:
        loads = _combine(cases_by_name, combination)
        combined_loads[combination.name] = loads
        solution = _solve_and_trace(frame, combination, loads, trail)
        member_forces.append(
            CombinationForces(combination=combination.name, members=solution.members)
        )

    envelopes = _build_envelopes(frame, geometry, build.combinations, combined_loads, trail)

    assumptions = [
        *build.assumptions,
        Assumption(
            field="frame_stiffness",
            value="haunches neglected",
            source="engine_default",
            note=f"Prismatic members at actual thicknesses; haunches neglected in stiffness — "
            f"{CITATION_FRAME_METHOD}.",
        ),
    ]
    return AnalysisResult(
        load_cases=build.cases,
        combinations=build.combinations,
        member_forces=member_forces,
        envelopes=envelopes,
        frame_model=frame,
        assumptions=assumptions,
        trail=trail.steps,
    )


def _combine(
    cases_by_name: dict[str, LoadCase], combination: LoadCombination
) -> tuple[float, float, float, float]:
    w_top = w_bottom = p_top = p_bottom = 0.0
    for case_name, factor in combination.case_factors.items():
        case = cases_by_name[case_name]
        w_top += factor * case.top_slab_udl_kn_m2
        w_bottom += factor * case.bottom_slab_net_udl_kn_m2
        p_top += factor * case.wall_pressure_top_kn_m2
        p_bottom += factor * case.wall_pressure_bottom_kn_m2
    return w_top, w_bottom, p_top, p_bottom


def _solve_and_trace(
    frame: FrameModel,
    combination: LoadCombination,
    loads: tuple[float, float, float, float],
    trail: TrailRecorder,
) -> FrameSolution:
    w_top, w_bottom, p_top, p_bottom = loads
    name = combination.name
    for description, formula, value, unit in (
        (f"{name}: combined top slab load", "w_top = sum(factor * case w_top)", w_top, "kN/m^2"),
        (
            f"{name}: combined net bottom slab load (upward)",
            "w_bottom = sum(factor * case w_bottom_net)",
            w_bottom,
            "kN/m^2",
        ),
        (
            f"{name}: combined wall pressure at the top node (inward +)",
            "p_top = sum(factor * case p_top)",
            p_top,
            "kN/m^2",
        ),
        (
            f"{name}: combined wall pressure at the bottom node (inward +)",
            "p_bottom = sum(factor * case p_bottom)",
            p_bottom,
            "kN/m^2",
        ),
    ):
        trail.record(
            description=description,
            formula=formula,
            inputs={"combination": name},
            value=value,
            unit=unit,
            citation=combination.citation,
        )

    solution = solve_closed_frame(frame, w_top, w_bottom, p_top, p_bottom)

    trail.record(
        description=f"{name}: top corner design moment (slope-deflection solve)",
        formula="M_top = a*theta_A + FEM_A_slab  (joint-balanced closed frame)",
        inputs={"combination": name, "w_top_kn_m2": w_top, "p_top_kn_m2": p_top},
        value=solution.m_top_corner_knm,
        unit="kN*m/m",
        citation=CITATION_FRAME_METHOD,
    )
    trail.record(
        description=f"{name}: bottom corner design moment (slope-deflection solve)",
        formula="M_bottom = k*(2*theta_B + theta_A) + FEM_B_wall",
        inputs={"combination": name, "w_bottom_kn_m2": w_bottom, "p_bottom_kn_m2": p_bottom},
        value=solution.m_bottom_corner_knm,
        unit="kN*m/m",
        citation=CITATION_FRAME_METHOD,
    )
    for member in solution.members:
        trail.record(
            description=f"{name}: {member.member} midspan design moment",
            formula="M_mid = M_corner + w*L^2/8 (slabs) / static mid value (walls)",
            inputs={"combination": name, "member": member.member},
            value=member.midspan_moment_knm,
            unit="kN*m/m",
            citation=CITATION_FRAME_METHOD,
        )
        trail.record(
            description=f"{name}: {member.member} end shear at the start node",
            formula="V_0 = (M_end - M_start)/L + u*L/2 + tri*L/3",
            inputs={"combination": name, "member": member.member},
            value=member.end_shear_start_kn,
            unit="kN/m",
            citation=CITATION_FRAME_METHOD,
        )
        trail.record(
            description=f"{name}: {member.member} end shear at the end node",
            formula="V_L = V_0 - total transverse load",
            inputs={"combination": name, "member": member.member},
            value=member.end_shear_end_kn,
            unit="kN/m",
            citation=CITATION_FRAME_METHOD,
        )
    return solution


def _section_positions(
    frame: FrameModel, geometry: BoxGeometry
) -> dict[str, list[tuple[str, float]]]:
    """Critical-section positions (member-local x, metres) — haunch faces clamped to midspan."""
    length, height = frame.span_centreline_m, frame.height_centreline_m
    haunch_m = geometry.haunch_mm / 1000.0
    slab_face = min((geometry.wall_thickness_mm / 2.0) / 1000.0 + haunch_m, length / 2.0)
    wall_face_bottom = min(
        (geometry.bottom_slab_thickness_mm / 2.0) / 1000.0 + haunch_m, height / 2.0
    )
    wall_face_top = max(
        height - (geometry.top_slab_thickness_mm / 2.0) / 1000.0 - haunch_m, height / 2.0
    )
    slab_sections = [("end", 0.0), ("haunch_face", slab_face), ("midspan", length / 2.0)]
    return {
        MEMBER_TOP_SLAB: slab_sections,
        MEMBER_BOTTOM_SLAB: slab_sections,
        MEMBER_WALL: [
            ("bottom_end", 0.0),
            ("bottom_haunch_face", wall_face_bottom),
            ("midheight", height / 2.0),
            ("top_haunch_face", wall_face_top),
            ("top_end", height),
        ],
    }


def _member_values_at(
    frame: FrameModel,
    member: str,
    x: float,
    loads: tuple[float, float, float, float],
    solution_cache: FrameSolution,
) -> tuple[float, float]:
    w_top, w_bottom, p_top, p_bottom = loads
    if member == MEMBER_TOP_SLAB:
        return _beam_moment_shear(
            x,
            frame.span_centreline_m,
            solution_cache.m_top_corner_knm,
            solution_cache.m_top_corner_knm,
            w_top,
            0.0,
        )
    if member == MEMBER_BOTTOM_SLAB:
        return _beam_moment_shear(
            x,
            frame.span_centreline_m,
            solution_cache.m_bottom_corner_knm,
            solution_cache.m_bottom_corner_knm,
            w_bottom,
            0.0,
        )
    return _beam_moment_shear(
        x,
        frame.height_centreline_m,
        solution_cache.m_bottom_corner_knm,
        solution_cache.m_top_corner_knm,
        p_top,
        p_bottom - p_top,
    )


def _build_envelopes(
    frame: FrameModel,
    geometry: BoxGeometry,
    combinations: list[LoadCombination],
    combined_loads: dict[str, tuple[float, float, float, float]],
    trail: TrailRecorder,
) -> list[SectionEnvelope]:
    solutions = {
        name: solve_closed_frame(frame, *loads) for name, loads in combined_loads.items()
    }
    envelopes: list[SectionEnvelope] = []
    for member, sections in _section_positions(frame, geometry).items():
        for section, x in sections:
            values = [
                (
                    combination.name,
                    *_member_values_at(
                        frame, member, x, combined_loads[combination.name],
                        solutions[combination.name],
                    ),
                )
                for combination in combinations
            ]
            max_name, max_moment, _ = max(values, key=lambda v: v[1])
            min_name, min_moment, _ = min(values, key=lambda v: v[1])
            shear_name, _, shear = max(values, key=lambda v: abs(v[2]))
            envelope = SectionEnvelope(
                member=member,
                section=section,
                position_m=x,
                max_moment_knm=max_moment,
                max_moment_combination=max_name,
                min_moment_knm=min_moment,
                min_moment_combination=min_name,
                max_abs_shear_kn=abs(shear),
                max_shear_combination=shear_name,
            )
            envelopes.append(envelope)
            for description, formula, value, governing in (
                (
                    f"Envelope: {member} {section} maximum design moment",
                    "M_max = max over combinations at the section",
                    max_moment,
                    max_name,
                ),
                (
                    f"Envelope: {member} {section} minimum design moment",
                    "M_min = min over combinations at the section",
                    min_moment,
                    min_name,
                ),
                (
                    f"Envelope: {member} {section} maximum shear",
                    "V_max = max |V| over combinations at the section",
                    abs(shear),
                    shear_name,
                ),
            ):
                trail.record(
                    description=description,
                    formula=formula,
                    inputs={"member": member, "section": section, "position_m": x,
                            "governing_combination": governing},
                    value=value,
                    unit="kN*m/m" if "moment" in description else "kN/m",
                    citation=CITATION_ENVELOPE,
                )
    return envelopes
