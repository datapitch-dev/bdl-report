"""Turns ReportData into a self-contained HTML page (the Excel workbook is in excel.py)."""

from __future__ import annotations

import base64
import html
import io
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from .builder import ReportData, Series  # noqa: E402

_COLORS = ["#1f4e79", "#c9a227", "#8c8c8c"]  # unit, voivodeship, Poland


def fmt(value: float | None, decimals: int | None = None) -> str:
    if value is None:
        return "–"
    if decimals is None:
        decimals = 0 if abs(value) >= 1000 or float(value).is_integer() else 1
    text = f"{value:,.{decimals}f}".replace(",", " ").replace(".", ",")
    return text


def series_title(s: Series) -> str:
    return s.indicator.label


def series_note(s: Series) -> str:
    parts = []
    if s.variable:
        parts.append(
            f"GUS: {s.variable.full_name}" + (f" [{s.variable.unit}]" if s.variable.unit else "")
        )
    if s.source:
        parts.append(f"brak danych dla gminy, pokazano {s.source.name}")
    if s.break_note:
        parts.append(s.break_note)
    return "; ".join(parts)


def chart_png(s: Series, unit_name: str) -> bytes:
    fig, ax = plt.subplots(figsize=(7, 3.2), dpi=110)
    lines = [(s.source.name if s.source else unit_name, s.values), *s.comparisons.items()]
    for (name, values), color in zip(lines, _COLORS, strict=False):
        years = sorted(values)
        ax.plot(years, [values[y] for y in years], marker="o", ms=3, lw=2, color=color, label=name)
    ax.set_title(series_title(s), loc="left", fontsize=11, fontweight="bold")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: fmt(v)))
    ax.xaxis.get_major_locator().set_params(integer=True)
    ax.grid(axis="y", alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)
    if len(lines) > 1:
        ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def _change_class(s: Series) -> str:
    change, better = s.change_pct, s.indicator.higher_is_better
    if change is None or better is None or abs(change) < 0.05:
        return ""
    return "good" if (change > 0) == better else "bad"


def write_html(report: ReportData, path: str | Path) -> None:
    unit = report.unit
    where = ", ".join(u.name for u in report.ancestors)
    rows, charts = [], []
    for s in report.series:
        latest = s.latest
        change = s.change_pct
        span = f"{s.years[0]}–{s.years[-1]}" if len(s.years) > 1 else ""
        change_text = "–" if change is None else ("+" if change > 0 else "") + fmt(change, 1) + " %"
        title, note = html.escape(series_title(s)), html.escape(series_note(s))
        rows.append(
            "<tr>"
            f"<td>{title}<div class='note'>{note}</div></td>"
            f"<td class='num'>{fmt(latest[1]) if latest else '–'}</td>"
            f"<td class='num'>{latest[0] if latest else ''}</td>"
            f"<td class='num {_change_class(s)}'>"
            f"{change_text}"
            f"<div class='note'>{span}</div></td>"
            "</tr>"
        )
        if s.values:
            img = base64.b64encode(chart_png(s, unit.name)).decode()
            charts.append(
                f"<figure><img alt='{html.escape(series_title(s))}' "
                f"src='data:image/png;base64,{img}'></figure>"
            )
        else:
            charts.append(
                f"<p class='note'>{html.escape(series_title(s))}: brak danych w BDL dla tej "
                "jednostki i wybranych lat.</p>"
            )

    page = f"""<!doctype html>
<html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(unit.name)}: raport GUS</title>
<style>
 :root {{ --ink:#1b2430; --muted:#6b7280; --line:#e5e7eb; --accent:#1f4e79; --gold:#c9a227; }}
 body {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif; color: var(--ink);
        background:#fff; max-width: 860px; margin: 0 auto; padding: 24px 16px 48px; }}
 h1 {{ margin: 0; font-size: 28px; }}
 .sub {{ color: var(--muted); margin: 4px 0 24px; }}
 table {{ width: 100%; border-collapse: collapse; margin-bottom: 28px; }}
 th, td {{ text-align: left; padding: 10px 8px; border-bottom: 1px solid var(--line);
           vertical-align: top; }}
 th {{ font-size: 13px; color: var(--muted); font-weight: 600; }}
 .num {{ text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }}
 .note {{ color: var(--muted); font-size: 12px; margin-top: 2px; }}
 .good {{ color: #15803d; }} .bad {{ color: #b91c1c; }}
 figure {{ margin: 0 0 18px; }} img {{ max-width: 100%; height: auto; }}
 footer {{ color: var(--muted); font-size: 12px; border-top: 3px solid var(--gold);
           padding-top: 10px; margin-top: 32px; }}
</style></head><body>
<h1>{html.escape(unit.name)}</h1>
<p class="sub">{html.escape(unit.level_name)}{(" · " + html.escape(where)) if where else ""}
 · lata {report.years[0]}–{report.years[-1]}</p>
<table><thead><tr><th>Wskaźnik</th><th class="num">Ostatnia wartość</th><th class="num">Rok</th>
<th class="num">Zmiana</th></tr></thead><tbody>
{"".join(rows)}
</tbody></table>
{"".join(charts)}
<footer>Źródło: Bank Danych Lokalnych GUS (bdl.stat.gov.pl), jednostka {html.escape(unit.id)}.
Wygenerowano {date.today().isoformat()} narzędziem bdl-report.</footer>
</body></html>
"""
    Path(path).write_text(page, encoding="utf-8")
