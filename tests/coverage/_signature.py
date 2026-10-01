"""Computes a "shape signature" for one real TR sample -- the dimensions
that actually change generated report CONTENT (resolved analysis names,
request type, whether additional elements were selected, Wafer's
reporting-units choice) as opposed to incidental ones that don't
(sample ID, dates, which real customer it is). Direct response to
Jamie's own idea (2026-09-28): dedupe "20 near-identical routine
submissions with different sample IDs" down to however many genuinely
distinct shapes are actually among them, so scanning/review effort goes
toward what's actually new, not re-confirming what's already covered.

Deliberately NOT exhaustive of every dimension that could theoretically
affect output (e.g. per-chemical KED-elements, unit overrides, metals
instrument) -- those are customer/chemical catalog data, not something
a signature over a TR FORM alone can see, and are covered instead by
the tests/golden/ tier's specific, curated real-evidence pairs. This
signature is Tier 2's breadth tool: "does this combination of
selections run without crashing," not "is the output correct."
"""

from __future__ import annotations

from dataclasses import dataclass

from slim_domain.domain.analysis.analysis_service import AnalysisService
from slim_domain.domain.tr.tr_sample import TRSample
from slim_domain.domain.tr.tr_submission import TRSubmission


@dataclass(frozen=True)
class SampleSignature:
    analysis_names: frozenset[str]
    request_type: str
    has_additional_elements: bool
    reporting_units: str  # Wafer-specific ("Reporting Unit" column); "" for Chemical/Water

    def key(self) -> str:
        names = ",".join(sorted(self.analysis_names)) or "(none)"
        return f"{self.request_type}|{names}|additional={self.has_additional_elements}|units={self.reporting_units or '-'}"


def sample_signature(sample: TRSample, request_type: str, analysis_service: AnalysisService) -> SampleSignature:
    names: set[str] = set()
    for analysis_id in sample.analysis_ids:
        analysis = analysis_service.load_analysis(analysis_id)
        if analysis is not None:
            names.add(analysis.name)
    return SampleSignature(
        analysis_names=frozenset(names),
        request_type=request_type,
        has_additional_elements=bool(sample.additional_element_ids),
        reporting_units=sample.reporting_units,
    )


def submission_Folder 071(submission: TRSubmission, analysis_service: AnalysisService) -> list[SampleSignature]:
    """One signature per sample -- a single TR file can (and often does,
    e.g. the dummy "test all analyses" TR) mix several distinct shapes
    in one submission."""
    request_type = submission.request_type.name
    return [sample_signature(s, request_type, analysis_service) for s in submission.samples]
