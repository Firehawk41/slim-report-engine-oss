"""Builds the "Current Specifications" Assay shape used by SX5's CSLX001,
WX-2000, and WX-7808 sheets — ported from clsSX5AssaySectionBuilder.cls.
Structurally different from the SX5 element-panel builder's 36-element
panel (no QC-code row, a single spec-range analyte row instead of 36
element rows, no "Data =< MDL"/"All data in ppb" notes).

Confirmed real differences between the 3 chemicals (both SX5-N and
SX5-S):
  - CSLX001 and WX-7808 share one exact shape: title, 2 blank rows,
    Sample# row, header (3rd col "% H2O2"), one data row ("Assay" as the
    parameter label). No footer, no extra note.
  - WX-2000 differs: an extra note row ("Bold Red Font: Indicates data
    outside specification limits") before the Sample# row, the header's
    3rd column is "EXAMPLE LAB Results" (not "% H2O2"), and the parameter label is
    "% H2O2" (not "Assay") with the unit text embedded directly in the
    spec-range string (e.g. "1.916 - 2.173   H2O2 % ", trailing space and
    all — reproduced verbatim).
  - The spec RANGE and even the parameter's numeric values differ by
    chemical AND by SX5-N vs SX5-S — always passed in by the caller, never
    hardcoded here.
"""

from __future__ import annotations

from slim_report_engine.reporting import row_builders
from slim_report_engine.reporting.report_row import ReportRow
from slim_report_engine.reporting.report_section import ReportSection


# The Assay table is four columns wide (spec, parameter, result, STDV) --
# confirmed real (legacy SX5 reports, 2026-10-02): nothing is boxed past D.
_ASSAY_COLUMNS = 4


def build_assay(
    id: str,
    chemical_label: str,
    spec_range: str,
    parameter_label: str,
    result_col_label: str = "% H2O2",
    note_text: str = "",
    bold_results_header: bool = True,
) -> ReportSection:
    """chemical_label: e.g. "CSLX001", "2to1WX2000", "WX7808" (becomes row
    1's title and the sheet tab name once written). spec_range: the
    literal spec-range text (e.g. "1.1 - 1.3"). parameter_label: e.g.
    "Assay" or "% H2O2". result_col_label: the header's 3rd column text
    ("% H2O2" for CSLX001/WX-7808, "EXAMPLE LAB Results" for WX-2000). note_text:
    WX-2000's extra "Bold Red Font..." row; omit for CSLX001/WX-7808, which
    have none. bold_results_header: confirmed real (2026-09-29): CSLX001/
    WX-7808's header columns 3-4 ("% H2O2"/"STDV") are bold, but WX-2000's
    ("EXAMPLE LAB Results"/"STDV") are plain -- a real per-chemical
    difference within this one shape, not a uniform rule.
    """
    section = ReportSection(id)

    title_row = ReportRow(style_name="SectionTitle", row_height=18.0)
    title_row.set_value(1, chemical_label)
    section.add_row(title_row)

    section.add_row(row_builders.blank_row())
    section.add_row(row_builders.blank_row())

    if note_text:
        # Confirmed real (legacy WX-2000 reports): the legend is bold red --
        # it shows what bold red font means.
        note_row = ReportRow(style_name="NormalBoldRed")
        note_row.set_value(1, note_text)
        section.add_row(note_row)

    # Confirmed real (CSLX001 template): no merge on this row -- the
    # Assay shape's Sample # value sits in a single unmerged cell.
    sample_row = ReportRow(style_name="SampleIdEchoAssay", row_height=37.5, max_columns=_ASSAY_COLUMNS)
    sample_row.set_value(2, "Sample #")
    # Column 3 (the sample-ID stamp) is intentionally left blank -- an
    # orchestration decision, same as sx5_element_panel_builder.
    section.add_row(sample_row)

    header_style = "ColumnHeaderAssay" if bold_results_header else "ColumnHeaderAssayPlain"
    header_row = ReportRow(style_name=header_style, row_height=24.75, max_columns=_ASSAY_COLUMNS)
    header_row.set_value(1, "Current Specifications")
    header_row.set_value(2, "Parameter")
    header_row.set_value(3, result_col_label)
    header_row.set_value(4, "STDV")
    section.add_row(header_row)

    data_row = ReportRow(style_name="DataLabel", row_height=20.25, max_columns=_ASSAY_COLUMNS)
    data_row.set_value(1, spec_range)
    data_row.set_value(2, parameter_label)
    section.add_row(data_row)

    return section


def build_embedded_assay(id: str, spec_range: str, note_text: str = "") -> ReportSection:
    """Confirmed real shape: the Assay block that follows the element+anion
    panel on SX5-N/SX5-S's "0.49%HF" and SX5-S's "2.5%HF-5%" sheets is
    structurally simpler than build_assay's standalone-sheet shape — no
    title, no note-before-Sample# row, no Sample# row at all (the sample ID
    is already established once by the element panel's own QC row on the
    same physical sheet). Just a header ("Current Specifications"/
    "Parameter"/"% HF"/"STDV") and one data row. note_text, when given,
    lands in column 5 of the DATA row itself (not its own row) — confirmed
    from SX5-N's "0.49%HF", which carries a deprecation note there; SX5-S's
    equivalents have no such note (the Assay content itself is real, wanted
    content for these two HF chemicals — the deprecation note is
    North-specific, not a reason to omit the block on either side).
    """
    section = ReportSection(id)

    header_row = ReportRow(style_name="ColumnHeaderAssay", max_columns=_ASSAY_COLUMNS)
    header_row.set_value(1, "Current Specifications")
    header_row.set_value(2, "Parameter")
    header_row.set_value(3, "% HF")
    header_row.set_value(4, "STDV")
    section.add_row(header_row)

    # Boxed A-D like the table above it (confirmed real, legacy SX5-S
    # reports); column 5 only carries North's note text, unboxed.
    data_row = ReportRow(style_name="DataLabel", blank_columns=frozenset({5, 6}))
    data_row.set_value(1, spec_range)
    data_row.set_value(2, "ASSAY")
    if note_text:
        data_row.set_value(5, note_text)
    section.add_row(data_row)

    return section
