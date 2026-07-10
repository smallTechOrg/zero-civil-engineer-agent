"""GA drawing package — parametric ezdxf template + same-document SVG render.

Public API (pinned — other slices import exactly this):

    from drawing.ga import generate_ga
"""

from drawing.ga import generate_ga
from drawing.validation import InvalidGeometryError

__all__ = ["InvalidGeometryError", "generate_ga"]
