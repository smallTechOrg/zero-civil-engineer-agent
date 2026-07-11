"""Code-set fidelity guard (citation domain honesty).

Every citation the deterministic RCC-cantilever-retaining-wall pipeline emits —
every ``calc_sheet.json`` line/trail ``citation`` and every ``compliance.json``
item ``clause`` — must be WITHIN the module's declared code set
(``RetainingWallComponent.codes``) or a recognised non-code provenance string, and
NONE may cite an out-of-domain design code. A retaining wall is a CONCRETE civil
structure: its basis is IS 456 / IRS Concrete Bridge Code (RCC section design) plus
the IRS Bridge Substructure & Foundation Code (Rankine/Coulomb earth pressure &
stability) and IR Bridge Rules (track surcharge) — road-congress (IRC), steel
(IS 800) and MECHANICAL codes (IS 816, RDSO Specifications, Machine Design) are
forbidden. This locks the earth-pressure citation reconcile: the module now
declares the IRS Bridge Substructure & Foundation Code that the Rankine/Coulomb
trail actually cites (exactly as the pier/abutment declares for the same basis).
"""

import json
import re
from pathlib import Path

import pytest

from components.retaining_wall.analysis import analyse_wall
from components.retaining_wall.calcsheet import compose_calc_sheet
from components.retaining_wall.checks import run_wall_checks
from components.retaining_wall.drawing import generate_ga
from components.retaining_wall.module import RetainingWallComponent
from components.retaining_wall.params import RetainingWallParams
from components.retaining_wall.proofcheck import (
    _FORBIDDEN_CITATION_PATTERNS,
    run_proof_check,
    validate_narration,
)
from components.retaining_wall.sizing import size_wall

# The single source of truth for the declared set — the same list the registry
# publishes and the spec declares.
DECLARED_CODES = tuple(RetainingWallComponent.codes)
# The engine writes the "IR Bridge Rules" loads document under its full official
# title, which opens "IRS Bridge Rules — Rules specifying the loads ...". That is
# the SAME Indian Railway Standard Bridge Rules the module declares as "IR Bridge
# Rules"; accept the document spelling so the track-surcharge citation reads as the
# declared code, not a foreign one. (The forbidden-code scan below is unaffected.)
_DECLARED_LOWER = tuple(code.lower() for code in DECLARED_CODES) + ("irs bridge rules",)

# Recognised NON-code provenance markers legitimately used as a citation/clause
# (user input, geometric proportioning, the earth-pressure METHOD names, and the
# two proof-check meta items). None of these name a design code.
_PROVENANCE_MARKERS = (
    "user design requirement",
    "preset default",
    "see the assumptions block",
    "proportioned geometry",
    "independent re-solve",
    "calc-vs-drawing",
    "rankine",
    "coulomb",
)

# A retaining wall is civil-concrete: MECHANICAL codes are out-of-domain defects.
# Patterns are assembled by concatenation so this file never greps as a violation.
# (Note "RDSO Spec" targets the rolling-stock *Specifications*, NOT the legitimate
# civil "RDSO B-10152/R" standard-drawing tags.)
_FOREIGN_MECHANICAL_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"\bI" + r"S\s*[:.\-]?\s*816\b",
        r"\bR" + r"DSO\s+Spec",
        r"\bM" + r"achine\s+Design",
        r"\bS" + r"higley",
        r"\bP" + r"SG\b",
    )
)
_ALL_FORBIDDEN = tuple(_FORBIDDEN_CITATION_PATTERNS) + _FOREIGN_MECHANICAL_PATTERNS

LEVEL = RetainingWallParams(
    retained_height_m=5.0, safe_bearing_capacity_kn_m2=200.0, backfill_friction_angle_deg=30.0,
)
SLOPED = RetainingWallParams(
    retained_height_m=6.0, safe_bearing_capacity_kn_m2=250.0,
    backfill_friction_angle_deg=28.0, backfill_slope_deg=15.0,
)


def _forbidden_hit(text: str) -> str | None:
    for pattern in _ALL_FORBIDDEN:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None


def _within_codeset(text: str) -> bool:
    lowered = " ".join(text.lower().split())
    if any(code in lowered for code in _DECLARED_LOWER):
        return True
    return any(marker in lowered for marker in _PROVENANCE_MARKERS)


def _run(params: RetainingWallParams, out_dir: Path):
    sizing = size_wall(params)
    geometry = sizing.geometry
    analysis = analyse_wall(params, geometry)
    checks = run_wall_checks(analysis, geometry, params)
    generate_ga(params, geometry, out_dir, run_id="cs")
    calc_sheet_path = compose_calc_sheet(
        trail=[list(sizing.trail), list(analysis.trail), list(checks.trail)],
        checks=list(checks.checks),
        assumptions=[*sizing.assumptions, *analysis.assumptions, *checks.assumptions],
        warnings=list(sizing.warnings),
        params=params,
        geometry=geometry,
        out_dir=out_dir,
    )
    result = run_proof_check(
        params=params, geometry=geometry, analysis=analysis,
        checks=list(checks.checks), ga_dxf_path=out_dir / "ga.dxf", out_dir=out_dir,
    )
    calc_sheet = json.loads(calc_sheet_path.read_text())
    compliance = json.loads((out_dir / "compliance.json").read_text())
    return calc_sheet, compliance, result


def _calc_sheet_citations(calc_sheet: dict) -> list[str]:
    citations: list[str] = []
    for section in calc_sheet["sections"]:
        for line in section["lines"]:
            citations.append(line["citation"])
    citations.extend(step["citation"] for step in calc_sheet["trail"])
    return citations


def test_declared_set_covers_the_earth_pressure_and_concrete_codes():
    # The reconcile (Finding B): the earth-pressure/stability basis the Rankine /
    # Coulomb trail actually cites is now declared, alongside the RCC concrete codes.
    assert "IRS Bridge Substructure & Foundation Code" in DECLARED_CODES
    assert "IRS Concrete Bridge Code" in DECLARED_CODES
    assert "IS 456" in DECLARED_CODES
    joined = " | ".join(DECLARED_CODES)
    assert "IRC" not in joined
    assert "IS 800" not in joined
    assert "IS 816" not in joined


@pytest.mark.parametrize("params", [LEVEL, SLOPED], ids=["level_backfill", "sloped_backfill"])
def test_every_calc_sheet_citation_is_within_the_declared_set(params, tmp_path):
    calc_sheet, _compliance, _result = _run(params, tmp_path)
    citations = _calc_sheet_citations(calc_sheet)
    assert citations, "calc sheet produced no citations to audit"
    for citation in citations:
        assert citation is not None and citation.strip(), "empty calc-sheet citation"
        assert _forbidden_hit(citation) is None, (
            f"out-of-domain (IRC / IS 800 / mechanical) citation leaked into calc sheet: {citation!r}"
        )
        assert _within_codeset(citation), (
            f"calc-sheet citation outside the declared code set / provenance: {citation!r}"
        )


@pytest.mark.parametrize("params", [LEVEL, SLOPED], ids=["level_backfill", "sloped_backfill"])
def test_every_compliance_clause_is_within_the_declared_set(params, tmp_path):
    _calc_sheet, compliance, _result = _run(params, tmp_path)
    clauses = [item["clause"] for item in compliance["items"]]
    assert len(clauses) == 12
    for clause in clauses:
        assert clause is not None and clause.strip(), "empty compliance clause"
        assert _forbidden_hit(clause) is None, (
            f"out-of-domain (IRC / IS 800 / mechanical) citation leaked into compliance: {clause!r}"
        )
        assert _within_codeset(clause), (
            f"compliance clause outside the declared code set / provenance: {clause!r}"
        )


@pytest.mark.parametrize("params", [LEVEL, SLOPED], ids=["level_backfill", "sloped_backfill"])
def test_narration_forbids_out_of_domain_codes_but_admits_is_456(params, tmp_path):
    _calc_sheet, _compliance, result = _run(params, tmp_path)

    def _forbidden_problems(narration: str) -> list[str]:
        return [p for p in validate_narration(narration, result) if "forbidden" in p]

    # Road (IRC) and steel (IS 800) are out-of-domain for a concrete retaining wall.
    assert _forbidden_problems("checked per IRC:78 provisions")
    assert _forbidden_problems("the fabricated section follows IS 800 clauses")
    # IS 456 is IN the declared set — it must NOT be flagged as a forbidden
    # out-of-set citation (numeric grounding of the digits is a separate concern).
    assert _forbidden_problems("the RCC stem follows IS 456 working stress") == []
