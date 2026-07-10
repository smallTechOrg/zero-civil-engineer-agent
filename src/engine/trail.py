"""Calc-trail recorder — every computed number in the engine passes through here."""

from domain.culvert import CalcStep


class TrailRecorder:
    """Builds the ordered `CalcStep` trail with sequential, sortable step ids."""

    def __init__(self) -> None:
        self._steps: list[CalcStep] = []

    def record(
        self,
        *,
        description: str,
        formula: str,
        inputs: dict[str, float | int | str],
        value: float,
        unit: str,
        citation: str,
    ) -> float:
        """Append one step and return its value, so call sites stay single-expression."""
        self._steps.append(
            CalcStep(
                step_id=f"S{len(self._steps) + 1:02d}",
                description=description,
                formula=formula,
                inputs=inputs,
                value=value,
                unit=unit,
                citation=citation,
            )
        )
        return value

    @property
    def steps(self) -> list[CalcStep]:
        return list(self._steps)
