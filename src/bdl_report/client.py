"""Client for the BDL API (https://bdl.stat.gov.pl/api/v1), with caching and throttling."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from urllib.parse import urlencode

import requests

from .cache import ResponseCache

BASE_URL = "https://bdl.stat.gov.pl/api/v1"
POLAND_ID = "000000000000"

LEVEL_NAMES = {
    0: "Polska",
    1: "Makroregion",
    2: "Województwo",
    3: "Region",
    4: "Podregion",
    5: "Powiat",
    6: "Gmina",
    7: "Miasto statystyczne",
}
GMINA_KINDS = {
    "1": "gmina miejska",
    "2": "gmina wiejska",
    "3": "gmina miejsko-wiejska",
    "4": "miasto w gminie miejsko-wiejskiej",
    "5": "obszar wiejski w gminie miejsko-wiejskiej",
}


class BdlError(Exception):
    pass


class NotFound(BdlError):
    pass


@dataclass
class Unit:
    id: str
    name: str
    level: int
    parent_id: str | None = None
    kind: str = ""

    @property
    def level_name(self) -> str:
        if self.level == 6 and self.kind in GMINA_KINDS:
            return GMINA_KINDS[self.kind]
        return LEVEL_NAMES.get(self.level, f"poziom {self.level}")

    @classmethod
    def from_api(cls, body: dict) -> Unit:
        return cls(
            id=body["id"],
            name=body["name"],
            level=int(body.get("level", 0)),
            parent_id=body.get("parentId"),
            kind=str(body.get("kind") or ""),
        )


@dataclass
class Variable:
    id: int
    name: str
    unit: str
    subject_id: str = ""
    level: int | None = None  # lowest unit level the variable is published for
    subject: str = ""  # filled in by BdlClient; n1..n5 alone are often just "ogółem"

    @property
    def full_name(self) -> str:
        return f"{self.subject}: {self.name}" if self.subject else self.name

    @classmethod
    def from_api(cls, body: dict) -> Variable:
        # Variable names are split across n1..n5 (e.g. "ogółem" / "mężczyźni") and only make
        # sense together with the name of their subject.
        parts = [body.get(f"n{i}") for i in range(1, 6)]
        level = body.get("level")
        return cls(
            id=int(body["id"]),
            name=", ".join(p for p in parts if p),
            unit=body.get("measureUnitName") or "",
            subject_id=body.get("subjectId") or "",
            level=int(level) if level is not None else None,
        )


class BdlClient:
    """``session``, ``sleep`` and ``clock`` are injectable so tests run offline and instantly."""

    def __init__(
        self,
        session: requests.Session | None = None,
        api_key: str | None = None,
        cache: ResponseCache | None = None,
        base_url: str = BASE_URL,
        min_interval: float = 0.25,  # anonymous limit is 5 requests per second
        retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.session = session or requests.Session()
        self.headers = {"X-ClientId": api_key} if api_key else {}
        self.cache = cache or ResponseCache()
        self.base_url = base_url.rstrip("/")
        self.min_interval = min_interval
        self.retries = retries
        self.sleep = sleep
        self.clock = clock
        self._last_request = float("-inf")
        self.requests_sent = 0

    # --- endpoints -------------------------------------------------------------------------

    def search_units(self, name: str, levels: Iterable[int] = (2, 5, 6)) -> list[Unit]:
        params = [("name", name), *(("level", lvl) for lvl in levels)]
        return [Unit.from_api(u) for u in self._get_all("units/search", params)]

    def unit(self, unit_id: str) -> Unit:
        if unit_id == POLAND_ID:
            return Unit(id=POLAND_ID, name="Polska", level=0)
        return Unit.from_api(self._get(f"units/{unit_id}", []))

    def ancestors(self, unit: Unit) -> list[Unit]:
        """Parents from the nearest up to the voivodeship (powiat, województwo)."""
        chain = []
        current = unit
        while current.parent_id and current.level > 2:
            current = self.unit(current.parent_id)
            if current.level in (2, 5):
                chain.append(current)
        return chain

    def variable(self, var_id: int) -> Variable:
        return self._with_subject(Variable.from_api(self._get(f"variables/{var_id}", [])))

    def search_variables(self, phrase: str, max_subjects: int = 8) -> list[Variable]:
        """Variables whose own name or whose subject's name contains ``phrase``.

        Variable names are often just "ogółem", so a search by subject ("bezrobocie",
        "wynagrodzenia") is what usually finds the right one.
        """
        found = {
            v["id"]: Variable.from_api(v)
            for v in self._get_all("variables/search", [("name", phrase)])
        }
        subjects = [
            s for s in self._get_all("subjects/search", [("name", phrase)]) if s.get("hasVariables")
        ]
        for subject in subjects[:max_subjects]:
            for v in self._get_all("variables", [("subject-id", subject["id"])]):
                found.setdefault(v["id"], Variable.from_api(v))
        return [self._with_subject(v) for v in found.values()]

    def subject_name(self, subject_id: str) -> str:
        try:
            return self._get(f"subjects/{subject_id}", []).get("name") or ""
        except NotFound:
            return ""

    def _with_subject(self, variable: Variable) -> Variable:
        if variable.subject_id:
            variable.subject = self.subject_name(variable.subject_id)
        return variable

    def data_by_unit(
        self, unit_id: str, var_ids: Iterable[int], years: Iterable[int]
    ) -> dict[int, dict[int, float]]:
        """``{variable id: {year: value}}``. Variables without data are left out."""
        params = [*(("var-id", v) for v in var_ids), *(("year", y) for y in years)]
        out: dict[int, dict[int, float]] = {}
        for result in self._get_all(f"data/by-unit/{unit_id}", params):
            series = {
                int(v["year"]): float(v["val"])
                for v in result.get("values") or []
                if v.get("val") is not None
            }
            if series:
                out[int(result["id"])] = series
        return out

    # --- transport -------------------------------------------------------------------------

    def _get_all(self, path: str, params: list[tuple]) -> list[dict]:
        results: list[dict] = []
        page = 0
        while True:
            try:
                body = self._get(path, [*params, ("page-size", 100), ("page", page)])
            except NotFound:
                return results
            results.extend(body.get("results") or [])
            if not (body.get("links") or {}).get("next") or not body.get("results"):
                return results
            page += 1

    def _get(self, path: str, params: list[tuple]) -> dict:
        query = urlencode([*params, ("format", "json"), ("lang", "pl")])
        url = f"{self.base_url}/{path}?{query}"
        cached = self.cache.get(url)
        if cached is not None:
            return cached

        for attempt in range(self.retries + 1):
            self._throttle()
            try:
                response = self.session.get(url, headers=self.headers, timeout=30)
            except requests.RequestException as exc:
                if attempt == self.retries:
                    raise BdlError(f"Brak połączenia z API GUS: {exc}") from exc
                self.sleep(2**attempt)
                continue
            self.requests_sent += 1

            if response.status_code == 404:
                raise NotFound(f"API GUS nie zna zasobu {path}")
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == self.retries:
                    raise BdlError(_limit_message(response))
                retry_after = response.headers.get("Retry-After", "")
                self.sleep(float(retry_after) if retry_after.isdigit() else 2**attempt * 5)
                continue
            if not response.ok:
                raise BdlError(f"API GUS: HTTP {response.status_code}: {response.text[:300]}")
            body = response.json()
            self.cache.put(url, body)
            return body
        raise AssertionError("unreachable")

    def _throttle(self) -> None:
        wait = self._last_request + self.min_interval - self.clock()
        if wait > 0:
            self.sleep(wait)
        self._last_request = self.clock()


def _limit_message(response: requests.Response) -> str:
    if response.status_code == 429:
        return (
            "Przekroczony limit zapytań API GUS (bez klucza: 100 na 15 minut). Odczekaj chwilę "
            "albo załóż darmowy klucz na api.stat.gov.pl i ustaw zmienną GUS_API_KEY."
        )
    return f"API GUS nie odpowiada (HTTP {response.status_code}). Spróbuj później."
