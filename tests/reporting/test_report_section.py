from slim_report_engine.reporting.report_row import ReportRow
from slim_report_engine.reporting.report_section import ReportSection


def test_new_section_is_empty():
    section = ReportSection(id="36 Elements")
    assert section.id == "36 Elements"
    assert section.rows == []
    assert section.row_count == 0


def test_add_row_appends_in_order():
    section = ReportSection(id="Silicon")
    row1 = ReportRow()
    row2 = ReportRow()
    section.add_row(row1)
    section.add_row(row2)
    assert section.rows == [row1, row2]


def test_row_count_reflects_state_before_next_add():
    """A builder reads row_count to know the 1-based index of the row it's
    about to add -- confirm it reports the count BEFORE that row lands."""
    section = ReportSection(id="Anions")
    assert section.row_count == 0
    section.add_row(ReportRow())
    assert section.row_count == 1
    section.add_row(ReportRow())
    assert section.row_count == 2


def test_rows_property_is_a_defensive_copy():
    section = ReportSection(id="pH")
    section.add_row(ReportRow())
    snapshot = section.rows
    snapshot.append(ReportRow())
    assert section.row_count == 1
