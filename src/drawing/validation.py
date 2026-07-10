"""Geometry validation for the GA template — fail loudly, never draw nonsense.

The template validates its BoxGeometry input before a single entity is drawn
(spec/capabilities/ga-drawing.md business rule). All checks work in millimetres
and report the offending numbers in the error message.
"""

from domain.culvert import BoxGeometry

CONSISTENCY_TOLERANCE_MM = 1.0


class InvalidGeometryError(ValueError):
    """Raised when BoxGeometry is impossible or internally inconsistent."""


def validate_geometry(geometry: BoxGeometry) -> None:
    span = geometry.clear_span_m * 1000.0
    height = geometry.clear_height_m * 1000.0
    cushion = geometry.cushion_m * 1000.0
    t_top = geometry.top_slab_thickness_mm
    t_bot = geometry.bottom_slab_thickness_mm
    t_wall = geometry.wall_thickness_mm
    haunch = geometry.haunch_mm
    w_ext = geometry.external_width_m * 1000.0
    h_ext = geometry.external_height_m * 1000.0
    l_barrel = geometry.barrel_length_m * 1000.0

    _require_positive("clear span", span)
    _require_positive("clear height", height)
    _require_positive("top slab thickness", t_top)
    _require_positive("bottom slab thickness", t_bot)
    _require_positive("wall thickness", t_wall)
    _require_positive("external width", w_ext)
    _require_positive("external height", h_ext)
    _require_positive("barrel length", l_barrel)
    if cushion < 0:
        raise InvalidGeometryError(
            f"cushion must not be negative, got {geometry.cushion_m:g} m"
        )
    if haunch < 0:
        raise InvalidGeometryError(
            f"haunch must not be negative, got {haunch:g} mm"
        )

    # Strictly greater: the RDSO family's own 1 m x 6 m extreme sizes the wall
    # at exactly half the clear span (500 mm on a 1000 mm opening) and is valid.
    if t_wall > span / 2.0:
        raise InvalidGeometryError(
            f"wall thickness {t_wall:g} mm exceeds half the clear span "
            f"({span:g} mm) - implausible section, refusing to draw"
        )
    if 2.0 * haunch >= span or 2.0 * haunch >= height:
        raise InvalidGeometryError(
            f"haunch legs of {haunch:g} mm at opposite corners ({2 * haunch:g} mm) "
            f"close the {span:g} x {height:g} mm clear opening"
        )

    expected_width = span + 2.0 * t_wall
    if abs(w_ext - expected_width) > CONSISTENCY_TOLERANCE_MM:
        raise InvalidGeometryError(
            f"external width {w_ext:g} mm is inconsistent with clear span + "
            f"2 x wall thickness = {expected_width:g} mm"
        )
    expected_height = height + t_top + t_bot
    if abs(h_ext - expected_height) > CONSISTENCY_TOLERANCE_MM:
        raise InvalidGeometryError(
            f"external height {h_ext:g} mm is inconsistent with clear height + "
            f"top slab + bottom slab = {expected_height:g} mm"
        )


def _require_positive(name: str, value_mm: float) -> None:
    if value_mm <= 0:
        raise InvalidGeometryError(f"{name} must be positive, got {value_mm:g} mm")
