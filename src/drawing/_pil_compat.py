"""Import-time compatibility: ezdxf's drawing add-on without Pillow.

ezdxf 1.4.4's ``addons.drawing.frontend`` and ``addons.drawing.pipeline``
import PIL at module level, but Pillow is only ever *exercised* when rendering
DXF IMAGE entities. This project pins plain ezdxf with no ``[draw]`` extra
(spec/architecture.md) and the GA template contains no IMAGE entities, so when
Pillow is absent we register minimal placeholder modules that let the import
succeed — and fail loudly if anything ever actually touches them.

Importing this module installs the placeholder as a side effect; import it
before any ``ezdxf.addons.drawing`` import. If Pillow is installed, this
module does nothing.
"""

import sys
import types

_SUBMODULES = ("Image", "ImageDraw", "ImageEnhance", "ImageOps")


def _install_placeholder() -> None:
    root = types.ModuleType("PIL")
    root.__doc__ = "Placeholder for Pillow - see src/drawing/_pil_compat.py"
    sys.modules["PIL"] = root
    for name in _SUBMODULES:
        module = types.ModuleType(f"PIL.{name}")

        def _missing(attr: str, _name: str = name) -> None:
            raise ModuleNotFoundError(
                f"PIL.{_name}.{attr} was requested but Pillow is not installed. "
                "Pillow is only needed to render DXF IMAGE entities, which the "
                "GA template never contains (see src/drawing/_pil_compat.py)."
            )

        module.__getattr__ = _missing  # type: ignore[method-assign]
        sys.modules[f"PIL.{name}"] = module
        setattr(root, name, module)


try:  # pragma: no cover - trivially environment-dependent
    import PIL.Image  # noqa: F401
    import PIL.ImageDraw  # noqa: F401
    import PIL.ImageEnhance  # noqa: F401
    import PIL.ImageOps  # noqa: F401
except ModuleNotFoundError:
    _install_placeholder()
