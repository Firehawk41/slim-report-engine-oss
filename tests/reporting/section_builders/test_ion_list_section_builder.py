from slim_report_engine.reporting.analyte import Analyte
from slim_report_engine.reporting.section_builders import ion_list_section_builder as builder


def test_build_ion_panel_uses_ql_not_mdl():
    section = builder.build_ion_panel("Anions", "Anion", [], "Analysis by IC")
    header = section.rows[1]
    assert header.get_value(6) == "QL"


def test_build_ion_panel_has_no_average_total_summary():
    analytes = [Analyte("Chloride", "Cl", 2), Analyte("Sulfate", "SO4", 5)]
    section = builder.build_ion_panel("Anions", "Anion", analytes, "Analysis by IC")
    for row in section.rows:
        value = row.get_value(2)
        if value:
            assert "AVERAGE" not in value
            assert "TOTAL" not in value


def test_build_ion_panel_footer_has_blank_rows_before_and_after():
    """Confirmed real (every ion panel checked): exactly one blank row
    separates the last analyte row from "Analysis by ...", and one more
    follows it -- add_footer_row supplies both automatically."""
    analytes = [Analyte("Chloride", "Cl", 2)]
    section = builder.build_ion_panel("Anions", "Anion", analytes, "Analysis by IC")
    # top, header, Chloride, blank, footer, blank
    assert section.row_count == 6
    footer = section.rows[-2]
    assert footer.get_value(1) == "Analysis by IC"
    assert section.rows[-1].values == {}


def test_build_ion_panel_rows_preserve_analyte_order():
    analytes = [Analyte("Fluoride", "F", 1), Analyte("Chloride", "Cl", 2)]
    section = builder.build_ion_panel("Anions", "Anion", analytes, "Analysis by IC")
    data_rows = section.rows[2:4]
    assert [r.get_value(3) for r in data_rows] == ["F", "Cl"]


def test_build_ion_panel_has_no_specification_label():
    """Confirmed real (2026-09-28, dummy "test all analyses" TR run
    through the real legacy macro and diffed): unlike metals/silicon
    panels, ion panels (Anions/Cations/GBP) never carry the
    "Specification" column-1 label on their top row."""
    section = builder.build_ion_panel("Anions", "Anion", [], "Analysis by IC")
    top_row = section.rows[0]
    assert top_row.get_value(1) is None
