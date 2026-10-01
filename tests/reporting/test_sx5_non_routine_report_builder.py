from dataclasses import dataclass
from datetime import date

import pytest

from slim_report_engine.reporting import column_widths, sx5_non_routine_report_builder as orchestrator
from slim_report_engine.reporting.sx5_non_routine_report_builder import SX5SpecData


@dataclass(frozen=True)
class _FakeElement:
    name: str
    symbol: str


class _FakeElementService:
    def get_by_symbol(self, symbol: str):
        return _FakeElement(name=symbol, symbol=symbol)


# Invented test data -- the customer's real values live in the database
# and are checked end to end by tests/golden against real legacy reports.
_DATA = SX5SpecData(
    specs={"Al": 0.1, "Fe": 0.2, "Cl": 40, "NO3": 60, "SO4": 30, "PO4": 10},
    qc_code="QC-TEST",
    assay_spec_text="1.0 - 2.0",
)


def _build(chemical, location="SX5N", requested=frozenset(), data=_DATA):
    return orchestrator.build_non_routine_report(
        chemical, location, date(2026, 3, 5), "S-001", _FakeElementService(), requested, spec_data=data
    )


# ---------------------------------------------------------------------------
# is_supported_chemical
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "chemical_name",
    ["NH4OH", "H2O2", "IPA", "BHF", "49%HF", "HCl", "SurfClean",  # Element (7)
     "CSLX001", "WX2000", "WX7808",  # Assay (3)
     "0.49%HF", "2.5%HF"],  # Composite (2)
)
def test_all_known_chemicals_are_supported(chemical_name):
    assert orchestrator.is_supported_chemical(chemical_name) is True


def test_unknown_chemical_not_supported():
    assert orchestrator.is_supported_chemical("Not A Real Chemical") is False


# ---------------------------------------------------------------------------
# Element-panel category
# ---------------------------------------------------------------------------

def test_nh4oh_sx5n_builds_one_element_panel_section():
    result = _build("NH4OH")
    assert len(result.sections) == 1
    assert result.chemical_label == "NH4OH"
    assert result.name_cell_address == "D5"
    assert "NH4OH" in result.sample_string


def test_element_panel_uses_the_passed_in_limits_and_qc_code():
    panel = _build("NH4OH").sections[0]
    al_row = next(row for row in panel.rows if row.get_value(3) == "Al")
    assert al_row.get_value(1) == 0.1
    assert any("QC-TEST" in str(v) for row in panel.rows for v in row.values.values())


def test_surfclean_is_sx5s_only_and_displays_with_canonical_casing():
    """"SurfClean" (mixed case) is canonical -- corrected 2026-09-29,
    direct user correction: an earlier belief that this lowercases to
    "Surfclean" was actually about the LEGACY macro's own intake-side
    matching, not about what the real output displays. South-only: the
    database also holds North SurfClean limits (from Access), but the
    validated SX5-N template has no SurfClean sheet."""
    assert _build("SurfClean", "SX5S").chemical_label == "SurfClean"
    with pytest.raises(ValueError):
        _build("SurfClean", "SX5N")


def test_element_panel_without_limits_on_file_raises():
    with pytest.raises(ValueError, match="specification limits"):
        _build("NH4OH", data=SX5SpecData(qc_code="QC-TEST"))


def test_element_panel_without_qc_code_on_file_raises():
    with pytest.raises(ValueError, match="QC code"):
        _build("NH4OH", data=SX5SpecData(specs={"Al": 0.1}))


# ---------------------------------------------------------------------------
# Assay category
# ---------------------------------------------------------------------------

def test_cslx001_uses_c4():
    assert _build("CSLX001").name_cell_address == "C4"


def test_wx7808_works_on_both_locations():
    for location in ("SX5N", "SX5S"):
        assert _build("WX7808", location).name_cell_address == "C4"


def test_display_label_from_the_database_drives_label_and_sample_string():
    """SX5-North's WX2000 displays as "2to1WX2000" (a real customer need,
    stored as chemical_report_settings.display_label); with no label on
    file the canonical name shows."""
    n = _build("WX2000", "SX5N", data=SX5SpecData(assay_spec_text="1 - 2", display_label="2to1WX2000"))
    s = _build("WX2000", "SX5S", data=SX5SpecData(assay_spec_text="1 - 2"))
    assert n.chemical_label == "2to1WX2000"
    assert "-2to1WX2000-SX5N-" in n.sample_string
    assert s.chemical_label == "WX2000"
    # both use the C5 cell (matches "*WX2000" via the label, not the raw name)
    assert n.name_cell_address == "C5"
    assert s.name_cell_address == "C5"


def test_assay_spec_range_comes_from_the_database():
    result = _build("WX2000", data=SX5SpecData(assay_spec_text="1.916 - 2.173   H2O2 % "))
    assert result.sections[0].rows[-1].get_value(1) == "1.916 - 2.173   H2O2 % "


def test_assay_without_spec_range_on_file_raises():
    with pytest.raises(ValueError, match="assay spec range"):
        _build("CSLX001", data=SX5SpecData())


# ---------------------------------------------------------------------------
# Composite category
# ---------------------------------------------------------------------------

_ANIONS_AND_ASSAY_REQUESTED = frozenset({"4 Anions", "Assay"})


def test_composite_with_nothing_else_requested_is_a_plain_element_panel():
    """Confirmed real (2026-09-03): the anion block and embedded Assay are
    NOT unconditional -- a real non-routine composite sample with neither
    Anions nor Titrations selected on its TR form gets neither block,
    just the plain element panel, same shape as an Element-category
    chemical. Its anion limits must not leak in as element rows."""
    result = _build("0.49%HF")
    assert len(result.sections) == 1
    assert not any(row.get_value(2) == "Chloride" for row in result.sections[0].rows)
    assert not any(row.get_value(3) == "Cl" for row in result.sections[0].rows)


def test_composite_anions_requested_but_not_assay_adds_only_the_anion_rows():
    result = _build("0.49%HF", requested=frozenset({"4 Anions"}))
    assert len(result.sections) == 1
    assert any(row.get_value(2) == "Chloride" for row in result.sections[0].rows)


def test_composite_assay_requested_but_not_anions_adds_only_the_assay_section():
    result = _build("0.49%HF", requested=frozenset({"Assay"}))
    assert len(result.sections) == 2
    assert result.sections[1].id == "0.49%HF_Assay"
    assert not any(row.get_value(2) == "Chloride" for row in result.sections[0].rows)


def test_composite_produces_two_sections_element_panel_plus_embedded_assay():
    result = _build("0.49%HF", requested=_ANIONS_AND_ASSAY_REQUESTED)
    assert len(result.sections) == 2
    assert result.sections[1].id == "0.49%HF_Assay"
    assert result.sections[1].rows[-1].get_value(1) == "1.0 - 2.0"


def test_composite_report_note_comes_from_the_database():
    with_note = _build(
        "0.49%HF", requested=_ANIONS_AND_ASSAY_REQUESTED,
        data=SX5SpecData(specs=_DATA.specs, qc_code="QC", assay_spec_text="1 - 2", report_note="A note"),
    )
    without = _build("0.49%HF", "SX5S", requested=_ANIONS_AND_ASSAY_REQUESTED)
    assert with_note.sections[1].rows[-1].get_value(5) == "A note"
    assert without.sections[1].rows[-1].get_value(5) is None


def test_composite_anions_requested_without_anion_limits_on_file_raises():
    data = SX5SpecData(specs={"Al": 0.1}, qc_code="QC", assay_spec_text="1 - 2")
    with pytest.raises(ValueError, match="anion specification limits"):
        _build("0.49%HF", requested=frozenset({"4 Anions"}), data=data)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

def test_unknown_chemical_raises():
    with pytest.raises(ValueError):
        _build("Not A Real Chemical")


def test_is_supported_chemical_is_case_insensitive():
    """Confirmed real (2026-09-23): a live production failure where the
    database had "HCL" against this module's "HCl" -- a human reads those
    as the same chemical, this module should too."""
    assert orchestrator.is_supported_chemical("HCL") is True
    assert orchestrator.is_supported_chemical("hcl") is True
    assert orchestrator.is_supported_chemical("HCl") is True
    assert orchestrator.is_supported_chemical("Not A Real Chemical") is False


def test_build_non_routine_report_chemical_name_is_case_insensitive():
    assert _build("HCL").chemical_label == "HCl"


# ---------------------------------------------------------------------------
# column_widths
# ---------------------------------------------------------------------------

def test_element_category_uses_sx5_element_widths():
    assert _build("NH4OH").column_widths == column_widths.SX5_ELEMENT


def test_assay_category_uses_sx5_assay_widths():
    assert _build("CSLX001").column_widths == column_widths.SX5_ASSAY


def test_composite_category_uses_sx5_element_widths():
    assert _build("0.49%HF").column_widths == column_widths.SX5_ELEMENT
