"""Row-assembly primitives shared by every analyte-list section builder
(metals, ions, ...) — ported from modReportRowBuilders.bas. Pulled out to a
plain module so ion_list_section_builder can reuse this header/row/footer
shape without any element-service dependency it has no use for.

COLUMNS (1-based), matching the real template's layout:
  1=Specification  2=Label  3=Symbol  4=Result  5=Recovery  6=<third column label>
"""

from __future__ import annotations

from typing import Any

from slim_report_engine.lab_identity import RESULTS_LABEL
from slim_report_engine.reporting.report_row import ReportRow
from slim_report_engine.reporting.report_section import ReportSection

_DEFAULT_RESULT_LABEL = RESULTS_LABEL


def build_header_preamble(title: str, unit_override: str | None = None) -> ReportSection:
    """The sheet-wide preamble every generic Chemical/Water report starts
    with, before ANY section's own sample-ID echo row -- confirmed real
    (every real Chemical/Water report checked, both request types): title
    (its own row, column 1 only), one blank row, then 3 fixed lines --
    "Notes:", "All data in units of ppb unless otherwise noted", "Blue
    font indicates data at or below detection limits". Always exactly
    these 3 lines and this order for the generic path; NOT shared with
    SX5 (its own, different 4-row shape -- title/blank/blank/one combined
    notes row, no "Blue font" line) or Wafer (which already reproduces
    this same 5-row shape itself, with its own analysis-specific note
    text, in wafer_panel_builder.py).

    unit_override: substitutes "ppb" for this real unit text when the
    customer+chemical's own specs are on file in something other than
    ppb (see SpecificationService.get_unit_override) -- confirmed real
    (modReportCreator.bas's Get_Specs, direct VBA source check
    2026-09-28; matches a real completed report, Customer a359c's PG,
    "All data in units of ppm unless otherwise noted"). None (the
    default, every caller before 2026-09-28) keeps the standard ppb
    wording -- the overwhelming majority of real chemicals have no spec
    on file, or one that's already in ppb.

    Returned as its OWN ReportSection, deliberately excluded from the
    "stamp column 4 of every section's row 0 with the sample-ID string"
    loop (submission_report_builder.py) -- the title row carries no
    sample-ID echo, only the real sample-ID-echo row (in the first REAL
    section) does.
    """
    section = ReportSection("Header")

    title_row = ReportRow(style_name="SectionTitle")
    title_row.set_value(1, title)
    section.add_row(title_row)

    section.add_row(blank_row())

    notes_row = ReportRow(style_name="NormalBold")
    notes_row.set_value(1, "Notes:")
    section.add_row(notes_row)

    units_row = ReportRow(style_name="NormalBold")
    unit_text = unit_override if unit_override else "ppb"
    units_row.set_value(1, f"All data in units of {unit_text} unless otherwise noted")
    section.add_row(units_row)

    # Confirmed real (Report Creator Template.xlsx row 5): this line is
    # itself rendered in blue, bold text -- not the plain black "NormalBold"
    # every other preamble line uses.
    blue_font_row = ReportRow(style_name="NormalBoldBlue")
    blue_font_row.set_value(1, "Blue font indicates data at or below detection limits")
    section.add_row(blue_font_row)

    return section


def _simple_shape_max_columns(second_col_label: str = "", third_col_label: str = "") -> int:
    """The real column extent for a single/multi-parameter block (TOC/
    Alkalinity/Bacteria/Electrical/Misc Analysis/Titrations' Assay/KF/
    GC-FID/hand titrations) -- confirmed real gap (2026-09-25, direct
    user correction, Customer 55a6b's Assay/Density/pH sheet): the
    shared ReportRow default (DEFAULT_MAX_COLUMNS=6) was being used for
    the header row regardless of whether a shape has a real 2nd or 3rd
    results column, leaving a genuinely unlabeled but still blue-filled
    (ColumnHeader) or bordered (DataLabel) "extra" column past the real
    content -- the same bug class already fixed for Wafer's per-sample-
    count width. 6 only when a real third column exists (e.g. TOC's QL),
    5 when only a second column exists (e.g. Density/Assay/LPC's STDEV),
    4 for a bare single-result shape (e.g. Bacteria/KF/GC-FID/misc-
    analysis pH).
    """
    if third_col_label:
        return 6
    if second_col_label:
        return 5
    return 4


def add_header_rows(
    section: ReportSection,
    category_label: str,
    third_column_label: str,
    result_label: str = _DEFAULT_RESULT_LABEL,
    include_specification_label: bool = True,
) -> None:
    """result_label defaults to the plural form used by metals/ions. Silicon's
    real header uses the SINGULAR "Result" instead — a genuine inconsistency
    in the template itself, not an error here — so it passes result_label
    explicitly rather than this default being "corrected" to match it.

    include_specification_label: confirmed real (2026-09-28, dummy
    "test all analyses" TR run through the real legacy macro and
    diffed): the "Specification" column-1 label is an Elements/Silicon-
    panel-only thing -- ion panels (Anions/Cations/GBP) never have it,
    unlike this function's own prior assumption that every analyte-panel
    caller wanted it. Ion panels pass False.
    """
    top_row = ReportRow(style_name="SampleIdEchoWide", row_height=60.0)
    if include_specification_label:
        top_row.set_value(1, "Specification")
    top_row.set_value(2, "Sample Identification:")
    # Column 4 (sample-string echo) is filled in by the caller assembling
    # the whole sheet, not here -- a section builder only knows about ONE
    # section's own content, not the sample-level identity string that
    # every section on a sheet shares.
    # Real template merges D:F into the one echo-value cell (confirmed:
    # "Full Analysis (8)" template's D6:F6) -- declared here since it's a
    # structural property of the row's shape, independent of the value.
    top_row.add_merge(4, 6)
    section.add_row(top_row)

    header_row = ReportRow(style_name="ColumnHeader", row_height=25.5)
    # Every panel with a limit slot labels its limit column(s) with the
    # customer's own header text ("Action Limit", "Warning Limit"...) --
    # direct user decision 2026-10-01: on every such panel, not only the
    # first one as the legacy macro did (it wrote cell A7 only).
    header_row.is_limit_header = True
    header_row.set_value(2, category_label)
    header_row.set_value(4, result_label)
    header_row.set_value(5, "Recovery")
    header_row.set_value(6, third_column_label)
    section.add_row(header_row)


def add_analyte_row(
    section: ReportSection, name: str, symbol: str, max_columns: int | None = None,
    blank_columns: frozenset[int] = frozenset(),
) -> None:
    """max_columns: override the row's style-application width -- confirmed
    real (Wafers Report Template.xlsx): Wafer's own analyte rows border/fill
    all the way to column 19 (its MAX_SAMPLE_COLUMNS, matching its header
    rows), not the standard family's column 6 -- wafer_panel_builder.py
    passes it explicitly; every other caller leaves this at the default.
    blank_columns: see ReportRow -- Wafer's spacer column.
    """
    row = ReportRow(
        style_name="DataLabel", blank_columns=blank_columns, **({"max_columns": max_columns} if max_columns else {})
    )
    row.set_value(2, name)
    row.set_value(3, symbol)
    section.add_row(row)


def add_analyte_row_with_spec(
    section: ReportSection, name: str, symbol: str, spec_value: Any = None, is_ked: bool = False
) -> None:
    """Same shape as add_analyte_row, plus an optional column-1 spec
    threshold (SX5 element panels carry a per-element spec value there —
    omit spec_value entirely for an element with no spec for that chemical,
    matching the real template rather than writing a 0/blank placeholder).

    is_ked: this specific element needs ICPMS-KEDS mode (added 2026-09-25,
    direct user correction). CORRECTED 2026-09-28 (direct user correction,
    a real Folder 3978d Z-report): the visible link back to the
    footer's "Note 1: ..." line is a bold-red "Note 1" marker in column 7
    (just past the panel's own bordered box), NOT bold-red styling on the
    element's own symbol cell -- see ReportRow.set_note.
    """
    row = ReportRow(style_name="DataLabel")
    if spec_value is not None:
        row.set_value(1, spec_value)
    row.set_value(2, name)
    row.set_value(3, symbol)
    if is_ked:
        row.set_note(7, "Note 1")
    section.add_row(row)


def add_simple_header_row(
    section: ReportSection,
    category_label: str,
    result_label: str,
    second_col_label: str = "",
    third_col_label: str = "",
    header_col1_label: str = "",
) -> int:
    """Header shape for the single/multi-parameter blocks (Electrical
    Testing, Titrations, Misc Analysis's pH/Density/LPC/APHA) — differs from
    the metals/ions analyte-panel header: no "Specification" text in column
    1, second results column is labeled "STDEV" (or blank) rather than
    always "Recovery", and there is never a third results column
    (no MDL/QL).

    header_col1_label: confirmed real (S:\\Reports\\Customer d53ad's "Ag-Sn
    Plating"/"SnAg" reports): the Sn+2/Free Acid/TS-SLG hand-titration
    assays put a section title in column 1 of the HEADER row itself
    (e.g. "Determination of Sn+"), unlike KF/GC-FID which leave it blank
    — optional so those two are unaffected.

    Returns the real max_columns this shape needs (see
    _simple_shape_max_columns) -- callers thread this into their own
    add_analyte_row calls so data rows match the header's real width
    instead of defaulting to the shared 6-column default and bordering
    out past their own real content.
    """
    max_columns = _simple_shape_max_columns(second_col_label, third_col_label)

    top_row = ReportRow(style_name="SampleIdEchoSimple", row_height=60.0, max_columns=max_columns)
    top_row.set_value(2, "Sample Identification:")
    # Confirmed real gap (2026-09-28, direct user correction, ACX): this
    # row previously stayed hardcoded at the shared 6-column default with
    # an unconditional D:F merge regardless of how narrow the header row
    # right below it actually was -- for a genuinely 2-result-column
    # shape (max_columns=5), that left this row's own border/merge
    # extending one column further right (out to F) than the header row
    # stops (E), reading as a phantom extra column sitting right above a
    # narrower one. Real template's merge span on this echo cell varies
    # by exact block (D:E for some, D:F for others) -- matching THIS
    # shape's own real width here instead of always guessing D:F. No
    # merge at all when max_columns is 4 (a bare single-result-column
    # shape): there's only column D past the label, nothing to merge it
    # with.
    if max_columns > 4:
        top_row.add_merge(4, max_columns)
    section.add_row(top_row)

    header_row = ReportRow(style_name="ColumnHeader", row_height=25.5, max_columns=max_columns)
    if header_col1_label:
        header_row.set_value(1, header_col1_label)
    header_row.set_value(2, category_label)
    header_row.set_value(4, result_label)
    if second_col_label:
        header_row.set_value(5, second_col_label)
    if third_col_label:
        header_row.set_value(6, third_col_label)
    section.add_row(header_row)
    return max_columns


def add_note_row(section: ReportSection, text: str) -> None:
    """A single-column note/footnote row (e.g. "Dimensionless quantity", the
    Colloidal Silica calculation footnote) — like add_footer_row but without
    the "Date of Analysis: " echo, since these aren't the section's closing
    row.
    """
    row = ReportRow(style_name="Normal")
    row.set_value(1, text)
    section.add_row(row)


_KED_NOTE_TEXT = "Note 1: ICPMS-KEDS used for the reduction of interferences"


def add_footer_row(
    section: ReportSection,
    text: str,
    sop_codes: list[str] | None = None,
    date_of_analysis: str | None = None,
    ked_note: bool = False,
) -> None:
    """Confirmed real (every shape checked -- metals/ion panels, Assay,
    LPC): exactly one blank row separates the last content row from
    "Analysis by ...", and exactly one blank row separates it from
    whatever comes next (the next section's own sample-ID echo row, or
    the end of the sheet). The leading blank is skipped when the section
    already ends in one (e.g. the metals panel's own AVERAGE/TOTAL
    summary already adds its own trailing spacer) so sections never end
    up with two blank rows in a row.

    sop_codes: real ISO17025 SOP codes covering this section (see
    sop_codes.py) -- when given, a "Test Methods: ..." row is added
    directly under the footer text row, BEFORE the trailing blank --
    confirmed real (every real "Test Methods:" line found sits
    immediately under its own section's "Analysis by ..." footer, not
    after the blank spacer). None (the default) means no confirmed real
    evidence yet for this exact combination -- omit the line entirely
    rather than guess.

    ked_note: whether to add "Note 1: ICPMS-KEDS used for the reduction of
    interferences" as the LAST line before the trailing blank -- UNDER
    both the footer text row AND the Test Methods row when one is present
    (direct user correction, 2026-09-28: the original 2026-09-23 fix put
    it directly under the footer text and ABOVE Test Methods, based on
    the one real report checked at the time, which predated Test
    Methods' own real-evidence date and so never actually exercised this
    ordering against Test Methods -- corrected once a real report with
    both lines present made the true order checkable). This was
    previously dropped entirely during the port from VBA -- confirmed
    absent from this whole codebase via a full-text search -- not a
    conditional that just failed to fire. Text and style corrected
    2026-09-28 (direct user correction, checked against 60+ real Cust41a14
    Ventures Reports, not just the original one): the real text has no
    "mode" and no trailing period, and the line itself is bold red
    (style "NormalBoldRed"), not plain.

    date_of_analysis: pre-formatted "MM-DD-YY" text (see
    submission_report_builder._date_of_analysis_text) appended after the
    "Date of Analysis: " label -- confirmed real format (every real
    completed report checked uses this pattern, e.g. "08-27-26"; a few
    use a 4-digit year or a trailing period, but MM-DD-YY with none is
    the majority convention, same "pick one for consistency" call already
    made for Test Methods' trailing period). None (the default) leaves
    the label with nothing after it, for callers that haven't resolved a
    submission/sample context (e.g. section-builder unit tests).
    """
    if section.rows and section.rows[-1].values:
        section.add_row(blank_row())
    row = ReportRow(style_name="Normal")
    row.set_value(1, text)
    label = "Date of Analysis: " + date_of_analysis if date_of_analysis else "Date of Analysis: "
    row.set_value(4, label)
    section.add_row(row)
    if sop_codes:
        section.add_row(test_methods_row(sop_codes))
    if ked_note:
        note_row = ReportRow(style_name="NormalBoldRed")
        note_row.set_value(1, _KED_NOTE_TEXT)
        section.add_row(note_row)
    section.add_row(blank_row())


def test_methods_row(codes: list[str], max_columns: int | None = None) -> ReportRow:
    """Confirmed real format: "Test Methods: " + codes joined with ", "
    between all but the last pair and " and " before the last, always
    ending in a period. Real reports are inconsistent about the trailing
    period on a SINGLE-code line (some real reports omit it, no
    discernible rule -- see sop_codes.py) -- always included here for
    consistency. max_columns: see add_analyte_row -- Wafer passes its own
    wide override here too.
    """
    row = ReportRow(style_name="Normal", **({"max_columns": max_columns} if max_columns else {}))
    if len(codes) == 1:
        text = f"Test Methods: {codes[0]}."
    else:
        text = f"Test Methods: {', '.join(codes[:-1])} and {codes[-1]}."
    row.set_value(1, text)
    return row


def blank_row() -> ReportRow:
    return ReportRow(style_name="Normal")
