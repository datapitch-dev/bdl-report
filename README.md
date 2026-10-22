# bdl-report

Raport statystyczny dla dowolnej gminy, powiatu lub województwa z **Banku Danych Lokalnych GUS**
(oficjalne, darmowe API `bdl.stat.gov.pl`). Jedno polecenie daje stronę HTML z wykresami
i plik Excel z danymi oraz gotowymi wykresami, z porównaniem do województwa i całej Polski.

```
$ bdl-report raport Sopot
Sopot (gmina miejska), lata 2015–2025
  Ludność ogółem: 31 205 (2025)
  Przeciętne wynagrodzenie brutto: 10 561 (2025), dane: Powiat m. Sopot
  …
Raport: raporty/sopot.html
Excel:  raporty/sopot.xlsx
```

Podgląd bez internetu: `bdl-report --demo raport Przykladowo` (fikcyjna gmina, zmyślone liczby).

## Po co to

Dane z BDL przydają się do wniosków o dotacje, strategii gmin, analiz lokalizacji sklepu czy
biura i raportów dla zarządu. Ręcznie oznacza to klikanie po kilku tabelach w BDL, eksport do
Excela, sklejanie lat i robienie wykresów. To narzędzie robi to w kilka sekund i zawsze tak samo.

## Co robi

- **Znajduje jednostkę po nazwie.** `bdl-report szukaj Gdynia` pokazuje wszystkie pasujące
  jednostki z ich 12-cyfrowym id. Gdy nazwa jest jednoznaczna, `raport` sam wybiera jednostkę.
- **Uzupełnia braki danymi powiatu.** Część wskaźników (np. wynagrodzenia)
  GUS publikuje tylko do poziomu powiatu. Wtedy raport pokazuje dane powiatu i wyraźnie to
  zaznacza, zamiast zostawiać pustą rubrykę.
- **Porównuje z województwem i Polską** tam, gdzie ma to sens (stopy, średnie), a nie przy
  liczbach bezwzględnych, takich jak liczba mieszkańców.
- **Podpisuje każdy wskaźnik oficjalną nazwą i jednostką z GUS**, pobraną z API, więc w
  raporcie zawsze widać, co dokładnie zostało policzone.
- **Szanuje limity API.** Bez klucza GUS pozwala na 5 zapytań na sekundę i 100 na 15 minut.
  Klient pilnuje odstępów, przy odpowiedzi 429 czeka tyle, ile każe serwer, a odpowiedzi trzyma
  tydzień w lokalnej bazie SQLite, więc kolejne raporty dla tego samego regionu nie zużywają
  limitu. Darmowy klucz z [api.stat.gov.pl](https://api.stat.gov.pl) podnosi limity
  pięciokrotnie: wystarczy ustawić zmienną `GUS_API_KEY`.
- **Excel gotowy do oddania.** Arkusz „Podsumowanie” z tabelą wskaźników, zmianą w okresie
  (na zielono lub czerwono, zależnie od tego, czy wzrost jest dobry), porównaniem z regionem
  i krajem oraz definicjami zmiennych GUS. Do tego osobny arkusz z danymi i natywnym wykresem
  Excela dla każdego wskaźnika. Prawdziwe formaty liczb, pasy wierszy, bez siatki, gotowe do
  druku na A4 z numerami stron.

## Instalacja i użycie

Wymaga Pythona 3.10+.

```bash
pip install -e .
bdl-report szukaj Gdynia                      # lista jednostek z id
bdl-report raport Sopot                       # raport dla ostatnich 11 lat
bdl-report raport <id z szukaj> --od 2010   # po id, od wybranego roku
bdl-report zmienne mieszkania --poziom gmina  # id wskaźników dostępnych dla gmin
bdl-report zmienne --sprawdz                  # oficjalne nazwy domyślnych wskaźników
bdl-report raport Sopot --zmienne moje.json   # własny zestaw wskaźników
```

Na Windowsie: dwuklik na `uruchom.bat` otwiera raport demo, a `uruchom.bat Sopot` w konsoli
robi raport dla Sopotu.

### Własny zestaw wskaźników

Plik JSON z listą wskaźników; id znajdziesz poleceniem `bdl-report zmienne <fraza>`:

```json
[
  {"id": 72305, "label": "Ludność ogółem"},
  {"id": 64428, "label": "Wynagrodzenie brutto", "compare": true, "higher_is_better": true}
]
```

`compare` dodaje do wykresu województwo i Polskę, a `higher_is_better` koloruje zmianę na
zielono lub czerwono.

## Budowa

```
src/bdl_report/
  client.py      klient API: paginacja, cache, odstępy między zapytaniami, ponawianie, 429
  cache.py       SQLite z odpowiedziami API
  indicators.py  domyślny zestaw wskaźników i wczytywanie własnego
  builder.py     zbiera dane: jednostka, powiat i województwo, braki z powiatu, porównania
  render.py      HTML z wykresami (matplotlib, obrazki wbudowane w plik)
  excel.py       sformatowany skoroszyt Excel z natywnymi wykresami (openpyxl)
  demo.py        udawane API z fikcyjną gminą, do demo i CI
  cli.py         wiersz poleceń
```

Testy działają bez sieci: klient dostaje podstawioną sesję HTTP, a czas i czekanie są
wstrzykiwane, więc testy limitów trwają milisekundy.

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## Zastrzeżenia

Dane pochodzą z Banku Danych Lokalnych GUS i są tak aktualne jak BDL. GUS publikuje większość
danych z opóźnieniem około roku, więc ostatni rok często jest pusty.

## Licencja

MIT
