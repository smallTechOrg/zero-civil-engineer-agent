"""Refinement suggestions (Phase 3) — schema, deterministic validation, run summary.

The LLM proposes; deterministic Python disposes. Whatever Gemini returns is
trimmed and validated here (non-empty, list prefixes stripped, ≤160 chars,
deduped, max 3) before anything is persisted. The finalize node swallows every
failure on this path — a run is complete with or without chips
(spec/capabilities/session-refinement.md: invisible-degrading).
"""

import re

from pydantic import BaseModel, Field

MAX_SUGGESTIONS = 3
SUGGESTION_MAX_CHARS = 160

# "1. ", "2) ", "(3) ", "4] ", "5: ", "- ", "* ", "• " — but never a leading
# VALUE like "450 mm" (digits must be followed by list punctuation to strip).
_LIST_PREFIX = re.compile(r"^\s*(?:[-*•]+|\(\d+\)|\d+\s*[.)\]:])\s*")

# Geometry lines surfaced to the suggestions prompt — the final as-designed
# members plus the overall envelope (a compact grounding set, not the full dump).
_GEOMETRY_FIELDS = (
    "top_slab_thickness_mm",
    "bottom_slab_thickness_mm",
    "wall_thickness_mm",
    "haunch_mm",
    "external_width_m",
    "external_height_m",
    "barrel_length_m",
)


class SuggestionsResult(BaseModel):
    """Structured output of the finalize suggestions call (suggest.md)."""

    suggestions: list[str] = Field(
        default_factory=list,
        description="Exactly 3 short refinement suggestions, each phrased so the "
        "user could type it verbatim as their next request.",
    )


def sanitize_suggestions(raw: list[str]) -> list[str]:
    """Deterministic post-validation of the LLM's suggestions.

    Trims whitespace, strips numbered/bulleted list prefixes, drops empty or
    over-long (> 160 chars) items, de-duplicates case-insensitively, and keeps
    at most 3 in their original order.
    """
    kept: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        text = _LIST_PREFIX.sub("", item.strip()).strip()
        if not text or len(text) > SUGGESTION_MAX_CHARS:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        kept.append(text)
        if len(kept) == MAX_SUGGESTIONS:
            break
    return kept


def run_summary(state: dict) -> str:
    """The compact RUN SUMMARY block fed to suggest.md.

    Everything a suggestion may reference is HERE: adopted parameters, final
    member geometry, the rule-computed verdict, warnings, and any non-PASS
    checklist titles. The prompt forbids referencing anything else.
    """
    lines = ["RUN SUMMARY"]
    params = state.get("params") or {}
    if params:
        lines.append("Adopted parameters:")
        lines.extend(
            f"- {field}: {value}" for field, value in params.items() if value is not None
        )
    geometry = state.get("geometry") or {}
    if geometry:
        lines.append("Final geometry (engine-sized or user-overridden):")
        lines.extend(
            f"- {field}: {geometry[field]}"
            for field in _GEOMETRY_FIELDS
            if field in geometry
        )
    lines.append(f"Verdict: {state.get('verdict') or 'not computed'}")
    warnings = state.get("warnings") or []
    if warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in warnings)
    non_pass = [
        item
        for item in (state.get("checklist") or [])
        if item.get("severity") != "PASS"
    ]
    if non_pass:
        lines.append("Non-PASS proof-check items:")
        lines.extend(
            f"- [{item.get('severity')}] {item.get('title')}" for item in non_pass
        )
    return "\n".join(lines)
