"""The component interface (normative) + shared result types.

This is the concrete contract every component module implements. The
retaining-wall slices build against exactly these signatures — they must not be
changed. Shared result types wrap the existing culvert domain shapes
(`Assumption`, `CalcStep`, `CheckResult`) so no existing type is broken.

Method-argument coercion: engineering methods accept either the typed
`param_model` / `geometry_model` instance OR its plain-dict form (state carries
dicts). Use `coerce(Model, value)` at the top of each method to normalise —
the culvert adapter does exactly this and the retaining-wall module should too.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel

# Re-export the shared engineering shapes so component authors import them from
# one place. `CheckResult` lives in engine.checks; `Assumption`/`CalcStep` in
# domain.culvert. Both are light modules (no heavy CAD/FE imports at load).
from domain.culvert import Assumption, CalcStep  # noqa: F401
from engine.checks import CheckResult  # noqa: F401

__all__ = [
    "Assumption",
    "CalcStep",
    "CheckResult",
    "SizingOutput",
    "AnalysisOutput",
    "CheckOutput",
    "ProofCheckOutput",
    "ComponentModule",
    "coerce",
]


def coerce(model: type[BaseModel], value):
    """Return `value` as a `model` instance, accepting an instance or a dict."""
    if value is None:
        return None
    if isinstance(value, model):
        return value
    if isinstance(value, BaseModel):
        return model(**value.model_dump())
    return model(**value)


# --------------------------------------------------------------------------- results


@dataclass
class SizingOutput:
    """`ComponentModule.size` result — geometry + full provenance.

    Mirrors the culvert `engine.SizingResult` shape.
    """

    geometry: BaseModel
    assumptions: list[Assumption] = field(default_factory=list)
    trail: list[CalcStep] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class AnalysisOutput:
    """`ComponentModule.analyse` result — the analysis model + its trail."""

    analysis: BaseModel
    assumptions: list[Assumption] = field(default_factory=list)
    trail: list[CalcStep] = field(default_factory=list)


@dataclass
class CheckOutput:
    """`ComponentModule.run_checks` result — code-checks + assumptions + trail."""

    checks: list[CheckResult] = field(default_factory=list)
    assumptions: list[Assumption] = field(default_factory=list)
    trail: list[CalcStep] = field(default_factory=list)


@dataclass
class ProofCheckOutput:
    """`ComponentModule.proof_check` result — the IR-protocol review spine output.

    `proof_check` has ALREADY written its diagram/compliance artefacts to
    `out_dir`; `artefacts` lists them as `(kind, filename)` so the review node
    emits them component-agnostically. Memo narration is component-specific, so
    the module pre-binds `validate_narration` (grounds an LLM narration against
    the deterministic facts → list of problems, empty = accept) and
    `render_memo` (composes the final markdown, embedding an accepted narration
    or standing fully deterministic). The review node feeds `memo_facts` to the
    LLM with `module.memo_prompt()`, validates, then renders — never touching a
    component-specific formatter directly.
    """

    fe_comparison: BaseModel | None
    checklist: list[dict]
    verdict: str
    fe_agreement_pct: float
    memo_facts: str
    validate_narration: Callable[[str | None], list[str]]
    render_memo: Callable[[str | None], str]
    artefacts: list[tuple[str, str]] = field(default_factory=list)
    memo_kind: str = "proof_memo"
    memo_filename: str = "proof_memo.md"


# --------------------------------------------------------------------------- protocol


@runtime_checkable
class ComponentModule(Protocol):
    """A first-class structure/component type the shared pipeline dispatches to."""

    # ---- declarative metadata (drives the gallery, auto-detect, citations) ----
    type_id: str
    display_name: str
    domain: Literal["civil", "mechanical"]
    summary: str
    status: Literal["available", "coming_soon"]
    codes: list[str]
    scope_examples: list[str]
    critical_fields: list[str]
    param_model: type[BaseModel]
    geometry_model: type[BaseModel]

    # ---- intake ----
    def extraction_schema(self) -> type[BaseModel]: ...
    def clarify_question(self, missing_field: str) -> str: ...
    def unusual_value_warnings(self, params) -> list[str]: ...

    # ---- deterministic engineering pipeline ----
    def size(self, params) -> SizingOutput: ...
    def analyse(self, params, geometry) -> AnalysisOutput: ...
    def run_checks(self, params, geometry, analysis) -> CheckOutput: ...
    def compose_calc_sheet(
        self,
        *,
        params,
        geometry,
        analysis,
        checks,
        assumptions,
        warnings,
        trail_segments,
        out_dir: Path,
    ) -> Path: ...
    def draw(self, params, geometry, out_dir: Path, run_id: str) -> dict[str, Path]: ...
    def model3d(self, geometry, out_dir: Path) -> dict[str, Path]: ...

    # ---- IR-protocol review spine (SAME workflow for every component) ----
    def proof_check(
        self, *, params, geometry, analysis, checks, ga_dxf_path: Path, out_dir: Path
    ) -> ProofCheckOutput: ...
    def memo_prompt(self) -> str: ...

    # ---- type-specific outputs ----
    def type_summary(self, *, params, geometry, analysis, checks, proof) -> dict: ...
