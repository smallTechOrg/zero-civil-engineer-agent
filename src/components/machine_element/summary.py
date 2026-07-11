"""Type-specific factor-of-safety summary for the machine-element FoS panel.

PINNED shape (matches the frontend TypeSummaryPanel + the api snapshot):
    {"kind": "fos_summary",
     "max_stress_mpa", "permissible_stress_mpa", "stress_ok",
     "factor_of_safety", "required_fos", "fos_ok", "verdict"}

The governing static strength result (combined bending+torsion for a shaft, throat
shear for a welded joint) drives the panel. `fos_ok` is
`factor_of_safety >= required_fos`.
"""

from __future__ import annotations

from components.base import coerce
from components.machine_element.analysis import MachineElementAnalysis


def type_summary(*, analysis: MachineElementAnalysis, verdict: str) -> dict:
    analysis = coerce(MachineElementAnalysis, analysis)
    return {
        "kind": "fos_summary",
        "max_stress_mpa": round(analysis.max_stress_mpa, 2),
        "permissible_stress_mpa": round(analysis.permissible_stress_mpa, 2),
        "stress_ok": bool(analysis.max_stress_mpa <= analysis.permissible_stress_mpa),
        "factor_of_safety": round(analysis.factor_of_safety, 2),
        "required_fos": round(analysis.required_fos, 2),
        "fos_ok": bool(analysis.factor_of_safety >= analysis.required_fos),
        "verdict": verdict,
    }
