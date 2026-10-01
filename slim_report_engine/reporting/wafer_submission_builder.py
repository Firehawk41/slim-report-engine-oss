"""Groups a Wafer TRSubmission's sample rows onto physical sheets and
builds each sheet's content — the piece the legacy macro's
Wafer_Blank_Report_Creator called grouping/dispatch, ported here as pure
Transform-stage logic operating on already-parsed TRSample data instead
of directly reading Excel cells.

A wafer's grouping identity is (Reporting Units, Wafer Size, resolved
Element/Anion selection, Processing Time) — confirmed real per
DOMAIN_BRIEF.md's Wafer section. Multiple physical sample rows sharing all
four values land on ONE sheet, one column per sample (see
wafer_report_builder.build_wafer_sheet). Grouping preserves the
submission's own sample order (TR-row order).

ELEMENT-COUNT NORMALIZATION: "10 Elements"/"26 Elements" render
byte-identical content to "36 Elements" on a Wafer sheet — confirmed
against the real form's own dropdown and against wafer_panel_builder
itself: unlike Chemical/Water's metals panel, a Wafer element panel has
no AVERAGE/TOTAL summary label, so there's nothing for these three
selections to differ on at all. Normalized to "36 Elements" for both the
group key and the content dispatch.

ADDITIONAL ELEMENTS: each sample row can independently request its own
"Additional Elements", but one sheet has one shared panel. Per explicit
direction: add the UNION of every sample's additional elements to the
shared sheet, and let the technician leave irrelevant cells blank for a
blank report — not one panel per sample.

CUSTOMER: uses the resolved Customer.name (the canonical property), not
the raw form_customer_name — needed for the sample-ID string's
substitution rules (e.g. UPX -> FXFILM UPX) to fire correctly.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

from slim_domain.domain.analysis.analysis_service import AnalysisService
from slim_domain.domain.customer.customer import Customer
from slim_domain.domain.element.element_service import ElementService
from slim_domain.domain.tr.tr_sample import TRSample
from slim_domain.domain.tr.tr_submission import TRSubmission

from slim_report_engine.reporting.wafer_report_builder import WaferReportResult, build_wafer_sheet

_NUMBER_OF_ELEMENTS_ALIASES = {
    "10 Elements": "36 Elements",
    "26 Elements": "36 Elements",
}

_RECOGNIZED_SELECTIONS = {
    "10 Elements", "26 Elements", "36 Elements", "67 Elements", "List #2 36 Elements",
    "4 Anions", "5 Anions", "7 Anions",
}


@dataclass(frozen=True)
class _GroupKey:
    reporting_units: str
    wafer_size: str
    number_of_elements_label: str  # already normalized
    processing_time: object  # ProcessingTime, kept loosely typed to avoid an import cycle in type checkers


def build_wafer_sheets(
    submission: TRSubmission,
    customer: Customer,
    analysis_service: AnalysisService,
    element_service: ElementService,
) -> list[WaferReportResult]:
    """submission must be a Wafer-type submission (every sample sharing a
    submission comes from the same intake form, so this doesn't re-check
    request_type). Returns one WaferReportResult per unique (Reporting
    Units, Wafer Size, Element/Anion selection, Processing Time)
    combination, in first-seen order.
    """
    groups: OrderedDict[_GroupKey, list[TRSample]] = OrderedDict()

    for sample in submission.samples:
        selection = _resolve_selection_label(sample, analysis_service)
        key = _GroupKey(
            reporting_units=sample.reporting_units,
            wafer_size=sample.form_chemical_name,
            number_of_elements_label=selection,
            processing_time=sample.processing_time,
        )
        groups.setdefault(key, []).append(sample)

    results: list[WaferReportResult] = []
    for key, samples in groups.items():
        slot_labels = [s.sample_name for s in samples]
        additional_names = _union_additional_element_names(samples, element_service)
        results.append(
            build_wafer_sheet(
                wafer_size=key.wafer_size,
                reporting_units=key.reporting_units,
                number_of_elements_label=key.number_of_elements_label,
                customer=customer.name,
                date_received=submission.date_received,
                slot_sample_labels=slot_labels,
                additional_element_names=additional_names,
                element_service=element_service,
                processing_time=key.processing_time,
            )
        )

    return results


def _resolve_selection_label(sample: TRSample, analysis_service: AnalysisService) -> str:
    """Finds the sample's one recognized Element/Anion-count selection
    among its resolved analyses, normalizing element-count aliases.
    Raises if none or more than one distinct selection is found -- a
    Wafer sample should request exactly one panel category.
    """
    matches: list[str] = []
    for analysis_id in sample.analysis_ids:
        analysis = analysis_service.load_analysis(analysis_id)
        if analysis is not None and analysis.name in _RECOGNIZED_SELECTIONS:
            matches.append(analysis.name)

    distinct = list(dict.fromkeys(matches))  # dedupe, preserve first-seen order
    if len(distinct) == 0:
        raise ValueError(
            f"sample {sample.sample_name!r} has no recognized Number-of-Elements/Anions selection"
        )
    if len(distinct) > 1:
        raise ValueError(
            f"sample {sample.sample_name!r} has multiple selections {distinct} -- expected exactly one"
        )
    return _NUMBER_OF_ELEMENTS_ALIASES.get(distinct[0], distinct[0])


def _union_additional_element_names(samples: list[TRSample], element_service: ElementService) -> list[str]:
    seen: set[int] = set()
    names: list[str] = []
    for sample in samples:
        for element_id in sample.additional_element_ids:
            if element_id in seen:
                continue
            seen.add(element_id)
            element = element_service.load_element(element_id)
            if element is not None:
                names.append(element.name)
    return names
