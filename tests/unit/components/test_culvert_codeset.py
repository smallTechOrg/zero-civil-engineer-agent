"""Code-set fidelity guard (citation domain honesty) — box culvert.

Every citation the deterministic box-culvert pipeline emits — every
``calc_sheet.json`` line/trail ``citation`` and every ``compliance.json`` item
``clause`` — must be WITHIN the module's declared code set
(``BoxCulvertComponent.codes``) or a recognised non-code provenance string (IR
engineering practice, RDSO standard-drawing tags, the analysis method, the
proof-check meta items), and NONE may cite an out-of-domain design code. A box
culvert is IRS-only civil concrete: its basis is the IRS Concrete Bridge Code +
IRS Bridge Rules (25t Loading-2008) + the IRS Bridge Substructure & Foundation Code
(earth pressure / LL surcharge). Concrete IS 456, steel IS 800, road IRC and
MECHANICAL codes (IS 816, RDSO Specifications, Machine Design) are forbidden.

Drives the REAL deterministic pipeline through the ``BoxCulvertComponent``
interface (no LLM), exactly as the shared graph does.
"""

import json
import re
from pathlib import Path

import pytest

from components import registry
from components.culvert.module import BoxCulvertComponent
from domain.culvert import CulvertParams
from proofcheck.memo import _FORBIDDEN_CITATION_PATTERNS

# The single source of truth for the declared set — the same list the registry
# publishes and the spec declares. The culvert declares "IRS Bridge Rules" (with
# the S) directly, so no document-spelling alias is needed here.
DECLARED_CODES = tuple(BoxCulvertComponent.codes)
_DECLARED_LOWER = tuple(code.lower() for code in DECLARED_CODES)

# Recognised NON-code provenance markers legitimately used as a citation/clause.
# None of these names a design code: they are user input, geometric provenance,
# IR engineering-practice references (IRICEN course/practice, IR Permanent Way,
# the Indian Railways Bridge Manual, IRS working-stress service combinations), the
# RDSO B-10152/R standard-drawing family tags, and the proof-check meta items.
_PROVENANCE_MARKERS = (
    "user design requirement",
    "preset default",
    "see the assumptions block",
    "sized geometry",
    "calc-vs-drawing",
    "design envelope",
    "ir permanent way practice",
    "iricen",
    "irs working-stress",
    "indian railways bridge manual",
    "rdso b-10152",
    "independent proof-check practice",
)

# The culvert's own proofcheck already forbids IS 456 / IS 800 / IRC (non-IRS civil
# codes). A box culvert is also not a machine element: MECHANICAL codes are
# out-of-domain. Patterns are assembled by concatenation so this file never greps
# as a violation. ("RDSO Spec" targets the rolling-stock *Specifications*, NOT the
# legitimate civil "RDSO B-10152/R" standard-drawing tags above.)
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

CANONICAL = CulvertParams(clear_span_m=4.0, clear_height_m=3.0, cushion_m=2.5)
THIN_CUSHION = CulvertParams(clear_span_m=3.0, clear_height_m=3.0, cushion_m=0.5)


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


def _run(params: CulvertParams, out_dir: Path):
    comp = registry.get("box_culvert")
    sizing = comp.size(params)
    analysis = comp.analyse(params, sizing.geometry)
    checks = comp.run_checks(params, sizing.geometry, analysis.analysis)
    calc_sheet_path = comp.compose_calc_sheet(
        params=params,
        geometry=sizing.geometry,
        analysis=analysis.analysis,
        checks=[c.model_dump() for c in checks.checks],
        assumptions=[a.model_dump() for a in sizing.assumptions],
        warnings=[],
        trail_segments=[
            [s.model_dump() for s in sizing.trail],
            [s.model_dump() for s in analysis.trail],
            [s.model_dump() for s in checks.trail],
        ],
        out_dir=out_dir,
    )
    comp.draw(params, sizing.geometry, out_dir, run_id="cs")  # proof reads ga.dxf
    proof = comp.proof_check(
        params=params,
        geometry=sizing.geometry,
        analysis=analysis.analysis,
        checks=[c.model_dump() for c in checks.checks],
        ga_dxf_path=out_dir / "ga.dxf",
        out_dir=out_dir,
    )
    calc_sheet = json.loads(calc_sheet_path.read_text())
    compliance = json.loads((out_dir / "compliance.json").read_text())
    return calc_sheet, compliance, proof


def _calc_sheet_citations(calc_sheet: dict) -> list[str]:
    citations: list[str] = []
    for section in calc_sheet["sections"]:
        for line in section["lines"]:
            citations.append(line["citation"])
    citations.extend(step["citation"] for step in calc_sheet["trail"])
    return citations


def test_declared_set_is_irs_only_including_the_substructure_code():
    # The reconcile (Finding B): the earth-pressure / LL-surcharge basis the culvert
    # loads trail actually cites is now declared, alongside the other IRS codes.
    assert "IRS Bridge Substructure & Foundation Code" in DECLARED_CODES
    assert "IRS Concrete Bridge Code" in DECLARED_CODES
    joined = " | ".join(DECLARED_CODES)
    assert "IS 456" not in joined
    assert "IS 800" not in joined
    assert "IRC" not in joined
    assert "IS 816" not in joined


@pytest.mark.parametrize("params", [CANONICAL, THIN_CUSHION], ids=["canonical", "thin_cushion"])
def test_every_calc_sheet_citation_is_within_the_declared_set(params, tmp_path):
    calc_sheet, _compliance, _proof = _run(params, tmp_path)
    citations = _calc_sheet_citations(calc_sheet)
    assert citations, "calc sheet produced no citations to audit"
    for citation in citations:
        assert citation is not None and citation.strip(), "empty calc-sheet citation"
        assert _forbidden_hit(citation) is None, (
            f"out-of-domain (IS 456 / IS 800 / IRC / mechanical) citation leaked into calc sheet: {citation!r}"
        )
        assert _within_codeset(citation), (
            f"calc-sheet citation outside the declared code set / provenance: {citation!r}"
        )


@pytest.mark.parametrize("params", [CANONICAL, THIN_CUSHION], ids=["canonical", "thin_cushion"])
def test_every_compliance_clause_is_within_the_declared_set(params, tmp_path):
    _calc_sheet, compliance, _proof = _run(params, tmp_path)
    clauses = [item["clause"] for item in compliance["items"]]
    assert len(clauses) == 12
    for clause in clauses:
        assert clause is not None and clause.strip(), "empty compliance clause"
        assert _forbidden_hit(clause) is None, (
            f"out-of-domain (IS 456 / IS 800 / IRC / mechanical) citation leaked into compliance: {clause!r}"
        )
        assert _within_codeset(clause), (
            f"compliance clause outside the declared code set / provenance: {clause!r}"
        )


@pytest.mark.parametrize("params", [CANONICAL, THIN_CUSHION], ids=["canonical", "thin_cushion"])
def test_narration_forbids_out_of_domain_codes_but_admits_irs(params, tmp_path):
    _calc_sheet, _compliance, proof = _run(params, tmp_path)

    def _forbidden_problems(narration: str) -> list[str]:
        return [p for p in proof.validate_narration(narration) if "forbidden" in p]

    # Concrete IS 456, steel IS 800 and road IRC are out-of-domain for the IRS-only
    # culvert citation set — REJECTED.
    assert _forbidden_problems("the RCC section per IS 456 working stress")
    assert _forbidden_problems("the steel member per IS 800 provisions")
    assert _forbidden_problems("checked per IRC:78 provisions")
    # The declared IRS Concrete Bridge Code basis is NOT flagged as forbidden.
    assert _forbidden_problems("per the IRS Concrete Bridge Code permissible stresses") == []
