from dataclasses import dataclass
from datetime import date

import pytest

from slim_domain.domain.tr.enums import ProcessingTime

from slim_report_engine.reporting import wafer_report_builder as orchestrator


@dataclass(frozen=True)
class _FakeElement:
    name: str
    symbol: str


class _FakeElementService:
    def get_by_symbol(self, symbol: str):
        return _FakeElement(name=symbol, symbol=symbol)

    def get_by_name(self, name: str):
        return _FakeElement(name=name, symbol=name[:2])


def test_sheet_title():
    result = orchestrator.build_wafer_sheet(
        "150mm", "atoms/cm^2", "36 Elements", "Customer ea6f9", date(2026, 3, 5), ["W-1"], [], _FakeElementService(), ProcessingTime.NEXT_DAY
    )
    assert result.sheet_title == "150mm Wafers"


def test_apply_superscript_quirk_only_for_atoms_reporting_units():
    result_atoms = orchestrator.build_wafer_sheet(
        "150mm", "atoms/cm^2", "36 Elements", "Customer ea6f9", date(2026, 3, 5), ["W-1"], [], _FakeElementService(), ProcessingTime.NEXT_DAY
    )
    result_scaled = orchestrator.build_wafer_sheet(
        "150mm", "atoms/cm^2 x 10^10", "36 Elements", "Customer ea6f9", date(2026, 3, 5), ["W-1"], [], _FakeElementService(), ProcessingTime.NEXT_DAY
    )
    result_other = orchestrator.build_wafer_sheet(
        "150mm", "ions/cm^2", "4 Anions", "Customer ea6f9", date(2026, 3, 5), ["W-1"], [], _FakeElementService(), ProcessingTime.NEXT_DAY
    )
    assert result_atoms.apply_atoms_superscript_quirk is True
    # Confirmed real 2026-09-26 (Customer abf1e's real completed reports):
    # this scaled selection ALSO needs superscript formatting -- it's not
    # unique to the plain "atoms/cm^2" case.
    assert result_scaled.apply_atoms_superscript_quirk is True
    assert result_other.apply_atoms_superscript_quirk is False


def test_process_blank_and_slot_sample_id_format():
    result = orchestrator.build_wafer_sheet(
        "150mm", "atoms/cm^2", "36 Elements", "Customer ea6f9", date(2026, 3, 5), ["Slot-1", "Slot-2"], [], _FakeElementService(), ProcessingTime.NEXT_DAY
    )
    sample_id_row = result.section.rows[5]
    assert sample_id_row.get_value(4) == "030526-150mm Wafers-Customer ea6f9-Process Blank"
    assert sample_id_row.get_value(5) == "030526-150mm Wafers-Customer ea6f9-Slot-1"
    assert sample_id_row.get_value(6) == "030526-150mm Wafers-Customer ea6f9-Slot-2"


def test_element_panel_gets_inferred_date_of_analysis():
    """Confirmed real (direct user request): Wafer's element panel is the
    only Wafer shape with a "Date of Analysis: " placeholder (see
    wafer_panel_builder.py's module docstring) -- date_received is a
    Thursday and NEXT_DAY is 1 business day, so the expected date is the
    very next day, Friday."""
    result = orchestrator.build_wafer_sheet(
        "150mm", "atoms/cm^2", "36 Elements", "Customer ea6f9", date(2026, 3, 5), ["W-1"], [], _FakeElementService(),
        ProcessingTime.NEXT_DAY,
    )
    footer = next(r for r in result.section.rows if r.get_value(1) == "Analysis by LP-ICPMS.")
    assert footer.get_value(4) == "Date of Analysis: 03-06-26"


def test_anion_panel_never_gets_date_of_analysis():
    """Confirmed real: the anion panel has no "Date of Analysis: "
    placeholder at all, unlike the element panel."""
    result = orchestrator.build_wafer_sheet(
        "150mm", "ions/cm^2", "4 Anions", "Customer ea6f9", date(2026, 3, 5), ["W-1"], [], _FakeElementService(),
        ProcessingTime.NEXT_DAY,
    )
    footer = next(r for r in result.section.rows if r.get_value(1) == "Analysis by LP-IC.")
    assert footer.get_value(4) is None


def test_element_selections_use_atoms_note():
    """Confirmed real against a live production report (2026-09-23,
    Customer d53ad): the plain "atoms/cm^2" reporting-unit selection gets no
    "1010" prefix. (A 2026-09-26 real-evidence check found this was
    over-generalized -- see test_element_selections_use_scaled_atoms_note
    below -- but for THIS specific reporting-unit value, unprefixed is
    still the confirmed real behavior.)"""
    for label in ("36 Elements", "67 Elements", "List #2 36 Elements"):
        result = orchestrator.build_wafer_sheet(
            "150mm", "atoms/cm^2", label, "Customer ea6f9", date(2026, 3, 5), ["W-1"], [], _FakeElementService(), ProcessingTime.NEXT_DAY
        )
        units_row = result.section.rows[4]
        assert units_row.get_value(1) == "Results in units of atoms/cm2"


def test_element_selections_use_scaled_atoms_note():
    """Confirmed real 2026-09-26 (direct real-evidence check, S:\\Reports\\
    Customer abf1e -- dozens of real completed wafer reports, 2017 through
    2023, every one using this exact flattened text): the "atoms/cm^2 x
    10^10" reporting-unit selection is a genuinely different, real, and
    still-selectable option on the real intake form (confirmed against
    Customer abf1e's own real 2023 TR form) -- it needed its own note text,
    which a 2026-09-23 "correction" had wrongly removed after checking
    only one customer (Customer d53ad) who never selects this option."""
    for label in ("36 Elements", "67 Elements", "List #2 36 Elements"):
        result = orchestrator.build_wafer_sheet(
            "150mm", "atoms/cm^2 x 10^10", label, "Customer ea6f9", date(2026, 3, 5), ["W-1"], [], _FakeElementService(), ProcessingTime.NEXT_DAY
        )
        units_row = result.section.rows[4]
        assert units_row.get_value(1) == "Results in units of 1010 atoms/cm2"


def test_anion_selections_use_ions_note():
    for label in ("4 Anions", "5 Anions", "7 Anions"):
        result = orchestrator.build_wafer_sheet(
            "150mm", "ions/cm^2", label, "Customer ea6f9", date(2026, 3, 5), ["W-1"], [], _FakeElementService(), ProcessingTime.NEXT_DAY
        )
        units_row = result.section.rows[4]
        assert units_row.get_value(1) == "Results in units of ions/cm2"


def test_67_elements_has_67_data_rows():
    result = orchestrator.build_wafer_sheet(
        "150mm", "atoms/cm^2", "67 Elements", "Customer ea6f9", date(2026, 3, 5), ["W-1"], [], _FakeElementService(), ProcessingTime.NEXT_DAY
    )
    data_rows = [r for r in result.section.rows if r.style_name == "DataLabel"]
    assert len(data_rows) == 67


def test_additional_element_names_appended_for_element_sheets():
    result = orchestrator.build_wafer_sheet(
        "150mm", "atoms/cm^2", "36 Elements", "Customer ea6f9", date(2026, 3, 5), ["W-1"], ["Gold", "Silver"],
        _FakeElementService(), ProcessingTime.NEXT_DAY,
    )
    data_rows = [r for r in result.section.rows if r.style_name == "DataLabel"]
    assert data_rows[-2].get_value(2) == "Gold"
    assert data_rows[-1].get_value(2) == "Silver"


def test_result_carries_processing_time():
    result = orchestrator.build_wafer_sheet(
        "150mm", "atoms/cm^2", "36 Elements", "Customer ea6f9", date(2026, 3, 5), ["W-1"], [],
        _FakeElementService(), ProcessingTime.SAME_DAY_RUSH,
    )
    assert result.processing_time == ProcessingTime.SAME_DAY_RUSH


def test_unknown_selection_raises():
    with pytest.raises(ValueError):
        orchestrator.build_wafer_sheet(
            "150mm", "atoms/cm^2", "Not A Real Selection", "Customer ea6f9", date(2026, 3, 5), ["W-1"], [],
            _FakeElementService(), ProcessingTime.NEXT_DAY,
        )
