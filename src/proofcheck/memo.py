"""Proof Checking Consultant memo — deterministic composer + narration grounding.

Pinned public API (the graph slice calls exactly this):

    from proofcheck import memo_facts, render_memo, validate_narration

    facts = memo_facts(result, params=..., geometry=..., warnings=..., assumptions=...)
        # deterministic, structured facts block (markdown) — everything the LLM
        # may narrate FROM (the review node passes it to Gemini with
        # src/prompts/memo.md)

    problems = validate_narration(narration_md, result)
        # grounding check — [] means the narration is safe to embed

    memo_md = render_memo(result, narration, params=..., geometry=...,
                          warnings=..., assumptions=...)
        # the PCC memo (reference / scope of check / observations by severity /
        # recommendation). `narration` is embedded ONLY if it passes the
        # grounding validator; None or rejected -> fully deterministic memo.

validate_narration semantics — a narration is rejected when it:

* contains a numeric value that does not appear in the deterministic results
  (checklist computed/limit/detail/clause values, the FE agreement figure, the
  params/geometry reference values). Matching is tolerant of display
  formatting: thousands separators are ignored and a narration number matches
  when a deterministic value rounds to it at the narration's own precision
  (narrating "3.2" is grounded by a recorded 3.18; "347.2" is grounded by
  nothing and rejected).
* cites a non-IRS design code (the IRS-only citation rule);
* states the opposite of the rule-computed verdict (the LLM never grades).

The memo itself is fully deterministic (no timestamps) and self-grounded:
every numeric it prints comes from the checklist items or the shared
reference lines — asserted by test with this same validator.
"""

import re
from collections.abc import Sequence

from domain.culvert import Assumption, BoxGeometry, CulvertParams
from proofcheck.checklist import (
    SEVERITY_MAJOR,
    SEVERITY_MINOR,
    SEVERITY_OBSERVATION,
    SEVERITY_PASS,
    VERDICT_APPROVAL,
    ChecklistItem,
    ProofCheckResult,
    reference_lines,
)

PROOF_MEMO_FILENAME = "proof_memo.md"

HYDRAULICS_NOTE = (
    "Hydraulic adequacy (vent area, HFL, afflux and scour per RBF-16) is user-supplied "
    "information — echoed for the record, not verified by this POC."
)

# Non-IRS design-code citations are defects (spec: IRS codes only). Patterns are
# assembled by concatenation so this source file never greps as a violation.
_FORBIDDEN_CITATION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (
        r"\bI" + r"S\s*[:.\-]?\s*456\b",
        r"\bI" + r"S\s*[:.\-]?\s*800\b",
        r"\bI" + r"RC\b",
    )
)

# Numbers with optional thousands separators; signs are ignored (magnitudes are
# compared) so hyphens in ranges ("1-8") and identifiers ("25t-2008") stay safe.
_NUMBER_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")

_SEVERITY_ORDER = (SEVERITY_MAJOR, SEVERITY_MINOR, SEVERITY_OBSERVATION, SEVERITY_PASS)
_SEVERITY_HEADINGS = {
    SEVERITY_MAJOR: "Non-conformities — major",
    SEVERITY_MINOR: "Non-conformities — minor",
    SEVERITY_OBSERVATION: "Observations",
    SEVERITY_PASS: "Conforming items",
}


def numeric_tokens(text: str) -> list[str]:
    """Every numeric token in ``text``, thousands separators stripped."""
    return [match.group(0).replace(",", "") for match in _NUMBER_RE.finditer(text)]


def _decimals(token: str) -> int:
    _, _, fraction = token.partition(".")
    return len(fraction)


def _grounded(token: str, allowed_values: list[float]) -> bool:
    """True when some deterministic value rounds to the token at its precision."""
    value = float(token)
    tolerance = 0.5 * 10.0 ** (-_decimals(token)) + 1e-9
    return any(abs(abs(allowed) - value) <= tolerance for allowed in allowed_values)


def _allowed_values(result: ProofCheckResult, extra_facts: str | None) -> list[float]:
    chunks: list[str] = []
    for item in result.items:
        chunks.append(str(item.item))
        chunks.extend(
            (item.title, item.clause, item.requirement, item.computed, item.limit, item.detail)
        )
    chunks.append(f"{result.fe_agreement_pct}")
    chunks.append(result.grounding_text)
    if extra_facts:
        chunks.append(extra_facts)
    return [float(token) for token in numeric_tokens("\n".join(chunks))]


def validate_narration(
    narration_md: str,
    result: ProofCheckResult,
    *,
    extra_facts: str | None = None,
) -> list[str]:
    """Grounding problems in ``narration_md`` — an empty list means it may be embedded."""
    if not narration_md or not narration_md.strip():
        return ["narration is empty"]

    problems: list[str] = []

    for pattern in _FORBIDDEN_CITATION_PATTERNS:
        match = pattern.search(narration_md)
        if match:
            problems.append(
                f"forbidden non-IRS citation '{match.group(0)}' — IRS codes only"
            )

    lowered = " ".join(narration_md.lower().split())
    opposite = (
        "recommended for approval"
        if result.verdict != VERDICT_APPROVAL
        else "return for revision"
    )
    if opposite in lowered:
        problems.append(
            f"narration states '{opposite}' but the rule-computed verdict is "
            f"'{result.verdict}' — the narration never grades or decides"
        )

    allowed = _allowed_values(result, extra_facts)
    for token in numeric_tokens(narration_md):
        if not _grounded(token, allowed):
            problems.append(
                f"numeric value '{token}' does not appear in the deterministic results"
            )
    return problems


def memo_facts(
    result: ProofCheckResult,
    *,
    params: CulvertParams,
    geometry: BoxGeometry,
    warnings: Sequence[str] = (),
    assumptions: Sequence[Assumption] = (),
) -> str:
    """The deterministic facts block — the ONLY source the LLM may narrate from."""
    counts = {severity: 0 for severity in _SEVERITY_ORDER}
    for item in result.items:
        counts[item.severity] = counts.get(item.severity, 0) + 1

    lines: list[str] = [
        "# Proof-check facts (deterministic — narrate ONLY from these values)",
        "",
        "## Reference",
        *(f"- {line}" for line in reference_lines(params, geometry)),
        "",
        "## Verdict (computed by rule — the narration never grades)",
        f"- verdict: {result.verdict}",
        f"- independent FE agreement: {result.fe_agreement_pct:g} %",
        (
            f"- items: {len(result.items)} total — {counts[SEVERITY_PASS]} pass, "
            f"{counts[SEVERITY_OBSERVATION]} observation, "
            f"{counts[SEVERITY_MINOR]} minor non-conformity, "
            f"{counts[SEVERITY_MAJOR]} major non-conformity"
        ),
        "",
        "## Checklist items",
    ]
    for item in result.items:
        lines.extend(
            [
                f"### Item {item.item} — {item.title} [{item.severity}]",
                f"- clause: {item.clause}",
                f"- requirement: {item.requirement}",
                f"- computed: {item.computed}",
                f"- limit: {item.limit}",
                f"- detail: {item.detail}",
            ]
        )
    lines.extend(["", "## Warnings on record"])
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- none")
    lines.extend(["", "## Assumptions on record"])
    if assumptions:
        lines.extend(
            f"- {assumption.field} = {assumption.value} ({assumption.source}): "
            f"{assumption.note}"
            for assumption in assumptions
        )
    else:
        lines.append("- none")
    lines.extend(["", "## Scope honesty", f"- {HYDRAULICS_NOTE}"])
    return "\n".join(lines)


def _clause_lead(clause: str) -> str:
    """The citation head of a clause string (before the source-document tail)."""
    return clause.split(" — ")[0].strip()


def _item_bullet(item: ChecklistItem) -> str:
    return (
        f"- Item {item.item} — {item.title}: {item.computed} (limit: {item.limit}). "
        f"{item.detail}"
    )


def render_memo(
    result: ProofCheckResult,
    narration: str | None = None,
    *,
    params: CulvertParams,
    geometry: BoxGeometry,
    warnings: Sequence[str] = (),
    assumptions: Sequence[Assumption] = (),
) -> str:
    """The Proof Checking Consultant memo (markdown), deterministic-by-default.

    ``narration`` (LLM prose) is embedded only when it passes
    ``validate_narration`` against these same deterministic facts; a rejected
    narration is omitted with a note and the memo stands fully deterministic.
    """
    facts = memo_facts(
        result, params=params, geometry=geometry, warnings=warnings, assumptions=assumptions
    )
    narration_block: str | None = None
    omission_note: str | None = None
    if narration is not None and narration.strip():
        problems = validate_narration(narration, result, extra_facts=facts)
        if problems:
            omission_note = (
                "> Note: an LLM-drafted narration was produced but has been omitted — "
                "it failed the deterministic grounding validation. The observations "
                "below are the unabridged deterministic findings."
            )
        else:
            narration_block = narration.strip()

    by_severity: dict[str, list[ChecklistItem]] = {s: [] for s in _SEVERITY_ORDER}
    for item in result.items:
        by_severity[item.severity].append(item)

    lines: list[str] = [
        "# Proof Checking Consultant — Memorandum",
        "",
        "## Reference",
        "",
        *reference_lines(params, geometry),
        "",
        "## Scope of check",
        "",
        (
            f"Deterministic {len(result.items)}-item proof-check of the submitted "
            "design, covering:"
        ),
        *(f"{item.item}. {item.title}" for item in result.items),
        "",
        HYDRAULICS_NOTE,
        "",
        "## Observations",
        "",
    ]
    if narration_block:
        lines.extend(
            [
                "### Reviewer's narrative (LLM-narrated from the deterministic facts)",
                "",
                narration_block,
                "",
            ]
        )
    if omission_note:
        lines.extend([omission_note, ""])
    if warnings:
        lines.extend(["### Warnings on record", ""])
        lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")
    for severity in _SEVERITY_ORDER:
        items = by_severity[severity]
        lines.extend([f"### {_SEVERITY_HEADINGS[severity]}", ""])
        if items:
            lines.extend(_item_bullet(item) for item in items)
        else:
            lines.append("- None.")
        lines.append("")

    lines.extend(["## Recommendation", ""])
    majors = by_severity[SEVERITY_MAJOR]
    if result.verdict == VERDICT_APPROVAL:
        item_11 = result.items[10]
        lines.append(
            f"RECOMMENDED FOR APPROVAL — all {len(result.items)} checklist items "
            "conform or carry observations only; the independent FE re-solve deviates "
            f"from the closed-form analysis by {result.fe_agreement_pct:g} % at most "
            f"({item_11.limit})."
        )
    else:
        lines.append(
            "RETURN FOR REVISION — the design must not be taken forward until the "
            "following major non-conformities are resolved:"
        )
        lines.append("")
        lines.extend(
            f"- Item {item.item} — {item.title} ({_clause_lead(item.clause)}): "
            f"{item.detail}"
            for item in majors
        )
    lines.append("")
    return "\n".join(lines)
