"""Dispatches a whole TRSubmission's samples to the right Transform-stage
builder (generic Chemical/Water, SX5 non-routine, or Wafer grouping) and
returns one OutputSheet per output sheet, ready for report_writer to
write. This is the piece that turns "the three paths work individually"
(chemical_water_report_builder, sx5_non_routine_report_builder,
wafer_submission_builder) into "a whole submission produces a whole
workbook" — the CLI entry point (cli.py) calls this once per parsed
submission.

SX5 ROUTING: the real macro's own check was `Customer Like "SX5?"` against
two separate legacy customer records, "SX5N"/"SX5S" -- but the real
Postgres customers table has only ONE "SX5" customer (North and South are
the same customer for invoicing, confirmed 2026-09-23; splitting them was
considered and explicitly rejected -- they must stay one customer despite
using different specs and never cross-pollinating reports). So routing
checks for the single real customer name "SX5", and North vs. South is
derived from the TR filename instead (see sx5_location_from_filename) --
Testing_Requests deliberately keeps both in one folder for historical
reasons, so the filename is the only place this distinction still lives.
A SX5 customer with a chemical that builder doesn't recognize raises a
clear error rather than silently falling back to a generic path that has
no SX5-specific content to offer.

SHEET NAMING: for generic Chemical/Water, ported from the real macro's
SetChemicalSheetName/SetWaterSheetName (modReportCreator.bas) — the
CHEMICAL MATRIX text (or literal "Water"), not the Sample ID, which is
what the real system actually shows and what the earlier Sample-ID-based
scheme got wrong (real Sample IDs are often unreadable delivery-lot/PO
strings). See _generic_tab_names. SX5 uses chemical_label, Wafer uses the
group's own sheet title -- both sanitized/deduplicated with the older,
simpler `_sanitize_sheet_name`/`_dedupe_name` fallback, since neither has
the same real-per-matrix-duplicate-numbering behavior confirmed for the
generic path.

SAMPLE-ID STRING ECHO: row_builders.add_header_rows/add_simple_header_row
deliberately leave column 4 of each section's own "Sample Identification:"
row blank -- "filled in by the caller assembling the whole sheet, not
here... the sample-level identity string every section on a sheet
shares" (see row_builders.py). This module is that caller: for generic
Chemical/Water it computes the standard "mmddyy-Chemical-Customer-SampleID"
string (sample_string_builder.build_sample_string -- the SAME format SX5
non-routine and Wafer use, just with different inputs) and stamps it into
EVERY section's row 1 / column 4, matching the "every section shares it"
framing. Cell A1 also gets a title stamp on every path (matching the
legacy macro's `.Range("A1").Value = ...`) -- SX5's own first section
already carries this internally (its TitleRow is row 1 of the section,
landing on A1 naturally), so only generic Chemical/Water and Wafer need
an explicit extra stamp for it.
"""

from __future__ import annotations

from dataclasses import dataclass

from slim_domain.domain.analysis.analysis_service import AnalysisService
from slim_domain.domain.chemical.chemical_service import ChemicalService
from slim_domain.domain.customer.customer import Customer
from slim_domain.domain.element.element_service import ElementService
from slim_domain.domain.specification.specification_service import SpecificationService
from slim_domain.domain.tr.enums import ProcessingTime, RequestType
from slim_domain.domain.tr.tr_sample import TRSample
from slim_domain.domain.tr.tr_submission import TRSubmission

from slim_report_engine.reporting import chemical_water_report_builder, column_widths, sx5_non_routine_report_builder
from slim_report_engine.reporting import date_of_analysis, row_builders, wafer_submission_builder
from slim_report_engine.reporting.report_section import ReportSection
from slim_report_engine.reporting.sample_string_builder import build_sample_string

SX5_CUSTOMER_NAME = "SX5"


def sx5_location_from_filename(file_name: str) -> str:
    """North vs. South can't come from the customer record (both are the
    same "SX5" customer -- see module docstring), so it's derived from the
    TR filename instead, matching the real, observed naming convention
    (e.g. "092226-SXOS5 South HCl-1 Same Day RUSH.xlsx"). Raises rather
    than guessing a default: silently picking one location's specs for a
    sample that's actually the other would misreport results, which is
    worse than failing loudly here."""
    lower = file_name.lower()
    has_north = "north" in lower
    has_south = "south" in lower
    if has_north and not has_south:
        return "SX5N"
    if has_south and not has_north:
        return "SX5S"
    raise ValueError(
        f"could not determine SX5 North/South from filename {file_name!r} -- "
        "expected exactly one of \"North\"/\"South\" to appear in it."
    )


@dataclass(frozen=True)
class OutputSheet:
    name: str
    sections: tuple[ReportSection, ...]
    header_title: str
    # Column index (1-based) -> width in points, matching whichever
    # report family produced this sheet's content -- see column_widths.py.
    column_widths: dict[int, float]
    # (cell_address, value) pairs to write AFTER the section content --
    # e.g. SX5's sample-ID cell. Applied in order, as plain unstyled
    # values -- NOT for a sheet title (see title_cell_stamp below).
    extra_cell_stamps: tuple[tuple[str, str], ...] = ()
    # (cell_address, text) for Wafer's own A1 sheet title -- separate from
    # extra_cell_stamps (2026-09-25, direct user correction, Cust082) since
    # a title needs real font styling (report_writer.apply_title_cell),
    # unlike extra_cell_stamps' plain values. None for every non-Wafer
    # sheet -- their titles ride through a real "SectionTitle" ReportRow
    # (SX5) or the generic preamble (row_builders.build_header_preamble)
    # instead.
    title_cell_stamp: tuple[str, str] | None = None
    # Confirmed real (openpyxl against every real template): the generic
    # Chemical/Water and SX5 templates are zoomed to 90% by default; Wafer
    # is the one exception, at 95% (see _build_wafer_sheets).
    zoom: int = 90
    # (cell_address, text, color, size) for report_writer.apply_processing_time_stamp
    # -- None (the default) means this sample's ProcessingTime has no
    # confirmed real stamp (see _processing_time_stamp).
    processing_time_stamp: tuple[str, str, str, int] | None = None
    # (limit kind, header label) per limit column, in column order -- see
    # report_writer.LimitColumns. Empty for every sheet with no limits on
    # file (and for SX5/Wafer, which lay out their own column 1).
    limit_columns: tuple[tuple[str, str | None], ...] = ()


def build_submission_sheets(
    submission: TRSubmission,
    customer: Customer,
    chemical_service: ChemicalService,
    analysis_service: AnalysisService,
    element_service: ElementService,
    specification_service: SpecificationService,
) -> list[OutputSheet]:
    if submission.request_type == RequestType.WAFER:
        # Wafer has no real spec-value column on any of its panels
        # (confirmed: neither element nor anion panel rows have a
        # column-1 spec slot at all) -- specification_service is simply
        # unused on this path.
        return _build_wafer_sheets(submission, customer, analysis_service, element_service)

    is_sx5 = customer.name == SX5_CUSTOMER_NAME
    sx5_location = sx5_location_from_filename(submission.file_name) if is_sx5 else None
    used_names: set[str] = set()
    sheets: list[OutputSheet] = []
    # Precomputed up front, not per-sample -- confirmed real (see
    # _generic_tab_names): whether a sample's tab gets a numeric suffix
    # depends on how many OTHER samples in the whole submission share its
    # chemical matrix, which isn't knowable one sample at a time.
    generic_tab_names = None if is_sx5 else _generic_tab_names(submission)
    sx5_tab_names = (
        _sx5_tab_names(submission, customer, chemical_service, specification_service, sx5_location) if is_sx5 else None
    )

    for i, sample in enumerate(submission.samples):
        if is_sx5:
            chemical = chemical_service.load_chemical(sample.chemical_id)
            chemical_name = chemical.name if chemical is not None else sample.form_chemical_name
            if not sx5_non_routine_report_builder.is_supported_chemical(chemical_name):
                raise ValueError(
                    f"sample {sample.sample_name!r}: SX5 chemical {chemical_name!r} is not one of the "
                    "21 chemicals sx5_non_routine_report_builder supports -- not silently falling back "
                    "to the generic path, which has no SX5-specific content to offer."
                )
            requested_analysis_names = _resolved_analysis_names(sample, analysis_service)
            result = sx5_non_routine_report_builder.build_non_routine_report(
                chemical_name, sx5_location, submission.date_received, sample.sample_name, element_service,
                requested_analysis_names,
                spec_data=_sx5_spec_data(customer, sample, sx5_location, specification_service),
            )
            name = sx5_tab_names[i]
            sheets.append(
                OutputSheet(
                    name=name,
                    sections=result.sections,
                    header_title=result.chemical_label,
                    column_widths=result.column_widths,
                    extra_cell_stamps=((result.name_cell_address, result.sample_string),),
                    processing_time_stamp=_processing_time_stamp(sample.processing_time, "E1", 10),
                )
            )
            continue

        metals_prep_text = _metals_prep_text(submission, sample, chemical_service)
        metals_instrument = _metals_instrument(submission, sample, chemical_service)
        ions_prep_text = _ions_prep_text(submission, sample, chemical_service)
        additional_elements_prep_text = customer.additional_elements_prep or None
        # Whose limits apply: the customer's own for this chemical, else its
        # group's (e.g. every Chemco site uses the Chemco group's limits).
        limits_owner = specification_service.limits_owner(customer.id, sample.chemical_id, customer.parent_customer_id)
        metals_specs = _specs_for_sample(submission, sample, chemical_service, specification_service, limits_owner)
        warning_limits = _warning_limits_for_sample(sample, chemical_service, specification_service, limits_owner)
        unit_override = _unit_override_for_sample(submission, sample, chemical_service, specification_service, limits_owner)
        has_ked_elements = _has_ked_elements(submission, sample, chemical_service)
        ked_element_ids = _ked_element_ids(submission, sample, chemical_service)
        date_of_analysis_text = _date_of_analysis_text(submission, sample)
        sections = chemical_water_report_builder.build_sections(
            sample, analysis_service, element_service, metals_prep_text, additional_elements_prep_text,
            # Limits are placed by apply_limits below, on every panel, not
            # by the metals panel itself.
            metals_instrument, ions_prep_text, None, has_ked_elements,
            ked_element_ids=ked_element_ids, date_of_analysis=date_of_analysis_text,
            request_type=submission.request_type,
        )
        # Limits print on every panel that lists the analyte, not just the
        # metals panel -- see chemical_water_report_builder.apply_limits.
        chemical_water_report_builder.apply_limits(
            sections, {"specification": metals_specs, "warning_limit": warning_limits}
        )
        chemical_name = sample.form_chemical_name if submission.request_type == RequestType.CHEMICAL else "Water"
        sample_string = build_sample_string(
            submission.date_received, chemical_name, customer.name, sample.sample_name
        )
        for section in sections:
            if section.rows:
                section.rows[0].set_value(4, sample_string)
        # Confirmed real: every generic Chemical/Water sheet starts with a
        # 5-row preamble (title/blank/Notes:/2 note lines) BEFORE the
        # first section's own sample-ID echo row -- see
        # row_builders.build_header_preamble. Prepended after the stamp
        # loop above so the preamble's own title row never gets the
        # sample-ID string stamped into it. Its title row IS column 1 of
        # row 1, so the old separate "A1" extra_cell_stamp is redundant
        # now -- removed.
        all_sections = (row_builders.build_header_preamble(chemical_name, unit_override), *sections)
        name = _dedupe_name(generic_tab_names[i], used_names)
        sheets.append(
            OutputSheet(
                name=name,
                sections=all_sections,
                header_title=chemical_name,
                column_widths=column_widths.STANDARD,
                processing_time_stamp=_processing_time_stamp(sample.processing_time, "D1", 10),
                limit_columns=_limit_columns(
                    limits_owner, sample, specification_service, metals_specs, warning_limits
                ),
            )
        )

    return sheets


def _build_wafer_sheets(
    submission: TRSubmission,
    customer: Customer,
    analysis_service: AnalysisService,
    element_service: ElementService,
) -> list[OutputSheet]:
    results = wafer_submission_builder.build_wafer_sheets(submission, customer, analysis_service, element_service)
    tab_names = _wafer_tab_names(results)
    sheets: list[OutputSheet] = []
    for result, tab_name in zip(results, tab_names):
        sheets.append(
            OutputSheet(
                name=_sanitize_sheet_name(tab_name),
                sections=(result.section,),
                header_title=result.sheet_title,
                column_widths=column_widths.WAFER,
                title_cell_stamp=("A1", result.sheet_title),
                zoom=95,
                processing_time_stamp=_processing_time_stamp(result.processing_time, "D1", 12),
            )
        )
    return sheets


def _wafer_tab_names(results: list) -> list[str]:
    """Confirmed real (2026-09-28, a real Wafer dummy TR run through the
    legacy macro): the real Excel TAB NAME (unlike A1's title text or the
    D1 processing-time stamp, both already correct via sheet_title/
    _processing_time_stamp) ALSO carries the processing-time label, but
    only for the same "notable" processing times _PROCESSING_TIME_STAMP_
    COLORS already tracks (the RUSH variants + Time Limited) -- e.g. real
    tabs "150mm Wafers Next Day RUSH 1"/"...2", "200mm Wafers Call-in
    RUSH". A plain (unstamped) processing time gets no suffix at all,
    e.g. a lone real "100mm Wafers" tab. Duplicate combined names get a
    " N" suffix in row order -- same convention as
    _chemical_matrix_tab_names (including its 28-char truncation, to
    leave room for a real 2-digit duplicate count), just keyed on this
    combined title+processing-time string instead of chemical matrix.
    """
    base_names = [
        (
            f"{r.sheet_title} {r.processing_time.label}"
            if r.processing_time in _PROCESSING_TIME_STAMP_COLORS
            else r.sheet_title
        )[:28]
        for r in results
    ]
    counts: dict[str, int] = {}
    for n in base_names:
        counts[n] = counts.get(n, 0) + 1

    running: dict[str, int] = {}
    names = []
    for n in base_names:
        if counts[n] > 1:
            running[n] = running.get(n, 0) + 1
            names.append(f"{n} {running[n]}")
        else:
            names.append(n)
    return names


def _resolved_analysis_names(sample: TRSample, analysis_service: AnalysisService) -> frozenset[str]:
    """Distinct resolved analysis names for a sample -- used by the SX5
    branch to tell sx5_non_routine_report_builder what else was requested
    (see its COMPOSITE'S ANION/ASSAY BLOCKS ARE CONDITIONAL note). Same
    resolution chemical_water_report_builder.py does for the generic
    path, duplicated here rather than imported since it's three lines and
    that module has no reason to know about SX5 at all.
    """
    names: set[str] = set()
    for analysis_id in sample.analysis_ids:
        analysis = analysis_service.load_analysis(analysis_id)
        if analysis is not None:
            names.add(analysis.name)
    return frozenset(names)


_DEFAULT_METALS_PREP = "Evaporation"
_WATER_METALS_PREP = "Dilute and Shoot"


def _metals_prep_text(submission: TRSubmission, sample: TRSample, chemical_service: ChemicalService) -> str:
    """Confirmed real (see chemical_water_report_builder.py's PREP TEXT
    docstring section): Chemical samples read the resolved Chemical's own
    catalog prep, defaulting to "Evaporation" (current lab practice) when
    that field is blank; Water samples have no Chemical record to read
    from at all and use "Dilute and Shoot" -- confirmed across every real
    Water sample checked, not just additional-elements-only ones.
    """
    if submission.request_type != RequestType.CHEMICAL:
        return _WATER_METALS_PREP
    chemical = chemical_service.load_chemical(sample.chemical_id)
    if chemical is not None and chemical.metals_prep:
        return chemical.metals_prep
    return _DEFAULT_METALS_PREP


_DEFAULT_METALS_INSTRUMENT = "ICPMS"


def _metals_instrument(submission: TRSubmission, sample: TRSample, chemical_service: ChemicalService) -> str:
    """Confirmed real: usually "ICPMS", manually switched to "ICPOES" per
    chemical during the quote process for a very dirty/nasty matrix, or
    one that itself contains a metal (e.g. NaOH) -- a real human judgment
    call, not derivable from parsed submission data (see
    Chemical.metals_instrument, slim-domain). No real evidence yet of a
    Water sample needing anything but the default -- Water has no
    Chemical record to read an override from anyway.
    """
    if submission.request_type != RequestType.CHEMICAL:
        return _DEFAULT_METALS_INSTRUMENT
    chemical = chemical_service.load_chemical(sample.chemical_id)
    if chemical is not None and chemical.metals_instrument:
        return chemical.metals_instrument
    return _DEFAULT_METALS_INSTRUMENT


def _ions_prep_text(submission: TRSubmission, sample: TRSample, chemical_service: ChemicalService) -> str | None:
    """Confirmed real (direct correction after this was initially built to
    reuse _metals_prep_text -- one real chemical's ions_prep genuinely
    happens to equal "Evaporation" too, which is what caused the original
    over-generalization): the ion panel's own catalog field
    (Chemical.ions_prep, slim-domain), NOT the same value as the metals
    panel. None when the chemical has no ions_prep on file (or for Water,
    which has no Chemical record at all) -- renders a bare "Analysis by
    IC" rather than guessing a prep. Chemical.ions_prep defaults to ""
    (blank) when nothing's been set, same convention as metals_prep.
    """
    if submission.request_type != RequestType.CHEMICAL:
        return None
    chemical = chemical_service.load_chemical(sample.chemical_id)
    if chemical is not None and chemical.ions_prep:
        return chemical.ions_prep
    return None


def _has_ked_elements(submission: TRSubmission, sample: TRSample, chemical_service: ChemicalService) -> bool:
    """Confirmed real (lab's own SOP master list, cross-checked against
    Chemical.ked_element_ids, slim-domain): 49 real chemicals have KED
    elements on file, overwhelmingly on "Dilute and Shoot" prep. False for
    Water (no Chemical record to read from at all) and for any Chemical
    with no ked_element_ids on file -- never guessed.
    """
    if submission.request_type != RequestType.CHEMICAL:
        return False
    chemical = chemical_service.load_chemical(sample.chemical_id)
    return chemical is not None and bool(chemical.ked_element_ids)


def _ked_element_ids(submission: TRSubmission, sample: TRSample, chemical_service: ChemicalService) -> frozenset[int]:
    """The actual set of KED-flagged element IDs (Chemical.ked_element_ids)
    -- added 2026-09-25 alongside _has_ked_elements above, which only
    returns whether ANY exist. Used to mark the specific affected element
    rows, not just the footer's SOP codes/Note 1 line."""
    if submission.request_type != RequestType.CHEMICAL:
        return frozenset()
    chemical = chemical_service.load_chemical(sample.chemical_id)
    if chemical is None:
        return frozenset()
    return chemical.ked_element_ids


def _date_of_analysis_text(submission: TRSubmission, sample: TRSample) -> str:
    """See date_of_analysis.compute_text -- a standalone module (not a
    method here) so the Wafer path, which only has date_received/
    processing_time as plain values by the time it needs this, can call
    the same computation without importing this module (which would be
    circular: this module already imports wafer_submission_builder).
    """
    return date_of_analysis.compute_text(submission.date_received, sample.processing_time)


def _specs_for_sample(
    submission: TRSubmission,
    sample: TRSample,
    chemical_service: ChemicalService,
    specification_service: SpecificationService,
    customer_id: int,
) -> dict[str, float]:
    """Real per-(customer, chemical) spec limits from the Specification
    data (slim-domain), for Chemical AND Water samples -- a Water sample
    resolves to the real "Water" chemical record, and the legacy macro
    looks Water limits up the same way (confirmed real: Customer 169's Water
    report prints Na/Si/Cl limits; an earlier version returned {} for
    every Water sample and printed none). {} when the resolved
    customer+chemical genuinely has no spec on file, never guessed.
    SX5's own per-site limits come from the same table, looked up with a
    location (see _sx5_spec_data).
    """
    chemical = chemical_service.load_chemical(sample.chemical_id)
    if chemical is None:
        return {}
    return specification_service.get_specs(customer_id, chemical.id)


def _warning_limits_for_sample(
    sample: TRSample,
    chemical_service: ChemicalService,
    specification_service: SpecificationService,
    customer_id: int,
) -> dict[str, float]:
    """The customer's warning limits for this sample's chemical -- the
    second limit table the legacy macro read (Warning_Limits_Database),
    printed in their own column (Customer 168, Customer 057). {} when none."""
    chemical = chemical_service.load_chemical(sample.chemical_id)
    if chemical is None:
        return {}
    return specification_service.get_warning_limits(customer_id, chemical.id)


def _limit_columns(
    customer_id: int,
    sample: TRSample,
    specification_service: SpecificationService,
    specs: dict[str, float],
    warning_limits: dict[str, float],
) -> tuple[tuple[str, str | None], ...]:
    """The sheet's limit columns and their customer-requested header
    labels (the database's category_label, e.g. "Action Limit" /
    "Warning Limit"): none without limits; specification first; a
    warning-limit column after it when warning limits exist -- the legacy
    layout (column A, then an inserted column B)."""
    if not specs and not warning_limits:
        return ()

    def label(kind: str) -> str | None:
        return specification_service.get_category_label(customer_id, sample.chemical_id, kind=kind)

    columns: list[tuple[str, str | None]] = [("specification", label("specification") if specs else None)]
    if warning_limits:
        columns.append(("warning_limit", label("warning_limit")))
    return tuple(columns)


def _unit_override_for_sample(
    submission: TRSubmission,
    sample: TRSample,
    chemical_service: ChemicalService,
    specification_service: SpecificationService,
    customer_id: int,
) -> str | None:
    """The real reporting unit for this sample's preamble ("All data in
    units of <X> unless otherwise noted"), when this customer+chemical's
    specs are on file in something other than ppb -- see
    SpecificationService.get_unit_override for the confirmed-real
    Customer 047 / PG ("ppm") evidence. Applies to Water samples
    too, as in the legacy macro (see _specs_for_sample). None (the
    default ppb wording) when there's genuinely no override.
    """
    chemical = chemical_service.load_chemical(sample.chemical_id)
    if chemical is None:
        return None
    return specification_service.get_unit_override(customer_id, chemical.id)


# Confirmed real (every completed report checked with a rush/time-limited
# sample, across generic Chemical/Water, SX5, and Wafer): a bold RED stamp
# for the RUSH variants, bold BLUE for "Next Day Time Limited". A plain
# "Next Day"/"Two Days"/"Three Days" sample gets no stamp at all -- and
# there's no real evidence either way yet for "Extended Time"/"Five Days"
# (no real form offers them as literal dropdown text), so they're left
# unstamped too rather than guessed.
_PROCESSING_TIME_STAMP_COLORS: dict[ProcessingTime, str] = {
    ProcessingTime.TIME_LIMITED: "blue",
    ProcessingTime.SAME_DAY_RUSH: "red",
    ProcessingTime.CALL_IN_RUSH: "red",
    ProcessingTime.NEXT_DAY_RUSH: "red",
}


def _processing_time_stamp(
    processing_time: ProcessingTime, cell_address: str, size: int
) -> tuple[str, str, str, int] | None:
    color = _PROCESSING_TIME_STAMP_COLORS.get(processing_time)
    if color is None:
        return None
    return (cell_address, processing_time.label, color, size)


_SHEET_NAME_ILLEGAL_CHARS = ":/\\?*[]<>|"


def _generic_tab_names(submission: TRSubmission) -> list[str]:
    """One tab name per sample in submission.samples order — ported from
    the real macro's SetChemicalSheetName/SetWaterSheetName
    (modReportCreator.bas), ground truth for the real naming scheme this
    replaces (the old scheme used the raw Sample ID, which produces
    unreadable tabs on real ID-like sample IDs -- e.g. a real delivery-lot
    string instead of the real system's actual "PMAC").
    """
    if submission.request_type == RequestType.WATER:
        return _water_tab_names(len(submission.samples))
    return _chemical_matrix_tab_names([s.form_chemical_name for s in submission.samples])


def _sx5_spec_data(
    customer: Customer, sample: TRSample, location: str, specification_service: SpecificationService
) -> sx5_non_routine_report_builder.SX5SpecData:
    """SX5's limits, QC code, assay spec range, note and display label for
    this sample's (location, chemical) -- all from the database, the same
    specification data every other customer's limits come from."""
    setting = specification_service.get_report_setting(customer.id, sample.chemical_id, location)
    return sx5_non_routine_report_builder.SX5SpecData(
        specs=specification_service.get_specs(customer.id, sample.chemical_id, location),
        qc_code=specification_service.get_category_label(customer.id, sample.chemical_id, location),
        assay_spec_text=setting.assay_spec_text if setting else None,
        report_note=setting.report_note if setting else None,
        display_label=setting.display_label if setting else None,
    )


def _sx5_tab_names(
    submission: TRSubmission,
    customer: Customer,
    chemical_service: ChemicalService,
    specification_service: SpecificationService,
    location: str,
) -> list[str]:
    """Confirmed real (2026-09-29, a real SX5-North comprehensive TR run
    through the legacy macro, sample "WX7808" x2): duplicate SX5 chemical
    sheets use the SAME " N" (every occurrence numbered, not just the
    2nd-onward) convention as the generic Chemical/Water path -- real
    legacy tabs "WX7808 1"/"WX7808 2" -- not the older bare/parenthetical
    _dedupe_name fallback this module used before (which produced
    "WX7808"/"WX7808 (2)"). Reuses _chemical_matrix_tab_names's exact
    algorithm.

    Uses sx5_non_routine_report_builder.resolve_chemical_label (the SAME
    canonicalize-then-label pipeline build_non_routine_report applies to
    its own chemical_label, which already drives OutputSheet.
    header_title) for each sample's name, not the raw resolved
    Chemical.name -- confirmed real gap (same TR, SX5-South this time):
    the raw DB name is "HCL"/"WX-2000" for two chemicals whose real tabs
    are "HCl"/"WX2000", so tab name and header title used to disagree with
    each other (and with legacy) whenever a chemical's raw DB spelling
    didn't already match its real display convention.
    """
    names = []
    for sample in submission.samples:
        chemical = chemical_service.load_chemical(sample.chemical_id)
        raw_name = chemical.name if chemical is not None else sample.form_chemical_name
        setting = specification_service.get_report_setting(customer.id, sample.chemical_id, location)
        names.append(
            sx5_non_routine_report_builder.resolve_chemical_label(
                raw_name, location, setting.display_label if setting else None
            )
        )
    return _chemical_matrix_tab_names(names)


def _water_tab_names(count: int) -> list[str]:
    """Confirmed real (SetWaterSheetName): "Water" alone when there's
    exactly one Water sample in the whole submission; "Water 1".."Water N"
    (by row/form order) when there's more than one -- Water samples have
    no chemical-matrix content to group by, so every sample counts as its
    own occurrence once there's more than one at all.
    """
    if count <= 1:
        return ["Water"] * count
    return [f"Water {i}" for i in range(1, count + 1)]


def _chemical_matrix_tab_names(chemical_matrices: list[str]) -> list[str]:
    """Confirmed real (SetChemicalSheetName): scrub illegal sheet-name
    characters (removed entirely, not replaced -- confirmed real:
    RemoveIllegalCharacters' Case Else branch), truncate to 28 characters
    (not 31 -- reserves room for a " N" suffix so a real 2-digit
    duplicate count still fits Excel's 31-character sheet-name limit),
    then group samples by that truncated value. A chemical matrix that's
    unique in the submission keeps its plain (truncated) name; one that
    repeats gets " N" appended to EVERY occurrence, N counted in the
    samples' own row/form order (1-based) -- not just the 2nd-onward,
    confirmed real (e.g. real duplicate tabs are "X 1"/"X 2", never a bare
    "X" alongside "X 2").
    """
    truncated = [_scrub_chemical_matrix_for_sheet_name(m)[:28] for m in chemical_matrices]
    counts: dict[str, int] = {}
    for t in truncated:
        counts[t] = counts.get(t, 0) + 1

    running: dict[str, int] = {}
    names = []
    for t in truncated:
        if counts[t] > 1:
            running[t] = running.get(t, 0) + 1
            names.append(f"{t} {running[t]}")
        else:
            names.append(t)
    return names


def _scrub_chemical_matrix_for_sheet_name(text: str) -> str:
    for ch in _SHEET_NAME_ILLEGAL_CHARS:
        text = text.replace(ch, "")
    return text


def _sanitize_sheet_name(name: str) -> str:
    for ch in "[]:*?/\\":
        name = name.replace(ch, "_")
    return (name.strip() or "Sheet")[:31]


def _dedupe_name(name: str, used: set[str]) -> str:
    base, n = name, 2
    while name in used:
        suffix = f" ({n})"
        name = base[: 31 - len(suffix)] + suffix
        n += 1
    used.add(name)
    return name
