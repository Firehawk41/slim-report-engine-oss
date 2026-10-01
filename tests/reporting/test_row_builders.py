from slim_report_engine.reporting import report_row, row_builders
from slim_report_engine.reporting.report_section import ReportSection


def test_build_header_preamble_default_units_line_is_ppb():
    section = row_builders.build_header_preamble("Test Acid")
    units_row = section.rows[3]
    assert units_row.get_value(1) == "All data in units of ppb unless otherwise noted"


def test_build_header_preamble_unit_override_substitutes_into_the_units_line():
    """Confirmed real (modReportCreator.bas's Get_Specs, direct VBA source
    check 2026-09-28; matches a real completed report, Folder 092
    Kentucky's PG, "All data in units of ppm unless otherwise noted")."""
    section = row_builders.build_header_preamble("PG", unit_override="ppm")
    units_row = section.rows[3]
    assert units_row.get_value(1) == "All data in units of ppm unless otherwise noted"


def test_add_header_rows_default_result_label():
    section = ReportSection("test")
    row_builders.add_header_rows(section, "Element", "MDL")
    assert section.row_count == 2
    top, header = section.rows
    assert top.get_value(1) == "Specification"
    assert top.get_value(2) == "Sample Identification:"
    assert header.get_value(2) == "Element"
    assert header.get_value(4) == "EXAMPLE LAB Results"
    assert header.get_value(5) == "Recovery"
    assert header.get_value(6) == "MDL"


def test_add_header_rows_custom_result_label():
    section = ReportSection("test")
    row_builders.add_header_rows(section, "Element", "MDL", result_label="Result")
    _, header = section.rows
    assert header.get_value(4) == "Result"


def test_add_analyte_row():
    section = ReportSection("test")
    row_builders.add_analyte_row(section, "Aluminum", "Al")
    row = section.rows[0]
    assert row.style_name == "DataLabel"
    assert row.get_value(2) == "Aluminum"
    assert row.get_value(3) == "Al"
    assert row.get_value(1) is None


def test_add_analyte_row_default_max_columns():
    section = ReportSection("test")
    row_builders.add_analyte_row(section, "Aluminum", "Al")
    assert section.rows[0].max_columns == report_row.DEFAULT_MAX_COLUMNS


def test_add_analyte_row_custom_max_columns():
    """Confirmed real (Wafers Report Template.xlsx): Wafer's analyte-row
    border/fill extends to column 19, not the standard family's 6 --
    wafer_panel_builder.py passes this explicitly."""
    section = ReportSection("test")
    row_builders.add_analyte_row(section, "Aluminum", "Al", max_columns=19)
    assert section.rows[0].max_columns == 19


def test_add_analyte_row_with_spec_omitted():
    section = ReportSection("test")
    row_builders.add_analyte_row_with_spec(section, "Aluminum", "Al")
    row = section.rows[0]
    assert row.get_value(1) is None


def test_add_analyte_row_with_spec_present():
    section = ReportSection("test")
    row_builders.add_analyte_row_with_spec(section, "Aluminum", "Al", spec_value=5.0)
    row = section.rows[0]
    assert row.get_value(1) == 5.0


def test_add_analyte_row_with_spec_is_ked_adds_note_marker_not_symbol_styling():
    """Confirmed real (2026-09-28, direct user correction, a real
    Folder 031 Z-report): the KED-mode marker is a bold-red
    "Note 1" in column 7, just past the panel's own bordered box -- NOT
    bold-red styling on the element's own symbol cell (column 3), and the
    row's style stays plain "DataLabel" either way."""
    section = ReportSection("test")
    row_builders.add_analyte_row_with_spec(section, "Nickel", "Ni", is_ked=True)
    row = section.rows[0]
    assert row.style_name == "DataLabel"
    assert row.notes == {7: "Note 1"}


def test_add_analyte_row_with_spec_not_ked_has_no_note_marker():
    section = ReportSection("test")
    row_builders.add_analyte_row_with_spec(section, "Aluminum", "Al")
    row = section.rows[0]
    assert row.notes == {}


def test_add_simple_header_row_optional_columns_omitted_when_blank():
    section = ReportSection("test")
    max_columns = row_builders.add_simple_header_row(section, "pH", "Result")
    _, header = section.rows
    assert header.get_value(5) is None
    assert header.get_value(6) is None
    # Confirmed real gap (2026-09-25, direct user correction,
    # Customer 033): a bare single-result shape's header row was
    # still styled out to the shared 6-column default, leaving an
    # unlabeled but still blue-filled "extra" column or two past the
    # real content -- now narrowed to just what's actually used.
    assert max_columns == 4
    assert header.max_columns == 4
    # Confirmed real gap (2026-09-28, direct user correction, ACX): the
    # "Sample Identification:" row (rows[0], right above the header) was
    # still hardcoded to the shared 6-column default with an
    # unconditional D:F merge regardless of the header row's own real
    # width -- for a bare 4-column shape there's only column D past the
    # label at all, so no merge is possible/needed.
    top_row = section.rows[0]
    assert top_row.max_columns == 4
    assert top_row.merges == []


def test_add_simple_header_row_second_column_only_narrows_to_5():
    section = ReportSection("test")
    max_columns = row_builders.add_simple_header_row(section, "Density", "Result", "STDEV")
    assert max_columns == 5
    assert section.rows[1].max_columns == 5
    # The "Sample Identification:" row must match the header's own real
    # width, not stay wider -- confirmed real gap (2026-09-28, ACX): a
    # mismatch here reads as a phantom extra column sitting above a
    # narrower header row.
    top_row = section.rows[0]
    assert top_row.max_columns == 5
    assert top_row.merges == [(4, 5)]


def test_add_simple_header_row_optional_columns_set_when_given():
    section = ReportSection("test")
    max_columns = row_builders.add_simple_header_row(section, "TOC", "Results", "STDEV", "QL")
    _, header = section.rows
    assert header.get_value(5) == "STDEV"
    assert header.get_value(6) == "QL"
    assert max_columns == 6
    assert header.max_columns == 6
    # A genuine 3-column shape keeps the full D:F merge -- only narrower
    # shapes should shrink it.
    top_row = section.rows[0]
    assert top_row.max_columns == 6
    assert top_row.merges == [(4, 6)]


def test_add_note_row():
    section = ReportSection("test")
    row_builders.add_note_row(section, "Dimensionless quantity")
    row = section.rows[0]
    assert row.get_value(1) == "Dimensionless quantity"
    assert row.get_value(4) is None


def test_add_footer_row_echoes_date_of_analysis():
    section = ReportSection("test")
    row_builders.add_footer_row(section, "Analysis by pH Electrode")
    row = section.rows[0]
    assert row.get_value(1) == "Analysis by pH Electrode"
    assert row.get_value(4) == "Date of Analysis: "


def test_add_footer_row_with_date_of_analysis_appends_it_to_the_label():
    section = ReportSection("test")
    row_builders.add_footer_row(section, "Analysis by pH Electrode", date_of_analysis="09-09-26")
    row = section.rows[0]
    assert row.get_value(4) == "Date of Analysis: 09-09-26"


def test_add_footer_row_without_sop_codes_has_no_test_methods_row():
    section = ReportSection("test")
    row_builders.add_footer_row(section, "Analysis by pH Electrode")
    assert section.row_count == 2  # footer, trailing blank -- no Test Methods line
    assert not any("Test Methods" in str(r.get_value(1)) for r in section.rows)


def test_add_footer_row_with_sop_codes_inserts_test_methods_row_before_trailing_blank():
    section = ReportSection("test")
    row_builders.add_footer_row(section, "Analysis by ICPMS (Evaporation)", sop_codes=["SOP-14", "SOP-48"])
    footer, test_methods, trailing_blank = section.rows
    assert footer.get_value(1) == "Analysis by ICPMS (Evaporation)"
    assert test_methods.get_value(1) == "Test Methods: SOP-14 and SOP-48."


def test_add_footer_row_without_ked_note_omits_it():
    section = ReportSection("test")
    row_builders.add_footer_row(section, "Analysis by ICPMS (Evaporation)", sop_codes=["SOP-14", "SOP-48"])
    assert not any("KEDS" in str(r.get_value(1)) for r in section.rows)


def test_add_footer_row_with_ked_note_sits_under_footer_and_test_methods():
    """Corrected 2026-09-28 (direct user correction): the KED note sits
    UNDER both the footer text row AND the Test Methods row, as the last
    line before the trailing blank -- not directly under the footer and
    above Test Methods (the original 2026-09-23 fix's ordering, based on
    a real report that predated Test Methods and so never actually
    exercised this ordering). Text/style also corrected 2026-09-28
    (checked against 60+ real Folder 031 Reports): no "mode",
    no trailing period, and the line is bold red."""
    section = ReportSection("test")
    row_builders.add_footer_row(
        section, "Analysis by ICPMS (Evaporation)", sop_codes=["SOP-14", "SOP-45", "SOP-48"], ked_note=True
    )
    footer, test_methods, note, trailing_blank = section.rows
    assert footer.get_value(1) == "Analysis by ICPMS (Evaporation)"
    assert test_methods.get_value(1) == "Test Methods: SOP-14, SOP-45 and SOP-48."
    assert note.get_value(1) == "Note 1: ICPMS-KEDS used for the reduction of interferences"
    assert note.style_name == "NormalBoldRed"
    assert trailing_blank.values == {}


def test_add_footer_row_with_ked_note_and_no_sop_codes_sits_under_footer_only():
    """No Test Methods row in this case -- the note still ends up as the
    last line before the trailing blank."""
    section = ReportSection("test")
    row_builders.add_footer_row(section, "Analysis by ICPMS (Evaporation)", ked_note=True)
    footer, note, trailing_blank = section.rows
    assert footer.get_value(1) == "Analysis by ICPMS (Evaporation)"
    assert note.get_value(1) == "Note 1: ICPMS-KEDS used for the reduction of interferences"
    assert trailing_blank.values == {}


def test_test_methods_row_single_code_has_trailing_period():
    row = row_builders.test_methods_row(["SOP-04"])
    assert row.get_value(1) == "Test Methods: SOP-04."


def test_test_methods_row_two_codes_joined_with_and():
    row = row_builders.test_methods_row(["SOP-46", "SOP-06"])
    assert row.get_value(1) == "Test Methods: SOP-46 and SOP-06."


def test_test_methods_row_three_codes_use_comma_then_and():
    row = row_builders.test_methods_row(["SOP-14", "SOP-48", "SOP-52"])
    assert row.get_value(1) == "Test Methods: SOP-14, SOP-48 and SOP-52."


def test_test_methods_row_default_max_columns():
    row = row_builders.test_methods_row(["SOP-04"])
    assert row.max_columns == report_row.DEFAULT_MAX_COLUMNS


def test_test_methods_row_custom_max_columns():
    row = row_builders.test_methods_row(["SOP-27", "SOP-45"], max_columns=19)
    assert row.max_columns == 19


def test_blank_row_has_no_values():
    row = row_builders.blank_row()
    assert row.style_name == "Normal"
    assert row.get_value(1) is None
