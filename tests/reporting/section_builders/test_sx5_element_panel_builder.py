from dataclasses import dataclass

import pytest

from slim_report_engine.reporting.section_builders import sx5_element_panel_builder as builder


@dataclass(frozen=True)
class _FakeElement:
    name: str
    symbol: str


class _FakeElementService:
    def get_by_symbol(self, symbol: str):
        return _FakeElement(name=symbol, symbol=symbol)


def test_build_element_panel_row_shape():
    specs = {"Al": 0.1, "Sb": 0.1}
    section = builder.build_element_panel("NH4OH", "NH4OH", "SX5N-QC-REF-NH4OH", specs, _FakeElementService())
    title, blank1, blank2, notes, qc, header = section.rows[:6]
    assert title.get_value(1) == "NH4OH"
    assert notes.get_value(1) == "   Data =< MDL"
    assert notes.get_value(4) == "All data in ppb"
    assert qc.get_value(1) == "SX5N-QC-REF-NH4OH"
    assert qc.get_value(2) == "Sample #:"
    assert qc.get_value(4) is None  # sample-ID stamp left blank
    assert header.get_value(4) == "EXAMPLE LAB Results"


def test_build_element_panel_has_36_element_rows():
    section = builder.build_element_panel("NH4OH", "NH4OH", "QC", {}, _FakeElementService())
    data_rows = [r for r in section.rows if r.style_name == "DataLabel"]
    assert len(data_rows) == 36


def test_element_with_spec_gets_column_1_value():
    section = builder.build_element_panel("NH4OH", "NH4OH", "QC", {"Al": 0.1}, _FakeElementService())
    al_row = next(r for r in section.rows if r.get_value(3) == "Al")
    assert al_row.get_value(1) == 0.1


def test_element_with_no_spec_gets_no_column_1_value():
    section = builder.build_element_panel("NH4OH", "NH4OH", "QC", {}, _FakeElementService())
    al_row = next(r for r in section.rows if r.get_value(3) == "Al")
    assert al_row.get_value(1) is None


def test_no_average_total_summary_no_footer():
    section = builder.build_element_panel("NH4OH", "NH4OH", "QC", {}, _FakeElementService())
    for row in section.rows:
        value = row.get_value(2)
        if value:
            assert "AVERAGE" not in value
            assert "TOTAL" not in value


def test_units_note_column_override():
    section = builder.build_element_panel_with_anions(
        "0.49%HF", "0.49%HF", "QC", {}, {}, _FakeElementService(),
        units_note_text="All data in ppb except where indicated below.",
        units_note_column=3,
    )
    notes_row = section.rows[3]
    assert notes_row.get_value(3) == "All data in ppb except where indicated below."
    assert notes_row.get_value(4) is None


def test_composite_appends_4_anions_in_sx5_order_with_specs():
    anion_specs = {"Cl": 40, "NO3": 60, "SO4": 30, "PO4": 10}
    section = builder.build_element_panel_with_anions(
        "0.49%HF", "0.49%HF", "QC", {}, anion_specs, _FakeElementService()
    )
    anion_rows = [r for r in section.rows if r.get_value(3) in ("Cl", "NO3", "SO4", "PO4")]
    assert [r.get_value(3) for r in anion_rows] == ["Cl", "NO3", "SO4", "PO4"]
    assert [r.get_value(1) for r in anion_rows] == [40, 60, 30, 10]


def test_unknown_element_symbol_raises():
    class _EmptyElementService:
        def get_by_symbol(self, symbol):
            return None

    with pytest.raises(ValueError):
        builder.build_element_panel("x", "x", "QC", {}, _EmptyElementService())
