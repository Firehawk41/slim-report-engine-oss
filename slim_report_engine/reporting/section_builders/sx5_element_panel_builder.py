"""Builds a SX5 element-panel section — ported from
clsSX5ElementPanelBuilder.cls. The 36-element trace-metals panel used by
SX5 chemicals like NH4OH, H2O2 (confirmed symbol-for-symbol identical
list/order to presets.analyte_presets.trace_elements_36), with
SX5-specific per-element spec values and header shape.

Confirmed real differences from the generic metals panel
(analyte_list_section_builder.build_metals_panel) that make this its OWN
builder rather than a variant:
  - a QC reference code row (e.g. "SX5N-QC-REF-NH4OH") and "Sample #:"
    instead of "Sample Identification:"
  - two note rows ("   Data =< MDL" / "All data in ppb") the generic panel
    doesn't have
  - a per-element spec THRESHOLD in column 1 of each analyte row (generic
    metals panels have no per-element spec at all)
  - no AVERAGE/TOTAL summary rows, no footer

The sample-ID cell (column 4 of the QC-code row) is deliberately left
BLANK here — which of the two real SX5 sample-ID formats applies is an
orchestration decision, not this builder's — see
sx5_non_routine_report_builder.py and sx5/chemical_rules.py.
"""

from __future__ import annotations

from slim_domain.domain.element.element_service import ElementService

from slim_report_engine.lab_identity import RESULTS_LABEL
from slim_report_engine.reporting import row_builders
from slim_report_engine.reporting.presets import analyte_presets
from slim_report_engine.reporting.report_row import ReportRow
from slim_report_engine.reporting.report_section import ReportSection


def build_element_panel(
    id: str,
    chemical_label: str,
    qc_code: str,
    specs: dict[str, float],
    element_service: ElementService,
    units_note_text: str = "All data in ppb",
    units_note_column: int = 4,
) -> ReportSection:
    """chemical_label: e.g. "NH4OH" (becomes row 1's title and the sheet tab
    name once written). specs: symbol -> spec value; a symbol absent from
    specs gets no column-1 value, matching the real template.

    units_note_text/units_note_column: same per-chemical override as
    build_element_panel_with_anions -- confirmed real: a composite
    chemical's units note (e.g. "0.49%HF"'s longer caveat in column 3)
    is chemical-specific, not conditional on whether the anion block is
    actually present on this particular sample (see
    sx5_non_routine_report_builder.py's Composite-category dispatch,
    which now calls this function -- not
    build_element_panel_with_anions -- when anions weren't requested).
    """
    section = ReportSection(id)

    _add_title_and_notes(section, chemical_label, "   Data =< MDL", units_note_column, units_note_text)
    _add_qc_row_and_header(section, qc_code)
    _add_element_rows(section, specs, element_service)

    return section


def build_element_panel_with_anions(
    id: str,
    chemical_label: str,
    qc_code: str,
    element_specs: dict[str, float],
    anion_specs: dict[str, float],
    element_service: ElementService,
    units_note_text: str = "All data in ppb",
    units_note_column: int = 4,
) -> ReportSection:
    """Confirmed real composite chemicals: SX5-N's "0.49%HF", SX5-S's
    "0.49%HF", and SX5-S's "2.5%HF-5%" all combine the standard 36-element
    panel with an appended 4-anion block (Chloride, Nitrate, Sulfate,
    Phosphate — SX5's own order, confirmed to differ from
    presets.ion_presets.anions_4()'s order) that ALSO carries per-analyte
    spec values, sharing the SAME column header as the elements (no
    separate header row for the anions). A deprecated "Assay" block also
    follows on the real sheet — see sx5_assay_section_builder.build_embedded_assay,
    built as a separate section by the caller, not by this function.

    units_note_text/units_note_column: confirmed real per-chemical
    variation — SX5-N/SX5-S's "0.49%HF" uses a longer caveat in column 3,
    while SX5-S's "2.5%HF-5%" uses the standard column-4 text. Defaults
    match the standard shape.
    """
    section = ReportSection(id)

    _add_title_and_notes(section, chemical_label, "   Data =< MDL", units_note_column, units_note_text)
    _add_qc_row_and_header(section, qc_code)
    _add_element_rows(section, element_specs, element_service)

    section.add_row(row_builders.blank_row())
    for name, symbol in (("Chloride", "Cl"), ("Nitrate", "NO3"), ("Sulfate", "SO4"), ("Phosphate", "PO4")):
        row_builders.add_analyte_row_with_spec(section, name, symbol, anion_specs.get(symbol))
    section.add_row(row_builders.blank_row())

    return section


def _add_title_and_notes(
    section: ReportSection, chemical_label: str, notes_text: str, notes_column: int, notes_value: str
) -> None:
    title_row = ReportRow(style_name="SectionTitle")
    title_row.set_value(1, chemical_label)
    section.add_row(title_row)

    section.add_row(row_builders.blank_row())
    section.add_row(row_builders.blank_row())

    notes_row = ReportRow(style_name="Normal")
    notes_row.set_value(1, notes_text)
    notes_row.set_value(notes_column, notes_value)
    section.add_row(notes_row)


def _add_qc_row_and_header(section: ReportSection, qc_code: str) -> None:
    # Confirmed real (NH4OH template): unlike the generic metals panel,
    # SX5's QC row does NOT merge its echo cell -- column 4 alone carries
    # the sample-ID string, no add_merge call here.
    qc_row = ReportRow(style_name="SampleIdEchoWide", row_height=43.5)
    qc_row.set_value(1, qc_code)
    qc_row.set_value(2, "Sample #:")
    # Column 4 (the sample-ID stamp) is intentionally left blank -- see
    # module docstring.
    section.add_row(qc_row)

    header_row = ReportRow(style_name="ColumnHeader", row_height=28.5)
    header_row.set_value(1, "Specification")
    header_row.set_value(2, "Element")
    header_row.set_value(4, RESULTS_LABEL)
    header_row.set_value(5, "Recovery")
    header_row.set_value(6, "MDL")
    section.add_row(header_row)


def _add_element_rows(
    section: ReportSection, specs: dict[str, float], element_service: ElementService
) -> None:
    for symbol in analyte_presets.trace_elements_36():
        element = element_service.get_by_symbol(symbol)
        if element is None:
            raise ValueError(f"unknown element symbol: {symbol!r}")
        row_builders.add_analyte_row_with_spec(section, element.name, element.symbol, specs.get(symbol))
