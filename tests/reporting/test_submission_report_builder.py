from dataclasses import dataclass
from datetime import date, datetime

import pytest

from slim_domain.domain.customer.customer import Customer
from slim_domain.domain.specification.specification import ChemicalReportSetting
from slim_domain.domain.tr.enums import ProcessingTime, RequestType
from slim_domain.domain.tr.tr_sample import TRSample
from slim_domain.domain.tr.tr_submission import TRSubmission

from slim_report_engine.reporting import column_widths, submission_report_builder as dispatcher


@dataclass(frozen=True)
class _FakeAnalysis:
    name: str


class _FakeAnalysisService:
    def __init__(self, id_to_name: dict[int, str]) -> None:
        self._id_to_name = id_to_name

    def load_analysis(self, analysis_id: int):
        name = self._id_to_name.get(analysis_id)
        return _FakeAnalysis(name) if name is not None else None


@dataclass(frozen=True)
class _FakeChemical:
    id: int
    name: str
    metals_prep: str = ""
    metals_instrument: str = "ICPMS"
    ions_prep: str = ""
    ked_element_ids: frozenset[int] = frozenset()


class _FakeChemicalService:
    def __init__(self, id_to_chemical: dict[int, _FakeChemical] | None = None) -> None:
        self._id_to_chemical = id_to_chemical or {}

    def load_chemical(self, chemical_id: int):
        return self._id_to_chemical.get(chemical_id)


@dataclass(frozen=True)
class _FakeElement:
    id: int
    name: str
    symbol: str


class _FakeElementService:
    _BY_ID = {101: _FakeElement(id=101, name="Antimony", symbol="Sb")}

    def get_by_symbol(self, symbol: str):
        return _FakeElement(id=0, name=symbol, symbol=symbol)

    def get_by_name(self, name: str):
        return next((e for e in self._BY_ID.values() if e.name == name), None)

    def load_element(self, element_id: int):
        return self._BY_ID.get(element_id)


# Invented SX5 data, returned for any site-split (location) lookup -- the
# real values live in the database and are checked by tests/golden.
_SX5_TEST_SPECS = {"Al": 0.1, "Cl": 40, "NO3": 60, "SO4": 30, "PO4": 10}
_SX5_TEST_SETTING = ChemicalReportSetting(customer_id=2, location="SX5N", chemical_id=9, assay_spec_text="1 - 2")


class _FakeSpecificationService:
    """Defaults to "no specs on file" for everything -- specs_by_ids lets
    a test opt a specific (customer_id, chemical_id) into real values.
    unit_overrides_by_ids: same idea for get_unit_override -- defaults to
    None (the standard ppb wording) unless a test opts a pair in."""

    def __init__(
        self,
        specs_by_ids: dict[tuple[int, int], dict[str, float]] | None = None,
        unit_overrides_by_ids: dict[tuple[int, int], str] | None = None,
    ) -> None:
        self._specs_by_ids = specs_by_ids or {}
        self._unit_overrides_by_ids = unit_overrides_by_ids or {}

    def get_specs(self, customer_id: int, chemical_id: int, location: str = "") -> dict[str, float]:
        if location:
            return dict(_SX5_TEST_SPECS)
        return dict(self._specs_by_ids.get((customer_id, chemical_id), {}))

    def get_category_label(
        self, customer_id: int, chemical_id: int, location: str = "", kind: str = "specification"
    ) -> str | None:
        return "QC-TEST" if location else None

    def get_warning_limits(self, customer_id: int, chemical_id: int, location: str = "") -> dict[str, float]:
        return {}

    def limits_owner(self, customer_id: int, chemical_id: int, parent_customer_id: int | None) -> int:
        own = (customer_id, chemical_id) in self._specs_by_ids
        return customer_id if own or parent_customer_id is None else parent_customer_id

    def get_report_setting(self, customer_id: int, chemical_id: int, location: str = ""):
        return _SX5_TEST_SETTING if location else None

    def get_unit_override(self, customer_id: int, chemical_id: int) -> str | None:
        return self._unit_overrides_by_ids.get((customer_id, chemical_id))


_CUSTOMER = Customer(
    id=1, name="Customer ea6f9", street_address="1 Main St",
    city="Springfield", state="IL", postal_code="62701", country="USA",
)
_SX5 = Customer(
    id=2, name="SX5", street_address="1 Fab Way",
    city="Austin", state="TX", postal_code="78701", country="USA",
)


def _sample(
    name: str,
    analysis_ids=(),
    chemical_id: int = 0,
    processing_time=ProcessingTime.NEXT_DAY,
    reporting_units="",
    form_chemical_name="Test Acid",
    additional_element_ids=(),
) -> TRSample:
    return TRSample(
        sample_name=name,
        form_chemical_name=form_chemical_name,
        processing_time=processing_time,
        additional_notes="",
        requested_time="",
        chemical_id=chemical_id,
        analysis_ids=analysis_ids,
        reporting_units=reporting_units,
        additional_element_ids=additional_element_ids,
    )


def _submission(
    samples: list[TRSample], request_type=RequestType.CHEMICAL, customer_id=1, file_name="test.xlsx"
) -> TRSubmission:
    return TRSubmission(
        customer_id=customer_id,
        date_submitted=date(2026, 3, 4),
        date_received=date(2026, 3, 5),
        request_type=request_type,
        customer_contact="Jane Doe",
        customer_phone="555-0100",
        po_information="",
        credit_card_information="",
        file_name=file_name,
        service_date=date(1901, 1, 1),
        download_date=datetime(2026, 3, 5, 12, 0, 0),
        form_customer_name="Customer ea6f9",
        form_customer_address="",
        form_customer_address_2="",
        samples=tuple(samples),
    )


def test_generic_chemical_customer_one_sheet_per_sample():
    samples = [
        _sample("S-001", analysis_ids=(1,), chemical_id=1),
        _sample("S-002", analysis_ids=(1,), chemical_id=1),
    ]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "TOC"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    assert len(sheets) == 2
    # Confirmed real (SetChemicalSheetName): tab name is the CHEMICAL
    # MATRIX, not the Sample ID -- both samples share "Test Acid" here,
    # so both get numbered "Test Acid 1"/"Test Acid 2".
    assert sheets[0].name == "Test Acid 1"
    assert sheets[1].name == "Test Acid 2"
    assert sheets[0].header_title == "Test Acid"
    # No more separate "A1" stamp -- the header preamble's own title row
    # sets column 1 of row 1 directly (see build_header_preamble).
    assert sheets[0].extra_cell_stamps == ()
    assert sheets[0].sections[0].id == "Header"
    assert sheets[0].sections[0].rows[0].get_value(1) == "Test Acid"


def test_generic_chemical_sample_string_stamped_into_every_section():
    """The behavior the user asked to confirm/fix: the standard
    "mmddyy-Chemical-Customer-SampleID" string (built the same way SX5/
    Wafer build theirs) lands in column 4 of EVERY REAL section's own
    "Sample Identification:" row -- not just the sheet's first real
    section, and not the header preamble (which has no such row at all)
    -- matching row_builders.py's "every section on a sheet shares it"
    framing."""
    samples = [_sample("S-001", analysis_ids=(1, 2), chemical_id=1, form_chemical_name="Test Acid Matrix")]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "TOC", 2: "Alkalinity"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    expected = "030526-Test Acid Matrix-Customer ea6f9-S-001"
    real_sections = sheets[0].sections[1:]  # sections[0] is the header preamble
    assert len(real_sections) == 2
    for section in real_sections:
        assert section.rows[0].get_value(4) == expected


def test_water_sample_string_uses_the_literal_water_chemical_name():
    samples = [_sample("S-001", analysis_ids=(1,))]
    submission = _submission(samples, request_type=RequestType.WATER)
    analysis_svc = _FakeAnalysisService({1: "TOC"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    assert sheets[0].sections[1].rows[0].get_value(4) == "030526-Water-Customer ea6f9-S-001"


def test_sample_with_multiple_independent_analyses_lands_on_one_sheet():
    """The behavior under test directly: a single physical sample
    requesting several independent analyses (here 36 Elements, TOC, and
    Alkalinity -- none of which combine like Conductivity+pH does) gets
    exactly ONE OutputSheet carrying all of their sections, not one
    sheet per analysis. Matches the real VBA architecture, which
    creates one new sheet per SAMPLE ROW and unions every requested
    analysis range onto that same sheet."""
    samples = [_sample("S-001", analysis_ids=(1, 2, 3), chemical_id=1)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "36 Elements", 2: "TOC", 3: "Alkalinity"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )

    assert len(sheets) == 1  # one sheet total, not three
    assert sheets[0].name == "Test Acid"  # only sample with this chemical matrix -- no numeric suffix
    assert [s.id for s in sheets[0].sections] == ["Header", "36 Elements", "TOC", "Alkalinity"]


def test_water_customer_header_title_is_water():
    samples = [_sample("S-001", analysis_ids=(1,))]
    submission = _submission(samples, request_type=RequestType.WATER)
    analysis_svc = _FakeAnalysisService({1: "TOC"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    assert sheets[0].header_title == "Water"


def test_sx5_customer_supported_chemical_routes_to_sx5_builder():
    samples = [_sample("S-001", chemical_id=9)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL, customer_id=2, file_name="092226-SXOS5 North HCl-1.xlsx")
    chemical_svc = _FakeChemicalService({9: _FakeChemical(id=9, name="NH4OH")})
    sheets = dispatcher.build_submission_sheets(
        submission, _SX5, chemical_svc, _FakeAnalysisService({}), _FakeElementService(), _FakeSpecificationService()
    )
    assert len(sheets) == 1
    assert sheets[0].name == "NH4OH"
    assert len(sheets[0].extra_cell_stamps) == 1
    cell_address, value = sheets[0].extra_cell_stamps[0]
    assert cell_address == "D5"
    assert "NH4OH" in value


def test_sx5_composite_chemical_with_nothing_else_requested_gets_plain_panel():
    """End-to-end wiring check: the dispatcher resolves the sample's OTHER
    analysis selections and passes them to sx5_non_routine_report_builder
    -- confirmed real, a Composite chemical with no Anions/Titrations
    selected gets no anion block, no embedded Assay."""
    samples = [_sample("S-001", chemical_id=9)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL, customer_id=2, file_name="092226-SXOS5 North HCl-1.xlsx")
    chemical_svc = _FakeChemicalService({9: _FakeChemical(id=9, name="0.49%HF")})
    sheets = dispatcher.build_submission_sheets(
        submission, _SX5, chemical_svc, _FakeAnalysisService({}), _FakeElementService(), _FakeSpecificationService()
    )
    assert len(sheets[0].sections) == 1


def test_sx5_composite_chemical_with_anions_and_assay_requested_gets_both_blocks():
    samples = [_sample("S-001", analysis_ids=(1, 2), chemical_id=9)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL, customer_id=2, file_name="092226-SXOS5 North HCl-1.xlsx")
    chemical_svc = _FakeChemicalService({9: _FakeChemical(id=9, name="0.49%HF")})
    analysis_svc = _FakeAnalysisService({1: "4 Anions", 2: "Assay"})
    sheets = dispatcher.build_submission_sheets(submission, _SX5, chemical_svc, analysis_svc, _FakeElementService(), _FakeSpecificationService())
    assert len(sheets[0].sections) == 2
    assert sheets[0].sections[1].id == "0.49%HF_Assay"


def test_sx5_customer_unsupported_chemical_raises():
    samples = [_sample("S-001", chemical_id=9)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL, customer_id=2, file_name="092226-SXOS5 North HCl-1.xlsx")
    chemical_svc = _FakeChemicalService({9: _FakeChemical(id=9, name="Not A Real SX5 Chemical")})
    with pytest.raises(ValueError, match="not one of the 21 chemicals"):
        dispatcher.build_submission_sheets(
            submission, _SX5, chemical_svc, _FakeAnalysisService({}), _FakeElementService(), _FakeSpecificationService()
        )


def test_wafer_request_type_routes_to_wafer_builder_regardless_of_customer():
    samples = [_sample("Slot-1", analysis_ids=(1,), reporting_units="atoms/cm^2", form_chemical_name="150mm")]
    submission = _submission(samples, request_type=RequestType.WAFER)
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    assert len(sheets) == 1
    assert sheets[0].header_title == "150mm Wafers"
    # A1's title moved to its own styled field (2026-09-25, direct user
    # correction, Custc4ea4): extra_cell_stamps writes plain unstyled values,
    # but the title needs real font styling (report_writer.apply_title_cell).
    assert sheets[0].extra_cell_stamps == ()
    assert sheets[0].title_cell_stamp == ("A1", "150mm Wafers")


def test_wafer_default_processing_time_gets_no_tab_name_suffix():
    """Confirmed real (2026-09-28, a real Wafer dummy TR run through the
    legacy macro): a plain (unstamped) processing time gets NO suffix on
    the tab name at all, e.g. a lone real "100mm Wafers" tab -- matching
    the same set of "notable" processing times _PROCESSING_TIME_STAMP_
    COLORS already tracks for the D1 stamp."""
    samples = [_sample("Slot-1", analysis_ids=(1,), reporting_units="atoms/cm^2", form_chemical_name="150mm", processing_time=ProcessingTime.NEXT_DAY)]
    submission = _submission(samples, request_type=RequestType.WAFER)
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    assert sheets[0].name == "150mm Wafers"
    assert sheets[0].header_title == "150mm Wafers"  # A1's title is unaffected either way


def test_wafer_notable_processing_time_gets_tab_name_suffix():
    """Confirmed real: the Excel TAB NAME (unlike A1's title or the D1
    stamp, both unaffected) carries the processing-time label too, e.g.
    real tabs "150mm Wafers Next Day RUSH 1", "200mm Wafers Call-in
    RUSH"."""
    samples = [_sample("Slot-1", analysis_ids=(1,), reporting_units="atoms/cm^2", form_chemical_name="150mm", processing_time=ProcessingTime.CALL_IN_RUSH)]
    submission = _submission(samples, request_type=RequestType.WAFER)
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    assert sheets[0].name == "150mm Wafers Call-in RUSH"
    assert sheets[0].header_title == "150mm Wafers"


def test_wafer_duplicate_title_and_processing_time_gets_numbered_suffix():
    """Confirmed real: two Wafer samples sharing size AND processing time
    but a DIFFERENT element/anion selection stay as two separate results
    (wafer_submission_builder groups by the full (units, size, selection,
    processing_time) key, so identical selections would merge into ONE
    result, not two -- this varies the selection to keep them distinct)
    and get " 1"/" 2" appended to their shared combined name, same
    convention as _chemical_matrix_tab_names -- e.g. real "150mm Wafers
    Next Day RUSH 1"/"...2"."""
    samples = [
        _sample("Slot-1", analysis_ids=(1,), reporting_units="atoms/cm^2", form_chemical_name="150mm", processing_time=ProcessingTime.NEXT_DAY_RUSH),
        _sample("Slot-2", analysis_ids=(2,), reporting_units="atoms/cm^2", form_chemical_name="150mm", processing_time=ProcessingTime.NEXT_DAY_RUSH),
    ]
    submission = _submission(samples, request_type=RequestType.WAFER)
    analysis_svc = _FakeAnalysisService({1: "36 Elements", 2: "67 Elements"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    assert len(sheets) == 2
    assert sheets[0].name == "150mm Wafers Next Day RUSH 1"
    assert sheets[1].name == "150mm Wafers Next Day RUSH 2"


def test_wafer_different_processing_times_are_not_grouped_as_duplicates():
    """Two Wafer samples with the SAME size but DIFFERENT notable
    processing times must not be numbered against each other -- their
    combined names already differ, so each is unique on its own."""
    samples = [
        _sample("Slot-1", analysis_ids=(1,), reporting_units="atoms/cm^2", form_chemical_name="150mm", processing_time=ProcessingTime.CALL_IN_RUSH),
        _sample("Slot-2", analysis_ids=(1,), reporting_units="atoms/cm^2", form_chemical_name="150mm", processing_time=ProcessingTime.SAME_DAY_RUSH),
    ]
    submission = _submission(samples, request_type=RequestType.WAFER)
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    assert sheets[0].name == "150mm Wafers Call-in RUSH"
    assert sheets[1].name == "150mm Wafers Same Day RUSH"


def test_duplicate_chemical_matrix_gets_numbered_not_deduplicated_with_parens():
    """Confirmed real (SetChemicalSheetName): samples sharing a chemical
    matrix get "X 1"/"X 2" -- not the generic "(2)" collision suffix,
    which is now only a fallback for names _generic_tab_names didn't
    already handle."""
    samples = [
        _sample("S-001", analysis_ids=(1,), form_chemical_name="Same Name"),
        _sample("S-002", analysis_ids=(1,), form_chemical_name="Same Name"),
    ]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "TOC"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    assert sheets[0].name == "Same Name 1"
    assert sheets[1].name == "Same Name 2"


def test_generic_chemical_sheet_uses_standard_column_widths():
    samples = [_sample("S-001", analysis_ids=(1,), chemical_id=1)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "TOC"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    assert sheets[0].column_widths == column_widths.STANDARD


def test_sx5_sheet_uses_sx5_element_column_widths():
    samples = [_sample("S-001", chemical_id=9)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL, customer_id=2, file_name="092226-SXOS5 North HCl-1.xlsx")
    chemical_svc = _FakeChemicalService({9: _FakeChemical(id=9, name="NH4OH")})
    sheets = dispatcher.build_submission_sheets(
        submission, _SX5, chemical_svc, _FakeAnalysisService({}), _FakeElementService(), _FakeSpecificationService()
    )
    assert sheets[0].column_widths == column_widths.SX5_ELEMENT


def test_sx5_sheet_zoom_is_90():
    samples = [_sample("S-001", chemical_id=9)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL, customer_id=2, file_name="092226-SXOS5 North HCl-1.xlsx")
    chemical_svc = _FakeChemicalService({9: _FakeChemical(id=9, name="NH4OH")})
    sheets = dispatcher.build_submission_sheets(
        submission, _SX5, chemical_svc, _FakeAnalysisService({}), _FakeElementService(), _FakeSpecificationService()
    )
    assert sheets[0].zoom == 90


def test_wafer_sheet_uses_wafer_column_widths():
    samples = [_sample("Slot-1", analysis_ids=(1,), reporting_units="atoms/cm^2", form_chemical_name="150mm")]
    submission = _submission(samples, request_type=RequestType.WAFER)
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    assert sheets[0].column_widths == column_widths.WAFER


def test_wafer_sheet_zoom_is_95():
    samples = [_sample("Slot-1", analysis_ids=(1,), reporting_units="atoms/cm^2", form_chemical_name="150mm")]
    submission = _submission(samples, request_type=RequestType.WAFER)
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    assert sheets[0].zoom == 95


# ---------------------------------------------------------------------------
# processing_time_stamp (confirmed real: RUSH variants = red, Time Limited =
# blue, plain Next Day/Two Days/Three Days = no stamp at all)
# ---------------------------------------------------------------------------

def test_generic_chemical_next_day_has_no_processing_time_stamp():
    samples = [_sample("S-001", analysis_ids=(1,), chemical_id=1, processing_time=ProcessingTime.NEXT_DAY)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "TOC"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    assert sheets[0].processing_time_stamp is None


def test_generic_chemical_same_day_rush_stamp():
    samples = [_sample("S-001", analysis_ids=(1,), chemical_id=1, processing_time=ProcessingTime.SAME_DAY_RUSH)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "TOC"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    assert sheets[0].processing_time_stamp == ("D1", "Same Day RUSH", "red", 10)


def test_generic_chemical_time_limited_stamp():
    samples = [_sample("S-001", analysis_ids=(1,), chemical_id=1, processing_time=ProcessingTime.TIME_LIMITED)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "TOC"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    assert sheets[0].processing_time_stamp == ("D1", "Next Day Time Limited", "blue", 10)


def test_generic_chemical_call_in_rush_stamp():
    samples = [_sample("S-001", analysis_ids=(1,), chemical_id=1, processing_time=ProcessingTime.CALL_IN_RUSH)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "TOC"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    assert sheets[0].processing_time_stamp == ("D1", "Call-in RUSH", "red", 10)


def test_generic_chemical_two_days_and_three_days_have_no_stamp():
    for pt in (ProcessingTime.TWO_DAYS, ProcessingTime.THREE_DAYS):
        samples = [_sample("S-001", analysis_ids=(1,), chemical_id=1, processing_time=pt)]
        submission = _submission(samples, request_type=RequestType.CHEMICAL)
        analysis_svc = _FakeAnalysisService({1: "TOC"})
        sheets = dispatcher.build_submission_sheets(
            submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
        )
        assert sheets[0].processing_time_stamp is None


def test_sx5_sheet_same_day_rush_stamp_at_e1():
    samples = [_sample("S-001", chemical_id=9, processing_time=ProcessingTime.SAME_DAY_RUSH)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL, customer_id=2, file_name="092226-SXOS5 North HCl-1.xlsx")
    chemical_svc = _FakeChemicalService({9: _FakeChemical(id=9, name="NH4OH")})
    sheets = dispatcher.build_submission_sheets(
        submission, _SX5, chemical_svc, _FakeAnalysisService({}), _FakeElementService(), _FakeSpecificationService()
    )
    assert sheets[0].processing_time_stamp == ("E1", "Same Day RUSH", "red", 10)


def test_wafer_sheet_next_day_rush_stamp_at_d1_size_12():
    samples = [
        _sample(
            "Slot-1", analysis_ids=(1,), reporting_units="atoms/cm^2", form_chemical_name="150mm",
            processing_time=ProcessingTime.NEXT_DAY_RUSH,
        )
    ]
    submission = _submission(samples, request_type=RequestType.WAFER)
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    assert sheets[0].processing_time_stamp == ("D1", "Next Day RUSH", "red", 12)


def test_wafer_sheet_next_day_has_no_stamp():
    samples = [
        _sample(
            "Slot-1", analysis_ids=(1,), reporting_units="atoms/cm^2", form_chemical_name="150mm",
            processing_time=ProcessingTime.NEXT_DAY,
        )
    ]
    submission = _submission(samples, request_type=RequestType.WAFER)
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    assert sheets[0].processing_time_stamp is None


def test_chemical_sample_uses_the_resolved_chemicals_catalog_prep():
    samples = [_sample("S-001", analysis_ids=(1,), chemical_id=1)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    chemical_svc = _FakeChemicalService({1: _FakeChemical(id=1, name="Test Acid", metals_prep="ICPMS Digestion")})
    sheets = dispatcher.build_submission_sheets(submission, _CUSTOMER, chemical_svc, analysis_svc, _FakeElementService(), _FakeSpecificationService())
    footer = next(
        r for r in sheets[0].sections[1].rows if r.get_value(1) and "Analysis by ICPMS" in str(r.get_value(1))
    )
    assert footer.get_value(1) == "Analysis by ICPMS (ICPMS Digestion)"


def test_chemical_sample_with_ked_elements_gets_pr_in45_in_test_methods():
    """Confirmed real (lab's own SOP master list, cross-checked against
    Chemical.ked_element_ids): a chemical with KED elements on file gets
    SOP-45 added to its metals panel's Test Methods line."""
    samples = [_sample("S-001", analysis_ids=(1,), chemical_id=1)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    chemical_svc = _FakeChemicalService(
        {1: _FakeChemical(id=1, name="Test Acid", metals_prep="Dilute and Shoot", ked_element_ids=frozenset({7}))}
    )
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, chemical_svc, analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    test_methods = next(
        r for r in sheets[0].sections[1].rows if r.get_value(1) and "Test Methods" in str(r.get_value(1))
    )
    assert test_methods.get_value(1) == "Test Methods: SOP-14, SOP-45 and SOP-48."


def test_chemical_sample_without_ked_elements_gets_no_pr_in45():
    samples = [_sample("S-001", analysis_ids=(1,), chemical_id=1)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    chemical_svc = _FakeChemicalService(
        {1: _FakeChemical(id=1, name="Test Acid", metals_prep="Dilute and Shoot")}
    )
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, chemical_svc, analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    test_methods = next(
        r for r in sheets[0].sections[1].rows if r.get_value(1) and "Test Methods" in str(r.get_value(1))
    )
    assert test_methods.get_value(1) == "Test Methods: SOP-14 and SOP-48."


def test_water_sample_never_gets_ked_elements_check():
    """Water has no Chemical record to read ked_element_ids from at all --
    has_ked_elements must be False, never guessed."""
    samples = [_sample("S-001", analysis_ids=(1,))]
    submission = _submission(samples, request_type=RequestType.WATER)
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    chemical_svc = _FakeChemicalService({})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, chemical_svc, analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    test_methods = next(
        r for r in sheets[0].sections[1].rows if r.get_value(1) and "Test Methods" in str(r.get_value(1))
    )
    assert test_methods.get_value(1) == "Test Methods: SOP-14 and SOP-48."


def test_generic_sample_gets_inferred_date_of_analysis_in_every_footer():
    """Confirmed real (direct user request): the "Date of Analysis: "
    placeholder gets a real inferred value (check-in + turnaround, weekend-
    aware -- see date_of_analysis.py) instead of staying blank. date_received
    is a Thursday (see _submission) and the default ProcessingTime.NEXT_DAY
    is 1 business day, so the expected date is the very next day, Friday."""
    samples = [_sample("S-001", analysis_ids=(1, 2), chemical_id=1)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "36 Elements", 2: "TOC"})
    chemical_svc = _FakeChemicalService({1: _FakeChemical(id=1, name="Test Acid", metals_prep="Evaporation")})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, chemical_svc, analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    date_cells = [
        r.get_value(4) for section in sheets[0].sections for r in section.rows
        if r.get_value(4) and "Date of Analysis" in str(r.get_value(4))
    ]
    assert date_cells == ["Date of Analysis: 03-06-26", "Date of Analysis: 03-06-26"]


def test_chemical_sample_uses_the_resolved_customer_and_chemicals_real_specs():
    samples = [_sample("S-001", analysis_ids=(1,), chemical_id=1)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    chemical_svc = _FakeChemicalService({1: _FakeChemical(id=1, name="Test Acid")})
    spec_svc = _FakeSpecificationService({(_CUSTOMER.id, 1): {"Al": 0.3}})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, chemical_svc, analysis_svc, _FakeElementService(), spec_svc
    )
    al_row = next(r for r in sheets[0].sections[1].rows if r.get_value(3) == "Al")
    assert al_row.limits == {"specification": 0.3}


def test_water_sample_never_gets_specs_no_chemical_record_to_key_on():
    samples = [_sample("S-001", analysis_ids=(1,))]
    submission = _submission(samples, request_type=RequestType.WATER)
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    # even if the fake service WOULD return something for this pair, Water
    # has no Chemical record to resolve chemical_id from at all
    spec_svc = _FakeSpecificationService({(_CUSTOMER.id, 0): {"Al": 0.3}})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), spec_svc
    )
    al_row = next(r for r in sheets[0].sections[1].rows if r.get_value(3) == "Al")
    assert al_row.get_value(1) is None


def test_chemical_sample_with_no_unit_override_uses_the_default_ppb_wording():
    samples = [_sample("S-001", analysis_ids=(1,), chemical_id=1)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    chemical_svc = _FakeChemicalService({1: _FakeChemical(id=1, name="Test Acid")})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, chemical_svc, analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    units_row = sheets[0].sections[0].rows[3]
    assert units_row.get_value(1) == "All data in units of ppb unless otherwise noted"


def test_chemical_sample_with_a_real_unit_override_substitutes_it_into_the_preamble():
    """Confirmed real (modReportCreator.bas's Get_Specs, direct VBA source
    check 2026-09-28; matches a real completed report, Customer a359c's
    PG, unit "ppm" on file): the preamble's own "ppb" gets replaced with
    whatever real unit the customer+chemical's specs are on file in."""
    samples = [_sample("S-001", analysis_ids=(1,), chemical_id=1)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    chemical_svc = _FakeChemicalService({1: _FakeChemical(id=1, name="PG")})
    spec_svc = _FakeSpecificationService(unit_overrides_by_ids={(_CUSTOMER.id, 1): "ppm"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, chemical_svc, analysis_svc, _FakeElementService(), spec_svc
    )
    units_row = sheets[0].sections[0].rows[3]
    assert units_row.get_value(1) == "All data in units of ppm unless otherwise noted"


def test_water_sample_never_gets_a_unit_override_no_chemical_record_to_key_on():
    samples = [_sample("S-001", analysis_ids=(1,))]
    submission = _submission(samples, request_type=RequestType.WATER)
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    # even if the fake service WOULD return something for this pair, Water
    # has no Chemical record to resolve chemical_id from at all
    spec_svc = _FakeSpecificationService(unit_overrides_by_ids={(_CUSTOMER.id, 0): "ppm"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), spec_svc
    )
    units_row = sheets[0].sections[0].rows[3]
    assert units_row.get_value(1) == "All data in units of ppb unless otherwise noted"


def test_chemical_sample_uses_the_resolved_chemicals_catalog_instrument():
    """Confirmed real: a very dirty/nasty matrix, or one that itself
    contains a metal (e.g. NaOH), gets its Chemical.metals_instrument
    manually set to ICPOES during the quote process."""
    samples = [_sample("S-001", analysis_ids=(1,), chemical_id=1)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    chemical_svc = _FakeChemicalService({1: _FakeChemical(id=1, name="Test Acid", metals_instrument="ICPOES")})
    sheets = dispatcher.build_submission_sheets(submission, _CUSTOMER, chemical_svc, analysis_svc, _FakeElementService(), _FakeSpecificationService())
    footer = next(r for r in sheets[0].sections[1].rows if r.get_value(1) and "Analysis by" in str(r.get_value(1)))
    assert footer.get_value(1) == "Analysis by ICP-OES (Evaporation)"


def test_chemical_sample_with_blank_catalog_instrument_defaults_to_icpms():
    samples = [_sample("S-001", analysis_ids=(1,), chemical_id=1)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    chemical_svc = _FakeChemicalService({1: _FakeChemical(id=1, name="Test Acid")})
    sheets = dispatcher.build_submission_sheets(submission, _CUSTOMER, chemical_svc, analysis_svc, _FakeElementService(), _FakeSpecificationService())
    footer = next(r for r in sheets[0].sections[1].rows if r.get_value(1) and "Analysis by" in str(r.get_value(1)))
    assert "ICPMS" in footer.get_value(1)


def test_water_sample_always_uses_icpms_no_chemical_lookup():
    samples = [_sample("S-001", analysis_ids=(1,))]
    submission = _submission(samples, request_type=RequestType.WATER)
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    footer = next(r for r in sheets[0].sections[1].rows if r.get_value(1) and "Analysis by" in str(r.get_value(1)))
    assert "ICPMS" in footer.get_value(1)


def test_chemical_sample_with_blank_catalog_prep_defaults_to_evaporation():
    samples = [_sample("S-001", analysis_ids=(1,), chemical_id=1)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    chemical_svc = _FakeChemicalService({1: _FakeChemical(id=1, name="Test Acid")})  # metals_prep="" (blank)
    sheets = dispatcher.build_submission_sheets(submission, _CUSTOMER, chemical_svc, analysis_svc, _FakeElementService(), _FakeSpecificationService())
    footer = next(
        r for r in sheets[0].sections[1].rows if r.get_value(1) and "Analysis by ICPMS" in str(r.get_value(1))
    )
    assert footer.get_value(1) == "Analysis by ICPMS (Evaporation)"


def test_water_sample_always_uses_dilute_and_shoot_no_chemical_lookup():
    samples = [_sample("S-001", analysis_ids=(1,))]
    submission = _submission(samples, request_type=RequestType.WATER)
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    footer = next(
        r for r in sheets[0].sections[1].rows if r.get_value(1) and "Analysis by ICPMS" in str(r.get_value(1))
    )
    assert footer.get_value(1) == "Analysis by ICPMS (Dilute and Shoot)"


# ---------------------------------------------------------------------------
# ions_prep_text (a SEPARATE catalog field from metals_prep -- see
# _ions_prep_text's own docstring for the real correction this fixes)
# ---------------------------------------------------------------------------

def test_chemical_sample_with_no_ions_prep_on_file_gets_bare_ic_footer():
    samples = [_sample("S-001", analysis_ids=(1,), chemical_id=1)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "4 Anions"})
    chemical_svc = _FakeChemicalService({1: _FakeChemical(id=1, name="Test Acid", metals_prep="Evaporation")})
    sheets = dispatcher.build_submission_sheets(submission, _CUSTOMER, chemical_svc, analysis_svc, _FakeElementService(), _FakeSpecificationService())
    footer = next(r for r in sheets[0].sections[1].rows if r.get_value(1) and "Analysis by IC" in str(r.get_value(1)))
    assert footer.get_value(1) == "Analysis by IC"


def test_chemical_sample_uses_the_resolved_chemicals_catalog_ions_prep():
    samples = [_sample("S-001", analysis_ids=(1,), chemical_id=1)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "4 Anions"})
    chemical_svc = _FakeChemicalService(
        {1: _FakeChemical(id=1, name="Test Acid", metals_prep="Dilute and Shoot", ions_prep="Evaporation")}
    )
    sheets = dispatcher.build_submission_sheets(submission, _CUSTOMER, chemical_svc, analysis_svc, _FakeElementService(), _FakeSpecificationService())
    footer = next(r for r in sheets[0].sections[1].rows if r.get_value(1) and "Analysis by IC" in str(r.get_value(1)))
    assert footer.get_value(1) == "Analysis by IC (Evaporation)"


def test_chemical_sample_with_dilute_and_shoot_ions_prep_gets_bare_ic_footer():
    """Confirmed real (direct user correction): "Dilute and Shoot" is the
    implied default ion prep by current lab convention, so it gets the
    same bare "Analysis by IC" treatment as no ions_prep on file at all --
    NOT "Analysis by IC (Dilute and Shoot)"."""
    samples = [_sample("S-001", analysis_ids=(1,), chemical_id=1)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "4 Anions"})
    chemical_svc = _FakeChemicalService(
        {1: _FakeChemical(id=1, name="Test Acid", metals_prep="Evaporation", ions_prep="Dilute and Shoot")}
    )
    sheets = dispatcher.build_submission_sheets(submission, _CUSTOMER, chemical_svc, analysis_svc, _FakeElementService(), _FakeSpecificationService())
    footer = next(r for r in sheets[0].sections[1].rows if r.get_value(1) and "Analysis by IC" in str(r.get_value(1)))
    assert footer.get_value(1) == "Analysis by IC"


def test_water_sample_always_gets_bare_ic_footer_no_chemical_lookup():
    samples = [_sample("S-001", analysis_ids=(1,))]
    submission = _submission(samples, request_type=RequestType.WATER)
    analysis_svc = _FakeAnalysisService({1: "4 Anions"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    footer = next(r for r in sheets[0].sections[1].rows if r.get_value(1) and "Analysis by IC" in str(r.get_value(1)))
    assert footer.get_value(1) == "Analysis by IC"


# ---------------------------------------------------------------------------
# zoom (confirmed real: 90% for generic Chemical/Water and SX5, 95% for Wafer)
# ---------------------------------------------------------------------------

def test_generic_chemical_sheet_zoom_is_90():
    samples = [_sample("S-001", analysis_ids=(1,), chemical_id=1)]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    chemical_svc = _FakeChemicalService({1: _FakeChemical(id=1, name="Test Acid")})
    sheets = dispatcher.build_submission_sheets(submission, _CUSTOMER, chemical_svc, analysis_svc, _FakeElementService(), _FakeSpecificationService())
    assert sheets[0].zoom == 90


def test_customer_additional_elements_prep_overrides_only_the_second_footer():
    """The customer-level flag, confirmed real: at least one customer's
    additional elements are run by a different method than their main
    panel. Deliberately customer-agnostic here -- any real customer's
    override value lives only in a real database record, never in this
    public repo (see Customer.additional_elements_prep, slim-domain)."""
    samples = [_sample("S-001", analysis_ids=(1,), chemical_id=1, additional_element_ids=(101,))]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    chemical_svc = _FakeChemicalService({1: _FakeChemical(id=1, name="Test Acid", metals_prep="Evaporation")})
    customer_with_override = _CUSTOMER.model_copy(update={"additional_elements_prep": "Alternate Method"})
    sheets = dispatcher.build_submission_sheets(
        submission, customer_with_override, chemical_svc, analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    footers = [
        r.get_value(1) for r in sheets[0].sections[1].rows if r.get_value(1) and "Analysis by ICPMS" in str(r.get_value(1))
    ]
    assert footers == ["Analysis by ICPMS (Evaporation)", "Analysis by ICPMS (Alternate Method)"]


def test_customer_with_no_additional_elements_prep_override_uses_same_prep_both_times():
    samples = [_sample("S-001", analysis_ids=(1,), chemical_id=1, additional_element_ids=(101,))]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    chemical_svc = _FakeChemicalService({1: _FakeChemical(id=1, name="Test Acid", metals_prep="Evaporation")})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, chemical_svc, analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    footers = [
        r.get_value(1) for r in sheets[0].sections[1].rows if r.get_value(1) and "Analysis by ICPMS" in str(r.get_value(1))
    ]
    assert footers == ["Analysis by ICPMS (Evaporation)", "Analysis by ICPMS (Evaporation)"]


def test_sheet_names_sanitize_illegal_characters():
    samples = [_sample("S-001", analysis_ids=(1,), form_chemical_name="Chem:With/Illegal*Chars")]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "TOC"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    for ch in "[]:*?/\\<>|":
        assert ch not in sheets[0].name


def test_illegal_characters_are_removed_not_replaced_with_a_placeholder():
    """Confirmed real (RemoveIllegalCharacters' Case Else branch): illegal
    sheet-name characters are dropped entirely, not swapped for "_"."""
    samples = [_sample("S-001", analysis_ids=(1,), form_chemical_name="A:B/C")]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "TOC"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    assert sheets[0].name == "ABC"


def test_generic_tab_names_water_single_sample_has_no_number():
    samples = [_sample("S-001", analysis_ids=(1,))]
    submission = _submission(samples, request_type=RequestType.WATER)
    analysis_svc = _FakeAnalysisService({1: "TOC"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    assert sheets[0].name == "Water"


def test_generic_tab_names_water_multiple_samples_all_numbered():
    samples = [
        _sample("S-001", analysis_ids=(1,)),
        _sample("S-002", analysis_ids=(1,)),
        _sample("S-003", analysis_ids=(1,)),
    ]
    submission = _submission(samples, request_type=RequestType.WATER)
    analysis_svc = _FakeAnalysisService({1: "TOC"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    assert [s.name for s in sheets] == ["Water 1", "Water 2", "Water 3"]


def test_generic_tab_names_unique_chemical_matrix_gets_no_number():
    samples = [
        _sample("S-001", analysis_ids=(1,), form_chemical_name="PGME"),
        _sample("S-002", analysis_ids=(1,), form_chemical_name="IPA"),
    ]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "TOC"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    assert [s.name for s in sheets] == ["PGME", "IPA"]


def test_generic_tab_names_mixed_unique_and_duplicate_chemical_matrices():
    samples = [
        _sample("S-001", analysis_ids=(1,), form_chemical_name="NMP"),
        _sample("S-002", analysis_ids=(1,), form_chemical_name="PGME"),
        _sample("S-003", analysis_ids=(1,), form_chemical_name="NMP"),
    ]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "TOC"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    assert [s.name for s in sheets] == ["NMP 1", "PGME", "NMP 2"]


def test_generic_tab_names_truncates_chemical_matrix_to_28_chars_leaving_room_for_suffix():
    long_name = "A" * 40
    samples = [
        _sample("S-001", analysis_ids=(1,), form_chemical_name=long_name),
        _sample("S-002", analysis_ids=(1,), form_chemical_name=long_name),
    ]
    submission = _submission(samples, request_type=RequestType.CHEMICAL)
    analysis_svc = _FakeAnalysisService({1: "TOC"})
    sheets = dispatcher.build_submission_sheets(
        submission, _CUSTOMER, _FakeChemicalService(), analysis_svc, _FakeElementService(), _FakeSpecificationService()
    )
    assert sheets[0].name == "A" * 28 + " 1"
    assert sheets[1].name == "A" * 28 + " 2"
    assert len(sheets[0].name) <= 31
    assert len(sheets[1].name) <= 31


def test_a_site_with_no_limits_of_its_own_uses_its_groups_limits():
    """Customer groups (2026-10-01): a Chemco site has no limits of its own;
    the Chemco group's limits for that chemical apply, as in the legacy macro."""
    site = Customer(
        id=5, name="Group Site", street_address="1 Plant Rd", city="Cust5b4b0", state="LA",
        postal_code="70057", country="USA", parent_customer_id=40,
    )
    submission = _submission([_sample("S-1", analysis_ids=(1,), chemical_id=9)])
    chemical_svc = _FakeChemicalService({9: _FakeChemical(id=9, name="Methyl Carbitol")})
    spec_svc = _FakeSpecificationService(specs_by_ids={(40, 9): {"Al": 0.4}})
    sheets = dispatcher.build_submission_sheets(
        submission, site, chemical_svc, _FakeAnalysisService({1: "36 Elements"}), _FakeElementService(), spec_svc
    )
    al_row = next(r for s in sheets[0].sections for r in s.rows if r.get_value(3) == "Al")
    assert al_row.limits == {"specification": 0.4}


def test_wafer_column_widths_match_the_real_template():
    assert column_widths.WAFER == {
        1: 14.29, 2: 14.86, 3: 5.29,
        4: 12.0, 5: 12.0, 6: 12.0, 7: 12.0, 8: 12.0, 9: 12.0, 10: 12.0, 11: 12.0, 12: 12.0, 13: 12.0, 14: 12.0, 15: 12.0,
        16: 9.43, 17: 6.29, 18: 9.00, 19: 8.43,
    }
