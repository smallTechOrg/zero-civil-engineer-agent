"""Component catalogue endpoint — the picker/gallery source (Expansion Phase 1).

Reads `registry.list_components()`; the registry is populated at import by
`src/components/__init__.py`. The frontend greys `coming_soon` cards.
"""

from fastapi import APIRouter

from api._common import ok

router = APIRouter(prefix="/api")


@router.get("/components")
def list_components() -> dict:
    from components import registry

    return ok({"components": registry.list_components()})
