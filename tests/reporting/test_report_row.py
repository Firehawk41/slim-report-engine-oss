import pytest

from slim_report_engine.reporting.report_row import DEFAULT_MAX_COLUMNS, ReportRow


def test_default_style_and_max_columns():
    row = ReportRow()
    assert row.style_name == "Normal"
    assert row.max_columns == DEFAULT_MAX_COLUMNS
    assert row.row_height is None
    assert row.merges == []


def test_row_height_is_stored():
    row = ReportRow(row_height=60.0)
    assert row.row_height == 60.0


def test_add_merge_records_the_range():
    row = ReportRow()
    row.add_merge(4, 6)
    assert row.merges == [(4, 6)]


def test_add_merge_supports_multiple_ranges():
    row = ReportRow(max_columns=19)
    row.add_merge(2, 3)
    row.add_merge(9, 11)
    assert row.merges == [(2, 3), (9, 11)]


def test_add_merge_rejects_a_single_column_range():
    row = ReportRow()
    with pytest.raises(ValueError):
        row.add_merge(4, 4)
    with pytest.raises(ValueError):
        row.add_merge(5, 4)


def test_add_merge_out_of_range_raises():
    row = ReportRow(max_columns=6)
    with pytest.raises(ValueError):
        row.add_merge(4, 7)


def test_merges_property_is_a_defensive_copy():
    row = ReportRow()
    row.add_merge(4, 6)
    snapshot = row.merges
    snapshot.append((1, 2))
    assert row.merges == [(4, 6)]


def test_set_and_get_value():
    row = ReportRow()
    row.set_value(2, "Aluminum")
    assert row.get_value(2) == "Aluminum"


def test_get_value_defaults_to_none():
    row = ReportRow()
    assert row.get_value(5) is None


def test_set_value_out_of_range_raises():
    row = ReportRow(max_columns=12)
    with pytest.raises(ValueError):
        row.set_value(13, "x")
    with pytest.raises(ValueError):
        row.set_value(0, "x")


def test_wafer_row_allows_up_to_19_columns():
    row = ReportRow(style_name="WaferHeader", max_columns=19)
    row.set_value(19, "MDL")
    assert row.get_value(19) == "MDL"


def test_formula_round_trip():
    row = ReportRow()
    assert row.has_formula(4) is False
    row.set_formula(4, "=AVERAGE(R[-36]C:R[-1]C)")
    assert row.has_formula(4) is True
    assert row.get_formula(4) == "=AVERAGE(R[-36]C:R[-1]C)"


def test_formula_columns_lists_only_set_formulas():
    row = ReportRow()
    row.set_formula(3, "=SUM(R[-1]C)")
    row.set_formula(5, "=SUM(R[-1]C)")
    assert sorted(row.formula_columns) == [3, 5]


def test_values_property_is_a_defensive_copy():
    row = ReportRow()
    row.set_value(1, "a")
    snapshot = row.values
    snapshot[1] = "mutated"
    assert row.get_value(1) == "a"


def test_superscript_runs_defaults_to_empty():
    row = ReportRow()
    assert row.superscript_runs == {}


def test_set_superscript_runs_records_them_by_column():
    row = ReportRow()
    row.set_value(1, "atoms/cm2")
    row.set_superscript_runs(1, (("atoms/cm", False), ("2", True)))
    assert row.superscript_runs == {1: (("atoms/cm", False), ("2", True))}


def test_set_superscript_runs_out_of_range_raises():
    row = ReportRow()
    with pytest.raises(ValueError):
        row.set_superscript_runs(99, (("x", False),))


def test_superscript_runs_property_is_a_defensive_copy():
    row = ReportRow()
    row.set_superscript_runs(1, (("a", False),))
    snapshot = row.superscript_runs
    snapshot[1] = (("mutated", True),)
    assert row.superscript_runs == {1: (("a", False),)}


def test_notes_defaults_to_empty():
    row = ReportRow()
    assert row.notes == {}


def test_set_note_records_it_by_column():
    row = ReportRow()
    row.set_note(7, "Note 1")
    assert row.notes == {7: "Note 1"}


def test_set_note_is_not_constrained_by_max_columns():
    """Deliberately unlike set_value/set_superscript_runs -- a note marker
    lives past the row's own bordered shape (e.g. column 7 on a
    max_columns=6 metals panel row), see ReportRow.set_note."""
    row = ReportRow(max_columns=6)
    row.set_note(7, "Note 1")
    assert row.notes == {7: "Note 1"}


def test_set_note_rejects_non_positive_column():
    row = ReportRow()
    with pytest.raises(ValueError):
        row.set_note(0, "Note 1")


def test_notes_property_is_a_defensive_copy():
    row = ReportRow()
    row.set_note(7, "Note 1")
    snapshot = row.notes
    snapshot[7] = "mutated"
    assert row.notes == {7: "Note 1"}
