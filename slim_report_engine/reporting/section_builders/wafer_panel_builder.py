"""Builds ONE wafer report sheet's analyte panel — either an element panel
(36/67/List#2 36) or an anion panel (4/5/7 Anions). Ported from
clsWaferPanelBuilder.cls.

Structurally NEW versus every other report shape: a variable number of
physical wafer SAMPLES share one sheet side by side in columns (column D
is always "Process Blank", column E onward are numbered "Slot #" samples),
so this builder writes N sample-ID cells across successive columns instead
of one fixed result column — ReportRow.set_value already accepts arbitrary
column indices, so no new Row/Section type was needed, only wider rows
(see MAX_SAMPLE_COLUMNS).

Confirmed real differences between the two categories:
  - column 2 header: "Element" vs "Anion"
  - column-1 note text: "...atoms/cm2" vs "...ions/cm2"
  - the bare per-analyte-count summary header at column (6 + sample_count):
    "MDL" vs "QL"
  - footer analysis text: "Analysis by LP-ICPMS." vs "Analysis by LP-IC."
  - ONLY element panels carry a "Date of Analysis: " placeholder on the
    same footer row (anion panels have no such placeholder anywhere on
    the sheet — confirmed absent, not a template oversight)
Otherwise identical shape.

The (6 + sample_count) MDL/QL column position is derived from the real
template's own unmodified worst case: 13 slot columns (E..Q) with the bare
MDL/QL header fixed at column S (19) — i.e. one blank spacer column after
the last slot column, then the header. Confirmed self-consistent: 6 + 13
= 19.

The sheet title ("<WaferSize> Wafers") is deliberately NOT set here — it
needs direct Worksheet/Range access this builder doesn't have; see
wafer_report_builder.py (the orchestrator), exactly the same division of
responsibility used by sx5_non_routine_report_builder.py for the
sample-ID stamp. The atoms/cm^2 units note's own superscript formatting
IS threaded through from here (as of 2026-09-26) via
ReportRow.set_superscript_runs -- the orchestrator computes the real
run structure (which segments are superscript) and passes it down as
units_note_superscript_runs, since only it knows which real
reporting_units selection is in play.
"""

from __future__ import annotations

from slim_domain.domain.element.element_service import ElementService

from slim_report_engine.lab_identity import RESULTS_LABEL
from slim_report_engine.reporting import row_builders, sop_codes
from slim_report_engine.reporting.analyte import Analyte
from slim_report_engine.reporting.report_row import ReportRow
from slim_report_engine.reporting.report_section import ReportSection

MAX_SAMPLE_COLUMNS = 19  # the real template's own WORST-CASE column span (D..Q + a bare S header)
# Confirmed real gap (2026-09-25, direct user correction): every row was
# always styled/bordered out to this fixed worst-case width regardless of
# how many real sample columns a given report actually has, leaving a
# long run of empty-but-bordered/filled "extra" columns for any report
# with fewer than 13 slot samples -- the overwhelmingly common case. Each
# build_* function below now computes the REAL width for its own
# sample_count (see _real_max_columns) and uses that everywhere instead.


def build_element_panel(
    id: str,
    units_note_text: str,
    process_blank_sample_id: str,
    slot_sample_ids: list[str],
    element_symbols: list[str],
    element_service: ElementService,
    additional_element_names: list[str] | None = None,
    date_of_analysis: str | None = None,
    units_note_superscript_runs: tuple[tuple[str, bool], ...] | None = None,
) -> ReportSection:
    """process_blank_sample_id/slot_sample_ids: fully-formatted sample-ID
    strings (see wafer_report_builder.py for the format) — this builder
    only places them, it doesn't compute the format. additional_element_names:
    optional element NAME strings (not symbols) requested via the intake
    form's free-text "Additional Elements" field — looked up by name,
    appended after the fixed panel, matching the real insertion point
    (just before the "Analysis by..." footer row). date_of_analysis:
    pre-formatted "MM-DD-YY" text (see date_of_analysis.py) -- Wafer's own
    element panel is the ONLY Wafer shape with a "Date of Analysis: "
    placeholder at all (confirmed real, see module docstring).
    units_note_superscript_runs: which segments of units_note_text are
    real superscript (see wafer_report_builder.py's own atoms/cm^2 run
    constants) -- None (e.g. the ions/cm2 anion panel, no confirmed real
    superscript evidence) means write it as plain text, unchanged.
    """
    section = ReportSection(id)
    real_max_columns = _real_max_columns(len(slot_sample_ids))
    _add_common_header_rows(
        section, "Element", units_note_text, process_blank_sample_id, slot_sample_ids, "MDL", real_max_columns,
        units_note_superscript_runs=units_note_superscript_runs,
    )

    for symbol in element_symbols:
        element = element_service.get_by_symbol(symbol)
        if element is None:
            raise ValueError(f"unknown element symbol: {symbol!r}")
        row_builders.add_analyte_row(section, element.name, element.symbol, max_columns=real_max_columns)

    for name in additional_element_names or []:
        element = element_service.get_by_name(name.strip())
        if element is None:
            raise ValueError(f"unknown additional element name: {name!r}")
        row_builders.add_analyte_row(section, element.name, element.symbol, max_columns=real_max_columns)

    _add_footer_rows(
        section, "Analysis by LP-ICPMS.", include_date_of_analysis=True,
        # has_ked_elements defaults to True here (see
        # sop_codes.wafer_element_panel_sop_codes) since nothing in the
        # Wafer report-building chain looks up a real Chemical yet --
        # matches every real Wafer instance found so far.
        sop_codes=sop_codes.wafer_element_panel_sop_codes(),
        date_of_analysis=date_of_analysis,
        max_columns=real_max_columns,
    )
    return section


def build_anion_panel(
    id: str,
    units_note_text: str,
    process_blank_sample_id: str,
    slot_sample_ids: list[str],
    anions: list[Analyte],
) -> ReportSection:
    """anions: see presets/wafer_anion_presets.py — wafer anion order is
    alphabetical, a third convention distinct from both presets/ion_presets'
    elution order and SX5's own anion order.
    """
    section = ReportSection(id)
    real_max_columns = _real_max_columns(len(slot_sample_ids))
    _add_common_header_rows(
        section, "Anion", units_note_text, process_blank_sample_id, slot_sample_ids, "QL", real_max_columns,
    )

    for anion in anions:
        row_builders.add_analyte_row(section, anion.name, anion.symbol, max_columns=real_max_columns)

    _add_footer_rows(section, "Analysis by LP-IC.", include_date_of_analysis=False, max_columns=real_max_columns)
    return section


def _real_max_columns(sample_count: int) -> int:
    """The real last meaningful column for THIS report's actual sample
    count (through the bare MDL/QL header, one column past the last real
    sample column) -- not the fixed 19-column worst case. Capped at
    MAX_SAMPLE_COLUMNS for the (currently unconfirmed) case of a real
    sample_count that would exceed the real template's own worst case."""
    return min(6 + sample_count, MAX_SAMPLE_COLUMNS)


def _add_common_header_rows(
    section: ReportSection,
    category_label: str,
    units_note_text: str,
    process_blank_sample_id: str,
    slot_sample_ids: list[str],
    third_column_header: str,
    max_columns: int,
    units_note_superscript_runs: tuple[tuple[str, bool], ...] | None = None,
) -> None:
    section.add_row(_blank_row_wide(max_columns))
    section.add_row(_blank_row_wide(max_columns))

    notes_label_row = ReportRow(style_name="NormalBold", max_columns=max_columns)
    notes_label_row.set_value(1, "Notes:")
    section.add_row(notes_label_row)

    # Confirmed real (Wafers Report Template.xlsx row 4): blue, but NOT
    # bold -- unlike the generic preamble's equivalent line.
    mdl_note_row = ReportRow(style_name="NormalBlue", max_columns=max_columns)
    mdl_note_row.set_value(1, "Blue font indicates data at or below the MDL")
    section.add_row(mdl_note_row)

    units_row = ReportRow(style_name="NormalBold", max_columns=max_columns)
    units_row.set_value(1, units_note_text)
    if units_note_superscript_runs is not None:
        units_row.set_superscript_runs(1, units_note_superscript_runs)
    section.add_row(units_row)

    # row_height bumped 60.0 -> 95.0 (2026-09-25, direct user correction,
    # Custc4ea4): the real sample-ID string here is often much longer than the
    # generic metals panel's own equivalent (it carries the wafer size AND
    # the customer name AND the per-slot label), and this row's narrow
    # column width means it wraps onto several lines -- 50.25pt wasn't
    # tall enough to show all of them.
    sample_id_row = ReportRow(style_name="SampleIdEchoWide", max_columns=max_columns, row_height=95.0)
    sample_id_row.set_value(1, "Specification")
    sample_id_row.set_value(2, "Sample #:")
    # Confirmed real ("36 Elements" template): B6:C6 merges the "Sample #:"
    # label across both columns -- unlike the generic metals panel, which
    # merges its VALUE cell instead (D:F) and leaves this label unmerged.
    sample_id_row.add_merge(2, 3)
    sample_id_row.set_value(4, process_blank_sample_id)
    col_index = 5
    for slot_id in slot_sample_ids:
        sample_id_row.set_value(col_index, slot_id)
        col_index += 1
    section.add_row(sample_id_row)

    sample_count = len(slot_sample_ids)
    # Confirmed real gap (2026-09-25, direct user correction): the single
    # deliberate spacer column between the last real sample column and the
    # bare MDL/QL header was still getting the same blue fill/border as
    # every other header cell -- looked like just another unlabeled
    # colored cell, not an intentional gap. Marked blank here so it
    # actually reads as one.
    gap_column = 5 + sample_count

    header_row = ReportRow(
        style_name="ColumnHeader", max_columns=max_columns, row_height=25.5,
        blank_columns=frozenset({gap_column}),
    )
    header_row.set_value(2, category_label)
    # Confirmed real: B7:C7 also merges the "Element"/"Anion" label.
    header_row.add_merge(2, 3)
    for c in range(4, 4 + sample_count + 1):
        header_row.set_value(c, RESULTS_LABEL)
    header_row.set_value(6 + sample_count, third_column_header)
    section.add_row(header_row)


def _add_footer_rows(
    section: ReportSection,
    analysis_text: str,
    include_date_of_analysis: bool,
    max_columns: int,
    sop_codes: list[str] | None = None,
    date_of_analysis: str | None = None,
) -> None:
    section.add_row(_blank_row_wide(max_columns))

    analysis_row = ReportRow(style_name="Normal", max_columns=max_columns)
    analysis_row.set_value(1, analysis_text)
    if include_date_of_analysis:
        label = "Date of Analysis: " + date_of_analysis if date_of_analysis else "Date of Analysis: "
        analysis_row.set_value(4, label)
    section.add_row(analysis_row)

    if sop_codes:
        section.add_row(row_builders.test_methods_row(sop_codes, max_columns=max_columns))

    wafer_number_row = ReportRow(style_name="Normal", max_columns=max_columns)
    wafer_number_row.set_value(4, "Wafer # ")
    wafer_number_row.set_value(5, "Etching comments below:")
    section.add_row(wafer_number_row)


def _blank_row_wide(max_columns: int) -> ReportRow:
    return ReportRow(style_name="Normal", max_columns=max_columns)
