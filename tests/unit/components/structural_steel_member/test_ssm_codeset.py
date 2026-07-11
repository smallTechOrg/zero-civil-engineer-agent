"""Code-set fidelity guard (the positive-citation guard that caught the P2 defect).

Every citation the deterministic steel-member pipeline emits — every
``calc_sheet.json`` line/trail ``citation`` and every ``compliance.json`` item
``clause`` — must be WITHIN the module's declared code set
(``StructuralSteelMemberComponent.codes`` = IS 800 + IS 816) or a recognised
non-code provenance string, and NONE may cite an out-of-domain design code. A
fabricated steel member is designed to the steel codes (IS 800 for the section,
IS 816 for the fillet welds) — so those are declared, while the concrete codes
(IS 456 / IRS Concrete Bridge Code) and road-congress code (IRC) remain forbidden
for a mechanical-domain steel member.
"""

import json
from pathlib import Path

import pytest

from components.structural_steel_member.analysis import analyse_member
from components.structural_steel_member.calcsheet import compose_calc_sheet
from components.structural_steel_member.checks import run_member_checks
from components.structural_steel_member.drawing import generate_ga
from components.structural_steel_member.module import StructuralSteelMemberComponent
from components.structural_steel_member.params import SteelMemberParams
from components.structural_steel_member.proofcheck import (
    _FORBIDDEN_CITATION_PATTERNS,
    run_proof_check,
    validate_narration,
)
from components.structural_steel_member.sizing import size_member

# The single source of truth for the declared set — the same list the registry
# publishes and the spec declares.
DECLARED_CODES = tuple(StructuralSteelMemberComponent.codes)
_DECLARED_LOWER = tuple(code.lower() for code in DECLARED_CODES)

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

POST = SteelMemberParams(cantilever_length_m=6.0, transverse_load_kn=20.0, member_type="gantry_post")
BRACKET = SteelMemberParams(cantilever_length_m=1.2, transverse_load_kn=40.0, member_type="bracket")


def _forbidden_hit(text: str) -> str | None:
    for pattern in _FORBIDDEN_CITATION_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None


def _within_codeset(text: str) -> bool:
    lowered = " ".join(text.lower().split())
    if any(code in lowered for code in _DECLARED_LOWER):
        return True
    return any(marker in lowered for marker in _PROVENANCE_MARKERS)


def _run(params: SteelMemberParams, out_dir: Path):
    sizing = size_member(params)
    geometry = sizing.geometry
    analysis = analyse_member(params, geometry)
    checks = run_member_checks(analysis, geometry, params)
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


def test_declared_set_is_the_steel_codes_only():
    # The reconcile: the steel section + weld codes are declared, and the
    # out-of-domain (concrete / road) codes are NOT.
    assert "IS 800" in DECLARED_CODES
    assert "IS 816" in DECLARED_CODES
    joined = " | ".join(DECLARED_CODES)
    assert "IRC" not in joined
    assert "IS 456" not in joined
    assert "Concrete Bridge Code" not in joined


@pytest.mark.parametrize("params", [POST, BRACKET], ids=["gantry_post", "bracket"])
def test_every_calc_sheet_citation_is_within_the_declared_set(params, tmp_path):
    calc_sheet, _compliance, _result = _run(params, tmp_path)
    citations = _calc_sheet_citations(calc_sheet)
    assert citations, "calc sheet produced no citations to audit"
    for citation in citations:
        assert citation is not None and citation.strip(), "empty calc-sheet citation"
        assert _forbidden_hit(citation) is None, (
            f"out-of-domain (IRC / IS 456 / Concrete Bridge Code) citation leaked into "
            f"calc sheet: {citation!r}"
        )
        assert _within_codeset(citation), (
            f"calc-sheet citation outside the declared code set / provenance: {citation!r}"
        )


@pytest.mark.parametrize("params", [POST, BRACKET], ids=["gantry_post", "bracket"])
def test_every_compliance_clause_is_within_the_declared_set(params, tmp_path):
    _calc_sheet, compliance, _result = _run(params, tmp_path)
    clauses = [item["clause"] for item in compliance["items"]]
    assert len(clauses) == 10
    for clause in clauses:
        assert clause is not None and clause.strip(), "empty compliance clause"
        assert _forbidden_hit(clause) is None, (
            f"out-of-domain (IRC / IS 456 / Concrete Bridge Code) citation leaked into "
            f"compliance: {clause!r}"
        )
        assert _within_codeset(clause), (
            f"compliance clause outside the declared code set / provenance: {clause!r}"
        )


@pytest.mark.parametrize("params", [POST, BRACKET], ids=["gantry_post", "bracket"])
def test_narration_forbids_out_of_domain_codes_but_admits_the_declared_steel_codes(params, tmp_path):
    _calc_sheet, _compliance, result = _run(params, tmp_path)

    def _forbidden_problems(narration: str) -> list[str]:
        return [p for p in validate_narration(narration, result) if "forbidden" in p]

    # IS 456 / IRS Concrete Bridge Code (concrete) and IRC (roads) are out-of-domain
    # for a fabricated steel member — REJECTED.
    assert _forbidden_problems("checked per IS 456 working stress")
    assert _forbidden_problems("as per IRC:78 provisions")
    assert _forbidden_problems("verified to the IRS Concrete Bridge Code")
    # The declared steel codes IS 800 / IS 816 must NOT be flagged as forbidden
    # out-of-set citations (numeric grounding of the digits is a separate concern).
    assert _forbidden_problems("the section follows IS 800 working stress") == []
    assert _forbidden_problems("the fillet weld follows IS 816") == []
