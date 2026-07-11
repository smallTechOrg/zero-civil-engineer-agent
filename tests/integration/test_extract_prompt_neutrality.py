"""Regression: the SHARED extract prompt must be component-neutral.

Real Gemini + the neutralized `src/prompts/extract.md`. Guards the bug where the
culvert-only few-shot (`"Fe500 steel" -> steel_grade = "Fe500"`) leaked a grade
that plate_girder's validator (E250/E350 per IS 2062) rejects, failing the run
with a Fe500 ValidationError. Also confirms the box culvert still extracts, so
the neutralization does not regress the original component.
"""

import components  # noqa: F401 — registers every component module at import
from components import registry
from graph.nodes import _load_prompt
from llm.client import LLMClient


def _extract(component_type: str, prompt: str) -> dict:
    """Run the real extract path (extract.md + the component's schema) on `prompt`."""
    module = registry.get(component_type)
    result = LLMClient().generate(
        prompt,
        system=_load_prompt("extract.md"),
        schema=module.extraction_schema(),
        temperature=0.0,
    )
    return {k: v for k, v in result.parsed.model_dump().items() if v is not None}


def test_plate_girder_input_never_extracts_culvert_grade_fe500(require_gemini):
    from components.plate_girder.params import PlateGirderParams

    extracted = _extract("plate_girder", "Welded Steel Plate Girder")

    # The core assertion: the shared prompt must NOT inject the culvert grade.
    steel_grade = extracted.get("steel_grade")
    assert steel_grade in (None, "E250", "E350"), (
        f"extract leaked a non-plate-girder steel grade: {steel_grade!r} "
        "(expected None or one of E250/E350)"
    )

    # And the merged params must construct — no Fe500 ValidationError.
    merged = {"span_m": 24.0, "steel_grade": "E250", **extracted}  # both critical fields
    params = PlateGirderParams(**merged)
    assert params.steel_grade in ("E250", "E350")


def test_box_culvert_extraction_still_works_after_neutralization(require_gemini):
    """Regression the other way: the neutral prompt still extracts culvert params."""
    from domain.culvert import CulvertParams  # the culvert param model

    extracted = _extract(
        "box_culvert",
        "single box culvert, 4 m clear span, 3 m height, 2.5 m cushion, "
        "BG single line, 25t loading, Fe500 steel, M30 concrete",
    )

    assert extracted.get("clear_span_m") == 4.0
    assert extracted.get("clear_height_m") == 3.0
    assert extracted.get("cushion_m") == 2.5
    # Fe500 IS a valid culvert grade — so here it SHOULD come through and validate.
    assert extracted.get("steel_grade") == "Fe500"
    CulvertParams(**extracted)  # constructs without error
