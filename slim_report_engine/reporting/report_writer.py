"""Writes ReportSection/ReportRow content into a real Excel worksheet
using openpyxl — ported from clsReportWriter.cls + modReportStyles.bas,
then corrected against the REAL templates' actual cell formatting
(Report Creator Template.xlsx, SX5-N/S Report Template.xlsx, Wafers
Report Template.xlsx), since modReportStyles.bas's 5-case vocabulary
turned out to be a simplification, not a precise match — e.g. it marks
column-header text bold, but the real templates never bold it; it has
no fill at all, but the real templates use a consistent 3-color palette
that this module now reproduces.

FIDELITY POLICY (per explicit direction, 2026-09-03): borders are
critical and applied unconditionally per row-type, matching the real
template's border presence/absence exactly. Font/color/fill are applied
precisely for every cell that carries real template text (labels,
headers, titles); cells that are blank in every real template (waiting
for a technician to fill in results by hand) are left at default
formatting even where the real template has an incidental/leftover
font or fill on them (e.g. a blank formula cell's leftover bold
AvantGarde font) — that's exactly the kind of "probably not important"
formatting explicitly called out as not worth chasing.

REAL COLOR PALETTE (confirmed identical across all three templates via
openpyxl, resolving indexed colors against the legacy palette):
  white   (idx 9,  00FFFFFF) -- "Specification"/category-label cells
  pale cyan (idx 41, 00CCFFFF) -- the "Sample Identification:"/"Sample #:" row
  light blue (idx 44, 0099CCFF) -- Results/Recovery/MDL/STDEV/QL column headers

LAYER: Writer — the only module in this package allowed to import
openpyxl's Worksheet type or touch cell formatting. Everything upstream
(entities, presets, section builders, orchestrators) stays pure
computation, independently testable without ever opening a workbook.
"""

from __future__ import annotations

import re
from copy import copy

from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from slim_report_engine.reporting.report_row import ReportRow
from slim_report_engine.reporting.report_section import ReportSection

_THIN_BOX_BORDER = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"), bottom=Side(style="thin"),
)
# Confirmed real (Report Creator Template.xlsx, every "Sample Identification:"
# row checked, Wide AND Simple shapes both): NO border between the label
# cell (column 2) and the cell immediately to its right (column 3) -- top/
# bottom/outer-left (or outer-right) stay thin, only the shared edge is
# omitted, on BOTH sides of it.
_THIN_BOX_BORDER_NO_RIGHT = Border(
    left=Side(style="thin"), top=Side(style="thin"), bottom=Side(style="thin"),
)
_THIN_BOX_BORDER_NO_LEFT = Border(
    right=Side(style="thin"), top=Side(style="thin"), bottom=Side(style="thin"),
)

# Real palette, confirmed via openpyxl against all three real templates
# (see module docstring). Written as opaque ARGB for PatternFill.
_FILL_WHITE = PatternFill(fill_type="solid", fgColor="FFFFFFFF")
_FILL_PALE_CYAN = PatternFill(fill_type="solid", fgColor="FFCCFFFF")
_FILL_LIGHT_BLUE = PatternFill(fill_type="solid", fgColor="FF99CCFF")

# Real fonts, confirmed via openpyxl. The real templates use Arial
# throughout content cells (a leftover Calibri/AvantGarde shows up only
# on cells that are blank in every real template -- not reproduced, see
# FIDELITY POLICY above).
_FONT_SPEC_LABEL = Font(name="Arial", size=8, bold=True)  # "Specification" / SX5 QC code / spec values
_FONT_SAMPLE_ECHO_LABEL = Font(name="Arial", size=9)  # "Sample Identification:" / "Sample #:"
_FONT_SAMPLE_ID_VALUE = Font(name="Arial", size=12, bold=True)  # the sample-ID string cell -- confirmed real size 12
_FONT_COLUMN_HEADER = Font(name="Arial", size=10)  # category label + Results/Recovery/MDL -- NOT bold, confirmed real
_FONT_HEADER_SPEC_LABEL = Font(name="AvantGarde", size=8, bold=True)  # SX5's header-row "Specification" text specifically
_FONT_DATA = Font(name="Arial", size=10)  # analyte name/symbol
_FONT_TITLE = Font(name="Arial", size=12, bold=True)  # SX5 title row
_FONT_NORMAL_BOLD = Font(name="Arial", size=10, bold=True)  # "NormalBold" style, and ColumnHeaderAssay's non-label columns
_FONT_ASSAY_HEADER_COL1 = Font(name="Arial", size=9, bold=True)  # ColumnHeaderAssay's column-1 label specifically
# Confirmed real need (2026-09-25, direct user correction): an element row
# using ICPMS-KEDS mode had no visible marker tying it back to the
# footer's "Note 1: ICPMS-KEDS mode..." line -- the note existed, nothing
# on the actual affected rows referenced it. Bold red on the symbol cell.
_FONT_DATA_KED = Font(name="Arial", size=10, bold=True, color="FFFF0000")
# Confirmed real (Report Creator Template.xlsx row 5 -- legacy indexed
# color 12, resolves to opaque blue; Wafers Report Template.xlsx row 4 --
# already stored as this exact ARGB): the "Blue font indicates..." line
# itself is rendered in blue in every real template.
_BLUE = "FF0000FF"
_FONT_NORMAL_BOLD_BLUE = Font(name="Arial", size=10, bold=True, color=_BLUE)  # generic preamble's own line
_FONT_NORMAL_BLUE = Font(name="Arial", size=10, color=_BLUE)  # Wafer's equivalent line -- NOT bold

# Limits display to 3 decimals, as on every real report (legacy "0.000";
# SX5's "#,##0.000" looks the same at these magnitudes). A display format
# only -- the cell stays a number Excel can compare against results.
LIMIT_NUMBER_FORMAT = "0.000"

_ALIGN_CENTER = Alignment(horizontal="center")
# wrap_text=True added 2026-09-25 (direct user correction, confirmed
# across multiple real generated reports -- ACX, Customer 138): the "EXAMPLE LAB
# Results"/"EXAMPLE LAB Result" header text is wider than its own column and
# was overflowing into the neighboring cell instead of wrapping onto a
# second line, unlike the sample-ID echo cell (_ALIGN_CENTER_WRAP below),
# which already wraps correctly. Single shared cause across every report
# family using "ColumnHeader" -- one fix here covers all of them.
_ALIGN_CENTER_VCENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)  # ColumnHeader row specifically -- confirmed real
_ALIGN_CENTER_WRAP = Alignment(horizontal="center", wrap_text=True, vertical="center")  # the sample-ID echo VALUE cell specifically -- confirmed real (D6 in the real template)
_ALIGN_LEFT = Alignment(horizontal="left")
_ALIGN_LEFT_VCENTER = Alignment(horizontal="left", vertical="center")  # the "Sample Identification:"/"Sample #:" label cell specifically -- confirmed real
_ALIGN_RIGHT = Alignment(horizontal="right")
_ALIGN_JUSTIFY = Alignment(horizontal="justify", vertical="center")  # the "Specification" label cell -- confirmed real

# R1C1-relative formula shapes actually used anywhere in this codebase --
# Excel itself always stores formulas as A1 references internally
# regardless of whether they were entered via .Formula or .FormulaR1C1 in
# VBA, so this translation produces an equivalent, not an approximation.
#
# Same-column ranges (the metals panel's AVERAGE/TOTAL summary rows):
_R1C1_SAME_COLUMN_RANGE = re.compile(r"^=([A-Z]+)\(R\[(-?\d+)\]C:R\[(-?\d+)\]C\)$")
# Same-column, non-contiguous cell LISTS (Hardness's live formula --
# confirmed real, modReportCreator.bas Set_Hardness_Formula/
# Formula_To_Sum_Elements -- sums specific elements' rows, which are
# never a contiguous range within the panel):
_R1C1_SAME_COLUMN_LIST = re.compile(r"^=([A-Z]+)\(((?:R\[-?\d+\]C,)*R\[-?\d+\]C)\)$")
_R1C1_LIST_ITEM = re.compile(r"R\[(-?\d+)\]C")


def apply_style(ws: Worksheet, row_index: int, min_col: int, max_col: int, style_name: str) -> None:
    """Ported from modReportStyles.ApplyStyle, then corrected against the
    real templates' actual formatting (see module docstring). Add a case
    here only when a genuinely new visual treatment is needed -- don't
    format ad hoc at a call site.
    """
    if style_name == "Normal":
        return  # no borders, no fill, no bold -- default cell appearance

    if style_name == "SectionTitle":
        # SX5's chemical-label title row (e.g. "NH4OH", "CSLX001").
        for col in range(min_col, max_col + 1):
            ws.cell(row=row_index, column=col).font = _FONT_TITLE
        return

    if style_name == "NormalBold":
        # No border, no fill (matches "Normal"), but bold text -- Wafer's
        # "Notes:" and units-note rows specifically.
        for col in range(min_col, max_col + 1):
            ws.cell(row=row_index, column=col).font = _FONT_NORMAL_BOLD
        return

    if style_name == "NormalBoldRed":
        # No border, no fill (matches "Normal"), but bold red text --
        # confirmed real (2026-09-28, a real Folder 031 Z-report):
        # the KED-mode footer note ("Note 1: ICPMS-KEDS used for the
        # reduction of interferences") is itself bold red, same font as
        # the inline "Note 1" marker (ReportRow.set_note) it links to.
        for col in range(min_col, max_col + 1):
            ws.cell(row=row_index, column=col).font = _FONT_DATA_KED
        return

    if style_name == "NormalBoldBlue":
        # Same as "NormalBold", but blue -- confirmed real (Report Creator
        # Template.xlsx row 5): the generic preamble's own "Blue font
        # indicates..." line is itself rendered in blue, bold text.
        for col in range(min_col, max_col + 1):
            ws.cell(row=row_index, column=col).font = _FONT_NORMAL_BOLD_BLUE
        return

    if style_name == "NormalBlue":
        # Same as "Normal", but blue, NOT bold -- confirmed real (Wafers
        # Report Template.xlsx row 4): Wafer's own "Blue font indicates
        # data at or below the MDL" line is blue but NOT bold, unlike the
        # generic preamble's equivalent line.
        for col in range(min_col, max_col + 1):
            ws.cell(row=row_index, column=col).font = _FONT_NORMAL_BLUE
        return

    if style_name == "SampleIdEchoWide":
        # The "Sample Identification:"/QC-code row for shapes that HAVE a
        # column-1 label (metals/silicon/ion panels via add_header_rows,
        # SX5's QC-code row, Wafer's sample-ID row). Confirmed real: NO
        # border between columns 2 and 3 (the label sits in column 2;
        # column 3 is a separate, borderless-on-that-side spacer cell).
        for col in range(min_col, max_col + 1):
            cell = ws.cell(row=row_index, column=col)
            if col == 2:
                cell.border = _THIN_BOX_BORDER_NO_RIGHT
            elif col == 3:
                cell.border = _THIN_BOX_BORDER_NO_LEFT
            else:
                cell.border = _THIN_BOX_BORDER
            if col == 1:
                cell.font = _FONT_SPEC_LABEL
                cell.fill = _FILL_WHITE
                cell.alignment = _ALIGN_JUSTIFY
            elif col in (2, 3):
                cell.font = _FONT_SAMPLE_ECHO_LABEL
                cell.fill = _FILL_PALE_CYAN
                cell.alignment = _ALIGN_LEFT_VCENTER
            else:
                cell.font = _FONT_SAMPLE_ID_VALUE
                cell.fill = _FILL_PALE_CYAN
                cell.alignment = _ALIGN_CENTER_WRAP
        return

    if style_name == "SampleIdEchoSimple":
        # Same row, for shapes with NO column-1 label (TOC/Alkalinity/
        # Bacteria/Electrical/Misc Analysis via add_simple_header_row) --
        # confirmed real: column 1 has no border or fill at all here,
        # unlike the "Wide" variant; same no-border-between-2-and-3 rule.
        for col in range(min_col, max_col + 1):
            cell = ws.cell(row=row_index, column=col)
            if col == 1:
                continue
            if col == 2:
                cell.border = _THIN_BOX_BORDER_NO_RIGHT
            elif col == 3:
                cell.border = _THIN_BOX_BORDER_NO_LEFT
            else:
                cell.border = _THIN_BOX_BORDER
            if col in (2, 3):
                cell.font = _FONT_SAMPLE_ECHO_LABEL
                cell.fill = _FILL_PALE_CYAN
                cell.alignment = _ALIGN_LEFT_VCENTER
            else:
                cell.font = _FONT_SAMPLE_ID_VALUE
                cell.fill = _FILL_PALE_CYAN
                cell.alignment = _ALIGN_CENTER_WRAP
        return

    if style_name == "SampleIdEchoAssay":
        # SX5's Assay-shape "Sample #" row (CSLX001/WX-2000/WX-7808) --
        # confirmed real: shifted one column left of the Wide variant
        # (label in column 2, the stamp target in column 3, nothing in
        # column 1 or beyond column 3).
        for col in range(min_col, max_col + 1):
            cell = ws.cell(row=row_index, column=col)
            if col not in (2, 3):
                continue
            cell.border = _THIN_BOX_BORDER
            cell.fill = _FILL_PALE_CYAN
            cell.font = _FONT_SAMPLE_ECHO_LABEL
        return

    if style_name == "ColumnHeader":
        # The category-label + Results/Recovery/MDL (or STDEV/QL) row.
        # Confirmed real: NOT bold, despite the name inherited from
        # modReportStyles.bas's "HeaderBold". Column 1 is blank in generic
        # Chemical/Water/Wafer panels (font is applied but invisible) but
        # carries real "Specification" text in SX5 element panels -- same
        # AvantGarde/no-fill treatment either way, since it's correct when
        # populated and harmless when not. Confirmed real: every label on
        # this row is vertically centered.
        for col in range(min_col, max_col + 1):
            cell = ws.cell(row=row_index, column=col)
            cell.border = _THIN_BOX_BORDER
            cell.alignment = _ALIGN_CENTER_VCENTER
            if col == 1:
                cell.font = _FONT_HEADER_SPEC_LABEL
                continue
            cell.font = _FONT_COLUMN_HEADER
            cell.fill = _FILL_WHITE if col in (2, 3) else _FILL_LIGHT_BLUE
        return

    if style_name == "ColumnHeaderAssay":
        # SX5's Assay-shape header row ("Current Specifications"/
        # "Parameter"/result-label/"STDV") -- confirmed real: results
        # start one column earlier than the Wide shapes (column 3, not
        # 4), column 1/2 have NO fill at all (not white), and the
        # results columns ARE bold here (unlike the general ColumnHeader
        # case) -- a genuinely different treatment, not reusable.
        for col in range(min_col, max_col + 1):
            cell = ws.cell(row=row_index, column=col)
            cell.border = _THIN_BOX_BORDER
            cell.alignment = _ALIGN_CENTER
            if col == 1:
                cell.font = _FONT_ASSAY_HEADER_COL1
            elif col == 2:
                cell.font = _FONT_COLUMN_HEADER
            else:
                cell.font = _FONT_NORMAL_BOLD
                cell.fill = _FILL_LIGHT_BLUE
        return

    if style_name == "ColumnHeaderAssayPlain":
        # WX-2000's own variant of ColumnHeaderAssay -- confirmed real
        # (2026-09-29, a real SX5-South comprehensive TR): identical
        # layout/border/fill, but columns 3-4 ("EXAMPLE LAB Results"/"STDV")
        # are NOT bold here, unlike CSLX001/WX-7808's confirmed-real bold
        # header (see sx5_assay_section_builder.build_assay's
        # bold_results_header docstring).
        for col in range(min_col, max_col + 1):
            cell = ws.cell(row=row_index, column=col)
            cell.border = _THIN_BOX_BORDER
            cell.alignment = _ALIGN_CENTER
            if col == 1:
                cell.font = _FONT_ASSAY_HEADER_COL1
            else:
                cell.font = _FONT_COLUMN_HEADER
            if col > 2:
                cell.fill = _FILL_LIGHT_BLUE
        return

    if style_name == "DataLabel":
        for col in range(min_col, max_col + 1):
            cell = ws.cell(row=row_index, column=col)
            cell.border = _THIN_BOX_BORDER
            if col == 1:
                # Only SX5 element panels populate this (a per-element
                # spec threshold) -- styled whether or not this
                # particular row has one, so a populated spec value
                # elsewhere in the same column looks consistent.
                cell.font = _FONT_SPEC_LABEL
                cell.alignment = _ALIGN_CENTER
                cell.number_format = LIMIT_NUMBER_FORMAT
            else:
                cell.font = _FONT_DATA
                cell.alignment = _ALIGN_LEFT
        return

    if style_name == "DataValue":
        for col in range(min_col, max_col + 1):
            cell = ws.cell(row=row_index, column=col)
            cell.border = _THIN_BOX_BORDER
            cell.font = _FONT_DATA
            cell.alignment = _ALIGN_RIGHT
        return

    if style_name == "SummaryRow":
        # The metals panel's AVERAGE/TOTAL rows -- confirmed real: same
        # pale-cyan fill as the Sample-ID row, starting at column 2 (no
        # real template populates column 1 here).
        for col in range(min_col, max_col + 1):
            if col == 1:
                continue
            cell = ws.cell(row=row_index, column=col)
            cell.border = _THIN_BOX_BORDER
            cell.font = _FONT_DATA
            cell.fill = _FILL_PALE_CYAN
        return

    raise ValueError(
        f"unknown style name: {style_name!r} -- add a case for it in apply_style, "
        "don't format ad hoc at the call site."
    )


_FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@")


def _neutralize_formula_injection(value: object) -> object:
    """Guards against CSV/Excel formula injection (CWE-1236): a cell VALUE
    that starts with =/+/-/@ gets evaluated by Excel as a formula when the
    file is later opened, not just displayed as text. Not actively
    exploitable here today -- every currently-echoed free-text string
    (e.g. sample-ID strings) happens to be prefixed with a computed date
    first, so nothing reaching this function currently starts with a
    trigger character -- but that's incidental, not a deliberate control,
    and this system does write real customer/technician-typed text into
    cells. Standard mitigation (OWASP CSV-injection guidance): prefix
    with a single quote, so Excel stores/displays it as plain text
    instead of evaluating it -- applied here, once, at the single choke
    point every cell value passes through, rather than trusting every
    future call site to remember it individually.
    """
    if isinstance(value, str) and value.startswith(_FORMULA_TRIGGER_CHARS):
        return "'" + value
    return value


def _apply_superscript_runs(
    ws: Worksheet, row_index: int, col_index: int, runs: tuple[tuple[str, bool], ...]
) -> None:
    """Rewrites this cell's plain string value (already written by
    write_row's main loop) as real superscript rich text -- confirmed
    real (direct openpyxl inspection of a live production report,
    S:\\Reports\\Customer 110): the real cell is genuine Excel rich
    text, not a Unicode superscript character or a caret. Matches the
    cell's OWN already-applied font (set by apply_style just before this
    runs) for every run's base attributes, only adding vertAlign=
    "superscript" where a run calls for it -- so this works for whatever
    style the row actually used, not one hardcoded font.
    """
    cell = ws.cell(row=row_index, column=col_index)
    base_font = cell.font
    blocks: list[str | TextBlock] = []
    for text, is_superscript in runs:
        if not is_superscript:
            blocks.append(text)
            continue
        blocks.append(
            TextBlock(
                InlineFont(
                    rFont=base_font.name, sz=base_font.size, b=base_font.bold, i=base_font.italic,
                    vertAlign="superscript",
                ),
                text,
            )
        )
    cell.value = CellRichText(blocks)


# A sheet's limit columns: (limit kind, customer-requested header label or
# None), in column order -- e.g. (("specification", "Action Limit"),
# ("warning_limit", "Warning Limit")). Empty means the default single limit
# slot in column 1, unlabelled -- every sheet without limits on file.
LimitColumns = tuple[tuple[str, "str | None"], ...]
_DEFAULT_LIMIT_COLUMNS: LimitColumns = (("specification", None),)


def _slots(limit_columns: LimitColumns) -> int:
    return max(1, len(limit_columns))


def physical_column(col_index: int, limit_columns: LimitColumns = ()) -> int:
    """Where a row's logical column lands on the sheet. Column 1 is the
    limit slot and stays put (titles, notes and the preamble live there
    too); with N limit columns, everything from column 2 on moves right by
    N - 1 -- the same layout the legacy macro produced by inserting a
    column B for warning limits."""
    return col_index if col_index == 1 else col_index + _slots(limit_columns) - 1


def shift_cell_address(address: str, limit_columns: LimitColumns = ()) -> str:
    """A fixed cell address written after the sections (e.g. the "D1"
    processing-time stamp), moved the same way as row content."""
    letters = address.rstrip("0123456789")
    col = column_index_from_string(letters)
    return f"{get_column_letter(physical_column(col, limit_columns))}{address[len(letters):]}"


class _ShiftedSheet:
    """Lets apply_style keep addressing logical columns while writing to
    the physical ones."""

    def __init__(self, ws: Worksheet, limit_columns: LimitColumns) -> None:
        self._ws = ws
        self._limit_columns = limit_columns

    def cell(self, row: int, column: int):
        return self._ws.cell(row=row, column=physical_column(column, self._limit_columns))


def write_row(ws: Worksheet, row: ReportRow, row_index: int, limit_columns: LimitColumns = ()) -> None:
    def phys(col_index: int) -> int:
        return physical_column(col_index, limit_columns)

    for col_index, value in row.values.items():
        ws.cell(row=row_index, column=phys(col_index)).value = _neutralize_formula_injection(value)

    # Sparse formula overrides: translated from R1C1-relative text to a
    # real A1 range using the row this row actually landed on, so the
    # offsets resolve correctly regardless of where the section ended up
    # on the sheet.
    for col_index in row.formula_columns:
        formula = row.get_formula(col_index)
        col_letter = get_column_letter(phys(col_index))

        range_match = _R1C1_SAME_COLUMN_RANGE.match(formula)
        if range_match is not None:
            func, offset_first, offset_last = range_match.group(1), int(range_match.group(2)), int(range_match.group(3))
            first_row, last_row = row_index + offset_first, row_index + offset_last
            ws.cell(row=row_index, column=phys(col_index)).value = f"={func}({col_letter}{first_row}:{col_letter}{last_row})"
            continue

        list_match = _R1C1_SAME_COLUMN_LIST.match(formula)
        if list_match is not None:
            func = list_match.group(1)
            offsets = (int(m.group(1)) for m in _R1C1_LIST_ITEM.finditer(list_match.group(2)))
            cell_refs = ",".join(f"{col_letter}{row_index + offset}" for offset in offsets)
            ws.cell(row=row_index, column=phys(col_index)).value = f"={func}({cell_refs})"
            continue

        raise ValueError(
            f"formula {formula!r} doesn't match either supported R1C1 shape "
            "(=FUNC(R[a]C:R[b]C) or =FUNC(R[a]C,R[b]C,...)) -- extend the translator "
            "in report_writer.py before using a new formula shape."
        )

    apply_style(_ShiftedSheet(ws, limit_columns), row_index, min_col=1, max_col=row.max_columns, style_name=row.style_name)
    # Extra limit columns take column 1's formatting, as an inserted Excel
    # column takes the formatting of the column to its left.
    source = ws.cell(row=row_index, column=1)
    for extra in range(2, _slots(limit_columns) + 1):
        target = ws.cell(row=row_index, column=extra)
        target.font, target.fill = copy(source.font), copy(source.fill)
        target.border, target.alignment = copy(source.border), copy(source.alignment)

    # Limits by kind, each in its own limit column; on a panel's header row,
    # each limit column's customer-requested label.
    columns = limit_columns or _DEFAULT_LIMIT_COLUMNS
    for position, (kind, label) in enumerate(columns, start=1):
        if kind in row.limits:
            cell = ws.cell(row=row_index, column=position)
            cell.value = row.limits[kind]
            cell.number_format = LIMIT_NUMBER_FORMAT
        if row.is_limit_header and label:
            ws.cell(row=row_index, column=position).value = label

    for col_index in row.blank_columns:
        cell = ws.cell(row=row_index, column=phys(col_index))
        cell.border = Border()
        cell.fill = PatternFill(fill_type=None)
        cell.font = Font()

    # After apply_style, so the base font to match (Arial/size/bold) is
    # whatever this row's own style already put there -- not hardcoded to
    # one specific style, so this works for any future row that needs it.
    for col_index, runs in row.superscript_runs.items():
        _apply_superscript_runs(ws, row_index, phys(col_index), runs)

    # After apply_style, since a note marker (e.g. the KED "Note 1" flag)
    # lives outside the row's own bordered/filled shape -- see
    # ReportRow.set_note.
    for col_index, text in row.notes.items():
        cell = ws.cell(row=row_index, column=phys(col_index))
        cell.value = text
        cell.font = _FONT_DATA_KED
        cell.border = Border()
        cell.fill = PatternFill(fill_type=None)

    if row.row_height is not None:
        ws.row_dimensions[row_index].height = row.row_height

    for start_col, end_col in row.merges:
        ws.merge_cells(
            start_row=row_index, start_column=phys(start_col), end_row=row_index, end_column=phys(end_col)
        )


def apply_zoom(ws: Worksheet, zoom: int) -> None:
    """Confirmed real (openpyxl against every real template): the generic
    Chemical/Water and SX5 templates are all zoomed to 90%; Wafer is the
    one exception, at 95% -- see OutputSheet.zoom (submission_report_builder.py).
    """
    ws.sheet_view.zoomScale = zoom


_PROCESSING_TIME_STAMP_COLORS = {"red": "FFFF0000", "blue": _BLUE}


def apply_processing_time_stamp(ws: Worksheet, cell_address: str, text: str, color: str, size: int) -> None:
    """Confirmed real (every completed report checked with a rush/time-
    limited sample -- generic Chemical/Water, SX5, and Wafer all showed
    it): a single-cell stamp on row 1, alongside the title (which already
    carries a different, row-wide style) -- bold, RED for the RUSH
    variants ("Same Day RUSH", "Call-in RUSH", Wafer's own "Next Day
    RUSH"), BLUE for "Next Day Time Limited". A plain "Next Day"/"Two
    Days"/"Three Days" sample has no stamp at all -- see
    submission_report_builder.py's _processing_time_stamp, which decides
    whether to call this at all.

    size: 10 for generic Chemical/Water and SX5, 12 for Wafer (matches its
    bigger title-row font throughout).
    """
    cell = ws[cell_address]
    cell.value = text
    cell.font = Font(name="Arial", size=size, bold=True, color=_PROCESSING_TIME_STAMP_COLORS[color])


def apply_plain_cell_stamp(ws: Worksheet, cell_address: str, value: str) -> None:
    """SX5's own sample-ID stamp cell (OutputSheet.extra_cell_stamps) --
    confirmed real gap (2026-09-29, this pair's FIRST-EVER golden-diff
    run against real legacy SX5 output): the cell's underlying row was
    already written with SampleIdEchoWide's own per-column styling
    (bold _FONT_SAMPLE_ID_VALUE for column 4 -- see
    sx5_element_panel_builder.py's QC row, which deliberately leaves that
    exact cell's VALUE blank for this external stamp, but doesn't know to
    leave its FONT unstyled too). The mirror image of apply_title_cell's
    own fix above (that one needed a font ADDED; this one needs the
    pre-existing bold REMOVED) -- same root cause: a cell stamped directly
    onto the worksheet after section content is written doesn't
    automatically end up styled the way the rest of that row's own
    ReportRow/apply_style path would have produced. Real legacy output
    confirmed plain (not bold) for this exact text -- matches
    OutputSheet.extra_cell_stamps' own docstring, which already promised
    "plain unstyled values" without actually enforcing it until now.
    """
    cell = ws[cell_address]
    cell.value = value
    cell.font = _FONT_DATA


def apply_title_cell(ws: Worksheet, cell_address: str, text: str) -> None:
    """Wafer's own A1 sheet title (e.g. "200mm Wafers") -- confirmed real
    gap (2026-09-25, direct user correction, Cust082): this cell was being
    written as a bare value with no font at all, unlike every other
    report family's title, which rides through a real "SectionTitle"
    ReportRow and gets bold Arial 12 (_FONT_TITLE) applied automatically.
    Wafer's title has no ReportRow of its own -- it's stamped directly
    onto the worksheet after section content is written (see
    OutputSheet.title_cell_stamp) -- so it needs the same font applied
    explicitly here instead.
    """
    cell = ws[cell_address]
    cell.value = text
    cell.font = _FONT_TITLE


def apply_column_widths(ws: Worksheet, widths: dict[int, float], limit_columns: LimitColumns = ()) -> None:
    """widths: logical column index (1-based) -> width in points, e.g.
    column_widths.STANDARD. Applied once per sheet by the caller that knows
    which report family produced it (see submission_report_builder.py).
    Each extra limit column takes column 1's width.
    """
    for col_index, width in widths.items():
        ws.column_dimensions[get_column_letter(physical_column(col_index, limit_columns))].width = width
    if 1 in widths:
        for extra in range(2, _slots(limit_columns) + 1):
            ws.column_dimensions[get_column_letter(extra)].width = widths[1]


def write_section(
    ws: Worksheet, section: ReportSection, start_row: int = 1, limit_columns: LimitColumns = ()
) -> int:
    """Writes one section starting at start_row; returns the row
    immediately after the last row written, so callers can chain sections
    back to back."""
    row_index = start_row
    for row in section.rows:
        write_row(ws, row, row_index, limit_columns)
        row_index += 1
    return row_index


def write_sections(
    ws: Worksheet, sections: list[ReportSection], start_row: int = 1, limit_columns: LimitColumns = ()
) -> int:
    """limit_columns: the sheet's limit columns (see LimitColumns) --
    decides where each row's limits land and how far content shifts."""
    current_row = start_row
    for section in sections:
        current_row = write_section(ws, section, current_row, limit_columns)
    return current_row


def _escape_header_text(text: str) -> str:
    """Excel header/footer text treats "&" as the start of a formatting
    code ("&B" bold, "&F" filename, ...), and openpyxl writes the text
    as-is -- so real customer and chemical names containing "&" (several
    exist in the live database) would render garbled. "&&" is Excel's escape for a literal ampersand. Only for
    data text; the footer's own deliberate "&F"/"&P" codes must not go
    through this."""
    return text.replace("&", "&&")


def apply_header_footer(
    ws: Worksheet,
    center_header: str,
    customer_name: str,
    customer_address_line1: str,
    customer_address_line2: str,
    lab_header_lines: tuple[str, ...] = (),
) -> None:
    """Ported from modReportCreator.bas's AddHeaderAndFooter. lab_header_lines:
    the lab's own name/address/phone block for the left header -- deliberately
    a caller-supplied parameter, not hardcoded, since that's real company
    identity this public repo doesn't carry (see DOMAIN_BRIEF.md's
    de-branding note); the internal/private fork supplies the real values.
    """
    # Confirmed real openpyxl quirk: assigning an explicit empty string to
    # a header/footer part corrupts the OTHER parts on save/reload (the
    # empty part's "&L"/"&C"/"&R" control code leaks into a neighboring
    # part's text instead of being omitted) -- only assign when there's
    # actual content, leave the attribute unset (its default) otherwise.
    if lab_header_lines:
        ws.oddHeader.left.text = _escape_header_text("\n".join(lab_header_lines))
    ws.oddHeader.center.text = _escape_header_text(center_header)
    ws.oddHeader.right.text = _escape_header_text(
        f"{customer_name}\n{customer_address_line1}\n{customer_address_line2}\n"
    )
    ws.oddFooter.center.text = "&F"
    ws.oddFooter.right.text = "Page &P"
    ws.page_margins.top = 0.99
