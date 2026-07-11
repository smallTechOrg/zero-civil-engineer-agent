"""Code-set fidelity guard (citation domain honesty).

Every citation the deterministic welded steel plate-girder pipeline emits — every
``calc_sheet.json`` line/trail ``citation`` and every ``compliance.json`` item
``clause`` — must be WITHIN the module's declared code set
(``PlateGirderComponent.codes``) or a recognised non-code provenance string, and
NONE may cite an out-of-domain design code. A plate girder is a STEEL
railway-bridge superstructure: its basis is IRS Steel Bridge Code + IS 800
(permissible stresses, section proportioning, web slenderness) with IR Bridge Rules
for the 25t live load — concrete (IS 456), road-congress (IRC) and MACHINE-DESIGN
codes (RDSO Specifications, Shigley / PSG / Machine Design) are forbidden.
"""

import json
import re
from pathlib import Path

import pytest

from components.plate_girder.analysis import analyse_girder
from components.plate_girder.calcsheet import compose_calc_sheet
from components.plate_girder.checks import run_girder_checks
from components.plate_girder.drawing import generate_ga
from components.plate_girder.module import PlateGirderComponent
from components.plate_girder.params import PlateGirderParams
from components.plate_girder.proofcheck import (
    _FORBIDDEN_CITATION_PATTERNS,
    run_proof_check,
    validate_narration,
)
from components.plate_girder.sizing import size_girder

# The single source of truth for the declared set — the same list the registry
# publishes and the spec declares.
DECLARED_CODES = tuple(PlateGirderComponent.codes)
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

# A plate girder's own proofcheck already forbids concrete (IS 456) and road (IRC).
# A steel BRIDGE girder is also not a machine element: machine-design / rolling-stock
# codes are out-of-domain. Patterns are assembled by concatenation so this file never
# greps as a violation. (IS 816 is a legitimate steel-welding code and is NOT
# forbidden here; "RDSO Spec" targets the rolling-stock *Specifications*.)
_FOREIGN_MECHANICAL_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"\bR" + r"DSO\s+Spec",
        r"\bM" + r"achine\s+Design",
        r"\bS" + r"higley",
        r"\bP" + r"SG\b",
    )
)
_ALL_FORBIDDEN = tuple(_FORBIDDEN_CITATION_PATTERNS) + _FOREIGN_MECHANICAL_PATTERNS

LONG_SPAN = PlateGirderParams(span_m=24.0)
SHORT_SPAN = PlateGirderParams(span_m=18.0)


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


def _run(params: PlateGirderParams, out_dir: Path):
    sizing = size_girder(params)
    geometry = sizing.geometry
    analysis = analyse_girder(params, geometry)
    checks = run_girder_checks(analysis, geometry, params)
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


def test_declared_set_is_steel_bridge_not_concrete_or_road():
    assert "IRS Steel Bridge Code" in DECLARED_CODES
    assert "IS 800" in DECLARED_CODES
    joined = " | ".join(DECLARED_CODES)
    assert "IS 456" not in joined
    assert "IRC" not in joined


@pytest.mark.parametrize("params", [LONG_SPAN, SHORT_SPAN], ids=["span24", "span18"])
def test_every_calc_sheet_citation_is_within_the_declared_set(params, tmp_path):
    calc_sheet, _compliance, _result = _run(params, tmp_path)
    citations = _calc_sheet_citations(calc_sheet)
    assert citations, "calc sheet produced no citations to audit"
    for citation in citations:
        assert citation is not None and citation.strip(), "empty calc-sheet citation"
        assert _forbidden_hit(citation) is None, (
            f"out-of-domain (IS 456 / IRC / machine-design) citation leaked into calc sheet: {citation!r}"
        )
        assert _within_codeset(citation), (
            f"calc-sheet citation outside the declared code set / provenance: {citation!r}"
        )


@pytest.mark.parametrize("params", [LONG_SPAN, SHORT_SPAN], ids=["span24", "span18"])
def test_every_compliance_clause_is_within_the_declared_set(params, tmp_path):
    _calc_sheet, compliance, _result = _run(params, tmp_path)
    clauses = [item["clause"] for item in compliance["items"]]
    assert len(clauses) == 9
    for clause in clauses:
        assert clause is not None and clause.strip(), "empty compliance clause"
        assert _forbidden_hit(clause) is None, (
            f"out-of-domain (IS 456 / IRC / machine-design) citation leaked into compliance: {clause!r}"
        )
        assert _within_codeset(clause), (
            f"compliance clause outside the declared code set / provenance: {clause!r}"
        )


@pytest.mark.parametrize("params", [LONG_SPAN, SHORT_SPAN], ids=["span24", "span18"])
def test_narration_forbids_out_of_domain_codes_but_admits_is_800(params, tmp_path):
    _calc_sheet, _compliance, result = _run(params, tmp_path)

    def _forbidden_problems(narration: str) -> list[str]:
        return [p for p in validate_narration(narration, result) if "forbidden" in p]

    # Concrete (IS 456) and road (IRC) are out-of-domain for a steel girder.
    assert _forbidden_problems("the RCC deck follows IS 456 working stress")
    assert _forbidden_problems("checked per IRC:24 provisions")
    # IS 800 is IN the declared set — it must NOT be flagged as a forbidden
    # out-of-set citation (numeric grounding of the digits is a separate concern).
    assert _forbidden_problems("the welded I-section per IS 800:2007") == []
