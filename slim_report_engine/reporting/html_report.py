"""The report as HTML, filled with results (the portfolio's report page; the Excel path is untouched).

The same sheets and sections the Excel writer lays out are rendered as plain HTML tables: one
section per sheet (a sheet per sample), the lab's header block on top. Every value is escaped, and
the markup carries classes only -- no inline styles or scripts -- so a host can show it under a
strict Content-Security-Policy and style it with its own stylesheet.

Results come from the caller as data, never from a database: per sheet, a mapping from
(section id, analyte symbol) to a ResultCell. A section's id is the analysis name ("36 Elements",
"5 Anions", "Assay"), and an analyte row is found by its symbol (column 3). A section with a single
data row (an assay: its only row is labelled with the unit) takes whichever result is given for the
section. Cells go under the column headers the template already has: Results / Result, Recovery,
and MDL or QL; a column the template doesn't have (an assay's STDEV) stays blank.

The output is deterministic -- no timestamps -- so its hash identifies what was issued.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html import escape

from slim_report_engine.lab_identity import LAB_HEADER_LINES
from slim_report_engine.reporting.report_row import ReportRow


@dataclass(frozen=True)
class ResultCell:
    text: str  # as the report prints it: "10.100", "< 0.050"
    mdl: str = ""
    ql: str = ""
    recovery: str = ""
    below_mdl: bool = False  # the template prints these in blue


SheetResults = Mapping[tuple[str, str], ResultCell]

_RESULT_LABELS = ("result", "results")
_DATA_STYLE = "DataLabel"
_HEADER_STYLE = "ColumnHeader"


def _css_name(style: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in style)


def _columns(header: ReportRow | None) -> dict[str, int]:
    """Which column holds what, read from the section's own header row."""
    found: dict[str, int] = {}
    if header is None:
        return found
    for col, value in header.values.items():
        label = str(value).strip().lower()
        words = label.split()
        if words and words[-1] in _RESULT_LABELS:  # "EXAMPLE LAB Results"
            found["result"] = col
        elif label == "recovery":
            found["recovery"] = col
        elif label in ("mdl", "ql"):
            found[label] = col
    return found


def _filled(section, results: SheetResults) -> dict[int, tuple[dict[int, str], bool]]:
    """Row index -> (column -> text, below MDL) for every data row that has a result."""
    rows = section.rows
    header = next((r for r in rows if r.style_name == _HEADER_STYLE), None)
    columns = _columns(header)
    data_rows = [i for i, r in enumerate(rows) if r.style_name == _DATA_STYLE]
    mine = {symbol: cell for (section_id, symbol), cell in results.items() if section_id == section.id}
    out = {}
    for i in data_rows:
        symbol = str(rows[i].get_value(3) or "").strip()
        cell = mine.get(symbol)
        if cell is None and len(data_rows) == 1 and len(mine) == 1:
            cell = next(iter(mine.values()))  # a single-parameter section (an assay)
        if cell is None:
            continue
        values = {}
        for key, text in (("result", cell.text), ("recovery", cell.recovery), ("mdl", cell.mdl), ("ql", cell.ql)):
            if key in columns and text:
                values[columns[key]] = text
        out[i] = (values, cell.below_mdl)
    return out


def _row_html(row: ReportRow, width: int, filled: tuple[dict[int, str], bool] | None) -> str:
    values = {col: str(v) for col, v in row.values.items() if v not in (None, "")}
    if row.limits and 1 not in values:
        values[1] = " / ".join(f"{v:g}" if isinstance(v, float) else str(v) for v in row.limits.values())
    for col, text in row.notes.items():
        values[col] = text
    below = False
    if filled:
        values.update(filled[0])
        below = filled[1]
    merges = {start: end for start, end in row.merges}
    cells, col = [], 1
    while col <= width:
        end = merges.get(col, col)
        span = f' colspan="{end - col + 1}"' if end > col else ""
        classes = [f"c{col}"]
        if filled and col in filled[0]:
            classes.append("value")
            if below:
                classes.append("below-mdl")
        cells.append(f'<td class="{" ".join(classes)}"{span}>{escape(values.get(col, ""))}</td>')
        col = end + 1
    return f'<tr class="r-{_css_name(row.style_name)}">{"".join(cells)}</tr>'


def render_html(sheets: Sequence, results: Sequence[SheetResults] | None = None, title: str = "") -> str:
    """The report as one HTML fragment. `results[i]` fills `sheets[i]` (a sheet per sample)."""
    results = list(results or [])
    parts = ['<div class="slim-report">', '<header class="slim-report__lab">']
    parts += [f"<p>{escape(line)}</p>" for line in LAB_HEADER_LINES]
    parts.append("</header>")
    if title:
        parts.append(f'<h1 class="slim-report__title">{escape(title)}</h1>')
    if len(sheets) > 1:
        parts.append('<nav class="slim-report__tabs" aria-label="Samples">')
        parts += [f'<a href="#sheet-{i + 1}">{escape(sheet.name)}</a>' for i, sheet in enumerate(sheets)]
        parts.append("</nav>")
    for i, sheet in enumerate(sheets):
        sheet_results = results[i] if i < len(results) else {}
        rows = [row for section in sheet.sections for row in section.rows]
        width = max([6, *(max(row.values, default=0) for row in rows), *(max(row.notes, default=0) for row in rows)])
        parts.append(f'<section class="slim-report__sheet" id="sheet-{i + 1}">')
        parts.append(f'<h2 class="slim-report__sheet-name">{escape(sheet.name)}</h2>')
        parts.append('<table class="slim-report__table"><tbody>')
        for section in sheet.sections:
            filled = _filled(section, sheet_results)
            for j, row in enumerate(section.rows):
                if not row.values and not row.notes and j not in filled:
                    continue  # spacer rows: the stylesheet spaces sections instead
                parts.append(_row_html(row, width, filled.get(j)))
        parts.append("</tbody></table></section>")
    parts.append("</div>")
    return "\n".join(parts)
