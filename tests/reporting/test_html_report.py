"""The HTML report: the template's own sections, filled with results under the template's columns."""

from slim_report_engine.reporting import row_builders
from slim_report_engine.reporting.html_report import ResultCell, render_html
from slim_report_engine.reporting.report_row import ReportRow
from slim_report_engine.reporting.report_section import ReportSection
from slim_report_engine.reporting.submission_report_builder import OutputSheet


def _sheet(name, *sections):
    return OutputSheet(name=name, sections=tuple(sections), header_title=name, column_widths={})


def _panel(section_id, third="MDL", rows=(("Copper", "Cu"), ("Zinc", "Zn"))):
    section = ReportSection(section_id)
    row_builders.add_header_rows(section, "Element", third)
    for name, symbol in rows:
        row_builders.add_analyte_row(section, name, symbol)
    return section


def test_results_go_under_the_templates_own_columns():
    html = render_html(
        [_sheet("IPA", _panel("36 Elements"))],
        [{("36 Elements", "Cu"): ResultCell("10.100", mdl="0.050", ql="0.167", recovery="99%")}],
        title="TR00001",
    )
    cu = html.split("Copper")[1].split("</tr>")[0]
    assert '<td class="c4 value">10.100</td>' in cu and '<td class="c5 value">99%</td>' in cu
    assert '<td class="c6 value">0.050</td>' in cu  # the MDL column prints the MDL, not the QL
    assert "EXAMPLE LAB" in html and "<h1" in html
    zn = html.split("Zinc")[1].split("</tr>")[0]
    assert "value" not in zn  # not measured: left blank


def test_a_ql_column_prints_the_ql_and_below_mdl_is_marked():
    html = render_html([_sheet("IPA", _panel("5 Anions", third="QL", rows=(("Fluoride", "F"),)))],
                       [{("5 Anions", "F"): ResultCell("< 0.050", mdl="0.050", ql="0.167", below_mdl=True)}])
    f = html.split("Fluoride")[1].split("</tr>")[0]
    assert '<td class="c6 value below-mdl">0.167</td>' in f and "&lt; 0.050" in f


def test_a_single_parameter_section_takes_its_result_and_values_are_escaped():
    section = ReportSection("Assay")  # the assay's shape: a header and one row labelled with the unit
    header = ReportRow(style_name="ColumnHeader")
    for col, label in ((2, "Assay"), (4, "EXAMPLE LAB Result"), (5, "STDEV")):
        header.set_value(col, label)
    row = ReportRow(style_name="DataLabel")
    row.set_value(3, "%")
    section.add_row(header)
    section.add_row(row)
    html = render_html([_sheet("<HNO3>", section), _sheet("IPA", _panel("10 Elements"))],
                       [{("Assay", "Assay"): ResultCell("69.55", recovery="ignored")}, {}])
    assert '<td class="c4 value">69.55</td>' in html
    assert "ignored" not in html  # no Recovery column in the template: nothing printed there
    assert "&lt;HNO3&gt;" in html and "<HNO3>" not in html
    assert 'href="#sheet-2"' in html  # a tab per sample


def test_rendering_is_deterministic():
    sheets = [_sheet("IPA", _panel("36 Elements"))]
    results = [{("36 Elements", "Cu"): ResultCell("10.100")}]
    assert render_html(sheets, results) == render_html(sheets, results)
