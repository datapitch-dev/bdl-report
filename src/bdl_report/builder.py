"""Collects the data for one report: the unit, its parents and a series per indicator."""

from __future__ import annotations

from dataclasses import dataclass, field

from .client import POLAND_ID, BdlClient, BdlError, Unit, Variable
from .indicators import Indicator


@dataclass
class Series:
    indicator: Indicator
    variable: Variable | None
    values: dict[int, float] = field(default_factory=dict)
    # Set when the unit itself has no data and the parent powiat's numbers are shown instead.
    source: Unit | None = None
    comparisons: dict[str, dict[int, float]] = field(default_factory=dict)

    @property
    def years(self) -> list[int]:
        return sorted(self.values)

    @property
    def latest(self) -> tuple[int, float] | None:
        return (self.years[-1], self.values[self.years[-1]]) if self.values else None

    @property
    def change_pct(self) -> float | None:
        years = self.years
        if len(years) < 2 or self.values[years[0]] == 0:
            return None
        return (self.values[years[-1]] / self.values[years[0]] - 1) * 100

    @property
    def breaks(self) -> list[tuple[int, float]]:
        """Years with a year-on-year jump over 25 %, as ``(year, change %)``.

        For stock measures such as population or density a jump like that almost always means
        a methodology change at GUS (e.g. a census rebase or a new way of counting area), not a
        real change, so the report points it out.
        """
        years = self.years
        out = []
        for prev, year in zip(years, years[1:], strict=False):
            before, after = self.values[prev], self.values[year]
            if before and abs(after / before - 1) > 0.25:
                out.append((year, (after / before - 1) * 100))
        return out

    @property
    def break_note(self) -> str:
        if not self.breaks:
            return ""
        jumps = ", ".join(f"{y} ({c:+.0f}%)".replace(".", ",") for y, c in self.breaks)
        return f"skok w {jumps}: prawdopodobnie zmiana metodologii GUS, porównuj ostrożnie"


@dataclass
class ReportData:
    unit: Unit
    ancestors: list[Unit]
    years: list[int]
    series: list[Series]

    @property
    def voivodeship(self) -> Unit | None:
        return next((u for u in self.ancestors if u.level == 2), None)

    @property
    def powiat(self) -> Unit | None:
        return next((u for u in self.ancestors if u.level == 5), None)


def build(
    client: BdlClient, unit_id: str, indicators: list[Indicator], years: list[int]
) -> ReportData:
    unit = client.unit(unit_id)
    ancestors = client.ancestors(unit)
    var_ids = [i.id for i in indicators]

    own = client.data_by_unit(unit.id, var_ids, years)
    report = ReportData(unit=unit, ancestors=ancestors, years=years, series=[])
    for indicator in indicators:
        try:
            variable = client.variable(indicator.id)
        except BdlError:  # metadata is cosmetic; a missing one must not sink the report
            variable = None
        report.series.append(Series(indicator, variable, own.get(indicator.id, {})))

    # Some indicators (e.g. wages, unemployment rate) are published only down to powiat level.
    missing = [s for s in report.series if not s.values]
    if missing and report.powiat:
        parent = client.data_by_unit(report.powiat.id, [s.indicator.id for s in missing], years)
        for s in missing:
            if parent.get(s.indicator.id):
                s.values, s.source = parent[s.indicator.id], report.powiat

    to_compare = [s.indicator.id for s in report.series if s.indicator.compare and s.values]
    if to_compare:
        refs = []
        if report.voivodeship:
            refs.append(report.voivodeship)
        refs.append(Unit(id=POLAND_ID, name="Polska", level=0))
        for ref in refs:
            data = client.data_by_unit(ref.id, to_compare, years)
            for s in report.series:
                if s.indicator.id in data:
                    s.comparisons[ref.name] = data[s.indicator.id]
    return report
