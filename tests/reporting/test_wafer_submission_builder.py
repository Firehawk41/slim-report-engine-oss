from dataclasses import dataclass
from datetime import date, datetime

import pytest

from slim_domain.domain.customer.customer import Customer
from slim_domain.domain.tr.enums import ProcessingTime, RequestType
from slim_domain.domain.tr.tr_sample import TRSample
from slim_domain.domain.tr.tr_submission import TRSubmission

from slim_report_engine.reporting import wafer_submission_builder as orchestrator


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
class _FakeElement:
    id: int
    name: str
    symbol: str


class _FakeElementService:
    def __init__(self, elements: dict[int, _FakeElement] | None = None) -> None:
        self._by_id = elements or {}
        self._by_name = {e.name: e for e in self._by_id.values()}

    def get_by_symbol(self, symbol: str):
        return _FakeElement(id=0, name=symbol, symbol=symbol)

    def get_by_name(self, name: str):
        return self._by_name.get(name)

    def load_element(self, element_id: int):
        return self._by_id.get(element_id)


_CUSTOMER = Customer(
    id=1, name="Customer 130", street_address="1 Main St",
    city="Springfield", state="IL", postal_code="62701", country="USA",
)


def _sample(
    name: str,
    analysis_ids: tuple[int, ...],
    reporting_units: str = "atoms/cm^2",
    wafer_size: str = "150mm",
    processing_time: ProcessingTime = ProcessingTime.NEXT_DAY,
    additional_element_ids: tuple[int, ...] = (),
) -> TRSample:
    return TRSample(
        sample_name=name,
        form_chemical_name=wafer_size,
        processing_time=processing_time,
        additional_notes="",
        requested_time="",
        chemical_id=0,
        analysis_ids=analysis_ids,
        additional_element_ids=additional_element_ids,
        reporting_units=reporting_units,
    )


def _submission(samples: list[TRSample]) -> TRSubmission:
    return TRSubmission(
        customer_id=1,
        date_submitted=date(2026, 3, 4),
        date_received=date(2026, 3, 5),
        request_type=RequestType.WAFER,
        customer_contact="Jane Doe",
        customer_phone="555-0100",
        po_information="",
        credit_card_information="",
        file_name="test.xlsx",
        service_date=date(1901, 1, 1),
        download_date=datetime(2026, 3, 5, 12, 0, 0),
        form_customer_name="Customer 130",
        form_customer_address="",
        form_customer_address_2="",
        samples=tuple(samples),
    )


def test_two_samples_sharing_all_four_keys_land_on_one_sheet():
    samples = [
        _sample("Slot-1", analysis_ids=(1,)),
        _sample("Slot-2", analysis_ids=(1,)),
    ]
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    results = orchestrator.build_wafer_sheets(
        _submission(samples), _CUSTOMER, analysis_svc, _FakeElementService()
    )
    assert len(results) == 1
    sample_id_row = results[0].section.rows[5]
    assert sample_id_row.get_value(5) == "030526-150mm Wafers-Customer 130-Slot-1"
    assert sample_id_row.get_value(6) == "030526-150mm Wafers-Customer 130-Slot-2"


def test_different_processing_time_splits_into_separate_sheets():
    samples = [
        _sample("Slot-1", analysis_ids=(1,), processing_time=ProcessingTime.NEXT_DAY),
        _sample("Slot-2", analysis_ids=(1,), processing_time=ProcessingTime.FIVE_DAYS),
    ]
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    results = orchestrator.build_wafer_sheets(
        _submission(samples), _CUSTOMER, analysis_svc, _FakeElementService()
    )
    assert len(results) == 2


def test_different_wafer_size_splits_into_separate_sheets():
    samples = [
        _sample("Slot-1", analysis_ids=(1,), wafer_size="150mm"),
        _sample("Slot-2", analysis_ids=(1,), wafer_size="200mm"),
    ]
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    results = orchestrator.build_wafer_sheets(
        _submission(samples), _CUSTOMER, analysis_svc, _FakeElementService()
    )
    assert len(results) == 2
    assert {r.sheet_title for r in results} == {"150mm Wafers", "200mm Wafers"}


def test_10_and_26_elements_normalize_to_36_and_group_together():
    """Confirmed identical content on a Wafer sheet -- no AVERAGE/TOTAL
    label to distinguish them, unlike Chemical/Water's metals panel."""
    samples = [
        _sample("Slot-1", analysis_ids=(1,)),
        _sample("Slot-2", analysis_ids=(2,)),
        _sample("Slot-3", analysis_ids=(3,)),
    ]
    analysis_svc = _FakeAnalysisService({1: "10 Elements", 2: "26 Elements", 3: "36 Elements"})
    results = orchestrator.build_wafer_sheets(
        _submission(samples), _CUSTOMER, analysis_svc, _FakeElementService()
    )
    assert len(results) == 1
    assert results[0].section.id == "36 Elements"
    sample_id_row = results[0].section.rows[5]
    assert sample_id_row.get_value(5) == "030526-150mm Wafers-Customer 130-Slot-1"
    assert sample_id_row.get_value(6) == "030526-150mm Wafers-Customer 130-Slot-2"
    assert sample_id_row.get_value(7) == "030526-150mm Wafers-Customer 130-Slot-3"


def test_67_elements_and_36_elements_stay_separate_groups():
    samples = [
        _sample("Slot-1", analysis_ids=(1,)),
        _sample("Slot-2", analysis_ids=(2,)),
    ]
    analysis_svc = _FakeAnalysisService({1: "36 Elements", 2: "67 Elements"})
    results = orchestrator.build_wafer_sheets(
        _submission(samples), _CUSTOMER, analysis_svc, _FakeElementService()
    )
    assert len(results) == 2


def test_additional_elements_are_unioned_across_the_group():
    gold = _FakeElement(id=101, name="Gold", symbol="Au")
    silver = _FakeElement(id=102, name="Silver", symbol="Ag")
    samples = [
        _sample("Slot-1", analysis_ids=(1,), additional_element_ids=(101,)),
        _sample("Slot-2", analysis_ids=(1,), additional_element_ids=(102,)),
    ]
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    element_svc = _FakeElementService({101: gold, 102: silver})
    results = orchestrator.build_wafer_sheets(
        _submission(samples), _CUSTOMER, analysis_svc, element_svc
    )
    assert len(results) == 1
    data_rows = [r for r in results[0].section.rows if r.style_name == "DataLabel"]
    additional_labels = [r.get_value(2) for r in data_rows[-2:]]
    assert additional_labels == ["Gold", "Silver"]


def test_additional_elements_deduplicated_across_the_group():
    gold = _FakeElement(id=101, name="Gold", symbol="Au")
    samples = [
        _sample("Slot-1", analysis_ids=(1,), additional_element_ids=(101,)),
        _sample("Slot-2", analysis_ids=(1,), additional_element_ids=(101,)),
    ]
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    element_svc = _FakeElementService({101: gold})
    results = orchestrator.build_wafer_sheets(
        _submission(samples), _CUSTOMER, analysis_svc, element_svc
    )
    data_rows = [r for r in results[0].section.rows if r.style_name == "DataLabel"]
    assert data_rows[-1].get_value(2) == "Gold"
    assert data_rows[-2].get_value(2) != "Gold"  # only appears once


def test_uses_resolved_customer_name_not_form_customer_name():
    """The sample-ID string must use the canonical Customer.name, not
    whatever raw text was typed on the form -- Wafer's own sample-string
    format (unlike the generic Chemical/Water/SX5 one) has no customer
    name substitution rules of its own, so this just confirms the right
    source field is used, not a specific substitution."""
    resolved_customer = Customer(
        id=2, name="Resolved Canonical Name", street_address="1 Main St",
        city="Springfield", state="IL", postal_code="62701", country="USA",
    )
    samples = [_sample("Slot-1", analysis_ids=(1,))]
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    submission = _submission(samples)
    assert submission.form_customer_name != resolved_customer.name  # sanity check the two differ

    results = orchestrator.build_wafer_sheets(
        submission, resolved_customer, analysis_svc, _FakeElementService()
    )
    sample_id_row = results[0].section.rows[5]
    assert "Resolved Canonical Name" in sample_id_row.get_value(5)
    assert submission.form_customer_name not in sample_id_row.get_value(5)


def test_groups_preserve_first_seen_order():
    samples = [
        _sample("Slot-1", analysis_ids=(1,), wafer_size="200mm"),
        _sample("Slot-2", analysis_ids=(1,), wafer_size="150mm"),
        _sample("Slot-3", analysis_ids=(1,), wafer_size="200mm"),
    ]
    analysis_svc = _FakeAnalysisService({1: "36 Elements"})
    results = orchestrator.build_wafer_sheets(
        _submission(samples), _CUSTOMER, analysis_svc, _FakeElementService()
    )
    assert [r.sheet_title for r in results] == ["200mm Wafers", "150mm Wafers"]


def test_sample_with_no_recognized_selection_raises():
    samples = [_sample("Slot-1", analysis_ids=(1,))]
    analysis_svc = _FakeAnalysisService({1: "Some Other Analysis"})
    with pytest.raises(ValueError, match="no recognized"):
        orchestrator.build_wafer_sheets(
            _submission(samples), _CUSTOMER, analysis_svc, _FakeElementService()
        )


def test_sample_with_multiple_selections_raises():
    samples = [_sample("Slot-1", analysis_ids=(1, 2))]
    analysis_svc = _FakeAnalysisService({1: "36 Elements", 2: "4 Anions"})
    with pytest.raises(ValueError, match="multiple selections"):
        orchestrator.build_wafer_sheets(
            _submission(samples), _CUSTOMER, analysis_svc, _FakeElementService()
        )
