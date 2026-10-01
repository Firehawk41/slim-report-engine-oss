"""Builds the "Misc Analysis" section shapes — ported from
clsMiscAnalysisSectionBuilder.cls: pH, Density, Liquid Particle Count
(LPC), and APHA Color. Confirmed from the real template to be 4 INDEPENDENT
atomic blocks — the real named ranges are every observed union of these 4
blocks, not independent content. Callers just include whichever build_*
results they want in their own section list; there's no preset per
combination.

NOTE: this Misc Analysis "pH" block is a separate TR-form entry point from
electrical_section_builder.build_ph — the real template has BOTH, since
Electrical Testing and Misc Analysis are offered as independent TR-form
selections (Water vs Chemical TR pathway). Confirmed real (2026-09-28,
direct user correction): there is not conceptually 2 pH, just 2 pathways
to the same real pH test, so this block shares Electrical Testing's own
confirmed 2-column ("STDEV") shape rather than being a genuinely distinct,
narrower shape.
"""

from __future__ import annotations

from slim_report_engine.lab_identity import RESULTS_LABEL, RESULT_LABEL
from slim_report_engine.reporting import row_builders, sop_codes
from slim_report_engine.reporting.report_section import ReportSection


def build_ph(id: str, date_of_analysis: str | None = None) -> ReportSection:
    section = ReportSection(id)
    max_columns = row_builders.add_simple_header_row(section, "pH", RESULT_LABEL, "STDEV")
    row_builders.add_analyte_row(section, "pH", "", max_columns=max_columns)
    row_builders.add_note_row(section, "Dimensionless quantity")
    row_builders.add_footer_row(
        section, "Analysis by pH Electrode", sop_codes=sop_codes.SIMPLE_SHAPE_SOP_CODES.get(id),
        date_of_analysis=date_of_analysis,
    )
    return section


def build_density(id: str, date_of_analysis: str | None = None) -> ReportSection:
    section = ReportSection(id)
    max_columns = row_builders.add_simple_header_row(section, "Density", RESULT_LABEL, "STDEV")
    row_builders.add_analyte_row(section, "Density of solution", "(g/mL)", max_columns=max_columns)
    row_builders.add_footer_row(
        section, "Analysis by Gay-Lussac Pycnometer", sop_codes=sop_codes.SIMPLE_SHAPE_SOP_CODES.get(id),
        date_of_analysis=date_of_analysis,
    )
    return section


def build_lpc(id: str, date_of_analysis: str | None = None) -> ReportSection:
    section = ReportSection(id)
    max_columns = row_builders.add_simple_header_row(section, "Particles/mL", RESULTS_LABEL, "STD Dev")
    for threshold in ("0.10", "0.15", "0.20", "0.30", "0.50", "1.00"):
        row_builders.add_analyte_row(section, _ge_threshold(threshold), "", max_columns=max_columns)
    row_builders.add_footer_row(
        section, "Analysis by Liquid Particle Counter.", sop_codes=sop_codes.SIMPLE_SHAPE_SOP_CODES.get(id),
        date_of_analysis=date_of_analysis,
    )
    return section


def build_apha(id: str, date_of_analysis: str | None = None) -> ReportSection:
    section = ReportSection(id)
    max_columns = row_builders.add_simple_header_row(section, "Parameter", RESULT_LABEL)
    row_builders.add_analyte_row(section, "APHA number", "", max_columns=max_columns)
    row_builders.add_footer_row(section, "Analysis by UV-Vis (average of six replicates)", date_of_analysis=date_of_analysis)
    return section


def build_standalone_hardness(id: str) -> ReportSection:
    """The shape when "Hardness" is requested on its OWN -- confirmed
    real (2026-09-28, a real Water "Premium package" bundle run through
    the real legacy macro; see water_package_builder.py) -- genuinely
    distinct from the metals-panel-embedded live-formula Hardness
    add-on (analyte_list_section_builder.py's include_hardness, "always
    an add-on to one of the panels above, never standalone" per that
    module's own docstring -- that claim covers the individual-checkbox
    path only, not this package-bundled one). Real, distinctive details
    reproduced verbatim: the result-column label is bare "Results", NOT
    "EXAMPLE LAB Result(s)" like every other shape, and there is NO
    "Analysis by ..." footer line at all -- the section ends directly
    with the standard one blank-row separator after the single data row.
    """
    section = ReportSection(id)
    max_columns = row_builders.add_simple_header_row(section, "Hardness", "Results")
    row_builders.add_analyte_row(section, "Hardness", "ppb", max_columns=max_columns)
    section.add_row(row_builders.blank_row())
    return section


def _ge_threshold(value_text: str) -> str:
    return f"≥ {value_text} µm"
