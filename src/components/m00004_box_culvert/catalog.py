"""The digitized M-00004 catalogue subset + the deterministic config selector.

Loads `catalog.json` once (15 configs = fill 0/1/2 m x five box sizes 2x2..6x6,
each with a PROVISIONAL a1..h bar schedule) and exposes `select_config`, which
picks the enclosing/nearest standard configuration and reports every PROVISIONAL
flag. NEVER a silent guess: an out-of-catalogue input always carries an explicit
nearest-config / extrapolation flag.

Selection rule (spec/capabilities/m00004-box-culvert.md — normative):
1. Fill tier: smallest catalogue `fill_m` >= requested cushion; if cushion > max
   tier (2 m) use the 2 m tier + a PROVISIONAL flag.
2. Box size: within that tier the config with `span_m >= clear_span` AND
   `height_m >= clear_height` of smallest `span_m*height_m`; if none encloses use
   the 6x6 config + a PROVISIONAL flag.
3. Surcharge: subset is surcharge = 0; any surcharge > 0 adds a PROVISIONAL flag.
4. If the entered box is not an exact standard size, add a nearest-config note.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_CATALOG_PATH = Path(__file__).resolve().parent / "catalog.json"

# The digitized fill tiers (m) and the maximum standard box side (m).
FILL_TIERS = (0.0, 1.0, 2.0)
MAX_FILL_TIER_M = 2.0
MAX_BOX_SIDE_M = 6.0


@lru_cache(maxsize=1)
def _catalog() -> dict:
    return json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))


def meta() -> dict:
    """The catalogue `_meta` block (status + PROVISIONAL notes)."""
    return dict(_catalog()["_meta"])


def all_configs() -> list[dict]:
    """Every standard config (copies, so callers cannot mutate the cache)."""
    return [dict(c) for c in _catalog()["configs"]]


def get_config(config_id: str) -> dict:
    for config in _catalog()["configs"]:
        if config["id"] == config_id:
            return dict(config)
    raise KeyError(f"no standard config with id {config_id!r}")


def _fill_tier(cushion_m: float) -> tuple[float, str | None]:
    """(chosen tier fill_m, PROVISIONAL flag or None)."""
    for tier in FILL_TIERS:
        if tier >= cushion_m - 1e-9:
            return tier, None
    return (
        MAX_FILL_TIER_M,
        f"fill {cushion_m:g} m exceeds digitized range (0-2 m); using 2 m standard config",
    )


def select_config(
    clear_span_m: float,
    clear_height_m: float,
    cushion_m: float,
    surcharge_kn_m2: float = 0.0,
) -> tuple[dict, list[str]]:
    """Return (selected config dict, PROVISIONAL flags) per the selection rule.

    The returned config is a copy of the catalogue row; the opening is always
    drawn at the entered size (only thickness/haunch/bars come from the config).
    """
    flags: list[str] = []

    # 1) fill tier (enclosing / conservative)
    tier, fill_flag = _fill_tier(cushion_m)
    if fill_flag:
        flags.append(fill_flag)
    tier_configs = [c for c in _catalog()["configs"] if abs(c["fill_m"] - tier) < 1e-9]

    # 2) smallest enclosing standard box within the tier
    enclosing = [
        c
        for c in tier_configs
        if c["span_m"] >= clear_span_m - 1e-9 and c["height_m"] >= clear_height_m - 1e-9
    ]
    if enclosing:
        config = min(enclosing, key=lambda c: c["span_m"] * c["height_m"])
    else:
        config = max(tier_configs, key=lambda c: c["span_m"] * c["height_m"])  # the 6x6 config
        flags.append(
            f"box {clear_span_m:g}x{clear_height_m:g} m exceeds digitized range "
            "(<=6x6 m); using 6x6 standard config"
        )

    # 3) surcharge (subset is surcharge = 0)
    if surcharge_kn_m2 > 0:
        flags.append(
            f"surcharge {surcharge_kn_m2:g} kN/m^2 not covered by the digitized subset "
            "(surcharge = 0)"
        )

    # 4) nearest-config note when the entered box is not an exact standard size
    if abs(config["span_m"] - clear_span_m) > 1e-9 or abs(config["height_m"] - clear_height_m) > 1e-9:
        flags.append(
            f"opening {clear_span_m:g}x{clear_height_m:g} m drawn at entered size; "
            f"thickness/haunch/bars taken from nearest standard config {config['id']} "
            f"({config['span_m']:g}x{config['height_m']:g} m)"
        )

    return dict(config), flags
