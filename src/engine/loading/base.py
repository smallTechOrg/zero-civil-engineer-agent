"""Pluggable railway loading-standard layer (irs-engine.md business rule).

`LoadingStandard` is the abstract interface the IRS engine consumes: EUDL for
bending moment and for shear by loaded length, CDA dynamic augment including the
fill/cushion reduction, and full source citations. Concrete standards register
themselves by name, so a future standard (e.g. DFC 32.5t) slots in without any
change to the engine — callers only ever ask `get_loading_standard(name)`.

Note: `domain.culvert.LoadingStandard` is the *enum of standard names* used in
`CulvertParams`; this class is the *behavioural interface* those names resolve to.
"""

from abc import ABC, abstractmethod
from bisect import bisect_left
from typing import NamedTuple


class EudlRow(NamedTuple):
    """One transcribed EUDL table row: kN per track (BG) against loaded length.

    `needs_verification` encodes transcription honesty — True until the row has
    been checked digit-for-digit against the cited source PDF.
    """

    loaded_length_m: float
    eudl_kn: float
    needs_verification: bool


class LoadingStandard(ABC):
    """One railway loading standard — tables + impact rules + citations."""

    name: str

    @abstractmethod
    def eudl_bm_kn(self, loaded_length_m: float) -> float:
        """EUDL for bending moment, kN per track, linearly interpolated between table rows."""

    @abstractmethod
    def eudl_shear_kn(self, loaded_length_m: float) -> float:
        """EUDL for shear (end shear), kN per track, linearly interpolated between table rows."""

    @abstractmethod
    def eudl_bm_table(self) -> tuple[EudlRow, ...]:
        """Raw transcribed BM table rows — for proof-check re-verification and audit."""

    @abstractmethod
    def eudl_shear_table(self) -> tuple[EudlRow, ...]:
        """Raw transcribed shear table rows — for proof-check re-verification and audit."""

    @abstractmethod
    def cda(self, loaded_length_m: float, cushion_m: float = 0.0) -> float:
        """Coefficient of Dynamic Augment as a fraction, including the fill/cushion reduction."""

    @property
    @abstractmethod
    def citation(self) -> str:
        """Source document + tables/pages + ACS correction-slip level for every value served."""


_REGISTRY: dict[str, LoadingStandard] = {}


def register_loading_standard(standard: LoadingStandard) -> LoadingStandard:
    """Register a standard under its `name`; re-registering the same instance is a no-op."""
    existing = _REGISTRY.get(standard.name)
    if existing is not None and existing is not standard:
        raise ValueError(f"loading standard '{standard.name}' is already registered")
    _REGISTRY[standard.name] = standard
    return standard


def get_loading_standard(name: str) -> LoadingStandard:
    """Resolve a standard by name — raises ValueError naming the registered standards."""
    standard = _REGISTRY.get(name)
    if standard is None:
        known = ", ".join(sorted(_REGISTRY)) or "none"
        raise ValueError(f"unknown loading standard '{name}' — registered standards: {known}")
    return standard


def registered_standard_names() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def validate_eudl_table(rows: tuple[EudlRow, ...], table_label: str) -> tuple[EudlRow, ...]:
    """Fail loudly at import if a transcribed table violates the engineering invariants."""
    if len(rows) < 2:
        raise ValueError(f"{table_label}: a EUDL table needs at least two rows")
    for previous, current in zip(rows, rows[1:]):
        if current.loaded_length_m <= previous.loaded_length_m:
            raise ValueError(
                f"{table_label}: loaded lengths must be strictly increasing "
                f"({previous.loaded_length_m} -> {current.loaded_length_m})"
            )
        if current.eudl_kn < previous.eudl_kn:
            raise ValueError(
                f"{table_label}: EUDL must be monotonically non-decreasing with loaded "
                f"length ({previous.eudl_kn} -> {current.eudl_kn} kN)"
            )
    return rows


def interpolate_eudl(
    rows: tuple[EudlRow, ...],
    loaded_length_m: float,
    *,
    table_label: str,
    standard_name: str,
) -> float:
    """Exact row value at a grid point; linear interpolation between adjacent rows otherwise."""
    first, last = rows[0].loaded_length_m, rows[-1].loaded_length_m
    if not first <= loaded_length_m <= last:
        raise ValueError(
            f"loaded length {loaded_length_m!r} m is outside the {standard_name} "
            f"{table_label} table range {first:g}-{last:g} m"
        )
    index = bisect_left(rows, loaded_length_m, key=lambda row: row.loaded_length_m)
    upper = rows[index]
    if upper.loaded_length_m == loaded_length_m:
        return upper.eudl_kn
    lower = rows[index - 1]
    fraction = (loaded_length_m - lower.loaded_length_m) / (
        upper.loaded_length_m - lower.loaded_length_m
    )
    return lower.eudl_kn + fraction * (upper.eudl_kn - lower.eudl_kn)
