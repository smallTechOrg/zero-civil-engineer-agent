"""Preset endpoints — list (Phase 1) and edit (Phase 3).

PUT values are whitelisted to NON-critical `CulvertParams` fields and validated by
the real `CulvertParams` validators (a probe instance with fixed critical values runs
the range/enum checks). Editing a preset never rewrites history — runs snapshot the
preset values they used into `params_json` at run time.
"""

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from api._common import api_error, ok
from db.models import PresetRow
from db.session import get_session
from domain.api import PresetInfo
from domain.culvert import CulvertParams

router = APIRouter(prefix="/api")

# Critical params must come from the user on every run (spec/data.md) — never a preset.
CRITICAL_FIELDS = frozenset({"clear_span_m", "clear_height_m", "cushion_m"})

# Fixed critical values for the validation probe (the canonical demo culvert) —
# only used to run the real CulvertParams range/enum validators; never stored.
_PROBE_CRITICALS = {"clear_span_m": 4.0, "clear_height_m": 3.0, "cushion_m": 2.5}


class PresetUpdateRequest(BaseModel):
    """PUT body — `name` and `values` only, both optional (partial update).

    `extra="forbid"` rejects any other key (incl. `is_default`, which is not
    editable through this endpoint) with FastAPI's 422 request validation.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    values: dict[str, Any] | None = None


def _preset_info(row: PresetRow) -> dict:
    """The one wire shape for a preset — shared by GET and PUT responses."""
    return PresetInfo(
        preset_id=row.id,
        name=row.name,
        is_default=row.is_default,
        values=json.loads(row.values_json),
    ).model_dump()


@router.get("/presets")
def list_presets(session: Session = Depends(get_session)) -> dict:
    rows = session.execute(
        select(PresetRow).order_by(PresetRow.is_default.desc(), PresetRow.name)
    ).scalars()
    return ok({"presets": [_preset_info(row) for row in rows]})


@router.put("/presets/{preset_id}")
def update_preset(
    preset_id: str, req: PresetUpdateRequest, session: Session = Depends(get_session)
) -> dict:
    row = session.get(PresetRow, preset_id)
    if row is None:
        raise api_error("NOT_FOUND", f"Preset {preset_id} not found", 404)
    if req.name is None and req.values is None:
        raise api_error("EMPTY_UPDATE", "Provide 'name' and/or 'values' to update", 422)

    # Validate everything before mutating anything (no partial writes on error).
    new_name = row.name
    if req.name is not None:
        new_name = req.name.strip()
        if not new_name:
            raise api_error("INVALID_VALUE", "Preset name must not be blank", 422)

    if req.values is not None:
        row.values_json = json.dumps(_merged_values(json.loads(row.values_json), req.values))
    row.name = new_name
    row.updated_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(row)
    return ok(_preset_info(row))


def _merged_values(existing: dict, candidate: dict) -> dict:
    """Merge candidate values over the stored ones, enforcing the whitelist and
    the real CulvertParams validators. `null` clears an override (the key is
    dropped — only the nullable thickness fields accept null; the probe rejects
    null anywhere else). Raises 422 api_error on any violation."""
    critical = sorted(k for k in candidate if k in CRITICAL_FIELDS)
    unknown = sorted(k for k in candidate if k not in CulvertParams.model_fields)
    if critical or unknown:
        problems = [
            f"'{key}' is a critical parameter (always user-supplied per run) "
            "and cannot be stored in a preset"
            for key in critical
        ] + [f"'{key}' is not a CulvertParams field" for key in unknown]
        raise api_error("INVALID_FIELD", "; ".join(problems), 422)

    merged = {**existing, **candidate}
    try:
        CulvertParams(**{**_PROBE_CRITICALS, **merged})
    except ValidationError as exc:
        raise api_error("INVALID_VALUE", _validation_message(exc), 422) from exc
    # Store only explicit overrides — a cleared (null) thickness reverts to auto-size.
    return {key: value for key, value in merged.items() if value is not None}


# Pydantic error types raised by numeric bound (ge/le/gt/lt) violations.
_NUMERIC_BOUND_ERRORS = frozenset(
    {"greater_than_equal", "less_than_equal", "greater_than", "less_than"}
)


def _validation_message(exc: ValidationError) -> str:
    """'clear_cover_mm: 200 is outside the valid range 40–75' — field, offending
    value, and the FULL declared range (both bounds) per design-library.md.
    Fields without numeric bounds (enums, custom validators) keep pydantic's own
    message — it already names all allowed values / the rule."""
    problems = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err["loc"]) or "values"
        range_text = (
            _field_range_text(str(err["loc"][0]))
            if err["type"] in _NUMERIC_BOUND_ERRORS and err["loc"]
            else None
        )
        if range_text is not None:
            problems.append(
                f"{loc}: {_format_number(err['input'])} is outside the valid range {range_text}"
            )
        else:
            problems.append(f"{loc}: {err['msg']}")
    return "Invalid preset value — " + "; ".join(problems)


def _field_range_text(field: str) -> str | None:
    """The full valid range declared on a CulvertParams field, read from its own
    ge/le/gt/lt constraint metadata — e.g. '40–75'. None if the field declares
    no numeric bounds."""
    info = CulvertParams.model_fields.get(field)
    bounds: dict[str, float] = {}
    for constraint in info.metadata if info is not None else []:
        for kind in ("ge", "le", "gt", "lt"):
            value = getattr(constraint, kind, None)
            if value is not None:
                bounds[kind] = value
    if not bounds:
        return None
    if "ge" in bounds and "le" in bounds:
        return f"{_format_number(bounds['ge'])}–{_format_number(bounds['le'])}"
    parts = []
    if "ge" in bounds:
        parts.append(f"at least {_format_number(bounds['ge'])}")
    if "gt" in bounds:
        parts.append(f"greater than {_format_number(bounds['gt'])}")
    if "le" in bounds:
        parts.append(f"at most {_format_number(bounds['le'])}")
    if "lt" in bounds:
        parts.append(f"less than {_format_number(bounds['lt'])}")
    return ", ".join(parts)


def _format_number(value: Any) -> str:
    """'40' not '40.0'; non-numeric inputs fall back to str()."""
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)
