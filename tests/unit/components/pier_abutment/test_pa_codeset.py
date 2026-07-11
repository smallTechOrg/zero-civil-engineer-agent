"""Code-set fidelity guard (defect B1).

Every citation the deterministic pier/abutment pipeline emits — every
``calc_sheet.json`` line/trail ``citation`` and every ``compliance.json`` item
``clause`` — must be WITHIN the module's declared code set
(``PierAbutmentComponent.codes``) or a recognised non-code provenance string, and
NONE may cite an out-of-domain design code (IRC / IS 800). This locks the honest
reconcile in ``spec/capabilities/pier-abutment.md``: a pier's RCC section is
designed to the concrete codes (IRS Concrete Bridge Code / IS 456), exactly like
the retaining wall — so those codes are declared, while IRC (roads) and IS 800
(steel) remain forbidden for a substructure.
"""

import json
from pathlib import Path

import pytest

from components.pier_abutment.analysis import analyse_substructure
from components.pier_abutment.calcsheet import compose_calc_sheet
from components.pier_abutment.checks import run_substructure_checks
from components.pier_abutment.drawing import generate_ga
from components.pier_abutment.module import PierAbutmentComponent
from components.pier_abutment.params import PierAbutmentParams
from components.pier_abutment.proofcheck import (
    _FORBIDDEN_CITATION_PATTERNS,
    run_proof_check,
    validate_narration,
)
from components.pier_abutment.sizing import size_substructure

# The single source of truth for the declared set — the same list the registry
# publishes and the spec declares.
DECLARED_CODES = tuple(PierAbutmentComponent.codes)
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

PIER = PierAbutmentParams(
    pier_height_m=10.0, superstructure_reaction_kn=3000.0,
    safe_bearing_capacity_kn_m2=300.0, span_m=20.0, component_kind="pier",
)
ABUTMENT = PierAbutmentParams(
    pier_height_m=8.0, superstructure_reaction_kn=2500.0,
    safe_bearing_capacity_kn_m2=250.0, component_kind="abutment",
    backfill_friction_angle_deg=32.0,
)


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


def _run(params: PierAbutmentParams, out_dir: Path):
    sizing = size_substructure(params)
    geometry = sizing.geometry
    analysis = analyse_substructure(params, geometry)
    checks = run_substructure_checks(analysis, geometry, params)
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


@pytest.mark.parametrize("params", [PIER, ABUTMENT], ids=["pier", "abutment"])
def test_declared_set_covers_the_module_concrete_codes(params: PierAbutmentParams):
    # The reconcile: the RCC section-design concrete codes are now declared, and
    # the out-of-domain codes are NOT.
    assert "IRS Concrete Bridge Code" in DECLARED_CODES
    assert "IS 456" in DECLARED_CODES
    assert "IRC" not in " | ".join(DECLARED_CODES)
    assert "IS 800" not in " | ".join(DECLARED_CODES)


@pytest.mark.parametrize("params", [PIER, ABUTMENT], ids=["pier", "abutment"])
def test_every_calc_sheet_citation_is_within_the_declared_set(params, tmp_path):
    calc_sheet, _compliance, _result = _run(params, tmp_path)
    citations = _calc_sheet_citations(calc_sheet)
    assert citations, "calc sheet produced no citations to audit"
    for citation in citations:
        assert citation is not None and citation.strip(), "empty calc-sheet citation"
        assert _forbidden_hit(citation) is None, (
            f"out-of-domain (IRC / IS 800) citation leaked into calc sheet: {citation!r}"
        )
        assert _within_codeset(citation), (
            f"calc-sheet citation outside the declared code set / provenance: {citation!r}"
        )


@pytest.mark.parametrize("params", [PIER, ABUTMENT], ids=["pier", "abutment"])
def test_every_compliance_clause_is_within_the_declared_set(params, tmp_path):
    _calc_sheet, compliance, _result = _run(params, tmp_path)
    clauses = [item["clause"] for item in compliance["items"]]
    assert len(clauses) == 10
    for clause in clauses:
        assert clause is not None and clause.strip(), "empty compliance clause"
        assert _forbidden_hit(clause) is None, (
            f"out-of-domain (IRC / IS 800) citation leaked into compliance: {clause!r}"
        )
        assert _within_codeset(clause), (
            f"compliance clause outside the declared code set / provenance: {clause!r}"
        )


@pytest.mark.parametrize("params", [PIER, ABUTMENT], ids=["pier", "abutment"])
def test_narration_forbids_out_of_domain_codes_but_admits_is_456(params, tmp_path):
    _calc_sheet, _compliance, result = _run(params, tmp_path)

    def _forbidden_problems(narration: str) -> list[str]:
        return [p for p in validate_narration(narration, result) if "forbidden" in p]

    # IRC (roads) and IS 800 (steel) are out-of-domain for a substructure — REJECTED.
    assert _forbidden_problems("checked per IRC:78 provisions")
    assert _forbidden_problems("section verified to IS 800 clauses")
    # IS 456 is now IN the declared set — it must NOT be flagged as a forbidden
    # out-of-set citation (numeric grounding of the digits is a separate concern).
    assert _forbidden_problems("the RCC section follows IS 456 working stress") == []
