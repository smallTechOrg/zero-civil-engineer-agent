"""Independent FE cross-check of the closed-form frame analysis (fixture V4).

Public API (pinned — the proof-check slice and graph wiring import exactly this):

    from engine.fe_check import cross_check, FeComparison
    fe: FeComparison = cross_check(params, geometry, analysis, out_dir)

Re-solves the box frame with anaStruct (a genuinely independent 2D FE solver),
diffs the results against the closed-form ``AnalysisResult`` and renders the
BMD/SFD diagrams to ``out_dir/bmd.svg`` and ``out_dir/sfd.svg``. The agreement
figure feeds proof-check item 11 ("independent FE re-solve agrees with
closed-form within +/-5%") and the UI caption.

Independence (the point of this module):
* The FE model is built ONLY from ``analysis.load_cases`` + ``analysis.frame_model``
  — never from the closed-form solver's internals. Every combination is
  re-solved from its ``case_factors`` over the elementary cases.
* Stiffness uses a realistic axial area (EA = E * t per metre strip), so the FE
  model independently includes the axial flexibility the closed form neglects —
  the diff is a true cross-check, not a re-run of the same idealisation.

Model (documented for the proof-check memo):
* Closed rectangular frame at the centreline dimensions of ``frame_model``,
  ``ELEMENTS_PER_MEMBER`` beam elements per member (midspan falls on a node).
* Loads per the ``LoadCase`` conventions (normative in ``domain.culvert``):
  top-slab UDL downward, net bottom UDL (incl. the uniform base reaction)
  upward, trapezoidal wall pressures inward-positive on BOTH walls (applied
  per element as anaStruct ``q=[q1, q2]`` segments — exact for linear
  profiles), wall self-weight as an axial point load at each wall top.
* Supports: the load set is self-equilibrated by construction (the base
  reaction closes vertical equilibrium), so only a minimal statically
  determinate restraint is added to remove rigid-body modes — a pin at the
  bottom-left corner and an x-roller at the bottom-right. Support reactions
  must therefore vanish; the residual is asserted at runtime and recorded
  (the proof of like-for-like modelling).

Sign mapping (explicit — anaStruct -> design convention):
* anaStruct plots a positive bending moment for tension on the right-hand side
  when walking an element from its first to its second node (verified: sagging
  midspan of a left->right beam under downward q is positive; the base moment
  of a bottom->top cantilever pushed toward +x is negative).
* Members are meshed bottom slab / top slab left->right and walls bottom->top,
  so mapping to the design convention (positive = tension on the INSIDE face)
  is a fixed per-member factor: top slab +1, bottom slab -1, left wall +1,
  right wall -1. The same factor maps shears (design V = dM_design/dx_local).

Significance floor (documented): relative diffs are only meaningful away from
zero crossings, so a row enters the agreement figure only when its closed-form
magnitude is at least ``max(absolute minimum, 2% of the peak closed-form
magnitude of that quantity kind)``. Below-floor rows are still reported in
``comparisons`` with ``included=False`` and ``diff_pct=None``.

Pure deterministic Python; matplotlib runs on the Agg backend (headless).
"""

# The Agg backend MUST be selected before pyplot is imported anywhere —
# anastruct imports matplotlib.pyplot at import time, so this precedes it.
import matplotlib

matplotlib.use("Agg")

from dataclasses import dataclass
from importlib.metadata import version as _package_version
from pathlib import Path
from typing import Literal, NamedTuple

import matplotlib.pyplot as plt
import numpy as np
from anastruct import SystemElements
from pydantic import BaseModel, Field

from domain.culvert import (
    AnalysisResult,
    BoxGeometry,
    CulvertParams,
    FrameModel,
    LoadCase,
    LoadCombination,
)

SOLVER = f"anastruct {_package_version('anastruct')}"
TOLERANCE_PCT = 5.0  # fixture V4 / proof-check item 11 contract
ELEMENTS_PER_MEMBER = 8  # >= 8 per member; even, so midspan falls on a node
E_CONCRETE_KN_M2 = 30.0e6  # nominal concrete modulus — ratios govern moments,
# but a realistic value gives realistic (finite) axial stiffness EA = E*t
REACTION_TOL_KN = 0.01  # self-equilibration guard: max acceptable support reaction
MOMENT_FLOOR_MIN_KNM = 1.0  # absolute minimum significance floor, moments
SHEAR_FLOOR_MIN_KN = 1.0  # absolute minimum significance floor, shears
FLOOR_FRACTION_OF_PEAK = 0.02  # floor = max(abs minimum, 2% of the peak magnitude)
_ZERO_LOAD = 1e-12

BMD_FILENAME = "bmd.svg"
SFD_FILENAME = "sfd.svg"

# Design-convention sign factor per FE member (see module docstring).
_MEMBER_SIGN = {"top_slab": 1.0, "bottom_slab": -1.0, "left_wall": 1.0, "right_wall": -1.0}
# FE member -> closed-form member name (one closed-form 'wall' entry covers both walls).
_COMPARED_MEMBERS = (("top_slab", "top_slab"), ("bottom_slab", "bottom_slab"), ("left_wall", "wall"))


class ForceComparison(BaseModel):
    """One compared quantity: closed-form vs independent FE, at a matching section.

    Sections use the member-local frames of ``MemberForces``: for slabs
    ``start`` = left corner, ``end`` = right corner; for the wall ``start`` =
    bottom corner, ``end`` = top corner; ``midspan`` = member mid-length.
    Values are in the design convention (moments tension-inside positive,
    kN*m/m; shears local dM/dx, kN/m).
    """

    combination: str = Field(description="LoadCombination.name this row was solved under")
    member: str = Field(description="'top_slab' | 'bottom_slab' | 'wall' (wall covers both walls)")
    section: str = Field(description="'start' | 'midspan' | 'end' in the member-local frame")
    quantity: Literal["moment", "shear"] = Field(description="Compared quantity kind")
    closed_form: float = Field(description="Closed-form value (kN*m/m for moments, kN/m for shears)")
    fe: float = Field(description="anaStruct value mapped to the design sign convention")
    diff_pct: float | None = Field(
        description="Relative difference |fe - closed_form| / |closed_form| * 100; "
        "None when the row is below the significance floor"
    )
    included: bool = Field(
        description="True when |closed_form| >= the significance floor and the row "
        "counts toward agreement_pct"
    )


class FeComparison(BaseModel):
    """Independent-FE cross-check result — consumed by proof-check item 11 and the UI.

    The UI caption reads: "Independent FE re-solve agrees within
    ``agreement_pct``%" and shows ``within_tolerance`` as the item verdict.
    """

    solver: str = Field(description=f"FE solver identity, e.g. '{SOLVER}'")
    tolerance_pct: float = Field(
        description="Agreement tolerance of the check item (5.0 per fixture V4)"
    )
    agreement_pct: float = Field(
        description="Governing (maximum) relative difference across all included "
        "compared quantities, percent — the 'agrees within X%' figure"
    )
    within_tolerance: bool = Field(description="agreement_pct <= tolerance_pct")
    comparisons: list[ForceComparison] = Field(
        description="Every compared quantity: per combination x member x section, "
        "moments and end shears, closed-form vs FE with relative diff"
    )
    governing: str = Field(
        description="Which quantity governs agreement_pct: "
        "'<combination> / <member> / <section> <quantity>'"
    )
    notes: list[str] = Field(
        description="Model description, sign mapping, significance floor, "
        "self-equilibration residual, diagram provenance — memo-ready"
    )
    combinations_checked: list[str] = Field(
        description="All combination names independently re-solved with the FE model"
    )
    diagram_combination: str = Field(
        description="Combination rendered in bmd.svg / sfd.svg (largest envelope moment)"
    )
    reaction_residual_kn: float = Field(
        description="Max |support reaction| across all re-solved combinations, kN — "
        "~0 proves the FE load set matches the closed-form model like-for-like"
    )
    wall_symmetry_residual: float = Field(
        description="Max |left wall - right wall| across the wall design quantities — "
        "~0 validates the per-member sign mapping"
    )
    elements_per_member: int = Field(description="FE mesh density used per member")
    moment_floor_knm: float = Field(
        description="Significance floor applied to moment rows, kN*m/m"
    )
    shear_floor_kn: float = Field(description="Significance floor applied to shear rows, kN/m")


class _CombinedLoads(NamedTuple):
    """Factored member loads of one combination, in LoadCase sign conventions."""

    w_top_kn_m2: float  # top slab UDL, downward positive
    w_bottom_net_kn_m2: float  # net bottom UDL incl. base reaction, upward positive
    p_wall_top_kn_m2: float  # wall pressure at the top node level, inward positive
    p_wall_bottom_kn_m2: float  # wall pressure at the bottom node level, inward positive
    wall_axial_kn_per_m: float  # axial load per wall (self-weight), downward


class _MemberDesignForces(NamedTuple):
    """FE end/mid forces for one member, mapped to the design sign convention."""

    moment_start: float
    moment_mid: float
    moment_end: float
    shear_start: float
    shear_end: float


@dataclass
class _FeSolve:
    """One solved anaStruct system plus the member -> element-id bookkeeping."""

    system: SystemElements
    members: dict[str, list[int]]
    reaction_residual_kn: float


def _combined_loads(
    cases_by_name: dict[str, LoadCase], combination: LoadCombination
) -> _CombinedLoads:
    """Factored sums over the elementary cases — rebuilt from load_cases only."""
    w_top = w_bottom = p_top = p_bottom = axial = 0.0
    for case_name, factor in combination.case_factors.items():
        case = cases_by_name.get(case_name)
        if case is None:
            raise ValueError(
                f"cross_check: combination '{combination.name}' references unknown "
                f"load case '{case_name}' — AnalysisResult is inconsistent"
            )
        w_top += factor * case.top_slab_udl_kn_m2
        w_bottom += factor * case.bottom_slab_net_udl_kn_m2
        p_top += factor * case.wall_pressure_top_kn_m2
        p_bottom += factor * case.wall_pressure_bottom_kn_m2
        axial += factor * case.wall_axial_kn_per_m
    return _CombinedLoads(w_top, w_bottom, p_top, p_bottom, axial)


def _build_and_solve(frame: FrameModel, loads: _CombinedLoads) -> _FeSolve:
    """Mesh the closed frame, apply one combination's loads, solve, check reactions."""
    length, height = frame.span_centreline_m, frame.height_centreline_m
    n = ELEMENTS_PER_MEMBER
    system = SystemElements()
    members: dict[str, list[int]] = {}

    def mesh_member(
        name: str, start: tuple[float, float], end: tuple[float, float],
        i_m4: float, thickness_mm: float,
    ) -> None:
        ea = E_CONCRETE_KN_M2 * (thickness_mm / 1000.0) * frame.strip_width_m
        ei = E_CONCRETE_KN_M2 * i_m4 * frame.strip_width_m
        ids = []
        for k in range(n):
            p1 = [start[0] + (end[0] - start[0]) * k / n, start[1] + (end[1] - start[1]) * k / n]
            p2 = [
                start[0] + (end[0] - start[0]) * (k + 1) / n,
                start[1] + (end[1] - start[1]) * (k + 1) / n,
            ]
            ids.append(system.add_element([p1, p2], EA=ea, EI=ei))
        members[name] = ids

    mesh_member("bottom_slab", (0.0, 0.0), (length, 0.0), frame.i_bottom_m4,
                frame.bottom_slab_thickness_mm)
    mesh_member("top_slab", (0.0, height), (length, height), frame.i_top_m4,
                frame.top_slab_thickness_mm)
    mesh_member("left_wall", (0.0, 0.0), (0.0, height), frame.i_wall_m4,
                frame.wall_thickness_mm)
    mesh_member("right_wall", (length, 0.0), (length, height), frame.i_wall_m4,
                frame.wall_thickness_mm)

    # Slab UDLs. anaStruct 'element' q on a left->right element is positive
    # DOWNWARD, so the downward-positive top UDL maps directly and the
    # upward-positive net bottom UDL is negated.
    if abs(loads.w_top_kn_m2) > _ZERO_LOAD:
        system.q_load(q=loads.w_top_kn_m2, element_id=members["top_slab"], direction="element")
    if abs(loads.w_bottom_net_kn_m2) > _ZERO_LOAD:
        system.q_load(
            q=-loads.w_bottom_net_kn_m2, element_id=members["bottom_slab"], direction="element"
        )

    # Wall trapezoids, piecewise-linear per element (exact for a linear profile).
    # anaStruct 'element' q on a bottom->top element is positive toward +x:
    # inward-positive maps to +q on the left wall and -q on the right wall.
    def wall_pressure_at(y: float) -> float:
        return loads.p_wall_bottom_kn_m2 + (
            loads.p_wall_top_kn_m2 - loads.p_wall_bottom_kn_m2
        ) * y / height

    for wall_name, inward_sign in (("left_wall", 1.0), ("right_wall", -1.0)):
        for k, element_id in enumerate(members[wall_name]):
            q1 = inward_sign * wall_pressure_at(height * k / n)
            q2 = inward_sign * wall_pressure_at(height * (k + 1) / n)
            if abs(q1) > _ZERO_LOAD or abs(q2) > _ZERO_LOAD:
                system.q_load(q=[q1, q2], element_id=element_id, direction="element")

    # Wall self-weight: axial-only in the load-case convention — a downward
    # point load at each wall top (anaStruct point_load Fy positive is downward).
    if abs(loads.wall_axial_kn_per_m) > _ZERO_LOAD:
        for x in (0.0, length):
            node_id = system.find_node_id([x, height])
            if node_id is None:  # pragma: no cover — mesh always creates the corners
                raise RuntimeError("cross_check: top corner node not found in the FE mesh")
            system.point_load(node_id, Fy=loads.wall_axial_kn_per_m)

    # Minimal statically determinate restraint — rigid-body modes only. The
    # load set is self-equilibrated, so these supports must carry ~nothing.
    bottom_left = system.find_node_id([0.0, 0.0])
    bottom_right = system.find_node_id([length, 0.0])
    if bottom_left is None or bottom_right is None:  # pragma: no cover
        raise RuntimeError("cross_check: bottom corner nodes not found in the FE mesh")
    system.add_support_hinged(bottom_left)
    system.add_support_roll(bottom_right, direction="x")

    system.solve()

    reaction_residual = max(
        max(abs(float(node.Fx)), abs(float(node.Fy)))
        for node in system.reaction_forces.values()
    )
    return _FeSolve(system=system, members=members, reaction_residual_kn=reaction_residual)


def _design_forces(solve: _FeSolve, member: str) -> _MemberDesignForces:
    """End/mid FE forces of one member, mapped to tension-inside-positive."""
    ids = solve.members[member]
    sign = _MEMBER_SIGN[member]
    first = solve.system.element_map[ids[0]]
    mid = solve.system.element_map[ids[len(ids) // 2]]  # even mesh: node at midspan
    last = solve.system.element_map[ids[-1]]
    return _MemberDesignForces(
        moment_start=sign * float(first.bending_moment[0]),
        moment_mid=sign * float(mid.bending_moment[0]),
        moment_end=sign * float(last.bending_moment[-1]),
        shear_start=sign * float(first.shear_force[0]),
        shear_end=sign * float(last.shear_force[-1]),
    )


def _comparison_row(
    combination: str,
    member: str,
    section: str,
    quantity: Literal["moment", "shear"],
    closed_form: float,
    fe: float,
    floor: float,
) -> ForceComparison:
    """Relative diff above the significance floor; below-floor rows are excluded."""
    included = abs(closed_form) >= floor
    diff_pct = abs(fe - closed_form) / abs(closed_form) * 100.0 if included else None
    return ForceComparison(
        combination=combination,
        member=member,
        section=section,
        quantity=quantity,
        closed_form=closed_form,
        fe=fe,
        diff_pct=diff_pct,
        included=included,
    )


def _wall_symmetry_residual(solve: _FeSolve) -> float:
    """Max |left - right| over the wall design quantities — sign-mapping validation."""
    left = _design_forces(solve, "left_wall")
    right = _design_forces(solve, "right_wall")
    return max(abs(l - r) for l, r in zip(left, right))


def _governing_diagram_combination(analysis: AnalysisResult) -> str:
    """The combination behind the largest envelope |moment| — rendered in the SVGs."""
    known = {combination.name for combination in analysis.combinations}
    best_value, best_name = -1.0, analysis.combinations[0].name
    for envelope in analysis.envelopes:
        for value, name in (
            (envelope.max_moment_knm, envelope.max_moment_combination),
            (envelope.min_moment_knm, envelope.min_moment_combination),
        ):
            if abs(value) > best_value and name in known:
                best_value, best_name = abs(value), name
    return best_name


def _fe_peak(solve: _FeSolve, attribute: str) -> float:
    """Peak |value| of an element result array over the whole frame."""
    return max(
        float(np.max(np.abs(getattr(solve.system.element_map[element_id], attribute))))
        for ids in solve.members.values()
        for element_id in ids
    )


def _render_diagram(
    solve: _FeSolve,
    kind: Literal["bmd", "sfd"],
    path: Path,
    combination: str,
    geometry: BoxGeometry,
) -> None:
    """Render one anaStruct diagram to SVG (Agg, vector-only, figure closed)."""
    if kind == "bmd":
        figure = solve.system.show_bending_moment(show=False, verbosity=1, figsize=(10.0, 7.0))
        title = f"Bending moment diagram — {combination} (kN·m per m strip)"
        peak = f"peak |M| = {_fe_peak(solve, 'bending_moment'):.1f} kN·m/m"
    else:
        figure = solve.system.show_shear_force(show=False, verbosity=1, figsize=(10.0, 7.0))
        title = f"Shear force diagram — {combination} (kN per m strip)"
        peak = f"peak |V| = {_fe_peak(solve, 'shear_force'):.1f} kN/m"
    caption = (
        f"Independent FE re-solve ({SOLVER}) — box "
        f"{geometry.clear_span_m:g} m × {geometry.clear_height_m:g} m clear, {peak}"
    )
    try:
        axes = figure.axes[0]
        axes.set_title(title, fontsize=11)
        figure.text(0.5, 0.02, caption, ha="center", fontsize=9)
        # svg.fonttype 'none' keeps labels as real SVG text (searchable, small);
        # a fixed hashsalt keeps the generated element ids deterministic.
        with matplotlib.rc_context({"svg.fonttype": "none", "svg.hashsalt": "fe_check"}):
            figure.savefig(path, format="svg", bbox_inches="tight")
    finally:
        plt.close(figure)


def cross_check(
    params: CulvertParams,
    geometry: BoxGeometry,
    analysis: AnalysisResult,
    out_dir: Path,
) -> FeComparison:
    """Independently re-solve the frame with anaStruct, diff, and render BMD/SFD.

    Every combination in ``analysis.combinations`` is re-solved from its
    elementary load cases; corner moments, midspan moments and end shears are
    compared per member against ``analysis.member_forces``. Writes
    ``out_dir/bmd.svg`` and ``out_dir/sfd.svg`` for the governing combination.
    Raises ``ValueError`` on an inconsistent ``AnalysisResult`` and
    ``RuntimeError`` when the FE model fails self-equilibration (which would
    void the like-for-like comparison).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not analysis.combinations:
        raise ValueError("cross_check: AnalysisResult has no load combinations to re-solve")
    closed_by_combination = {
        forces.combination: {member.member: member for member in forces.members}
        for forces in analysis.member_forces
    }
    missing = [c.name for c in analysis.combinations if c.name not in closed_by_combination]
    if missing:
        raise ValueError(
            f"cross_check: AnalysisResult has no member forces for combination(s) {missing}"
        )

    cases_by_name = {case.name: case for case in analysis.load_cases}
    solves: dict[str, _FeSolve] = {}
    raw_rows: list[tuple[str, str, str, str, float, float]] = []
    symmetry_residual = 0.0

    for combination in analysis.combinations:
        loads = _combined_loads(cases_by_name, combination)
        solve = _build_and_solve(analysis.frame_model, loads)
        solves[combination.name] = solve
        symmetry_residual = max(symmetry_residual, _wall_symmetry_residual(solve))

        closed = closed_by_combination[combination.name]
        for fe_member, cf_member in _COMPARED_MEMBERS:
            fe = _design_forces(solve, fe_member)
            cf = closed[cf_member]
            raw_rows.extend(
                [
                    (combination.name, cf_member, "start", "moment",
                     cf.end_moment_start_knm, fe.moment_start),
                    (combination.name, cf_member, "midspan", "moment",
                     cf.midspan_moment_knm, fe.moment_mid),
                    (combination.name, cf_member, "end", "moment",
                     cf.end_moment_end_knm, fe.moment_end),
                    (combination.name, cf_member, "start", "shear",
                     cf.end_shear_start_kn, fe.shear_start),
                    (combination.name, cf_member, "end", "shear",
                     cf.end_shear_end_kn, fe.shear_end),
                ]
            )

    reaction_residual = max(solve.reaction_residual_kn for solve in solves.values())
    if reaction_residual > REACTION_TOL_KN:
        raise RuntimeError(
            f"cross_check: FE support reactions do not vanish (max {reaction_residual:.4g} kN "
            f"> {REACTION_TOL_KN} kN) — the load set is not self-equilibrated, so the "
            "like-for-like comparison with the closed form is void"
        )

    peak_moment = max(
        (abs(r[4]) for r in raw_rows if r[3] == "moment"), default=0.0
    )
    peak_shear = max((abs(r[4]) for r in raw_rows if r[3] == "shear"), default=0.0)
    moment_floor = max(MOMENT_FLOOR_MIN_KNM, FLOOR_FRACTION_OF_PEAK * peak_moment)
    shear_floor = max(SHEAR_FLOOR_MIN_KN, FLOOR_FRACTION_OF_PEAK * peak_shear)

    comparisons = [
        _comparison_row(
            combination, member, section, quantity, closed_form, fe,  # type: ignore[arg-type]
            moment_floor if quantity == "moment" else shear_floor,
        )
        for combination, member, section, quantity, closed_form, fe in raw_rows
    ]
    included = [row for row in comparisons if row.included]
    if included:
        governing_row = max(included, key=lambda row: row.diff_pct or 0.0)
        agreement_pct = float(governing_row.diff_pct or 0.0)
        governing = (
            f"{governing_row.combination} / {governing_row.member} / "
            f"{governing_row.section} {governing_row.quantity}"
        )
    else:  # pragma: no cover — a real AnalysisResult always has significant forces
        agreement_pct, governing = 0.0, "none (all quantities below the significance floor)"

    diagram_combination = _governing_diagram_combination(analysis)
    diagram_solve = solves[diagram_combination]
    _render_diagram(diagram_solve, "bmd", out_dir / BMD_FILENAME, diagram_combination, geometry)
    _render_diagram(diagram_solve, "sfd", out_dir / SFD_FILENAME, diagram_combination, geometry)

    length = analysis.frame_model.span_centreline_m
    height = analysis.frame_model.height_centreline_m
    notes = [
        (
            f"Model: closed rectangular frame at centreline dimensions "
            f"{length:g} m x {height:g} m, {ELEMENTS_PER_MEMBER} beam elements per member "
            f"({4 * ELEMENTS_PER_MEMBER} total), rebuilt solely from AnalysisResult "
            "load_cases + frame_model — independent of the closed-form solver."
        ),
        (
            f"Stiffness: E = {E_CONCRETE_KN_M2:g} kN/m^2 (nominal concrete), EI from "
            "I = t^3/12 per metre strip, realistic axial area EA = E*t — the FE model "
            "includes the axial flexibility the closed form neglects."
        ),
        (
            "Supports: minimal statically determinate restraint (pin at bottom-left, "
            "x-roller at bottom-right) removing rigid-body modes only; the applied load "
            "set incl. the uniform base reaction is self-equilibrated — max support "
            f"reaction residual {reaction_residual:.3g} kN proves like-for-like modelling."
        ),
        (
            "Sign mapping: anaStruct positive moment = tension on the right-hand side "
            "walking start->end; members meshed slabs left->right / walls bottom->top; "
            "design-convention (tension inside positive) factors: top slab +1, "
            "bottom slab -1, left wall +1, right wall -1. Max left/right wall symmetry "
            f"residual {symmetry_residual:.3g}."
        ),
        (
            f"Significance floor: rows compared only where |closed-form| >= "
            f"max({MOMENT_FLOOR_MIN_KNM:g} kN*m/m, {FLOOR_FRACTION_OF_PEAK:.0%} of peak) "
            f"for moments ({moment_floor:.2f}) and max({SHEAR_FLOOR_MIN_KN:g} kN/m, "
            f"{FLOOR_FRACTION_OF_PEAK:.0%} of peak) for shears ({shear_floor:.2f}); "
            "below-floor rows are reported but excluded from agreement_pct."
        ),
        (
            f"All {len(analysis.combinations)} combinations re-solved; diagrams rendered "
            f"for '{diagram_combination}' (largest envelope moment)."
        ),
    ]

    return FeComparison(
        solver=SOLVER,
        tolerance_pct=TOLERANCE_PCT,
        agreement_pct=agreement_pct,
        within_tolerance=agreement_pct <= TOLERANCE_PCT,
        comparisons=comparisons,
        governing=governing,
        notes=notes,
        combinations_checked=[combination.name for combination in analysis.combinations],
        diagram_combination=diagram_combination,
        reaction_residual_kn=reaction_residual,
        wall_symmetry_residual=symmetry_residual,
        elements_per_member=ELEMENTS_PER_MEMBER,
        moment_floor_knm=moment_floor,
        shear_floor_kn=shear_floor,
    )
