"""Code-set fidelity guard (citation domain honesty).

Every citation the deterministic slab / T-beam deck pipeline emits — every
``calc_sheet.json`` line/trail ``citation`` and every ``compliance.json`` item
``clause`` — must be WITHIN the module's declared code set
(``SlabTbeamComponent.codes``) or a recognised non-code provenance string, and
NONE may cite an out-of-domain design code. A slab / T-beam deck is a CONCRETE
railway-bridge superstructure: its basis is IRS Concrete Bridge Code + IS 456 (RCC
flexure / shear / minimum steel / deflection) with IR Bridge Rules for the 25t
live load — road-congress (IRC), steel (IS 800) and MECHANICAL codes (IS 816,
RDSO Specifications, Machine Design) are forbidden.
"""

import json
import re
from pathlib import Path

import pytest

from components.slab_tbeam.analysis import analyse_deck
from components.slab_tbeam.calcsheet import compose_calc_sheet
from components.slab_tbeam.checks import run_deck_checks
from components.slab_tbeam.drawing import generate_ga
from components.slab_tbeam.module import SlabTbeamComponent
from components.slab_tbeam.params import SlabTbeamParams
from components.slab_tbeam.proofcheck import (
    _FORBIDDEN_CITATION_PATTERNS,
    run_proof_check,
    validate_narration,
)
from components.slab_tbeam.sizing import size_deck

# The single source of truth for the declared set — the same list the registry
# publishes and the spec declares.
DECLARED_CODES = tuple(SlabTbeamComponent.codes)
# The engine writes the "IR Bridge Rules" loads document under its full official
# title, which opens "IRS Bridge Rules — Rules specifying the loads ...". That is
# the SAME Indian Railway Standard Bridge Rules the module declares as "IR Bridge
# Rules"; accept the document spelling so the 25t live-load citation reads as the
# declared code, not a foreign one. (The forbidden-code scan below is unaffected.)
_DECLARED_LOWER = tuple(code.lower() for code in DECLARED_CODES) + ("irs bridge rules",)

# Recognised NON-code provenance markers legitimately used as a citation/clause
# (user input, geometric proportioning, and the two proof-check meta items). None
# of these name a design code.
_PROVENANCE_MARKERS = (
    "user design requirement",
    "preset default",
    "see the assumptions block",
    "proportioned geometry",
    "independent re-solve",
    "calc-vs-drawing",
)

# A slab / T-beam deck is civil-concrete: MECHANICAL codes are out-of-domain
# defects. Patterns are assembled by concatenation so this file never greps as a
# violation. ("RDSO Spec" targets the rolling-stock *Specifications*, NOT the
# legitimate civil "RDSO" standard-drawing tags.)
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

T_BEAM = SlabTbeamParams(span_m=12.0, deck_type="t_beam")
SOLID_SLAB = SlabTbeamParams(span_m=8.0, deck_type="solid_slab")


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


def _run(params: SlabTbeamParams, out_dir: Path):
    sizing = size_deck(params)
    geometry = sizing.geometry
    analysis = analyse_deck(params, geometry)
    checks = run_deck_checks(analysis, geometry, params)
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


def test_declared_set_is_concrete_bridge_not_steel_or_road():
    assert "IRS Concrete Bridge Code" in DECLARED_CODES
    assert "IS 456" in DECLARED_CODES
    joined = " | ".join(DECLARED_CODES)
    assert "IRC" not in joined
    assert "IS 800" not in joined
    assert "IS 816" not in joined


@pytest.mark.parametrize("params", [T_BEAM, SOLID_SLAB], ids=["t_beam", "solid_slab"])
def test_every_calc_sheet_citation_is_within_the_declared_set(params, tmp_path):
    calc_sheet, _compliance, _result = _run(params, tmp_path)
    citations = _calc_sheet_citations(calc_sheet)
    assert citations, "calc sheet produced no citations to audit"
    for citation in citations:
        assert citation is not None and citation.strip(), "empty calc-sheet citation"
        assert _forbidden_hit(citation) is None, (
            f"out-of-domain (IS 800 / IRC / mechanical) citation leaked into calc sheet: {citation!r}"
        )
        assert _within_codeset(citation), (
            f"calc-sheet citation outside the declared code set / provenance: {citation!r}"
        )


@pytest.mark.parametrize("params", [T_BEAM, SOLID_SLAB], ids=["t_beam", "solid_slab"])
def test_every_compliance_clause_is_within_the_declared_set(params, tmp_path):
    _calc_sheet, compliance, _result = _run(params, tmp_path)
    clauses = [item["clause"] for item in compliance["items"]]
    assert len(clauses) == 9
    for clause in clauses:
        assert clause is not None and clause.strip(), "empty compliance clause"
        assert _forbidden_hit(clause) is None, (
            f"out-of-domain (IS 800 / IRC / mechanical) citation leaked into compliance: {clause!r}"
        )
        assert _within_codeset(clause), (
            f"compliance clause outside the declared code set / provenance: {clause!r}"
        )


@pytest.mark.parametrize("params", [T_BEAM, SOLID_SLAB], ids=["t_beam", "solid_slab"])
def test_narration_forbids_out_of_domain_codes_but_admits_is_456(params, tmp_path):
    _calc_sheet, _compliance, result = _run(params, tmp_path)

    def _forbidden_problems(narration: str) -> list[str]:
        return [p for p in validate_narration(narration, result) if "forbidden" in p]

    # Steel (IS 800) and road (IRC) are out-of-domain for a concrete deck.
    assert _forbidden_problems("the plate girder per IS 800 provisions")
    assert _forbidden_problems("checked per IRC:6 loads")
    # IS 456 is IN the declared set — it must NOT be flagged as a forbidden
    # out-of-set citation (numeric grounding of the digits is a separate concern).
    assert _forbidden_problems("the RCC deck follows IS 456 working stress") == []
