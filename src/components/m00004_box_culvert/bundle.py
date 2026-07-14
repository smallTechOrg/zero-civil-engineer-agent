"""M-00004 downloadable ZIP bundle — every per-diagram DXF + STEP part on disk.

Stdlib ``zipfile`` only (no new dependency). The bundle is a review-stage
convenience artefact: it gathers whatever the 2D (`drawing.draw`) and 3D
(`model3d.model3d`) steps left in ``out_dir`` into a single ``m00004_bundle.zip``.

Robust by design: it includes exactly the files that are present. The 2D DXFs are
always on disk by review; the STEP parts may be absent (the 3D step is non-fatal),
in which case the zip still builds with the DXFs alone. It never raises on a
missing input — only on an unwritable ``out_dir``.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

BUNDLE_FILENAME = "m00004_bundle.zip"

# The ten per-diagram DXF stems authored by drawing.py (fixed filenames), plus the
# Phase-1 GA DXF. Ordered for a stable, readable archive listing.
_DXF_STEMS = (
    "ga",
    "elevation",
    "cross_section",
    "plan",
    "curtain_wall",
    "typical_details",
    "return_wall",
    "bar_shape_table",
    "notations",
    "notes",
    "haunch_table",
)

# The STEP parts authored by model3d.py (fixed filenames). Possibly absent — the
# 3D step is non-fatal — so each is included only if present on disk.
_STEP_NAMES = (
    "model.step",
    "assembly.step",
    "box.step",
    "curtain_wall.step",
    "return_wall.step",
)


def _members(out_dir: Path) -> list[Path]:
    """Return the on-disk DXF + STEP files to archive, in stable order."""
    members: list[Path] = []
    for stem in _DXF_STEMS:
        candidate = out_dir / f"{stem}.dxf"
        if candidate.is_file():
            members.append(candidate)
    for name in _STEP_NAMES:
        candidate = out_dir / name
        if candidate.is_file():
            members.append(candidate)
    return members


def build_bundle(out_dir: Path) -> Path:
    """Zip every per-diagram DXF + STEP part present in ``out_dir``.

    Returns the ``out_dir/m00004_bundle.zip`` Path. Builds even if only the DXFs
    (or, in the pathological empty case, nothing) are present.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / BUNDLE_FILENAME

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for member in _members(out_dir):
            # arcname = bare filename so the archive is flat and predictable
            archive.write(member, arcname=member.name)
    return zip_path
