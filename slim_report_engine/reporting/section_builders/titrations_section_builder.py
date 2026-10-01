"""Builds the generic Titrations section shapes — ported from
clsTitrationsSectionBuilder.cls. Confirmed from the real template
("Full Analysis (8)" rows 295-332) to be 3 INDEPENDENT atomic blocks: Assay
(%), Karl Fischer Water (%), and GC-FID (Chemical 1/2, %/Vol) — the 4 real
Titrations_* named ranges are every observed union of these 3, not
independent content.

GC-FID's "Chemical 1"/"Chemical 2" row labels, and Assay's blank analyte
name, are real placeholders manually filled in by staff per sample after
generation — not resolved by any code path, so they're reproduced verbatim
here (same category as Wafer's own hand-filled notes).

DISPATCH STATUS: "Assay", "GC-FID", "Moisture (Karl Fischer)"/"Moisture",
"Sn+2 Iodine Titration", "Determination of Free Acid", and "Analysis of
TS-SLG" are all wired into chemical_water_report_builder.py — confirmed
against real completed reports (Assay: 3 different real Chemical
customers; GC-FID and Moisture (Karl Fischer): one real Chemical
customer's intake form uses both verbatim as Titrations selections, on
the same submission; Sn+2/Free Acid/TS-SLG: S:\\Reports\\Customer d53ad's real
"Ag-Sn Plating"/"SnAg" reports, which bundle all three together with a
2-element Ag/Sn metals block and a UV-Vis reading on one sheet -- the
generic builders here are the ones GENERIC to any customer requesting
that catalog analysis; Customer d53ad's own specific bundling of them together on
one sheet is its own customer-specific workflow, not reproduced here).

EXCLUDED (customer-specific edge cases, deferred, same bucket as other
customer-specific edge cases already out of scope): bespoke titration
blocks with hardcoded specification text tied to a specific customer/
chemical combination.
"""

from __future__ import annotations

from slim_report_engine.lab_identity import RESULTS_LABEL, RESULT_LABEL
from slim_report_engine.reporting import row_builders, sop_codes
from slim_report_engine.reporting.report_row import ReportRow
from slim_report_engine.reporting.report_section import ReportSection

_UV_VIS_MAX_COLUMNS = 9  # confirmed real: "Replicate 3" reaches column I


def build_assay(id: str, date_of_analysis: str | None = None) -> ReportSection:
    section = ReportSection(id)
    max_columns = row_builders.add_simple_header_row(section, "Assay", RESULT_LABEL, "STDEV")
    row_builders.add_analyte_row(section, "", "%", max_columns=max_columns)
    row_builders.add_footer_row(
        section, "Analysis by Auto-Titrator", sop_codes=sop_codes.SIMPLE_SHAPE_SOP_CODES.get(id),
        date_of_analysis=date_of_analysis,
    )
    return section


def build_kf_water(id: str, date_of_analysis: str | None = None) -> ReportSection:
    """Confirmed real: the data row's unit is "ppm", not the "%" the real
    VBA reference source (clsTitrationsSectionBuilder.cls) has -- the
    template that source was ported from disagrees with a real completed
    report on this one detail, and the real report wins (see this
    project's general policy: verify against real source over the
    closest local approximation).

    2-column (category label + Result + STDEV) -- confirmed real
    2026-09-28 (direct user correction): the 2026-09-25 fix that dropped
    this down to a single result column was itself wrong -- "2 column"
    means 2 real result columns (Result + STDEV), matching Electrical
    Testing's own confirmed shape, not "drop to 1."""
    section = ReportSection(id)
    max_columns = row_builders.add_simple_header_row(section, "Karl Fischer", RESULT_LABEL, "STDEV")
    row_builders.add_analyte_row(section, "Water", "ppm", max_columns=max_columns)
    row_builders.add_footer_row(
        section, "Analysis by KF-Titration", sop_codes=sop_codes.SIMPLE_SHAPE_SOP_CODES.get(id),
        date_of_analysis=date_of_analysis,
    )
    return section


def build_gc_fid(id: str, date_of_analysis: str | None = None) -> ReportSection:
    # 2-column (category label + Results + STDEV) -- confirmed real
    # 2026-09-28 (direct user correction): the 2026-09-25 fix that
    # dropped this down to a single result column was itself wrong -- "2
    # column" means 2 real result columns (Results + STDEV), matching
    # Electrical Testing's own confirmed shape, not "drop to 1."
    section = ReportSection(id)
    max_columns = row_builders.add_simple_header_row(section, "GC-FID", RESULTS_LABEL, "STDEV")
    row_builders.add_analyte_row(section, "Chemical 1", "%/Vol", max_columns=max_columns)
    row_builders.add_analyte_row(section, "Chemical 2", "%/Vol", max_columns=max_columns)
    row_builders.add_footer_row(
        section, "Analysis by GC-FID (average of triplicates)",
        sop_codes=sop_codes.SIMPLE_SHAPE_SOP_CODES.get(id),
        date_of_analysis=date_of_analysis,
    )
    return section


def build_sn2_iodine_titration(id: str, date_of_analysis: str | None = None) -> ReportSection:
    """Confirmed real (S:\\Reports\\Customer d53ad, multiple 2026 "Ag-Sn Plating"/
    "SnAg" reports, one-time permission granted 2026-09-17): "Determination
    of Sn+" in column 1 of the header row -- a real, specific title, not
    paraphrased from the catalog's own "Sn+2 Iodine Titration" name.
    Footer defaults to "Analysis by Hand Titration" -- the majority real
    form (4 of 5 real instances checked); one real instance instead reads
    "Analysis by Auto-Titrator", presumably hand-corrected by the
    technician for that specific run, same "review the Analysis by line
    before finalizing" workflow this whole system already assumes."""
    section = ReportSection(id)
    max_columns = row_builders.add_simple_header_row(
        section, "Assay", RESULT_LABEL, "STDEV", header_col1_label="Determination of Sn+"
    )
    row_builders.add_analyte_row(section, "Sn2+", "(g/L)", max_columns=max_columns)
    row_builders.add_footer_row(section, "Analysis by Hand Titration", date_of_analysis=date_of_analysis)
    return section


def build_free_acid(id: str, date_of_analysis: str | None = None) -> ReportSection:
    """Confirmed real (same Customer d53ad reports as build_sn2_iodine_titration,
    same sheet, same footer-method caveat)."""
    section = ReportSection(id)
    max_columns = row_builders.add_simple_header_row(
        section, "Assay", RESULT_LABEL, "STDEV", header_col1_label="Free Acid"
    )
    row_builders.add_analyte_row(section, "Free Acid", "(g/L)", max_columns=max_columns)
    row_builders.add_footer_row(section, "Analysis by Hand Titration", date_of_analysis=date_of_analysis)
    return section


def build_ts_slg(id: str, date_of_analysis: str | None = None) -> ReportSection:
    """Confirmed real (same Customer d53ad reports). One of 5 real instances checked
    reads "Analysis by Auto-Titrator" instead of "Analysis by Hand
    Titration" -- same majority-form/hand-correctable caveat as
    build_sn2_iodine_titration."""
    section = ReportSection(id)
    max_columns = row_builders.add_simple_header_row(
        section, "Assay", RESULT_LABEL, "STDEV", header_col1_label="TS-SLG"
    )
    row_builders.add_analyte_row(section, "TS-SLG", "(g/L)", max_columns=max_columns)
    row_builders.add_footer_row(section, "Analysis by Hand Titration", date_of_analysis=date_of_analysis)
    return section


def build_uv_vis(id: str, wavelengths: list[str], date_of_analysis: str | None = None) -> ReportSection:
    """Confirmed real (S:\\Reports\\Folder 2b00f, one-time permission granted
    2026-09-17: "010526-Folder 2b00f Acetonitrile Results.xlsx", matching the
    real intake form's free-text request "UV Vis Abs @ 190,200,210,220,
    230,254,400nm"). A variable-length wavelength/absorbance table, NOT a
    single reading -- the catalog's own "UV-Vis" description ("Absorbsion
    spectra by UV-Vis") confirms a spectrum scan is the real intent. This
    is a genuinely DIFFERENT thing from Customer d53ad's own "TS-140AD" (a fixed,
    single-value, customer-specific hand addition seen in the Ag-Sn
    Plating bundle) -- not the same test under two names, per direct user
    confirmation (2026-09-17): "UV-Vis and SnAg are two separate things".

    Real column shape: "Wavelength" / "EXAMPLE LAB Results" / "Replicate 1" /
    "Replicate 2" / "Replicate 3" (columns 2, 4, 7, 8, 9) -- wider than
    the family default (6), same override mechanism Wafer already uses
    for its own wide rows. One row per requested wavelength, exactly as
    typed in the free-text request (e.g. "190 nm"); value cells are left
    BLANK, same "blank report, staff fill in real readings after running
    it" convention every other section builder already follows -- this
    was never about pre-filling real instrument data.

    wavelengths: NOT resolved from anything today -- the real intake form
    only carries this as free text (no structured per-wavelength field
    exists yet), so nothing calls this yet. Ready for whenever the intake
    form is updated to capture a real wavelength list.
    """
    section = ReportSection(id)

    top_row = ReportRow(style_name="SampleIdEchoSimple", row_height=60.0, max_columns=_UV_VIS_MAX_COLUMNS)
    top_row.set_value(2, "Sample Identification:")
    top_row.add_merge(4, 6)
    section.add_row(top_row)

    header_row = ReportRow(style_name="ColumnHeader", row_height=25.5, max_columns=_UV_VIS_MAX_COLUMNS)
    header_row.set_value(2, "Wavelength")
    header_row.set_value(4, RESULTS_LABEL)
    header_row.set_value(7, "Replicate 1")
    header_row.set_value(8, "Replicate 2")
    header_row.set_value(9, "Replicate 3")
    section.add_row(header_row)

    for wavelength in wavelengths:
        row = ReportRow(style_name="DataLabel", max_columns=_UV_VIS_MAX_COLUMNS)
        row.set_value(2, wavelength)
        section.add_row(row)

    row_builders.add_footer_row(section, "Analysis by UV-Vis (Abs)", date_of_analysis=date_of_analysis)
    return section
