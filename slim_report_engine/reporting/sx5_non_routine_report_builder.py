"""Orchestrates a NON-ROUTINE SX5 sample's report content — ported from
clsSX5NonRoutineReportBuilder.cls. This is the path where a SX5 sample
arrives via a normal testing request, same as every other Chemical/Water
sample (the routine schedule-grid path is explicitly out of scope, see
DOMAIN_BRIEF.md). For a given (chemical_name, location), this dispatches
to the right content builder(s) across all 3 SX5 shapes (element panel,
standalone Assay, composite element+anions+Assay) and computes the
standard sample-ID string and the cell address it belongs in.

SCOPE: all 21 SX5 chemicals across both locations dispatch correctly
(element panel: 13, standalone Assay: 5, composite: 3).

COMPOSITE'S ANION/ASSAY BLOCKS ARE CONDITIONAL, NOT FIXED — confirmed
real: unlike the routine schedule-grid path (out of scope, always renders
a fixed set of blocks), a non-routine sample only gets the composite
chemical's anion block and/or embedded Assay when those were actually
requested on THAT sample's TR form (same Anions/Titrations selections the
generic Chemical/Water path already reads) — see
requested_analysis_names below and _ANION_ANALYSIS_NAMES.

Per the Parse -> Transform -> Write pipeline (see project memory
feedback_pipeline_stages), this function is Transform-stage only: it
returns WHAT to write and WHERE (sections, sample string, target cell
address) as plain data. The actual worksheet write happens later, in
report_writer.py (driven by cli.run() via submission_report_builder).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from slim_domain.domain.element.element_service import ElementService

from slim_report_engine.lab_identity import RESULTS_LABEL
from slim_report_engine.reporting import column_widths
from slim_report_engine.reporting.sx5 import chemical_rules
from slim_report_engine.reporting.report_section import ReportSection
from slim_report_engine.reporting.sample_string_builder import build_sample_string
from slim_report_engine.reporting.section_builders import (
    sx5_assay_section_builder,
    sx5_element_panel_builder,
)

_ELEMENT_CHEMICALS = {"NH4OH", "H2O2", "IPA", "BHF", "49%HF", "HCl", "SurfClean"}
_ASSAY_CHEMICALS = {"CSLX001", "WX2000", "WX7808"}
_COMPOSITE_CHEMICALS = {"0.49%HF", "2.5%HF"}

# Confirmed real (2026-09-23): the resolved Chemical.name coming out of the
# database isn't guaranteed to match these dispatch tables' exact casing --
# confirmed via a live production failure where the DB had "HCL" against
# this table's "HCl". A human reads those as the same chemical instantly;
# this module should too. Case-insensitive lookup ONLY -- the canonical
# (correctly-cased) spelling from these sets is still what every downstream
# dict/label lookup uses, so "HCl" is never silently replaced by whatever
# casing the database happened to have.
_CANONICAL_CHEMICAL_NAMES = {
    name.upper(): name for name in (_ELEMENT_CHEMICALS | _ASSAY_CHEMICALS | _COMPOSITE_CHEMICALS)
}
# Confirmed real (2026-09-29, SX5N comprehensive TR): the DB's own
# canonical Chemical.name for this one chemical is "WX-2000" (hyphenated)
# -- matches the real template's own sheet TAB name (chemical_rules.
# translate_sheet_name's "WX2000": "WX-2000" entry), but doesn't match this
# table's internal dispatch key "WX2000" even after uppercasing, since a
# hyphen isn't a casing difference. Same "a human reads these as the same
# chemical instantly" principle as the HCl/HCL fix above -- not a
# database data-entry mistake to correct, since "WX-2000" IS this
# chemical's real, correct name.
_CANONICAL_CHEMICAL_NAMES["WX-2000"] = "WX2000"


def _canonicalize_chemical_name(chemical_name: str) -> str:
    """Case-insensitive match against the known SX5 chemical names, or the
    input unchanged if it doesn't match any of them (so an actually-unknown
    chemical still fails the normal "not one of the 21 chemicals" path,
    rather than being silently accepted)."""
    return _CANONICAL_CHEMICAL_NAMES.get(chemical_name.upper(), chemical_name)

# Confirmed real (2026-09-03): a Composite chemical's anion block and
# embedded Assay are NOT unconditional -- they only appear on the real
# report when the sample's TR form actually requested them, same as
# every other Chemical/Water sample's analysis selections. The routine
# SX5 schedule-grid path (out of scope) DOES always get a fixed set --
# non-routine, which this module builds, does not.
_ANION_ANALYSIS_NAMES = {"4 Anions", "5 Anions", "7 Anions", "Anions", "5 Anions + MS Confirmation"}

# Which element-panel sheets each site's real template actually has --
# report layout, not customer data, so it stays in code. SurfClean is
# South-only: the database also holds North SurfClean limits (migrated from
# Access), but the validated SX5-N template has no SurfClean sheet, so a
# North SurfClean sample raises rather than inventing one.
_ELEMENT_CHEMICALS_BY_LOCATION = {
    "SX5N": {"NH4OH", "H2O2", "IPA", "BHF", "49%HF", "HCl"},
    "SX5S": {"NH4OH", "H2O2", "IPA", "BHF", "49%HF", "HCl", "SurfClean"},
}

# A composite sheet's spec rows hold both its element limits and these
# anion limits, in one set (same as the database stores them).
_COMPOSITE_ANION_SYMBOLS = frozenset({"Cl", "NO3", "SO4", "PO4"})


@dataclass(frozen=True)
class SX5SpecData:
    """The customer's own data for one (location, chemical) sheet, looked
    up from the database by the caller (see submission_report_builder.
    _sx5_spec_data) -- this module has no database dependency of its own,
    same as chemical_water_report_builder's metals_specs.

    specs: symbol -> limit, from the specifications table (element limits,
    plus anion limits for a composite sheet). qc_code: that table's
    category_label for these rows. assay_spec_text / report_note /
    display_label: from chemical_report_settings. Anything missing that a
    sheet needs raises a clear error rather than rendering a blank limit.
    """

    specs: dict[str, float] = field(default_factory=dict)
    qc_code: str | None = None
    assay_spec_text: str | None = None
    report_note: str | None = None
    display_label: str | None = None


@dataclass(frozen=True)
class SX5NonRoutineResult:
    sections: tuple[ReportSection, ...]
    chemical_label: str
    name_cell_address: str
    sample_string: str
    column_widths: dict[int, float]


def is_supported_chemical(chemical_name: str) -> bool:
    """Lets a caller check before committing to this path -- e.g. falling
    back to legacy handling for a SX5 chemical this doesn't know about
    yet, rather than raising.
    """
    return _get_category(_canonicalize_chemical_name(chemical_name)) != ""


def resolve_chemical_label(chemical_name: str, location: str, display_label: str | None = None) -> str:
    """The real display name (sheet tab AND title row) for a SX5 sample,
    given its raw resolved Chemical.name -- same canonicalize-then-label
    pipeline build_non_routine_report uses internally for its own
    chemical_label, exposed here so a caller that needs sheet NAMES for
    every sample up front (see submission_report_builder._sx5_tab_names)
    doesn't have to run the full builder just to get them. Confirmed real
    gap (2026-09-29, a real SX5-South comprehensive TR): the caller used
    to build tab names from the raw, un-canonicalized Chemical.name
    directly, which is wrong whenever the DB's own stored name doesn't
    match the real display convention -- e.g. the DB has "HCL" (real
    legacy tab: "HCl") and "WX-2000" (real SX5-South tab: "WX2000", no
    hyphen).

    display_label: the customer's required display name for this
    (location, chemical), if one is on file (SX5SpecData.display_label --
    e.g. SX5-North's WX2000 displays as "2to1WX2000", a real, currently
    unmet customer need that legacy never delivered because of an exact-
    string mismatch). None means the canonical chemical name is shown.
    """
    return display_label or _canonicalize_chemical_name(chemical_name)


def build_non_routine_report(
    chemical_name: str,
    location: str,
    date_received: date,
    sample_id: str,
    element_service: ElementService,
    requested_analysis_names: frozenset[str] = frozenset(),
    spec_data: SX5SpecData = SX5SpecData(),
) -> SX5NonRoutineResult:
    """chemical_name: the raw selection value (e.g. "NH4OH", "WX2000",
    "2.5%HF" -- one of the 21 known SX5 chemical names, raises if not).
    location: "SX5N" or "SX5S". sample_id: the TR-form's own sample
    identifier for this row (the same value every other Chemical/Water
    sample's sample string embeds).

    requested_analysis_names: the sample's OTHER resolved analysis
    selections (Anions/Titrations column), same names the generic
    Chemical/Water path resolves -- only consulted for the Composite
    category, to decide whether this sample's anion block / embedded
    Assay are actually present (see _ANION_ANALYSIS_NAMES above). Element
    and Assay category chemicals ignore this entirely; their shape never
    varies by what else was requested.

    spec_data: this (location, chemical)'s own limits, QC code, assay spec
    range, note and display label, looked up by the caller -- see
    SX5SpecData.
    """
    chemical_name = _canonicalize_chemical_name(chemical_name)
    category = _get_category(chemical_name)
    chemical_label = resolve_chemical_label(chemical_name, location, spec_data.display_label)
    where = f"{location} {chemical_name}"

    if category == "Element":
        if chemical_name not in _ELEMENT_CHEMICALS_BY_LOCATION.get(location, set()):
            raise ValueError(f"not a known element-panel chemical for {location}: {chemical_name!r}")
        sections = [
            sx5_element_panel_builder.build_element_panel(
                chemical_name, chemical_label, _require(spec_data.qc_code, "QC code", where),
                _require(spec_data.specs, "specification limits", where), element_service,
            )
        ]
        widths = column_widths.SX5_ELEMENT
    elif category == "Assay":
        parameter_label, result_col_label, note_text, bold_results_header = _get_assay_layout(chemical_name)
        sections = [
            sx5_assay_section_builder.build_assay(
                chemical_name, chemical_label, _require(spec_data.assay_spec_text, "assay spec range", where),
                parameter_label, result_col_label, note_text,
                bold_results_header=bold_results_header,
            )
        ]
        widths = column_widths.SX5_ASSAY
    elif category == "Composite":
        units_note_text, units_note_column = _get_composite_layout(chemical_name)
        qc_code = _require(spec_data.qc_code, "QC code", where)
        specs = _require(spec_data.specs, "specification limits", where)
        element_limits = {k: v for k, v in specs.items() if k not in _COMPOSITE_ANION_SYMBOLS}
        anion_limits = {k: v for k, v in specs.items() if k in _COMPOSITE_ANION_SYMBOLS}
        include_anions = bool(requested_analysis_names & _ANION_ANALYSIS_NAMES)
        include_assay = "Assay" in requested_analysis_names

        if include_anions:
            sections = [
                sx5_element_panel_builder.build_element_panel_with_anions(
                    chemical_name,
                    chemical_label,
                    qc_code,
                    element_limits,
                    _require(anion_limits, "anion specification limits", where),
                    element_service,
                    units_note_text,
                    units_note_column,
                )
            ]
        else:
            sections = [
                sx5_element_panel_builder.build_element_panel(
                    chemical_name,
                    chemical_label,
                    qc_code,
                    element_limits,
                    element_service,
                    units_note_text,
                    units_note_column,
                )
            ]
        if include_assay:
            sections.append(
                sx5_assay_section_builder.build_embedded_assay(
                    f"{chemical_name}_Assay",
                    _require(spec_data.assay_spec_text, "assay spec range", where),
                    spec_data.report_note or "",
                )
            )
        widths = column_widths.SX5_ELEMENT
    else:
        raise ValueError(f"unknown SX5 chemical for {location}: {chemical_name!r}")

    # The sample string shows the same display label as the sheet (e.g.
    # "2to1WX2000"), which the customer's own database needs to match.
    sample_string = build_sample_string(date_received, chemical_label, location, sample_id)
    # name_cell_address decides from the real LABEL, not the raw dispatch
    # key -- confirmed to resolve correctly for all 3 shapes (D5 for
    # element/composite, C4/C5 for the Assay shape's special cases) since
    # each shape's QC/Sample-# row was independently built to match the
    # real template's row position.
    cell_address = chemical_rules.name_cell_address(chemical_label)

    return SX5NonRoutineResult(
        sections=tuple(sections),
        chemical_label=chemical_label,
        name_cell_address=cell_address,
        sample_string=sample_string,
        column_widths=widths,
    )


# ---------------------------------------------------------------------------
# Private dispatch tables / helpers
# ---------------------------------------------------------------------------

def _get_category(chemical_name: str) -> str:
    if chemical_name in _ELEMENT_CHEMICALS:
        return "Element"
    if chemical_name in _ASSAY_CHEMICALS:
        return "Assay"
    if chemical_name in _COMPOSITE_CHEMICALS:
        return "Composite"
    return ""


def _require(value, what: str, where: str):
    """A SX5 sheet with a missing limit, QC code or spec range would print
    blank where the customer's specification belongs -- refuse instead,
    with a message naming exactly what's missing from the database."""
    if not value:
        raise ValueError(
            f"no SX5 {what} on file for {where} -- add it to the specification database "
            "before generating this report."
        )
    return value


def _get_assay_layout(chemical_name: str) -> tuple[str, str, str, bool]:
    """Returns (parameter_label, result_col_label, note_text,
    bold_results_header) -- the Assay sheet's layout; its spec range comes
    from the database (SX5SpecData.assay_spec_text). CSLX001 and WX7808
    share one shape ("% H2O2" result column, BOLD results-header columns,
    no note -- confirmed real via sxos5_north_wx7808, 0 mismatches). WX2000
    differs: "EXAMPLE LAB Results" result column, the "Bold Red Font..."
    note, and its results-header columns are NOT bold -- confirmed real
    (2026-09-29, a real SX5-South comprehensive TR).
    """
    if chemical_name in ("CSLX001", "WX7808"):
        return "Assay", "% H2O2", "", True
    if chemical_name == "WX2000":
        return "% H2O2", RESULTS_LABEL, "Bold Red Font: Indicates data outside specification limits", False
    raise ValueError(f"not a known Assay-shape chemical: {chemical_name!r}")


def _get_composite_layout(chemical_name: str) -> tuple[str, int]:
    """Returns (units_note_text, units_note_column). Both "0.49%HF" sheets
    use a longer caveat in column 3; "2.5%HF" uses the standard column-4
    text. QC code, limits, assay spec range and the assay note all come
    from the database (SX5SpecData)."""
    if chemical_name == "0.49%HF":
        return "All data in ppb except where indicated below.", 3
    if chemical_name == "2.5%HF":
        return "All data in ppb", 4
    raise ValueError(f"not a known composite chemical: {chemical_name!r}")
