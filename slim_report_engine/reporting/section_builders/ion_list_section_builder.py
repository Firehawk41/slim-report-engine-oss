"""Builds a ReportSection for the Anions/Cations/GBP panel shape — ported
from clsIonListSectionBuilder.cls. Shares the header/row/footer shape with
the metals panels (see row_builders) but differs in that:

- ions aren't DB-backed at all (no "add a new anion" business process the
  way there is for chemicals/customers — fixed reference data, see
  presets/ion_presets.py), so this takes ready-made Analyte objects
  directly and has no element-service dependency;
- the third results column is labeled "QL", not "MDL" (confirmed from the
  real template);
- there is NO AVERAGE/TOTAL summary — confirmed from the real template,
  the block ends directly at the "Analysis by IC" footer;
- NO "Specification" column-1 label on the header's top row, unlike
  metals/silicon panels -- confirmed real (2026-09-28, dummy "test all
  analyses" TR run through the real legacy macro and diffed): ion panels
  never carry it.
"""

from __future__ import annotations

from slim_report_engine.reporting import row_builders
from slim_report_engine.reporting.analyte import Analyte
from slim_report_engine.reporting.report_section import ReportSection


def build_ion_panel(
    id: str,
    category_label: str,
    analytes: list[Analyte],
    footer_text: str,
    sop_codes: list[str] | None = None,
    date_of_analysis: str | None = None,
) -> ReportSection:
    """category_label: e.g. "Anion"/"Cation" (the column-header label above
    the analyte list). analytes: in display order (see presets/ion_presets.py).
    footer_text: e.g. "Analysis by IC". sop_codes: see
    row_builders.add_footer_row / reporting/sop_codes.py -- only a handful
    of real panels have a confirmed real mapping; None omits the line.
    """
    section = ReportSection(id)
    row_builders.add_header_rows(section, category_label, "QL", include_specification_label=False)

    for analyte in analytes:
        row_builders.add_analyte_row(section, analyte.name, analyte.symbol)

    row_builders.add_footer_row(section, footer_text, sop_codes=sop_codes, date_of_analysis=date_of_analysis)

    return section
