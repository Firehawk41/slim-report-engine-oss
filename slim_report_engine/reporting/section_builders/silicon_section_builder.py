"""Builds the Silicon section — ported from clsSiliconSectionBuilder.cls:
Total Si (element "Silicon"/Si), Dissolved Si ("Dissolved Silica"/SiO2),
and — only when BOTH are selected — a calculated "Colloidal Silica"/SiO2
row (defined as the difference between the two; Total_Si = Silicon row
alone, Dissolved_Si = Dissolved Silica row alone, Colloidal Silica only
appears when both are requested together).

Not DB-backed like the metals builder: "Dissolved Silica"/"Colloidal
Silica" are chemical species, not periodic elements, so they aren't
resolvable via an element service.

Shares the metals/ions analyte-panel header shape (Element/Result/Recovery/
MDL) via row_builders.add_header_rows, but the real template uses the
SINGULAR "Result" here rather than the plural metals/ions use — a genuine
inconsistency in the template, reproduced verbatim via the result_label
override rather than "corrected" to match metals.

WATER-ONLY "silica" nomenclature (2026-09-28, direct user correction,
confirmed against the real legacy macro's own dummy-TR output): Water
customers expect silica nomenclature ("Compound" header, "Total
Silica"/SiO2" first row) even though the lab is actually testing for
elemental silicon -- since there's exactly one silicon atom per silica
molecule, the reported VALUE never needs adjusting, only the label.
Chemical customers keep the plain "Element"/"Silicon"/"Si" convention
unchanged -- confirmed real, NOT to be unified with Water's.
"""

from __future__ import annotations

from slim_domain.domain.tr.enums import RequestType

from slim_report_engine.lab_identity import RESULT_LABEL
from slim_report_engine.reporting import row_builders, sop_codes
from slim_report_engine.reporting.report_section import ReportSection


def build_silicon(
    id: str,
    include_total: bool,
    include_dissolved: bool,
    date_of_analysis: str | None = None,
    request_type: RequestType = RequestType.CHEMICAL,
) -> ReportSection:
    if not include_total and not include_dissolved:
        raise ValueError("must include at least one of total/dissolved Si")

    # Confirmed real (2026-09-28, checked against TWO real Water dummy-TR
    # samples, not just one -- see the "one example isn't enough" lesson):
    # the "silica" nomenclature is specific to the Total+Dissolved COMBO
    # case, not to Water in general. A Water sample selecting Total
    # Silicon ALONE (no Dissolved) uses the SAME plain "Element"/
    # "Silicon"/"Si" convention as Chemical -- the first check assumed
    # this applied whenever include_total and request_type==WATER, which
    # a second real example (Total-only) directly contradicted.
    is_water_combo = request_type == RequestType.WATER and include_total and include_dissolved
    header_col1_label = "Compound" if is_water_combo else "Element"
    total_si_name = "Total Silica" if is_water_combo else "Silicon"
    total_si_symbol = "SiO2" if is_water_combo else "Si"

    section = ReportSection(id)
    row_builders.add_header_rows(section, header_col1_label, "MDL", result_label=RESULT_LABEL)

    if include_total:
        row_builders.add_analyte_row(section, total_si_name, total_si_symbol)
    if include_dissolved:
        row_builders.add_analyte_row(section, "Dissolved Silica", "SiO2")
    if include_total and include_dissolved:
        row_builders.add_analyte_row(section, "Colloidal Silica *", "SiO2")

    if include_total:
        # Same real footer TEXT as the generic metals panel's own
        # ICP-OES/Evaporation combo, but NOT the same SOP codes -- the
        # lab's own SOP master list gives Silicon its own dedicated
        # "ICP-OES - Water Evaporator + Silicon" entry (SOP-49 in
        # addition to the shared SOP-02 base code), confirmed real; see
        # sop_codes.SILICON_TOTAL_SOP_CODES. The Water Total+Dissolved
        # combo prefixes this line with "Total Silica " (matching the
        # "Dissolved Silica " prefix the other footer line already
        # carries, unconditionally, below) -- confirmed real (2026-09-28).
        # Chemical, and Water's own Total-only case, keep the bare text.
        total_footer_text = "Total Silica Analysis by ICP-OES (Evaporation)" if is_water_combo else "Analysis by ICP-OES (Evaporation)"
        row_builders.add_footer_row(
            section, total_footer_text,
            sop_codes=sop_codes.SILICON_TOTAL_SOP_CODES, date_of_analysis=date_of_analysis,
        )
    if include_dissolved:
        row_builders.add_footer_row(
            section, "Dissolved Silica Analysis by UV-VIS (Evaporation)",
            sop_codes=sop_codes.SILICON_DISSOLVED_SOP_CODES, date_of_analysis=date_of_analysis,
        )
    if include_total and include_dissolved:
        row_builders.add_note_row(
            section,
            "* Colloidal silica is calculated as the difference between Total Silica and Dissolved Silica",
        )
        # Confirmed real gap (2026-09-25, direct user correction, Folder 111):
        # unlike add_footer_row (every other section's own closing row),
        # add_note_row never adds its own trailing blank spacer -- since
        # this note row is genuinely the LAST row of the section whenever
        # both Total and Dissolved Si are selected, the next section's own
        # sample-ID echo row was landing directly underneath it with no
        # gap at all, unlike every other section boundary in the report.
        section.add_row(row_builders.blank_row())

    return section
