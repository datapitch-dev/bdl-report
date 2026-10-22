"""Command line: ``bdl-report szukaj``, ``bdl-report raport``, ``bdl-report zmienne``."""

from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

from .builder import build
from .cache import ResponseCache
from .client import LEVEL_NAMES, BdlClient, BdlError, NotFound
from .demo import GMINA, DemoSession
from .excel import write_xlsx
from .indicators import load_indicators
from .render import fmt, write_html

_UNIT_ID = re.compile(r"^\d{12}$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bdl-report",
        description="Raport z danych GUS (Bank Danych Lokalnych) dla gminy, powiatu "
        "albo województwa.",
    )
    parser.add_argument("--demo", action="store_true", help="dane fikcyjne, bez internetu")
    parser.add_argument("--cache", default=".bdl_cache.sqlite", help="plik pamięci podręcznej")
    sub = parser.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("szukaj", help="znajdź jednostkę i jej id")
    s.add_argument("nazwa")

    r = sub.add_parser("raport", help="zrób raport HTML i Excel")
    r.add_argument("jednostka", help="nazwa (np. Sopot) albo 12-cyfrowe id z polecenia szukaj")
    this_year = date.today().year
    r.add_argument("--od", type=int, default=this_year - 11, help="pierwszy rok")
    r.add_argument("--do", type=int, default=this_year - 1, help="ostatni rok")
    r.add_argument("--zmienne", help="plik JSON z własnym zestawem wskaźników")
    r.add_argument("-o", "--folder", default="raporty", help="folder na raporty")

    z = sub.add_parser("zmienne", help="szukaj zmiennych BDL albo sprawdź domyślne")
    z.add_argument("fraza", nargs="?", help="np. bezrobocie, wynagrodzenie, mieszkania")
    z.add_argument("--sprawdz", action="store_true", help="pokaż oficjalne nazwy domyślnych")
    z.add_argument(
        "--poziom",
        choices=["powiat", "gmina"],
        help="tylko zmienne publikowane co najmniej do tego poziomu",
    )
    z.add_argument("--wszystkie", action="store_true", help="pokaż też wskaźniki precyzji")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.demo:
        client = BdlClient(session=DemoSession(), min_interval=0)
    else:
        client = BdlClient(api_key=os.environ.get("GUS_API_KEY"), cache=ResponseCache(args.cache))
    try:
        return {"szukaj": _search, "raport": _report, "zmienne": _variables}[args.cmd](client, args)
    except BdlError as exc:
        print(f"BŁĄD: {exc}", file=sys.stderr)
        return 1


def _search(client: BdlClient, args) -> int:
    units = client.search_units(args.nazwa)
    if not units:
        print(f"Nic nie znalazłem dla {args.nazwa!r}.")
        return 1
    for u in units:
        print(f"{u.id}  {u.name}  ({u.level_name})")
    return 0


def _report(client: BdlClient, args) -> int:
    if args.od > args.do:
        print("Rok --od musi być wcześniejszy niż --do.", file=sys.stderr)
        return 2
    unit_id = args.jednostka
    if args.demo and not _UNIT_ID.match(unit_id):
        unit_id = GMINA
    elif not _UNIT_ID.match(unit_id):
        units = client.search_units(unit_id)
        exact = [u for u in units if u.name.lower() == unit_id.lower()] or units
        if len(exact) != 1:
            print(f"{args.jednostka!r} pasuje do {len(units)} jednostek, podaj id:")
            for u in units:
                print(f"  {u.id}  {u.name}  ({u.level_name})")
            return 2
        unit_id = exact[0].id

    years = list(range(args.od, args.do + 1))
    report = build(client, unit_id, load_indicators(args.zmienne), years)

    folder = Path(args.folder)
    folder.mkdir(parents=True, exist_ok=True)
    slug = _slug(report.unit.name)
    html_path, xlsx_path = folder / f"{slug}.html", folder / f"{slug}.xlsx"
    write_html(report, html_path)
    write_xlsx(report, xlsx_path)

    print(f"{report.unit.name} ({report.unit.level_name}), lata {years[0]}–{years[-1]}")
    for s in report.series:
        latest = s.latest
        state = f"{fmt(latest[1])} ({latest[0]})" if latest else "brak danych"
        extra = f", dane: {s.source.name}" if s.source else ""
        print(f"  {s.indicator.label}: {state}{extra}")
    print(f"Zapytań do API: {client.requests_sent}")
    print(f"Raport: {html_path.resolve()}\nExcel:  {xlsx_path.resolve()}")
    return 0


def _slug(name: str) -> str:
    """ASCII file name, so it also works in .bat files and old Windows consoles."""
    ascii_name = (
        unicodedata.normalize("NFKD", name.replace("ł", "l").replace("Ł", "L"))
        .encode("ascii", "ignore")
        .decode()
    )
    return re.sub(r"[^A-Za-z0-9]+", "_", ascii_name).strip("_").lower()


def _variables(client: BdlClient, args) -> int:
    if args.sprawdz or not args.fraza:
        ok = True
        for ind in load_indicators(None):
            try:
                v = client.variable(ind.id)
            except NotFound:
                print(f"{ind.id:>7}  {ind.label:<36} BRAK TAKIEJ ZMIENNEJ W BDL")
                ok = False
                continue
            print(f"{ind.id:>7}  {ind.label:<36} GUS: {v.full_name} [{v.unit}]{_level(v)}")
        return 0 if ok else 1
    found = client.search_variables(args.fraza)
    if not args.wszystkie:  # BAEL error margins, rarely what anyone wants
        found = [v for v in found if "wskaźnik precyzji" not in v.full_name]
    if args.poziom:
        min_level = {"powiat": 5, "gmina": 6}[args.poziom]
        found = [v for v in found if v.level is not None and v.level >= min_level]
    for v in found[:50]:
        print(f"{v.id:>7}  {v.full_name} [{v.unit}]{_level(v)}")
    if len(found) > 50:
        print(f"... i {len(found) - 50} więcej, zawęź frazę")
    return 0 if found else 1


def _level(v) -> str:
    return f" (najniżej: {LEVEL_NAMES.get(v.level, v.level).lower()})" if v.level else ""


if __name__ == "__main__":
    sys.exit(main())
