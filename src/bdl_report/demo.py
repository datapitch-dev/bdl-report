"""Offline stand-in for the BDL API with a fictional gmina, so the report can be tried without
network (and is exercised in CI). All names and numbers here are made up."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

GMINA = "099999999996"
POWIAT = "099999999000"
VOIVODESHIP = "090000000000"
POLAND = "000000000000"

_UNITS = {
    GMINA: {"id": GMINA, "name": "Przykładowo (DEMO)", "level": 6, "kind": "3", "parentId": POWIAT},
    POWIAT: {
        "id": POWIAT,
        "name": "Powiat przykładowski (DEMO)",
        "level": 5,
        "parentId": VOIVODESHIP,
    },
    VOIVODESHIP: {
        "id": VOIVODESHIP,
        "name": "Województwo przykładowe (DEMO)",
        "level": 2,
        "parentId": POLAND,
    },
}

_SUBJECTS = {
    "D1": "Ludność (DEMO)",
    "D2": "Stopa bezrobocia rejestrowanego (DEMO)",
    "D3": "Przeciętne miesięczne wynagrodzenia brutto (DEMO)",
    "D4": "Podmioty gospodarki narodowej w rejestrze REGON (DEMO)",
}

_VARIABLES = {
    72305: {"n1": "ogółem", "measureUnitName": "osoba", "subjectId": "D1", "level": 6},
    60559: {"n1": "ogółem", "measureUnitName": "%", "subjectId": "D2", "level": 5},
    64428: {"n1": "ogółem", "measureUnitName": "zł", "subjectId": "D3", "level": 5},
    10110: {"n1": "ogółem", "measureUnitName": "jed. gosp.", "subjectId": "D4", "level": 6},
}


def _trend(start: float, step: float, year: int, wobble: float = 0.0) -> float:
    k = year - 2014
    return round(start + step * k + wobble * ((k * 7) % 3 - 1), 1)


def _value(unit: str, var: int, year: int) -> float | None:
    if var == 72305 and unit == GMINA:
        return round(_trend(18_420, -45, year, 20))
    if var == 10110 and unit == GMINA:
        return round(_trend(1_910, 62, year, 15))
    if var == 60559 and unit in (POWIAT, VOIVODESHIP, POLAND):
        base = {POWIAT: 14.8, VOIVODESHIP: 11.2, POLAND: 11.4}[unit]
        covid = 1.1 if year == 2020 else 0.0
        return round(max(base - 0.95 * (year - 2014), base * 0.38) + covid, 1)
    if var == 64428 and unit in (POWIAT, VOIVODESHIP, POLAND):
        base = {POWIAT: 3_310, VOIVODESHIP: 3_620, POLAND: 4_003}[unit]
        return round(base * 1.064 ** (year - 2014), 2)
    return None


class _Response:
    def __init__(self, payload: dict, status_code: int = 200):
        self.status_code = status_code
        self.ok = status_code < 400
        self.headers: dict = {}
        self._payload = payload
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self) -> dict:
        return self._payload


class DemoSession:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get(self, url: str, headers: dict | None = None, timeout: float | None = None):
        self.calls.append(url)
        parts = urlsplit(url)
        path = parts.path.split("/api/v1/", 1)[1]
        query = parse_qs(parts.query)

        if path == "units/search":
            phrase = query.get("name", [""])[0].lower()
            found = [u for u in _UNITS.values() if phrase in u["name"].lower()]
            return _Response({"results": found})
        if path.startswith("units/"):
            unit = _UNITS.get(path.split("/")[1])
            return _Response(unit) if unit else _Response({}, 404)
        if path == "variables/search":
            phrase = query.get("name", [""])[0].lower()
            found = [
                {"id": vid, **meta}
                for vid, meta in _VARIABLES.items()
                if phrase in meta["n1"].lower()
            ]
            return _Response({"results": found})
        if path == "subjects/search":
            phrase = query.get("name", [""])[0].lower()
            found = [
                {"id": sid, "name": name, "hasVariables": True}
                for sid, name in _SUBJECTS.items()
                if phrase in name.lower()
            ]
            return _Response({"results": found})
        if path == "variables":
            sid = query.get("subject-id", [""])[0]
            found = [{"id": vid, **m} for vid, m in _VARIABLES.items() if m["subjectId"] == sid]
            return _Response({"results": found})
        if path.startswith("subjects/"):
            name = _SUBJECTS.get(path.split("/")[1])
            return (
                _Response({"id": path.split("/")[1], "name": name}) if name else _Response({}, 404)
            )
        if path.startswith("variables/"):
            vid = int(path.split("/")[1])
            meta = _VARIABLES.get(vid)
            return _Response({"id": vid, **meta}) if meta else _Response({}, 404)
        if path.startswith("data/by-unit/"):
            unit = path.split("/")[2]
            years = [int(y) for y in query.get("year", [])]
            results = []
            for vid in (int(v) for v in query.get("var-id", [])):
                values = [
                    {"year": str(y), "val": val, "attrId": 1}
                    for y in years
                    if (val := _value(unit, vid, y)) is not None
                ]
                results.append({"id": vid, "values": values})
            return _Response({"unitId": unit, "results": results})
        return _Response({}, 404)
