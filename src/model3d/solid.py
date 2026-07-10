"""Parametric culvert solid — the hand-validated build123d template.

Model space and units (normative for every consumer of this solid):

* **Units: metres.** One model unit is one metre — BoxGeometry's `_m`
  fields are used as-is and `_mm` fields are converted exactly once, here.
  Exports declare the unit explicitly (`Unit.M`), so the GLB carries vertex
  data in metres (the glTF convention) and the STEP declares its length
  unit — FreeCAD opens the barrel at real-world size.
* **Axis mapping:** X = external width (across the barrel), Y = barrel
  length (along the track axis), Z = external height (vertical). The solid
  is centred at the origin on all three axes. (OCCT's glTF writer adds the
  standard Z-up -> Y-up rotation node on export; mesh vertex data keeps
  this mapping.)

Construction: outer prism (external width x height cross-section, extruded
the barrel length) minus the clear-opening void. The void cross-section is
the clear span x clear height rectangle with each inside corner filled by a
45-degree haunch of equal legs `haunch_mm` — i.e. minus a corner triangle
of area leg^2 / 2 — and it runs the full barrel length, so both ends are
open (a barrel you can see through).

The template verifies its own output against the closed-form concrete
volume and the external dimensions before returning — never a silent bad
model (spec/capabilities/model-3d.md). It is a fixed parametric template:
no generated geometry code, ever.
"""

from build123d import Part, Plane, Polyline, Rectangle, extrude, make_face

from domain.culvert import BoxGeometry
from model3d.validation import validate_geometry

MM_PER_M = 1000.0

# The void tool overruns each open end by this much so the boolean cut never
# resolves coincident end faces; the overrun lies outside the outer prism and
# removes no material.
_VOID_END_OVERRUN_M = 0.01

# Consecutive profile points closer than this collapse into one, so the
# haunch octagon degenerates cleanly to the plain rectangle at haunch = 0.
_DEDUPE_TOL_M = 1e-9

# Self-verification bounds — 10x tighter than the 0.1% / 1 mm the gate tests
# allow, so a template regression trips here first.
_VERIFY_VOLUME_REL_TOL = 1e-4
_VERIFY_BBOX_TOL_M = 1e-4


class SolidVerificationError(ValueError):
    """Raised when the built solid disagrees with the closed-form geometry."""


def analytic_concrete_volume_m3(geometry: BoxGeometry) -> float:
    """(outer area - haunched void area) x barrel length, metres cubed."""
    haunch_m = geometry.haunch_mm / MM_PER_M
    void_area_m2 = geometry.clear_span_m * geometry.clear_height_m - 2.0 * haunch_m**2
    concrete_area_m2 = geometry.external_width_m * geometry.external_height_m - void_area_m2
    return concrete_area_m2 * geometry.barrel_length_m


def build_culvert_solid(geometry: BoxGeometry) -> Part:
    """Outer prism minus the haunched clear opening, centred at the origin."""
    validate_geometry(geometry)

    half_length = geometry.barrel_length_m / 2.0
    outer = extrude(
        Plane.XZ * Rectangle(geometry.external_width_m, geometry.external_height_m),
        amount=half_length,
        both=True,
    )
    void = extrude(
        Plane.XZ * make_face(Polyline(*_void_profile_points(geometry), close=True)),
        amount=half_length + _VOID_END_OVERRUN_M,
        both=True,
    )
    solid = outer - void
    _verify(solid, geometry)
    return solid


def _void_profile_points(geometry: BoxGeometry) -> list[tuple[float, float]]:
    """Clear-opening octagon in Plane.XZ local coordinates (x = width,
    y = height), counter-clockwise from the bottom edge."""
    half_span = geometry.clear_span_m / 2.0
    half_height = geometry.clear_height_m / 2.0
    leg = geometry.haunch_mm / MM_PER_M
    raw = [
        (-half_span + leg, -half_height),
        (half_span - leg, -half_height),
        (half_span, -half_height + leg),
        (half_span, half_height - leg),
        (half_span - leg, half_height),
        (-half_span + leg, half_height),
        (-half_span, half_height - leg),
        (-half_span, -half_height + leg),
    ]
    points: list[tuple[float, float]] = []
    for point in raw:
        if not points or not _same_point(point, points[-1]):
            points.append(point)
    if len(points) > 1 and _same_point(points[0], points[-1]):
        points.pop()
    return points


def _same_point(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return abs(a[0] - b[0]) <= _DEDUPE_TOL_M and abs(a[1] - b[1]) <= _DEDUPE_TOL_M


def _verify(solid: Part, geometry: BoxGeometry) -> None:
    expected_volume = analytic_concrete_volume_m3(geometry)
    if abs(solid.volume - expected_volume) > _VERIFY_VOLUME_REL_TOL * expected_volume:
        raise SolidVerificationError(
            f"solid volume {solid.volume:.6f} m^3 disagrees with the closed-form "
            f"concrete volume {expected_volume:.6f} m^3 - refusing to export"
        )
    size = solid.bounding_box().size
    for name, actual_m, expected_m in (
        ("external width (X)", size.X, geometry.external_width_m),
        ("barrel length (Y)", size.Y, geometry.barrel_length_m),
        ("external height (Z)", size.Z, geometry.external_height_m),
    ):
        if abs(actual_m - expected_m) > _VERIFY_BBOX_TOL_M:
            raise SolidVerificationError(
                f"solid {name} {actual_m:.6f} m disagrees with BoxGeometry "
                f"{expected_m:.6f} m - refusing to export"
            )
