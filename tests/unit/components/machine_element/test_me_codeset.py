"""Code-set fidelity guard (citation domain honesty).

Every citation the deterministic machine-element pipeline emits — every
``calc_sheet.json`` line/trail ``citation`` and every ``compliance.json`` item
``clause`` — must be WITHIN the module's declared code set
(``MachineElementComponent.codes``) or a recognised non-code provenance string,
and NONE may cite an out-of-domain design code. A machine element is MECHANICAL:
its basis is standard machine-design practice (Shigley / PSG / Design Data Book)
plus IS 816 for the fillet weld — bridge/road/concrete codes (IRC, IS 456, IRS
Concrete Bridge Code) are forbidden.
"""

import json
from pathlib import Path

import pytest

from components.machine_element.analysis import analyse_element
from components.machine_element.calcsheet import compose_calc_sheet
from components.machine_element.checks import run_element_checks
from components.machine_element.drawing import generate_ga
from components.machine_element.module import MachineElementComponent
from components.machine_element.params import MachineElementParams
from components.machine_element.proofcheck import (
    _FORBIDDEN_CITATION_PATTERNS,
    run_proof_check,
    validate_narration,
)
from components.machine_element.sizing import size_element

# The single source of truth for the declared set — the same list the registry
# publishes and the spec declares.
DECLARED_CODES = tuple(MachineElementComponent.codes)
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

SHAFT = MachineElementParams(power_kw=20.0, speed_rpm=1000.0)
WELD = MachineElementParams(
    power_kw=100.0, speed_rpm=100.0, element_kind="welded_joint", hub_diameter_mm=120.0
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


def _run(params: MachineElementParams, out_dir: Path):
    sizing = size_element(params)
    geometry = sizing.geometry
    analysis = analyse_element(params, geometry)
    checks = run_element_checks(analysis, geometry, params)
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


def test_declared_set_is_mechanical_not_civil():
    assert "IS 816" in DECLARED_CODES
    assert any("machine design code" in code.lower() for code in DECLARED_CODES)
    joined = " | ".join(DECLARED_CODES)
    assert "IRC" not in joined
    assert "IS 456" not in joined
    assert "IRS Concrete Bridge Code" not in joined


@pytest.mark.parametrize("params", [SHAFT, WELD], ids=["shaft", "welded_joint"])
def test_every_calc_sheet_citation_is_within_the_declared_set(params, tmp_path):
    calc_sheet, _compliance, _result = _run(params, tmp_path)
    citations = _calc_sheet_citations(calc_sheet)
    assert citations, "calc sheet produced no citations to audit"
    for citation in citations:
        assert citation is not None and citation.strip(), "empty calc-sheet citation"
        assert _forbidden_hit(citation) is None, (
            f"out-of-domain (IRC / IS 456 / IRS CBC) citation leaked into calc sheet: {citation!r}"
        )
        assert _within_codeset(citation), (
            f"calc-sheet citation outside the declared code set / provenance: {citation!r}"
        )


@pytest.mark.parametrize("params", [SHAFT, WELD], ids=["shaft", "welded_joint"])
def test_every_compliance_clause_is_within_the_declared_set(params, tmp_path):
    _calc_sheet, compliance, _result = _run(params, tmp_path)
    clauses = [item["clause"] for item in compliance["items"]]
    assert len(clauses) == 7
    for clause in clauses:
        assert clause is not None and clause.strip(), "empty compliance clause"
        assert _forbidden_hit(clause) is None, (
            f"out-of-domain (IRC / IS 456 / IRS CBC) citation leaked into compliance: {clause!r}"
        )
        assert _within_codeset(clause), (
            f"compliance clause outside the declared code set / provenance: {clause!r}"
        )


@pytest.mark.parametrize("params", [SHAFT, WELD], ids=["shaft", "welded_joint"])
def test_narration_forbids_out_of_domain_codes(params, tmp_path):
    _calc_sheet, _compliance, result = _run(params, tmp_path)

    def _forbidden_problems(narration: str) -> list[str]:
        return [p for p in validate_narration(narration, result) if "forbidden" in p]

    # Bridge/road/concrete codes are out-of-domain for a machine element — REJECTED.
    assert _forbidden_problems("checked per IRC:78 provisions")
    assert _forbidden_problems("the RCC section follows IS 456 working stress")
    assert _forbidden_problems("verified to the IRS Concrete Bridge Code")
    # The declared machine-design basis is NOT flagged as forbidden.
    assert _forbidden_problems("designed per the Machine Design Code / IS 816") == []
