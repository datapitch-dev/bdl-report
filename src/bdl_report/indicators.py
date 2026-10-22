"""Default set of indicators in the report.

IDs are BDL variable ids. Run ``bdl-report zmienne --sprawdz`` to print the official name and
unit of each one straight from the API, and ``bdl-report zmienne <fraza>`` to find others.
A custom set can be passed with ``--zmienne plik.json`` (a list of objects with these fields).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Indicator:
    id: int
    label: str
    # Rates and averages can be compared with the voivodeship and Poland; absolute counts cannot.
    compare: bool = False
    # Higher is better (True), worse (False) or neither (None); only colours the change column.
    higher_is_better: bool | None = None


DEFAULT_INDICATORS = [
    Indicator(72305, "Ludność ogółem"),
    Indicator(60559, "Stopa bezrobocia rejestrowanego", compare=True, higher_is_better=False),
    Indicator(64428, "Przeciętne wynagrodzenie brutto", compare=True, higher_is_better=True),
    Indicator(10110, "Podmioty gospodarki narodowej (REGON)", higher_is_better=True),
]


def load_indicators(path: str | Path | None) -> list[Indicator]:
    if path is None:
        return list(DEFAULT_INDICATORS)
    items = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        Indicator(
            id=int(item["id"]),
            label=item["label"],
            compare=bool(item.get("compare", False)),
            higher_is_better=item.get("higher_is_better"),
        )
        for item in items
    ]
