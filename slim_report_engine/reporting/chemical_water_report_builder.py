"""Orchestrates ONE Chemical/Water sample's report content — dispatches
each of the sample's resolved analysis IDs (TRSample.analysis_ids, from
slim-domain's TR parsing stack) to the right section-builder function, in
the ORDER the analyses were requested, and returns the assembled sections.
Ported from clsChemicalWaterReportBuilder.cls.

Covers the analyses that map unambiguously onto an existing section
builder. Deliberately NOT supported yet (raises a clear, actionable error
rather than guessing):
  - Organic-matrix / ICP-OES / microwave-digestion / "with reported
    replicates" element-panel variants, GC-MS, Mixed Acid Assay, UV-Vis,
    and all customer-specific edge cases — deliberately last priority, not
    attempted here.

"MOISTURE" — confirmed real (2026-09-17, direct user correction): the
catalog's plain "Moisture" name is the same Karl Fischer content as
"Moisture (Karl Fischer)", not a different method -- both dispatch to
titrations_section_builder.build_kf_water. Not to be confused with a
GC-MS-based moisture method, if one exists in the catalog -- still
deferred, no evidence yet either way.

"5 ANIONS + MS CONFIRMATION" — confirmed real (one real Chemical
customer's report): renders the EXACT SAME 5-anion panel as plain
"5 Anions" (same analytes, same order, same footer). The "MS
Authentication" appendix visible on the real report (a "Conductivity"
label, ~35 blank rows, then an "MS data with..." label and 3 hand-typed
notes) is confirmed genuinely blank in every real file checked — no
embedded image, no cell data — i.e. staff paste/type it in separately
after generation; not reproduced here, same category as GC-FID's
manually-filled chemical-name placeholders. This matches the legacy
macro's own treatment (modReportCreator.bas only substitutes the TAB NAME
text for this variant, "MS confirmation" -> "MS Authentication", implying
the underlying content was already understood to be identical).

"MS Authentication" is the FORM-facing selection label (and the legacy
tab-name text above) -- the resolved analysis this dispatches on is the
CATALOG's own name, confirmed real (form_analyses -> analyses join):
"5 Anions + MS Confirmation". A real bug until this fix: this branch
compared against the form label ("...Authentication") instead of the
resolved catalog name ("...Confirmation") that analysis_service.
load_analysis(...).name actually returns, so it could never match --
every real customer selecting this analysis (via any of its several real
form labels: "5 Anions + MS Authentication", "5 Anions with MS
confirmation", "5 Anions + MS confirmation") would have hit the
"not yet supported" fallback instead of this already-confirmed-correct
panel.

"4/7 ANIONS + MS CONFIRMATION" and "GBP + MS CONFIRMATION" — confirmed
real (2026-09-28, direct user instruction after a fresh dummy "test all
analyses" TR was run through the real legacy macro and diffed against
this project's output): same treatment as "5 Anions + MS Confirmation"
above -- identical panel content to the plain "4 Anions"/"7 Anions"/"GBP"
panel. (An earlier version of this note cited a separate, ABANDONED "new
VBA" rewrite project -- clsChemicalWaterReportBuilder.cls in the
Python-VBA-Bridge repo -- as evidence the whole "+ MS Confirmation"
family was unsupported in the real legacy macro; direct user correction:
that file is scrap from a rewrite attempt superseded by this very
Python+hook project, not the real production macro, and doesn't apply
here.)

PREP TEXT — the metals panel's footer ("Analysis by ICPMS (<prep>)") is
NOT a fixed string. Confirmed real: Chemical samples use the resolved
Chemical's own catalog prep method (Chemical.metals_prep -- one real
Chemical sample's report used "Evaporation"), defaulting to "Evaporation"
when that field is blank (current lab practice, per direct confirmation:
default to Evaporation, then hand-correct when something else applies).
Water samples use "Dilute and Shoot" instead — confirmed across every real
Water sample checked, including ones with a full catalog panel, not just
additional-elements-only ones — there's no Chemical record for Water to
read a prep from at all, and physically it's a different method
(concentrates get evaporated down; water samples are already dilute). The
caller (submission_report_builder.py) computes this and passes it in as
metals_prep_text; this module has no DB dependency of its own.

ION PANEL PREP TEXT is a SEPARATE catalog field, not the same as the
metals panel's — a real, direct correction after this was initially
(incorrectly) built to reuse metals_prep_text: Chemical.ions_prep
(slim-domain) already existed as its own field but was never actually
read anywhere. Confirmed real (cross-checked against a completed report):
one specific real chemical's ions_prep genuinely happens to equal
"Evaporation" too (hence the original, too-hasty generalization), but
every other real chemical's ion panel footer has NO parenthesized prep
at all — just a bare "Analysis by IC". ions_prep_text is None by default
(bare form); the caller only passes a value when the resolved Chemical
has one on file.

ADDITIONAL ELEMENTS — confirmed real (several real Chemical and Water
customers' reports): the free-text "Additional Elements (specify)"
request was previously silently dropped entirely by this module. Now
rendered two ways, confirmed against real completed reports: appended as
a second labeled block after an existing metals panel's footer when one
was also requested (see
analyte_list_section_builder.add_additional_elements_block), or as its own
minimal panel-shaped section when additional elements are the ONLY thing
requested on a sample (confirmed real: several real Water samples were
exactly like this — see
analyte_list_section_builder.build_additional_elements_only_panel). Both
default to the SAME prep_text as the sample's main metals panel, unless
additional_elements_prep_text overrides it — confirmed real: at least one
customer's additional elements are run by a different method than their
main panel, per an agreement with that customer. The override is
deliberately customer-agnostic here: this module has no idea WHICH
customer, just whatever text the caller resolved from
Customer.additional_elements_prep (slim-domain) — the real customer-
specific value belongs only in a real database record, never in this
public repo.

PH DISPATCH — a deliberate improvement over the VBA source: standalone
"pH" (Conductivity NOT also requested) maps to
misc_analysis_section_builder.build_ph; "pH" + "Conductivity" together map
to electrical_section_builder.build_conductivity_and_ph. The VBA source
raises on standalone "pH" rather than resolving it, reasoning the resolved
analysis ID alone couldn't disambiguate two real, distinct template blocks.
Verified empirically against the real Chemical/Water intake forms' own
dropdown option lists that this ambiguity doesn't actually exist in
practice: Chemical's form never offers "Conductivity" as an option at all,
and Water's dropdown has a distinct "Conductivity + pH" value separate
from standalone "pH" — so `has_conductivity` alone is sufficient, no need
to carry original form text through the parsing stack.

SILICON GAP FIX — also a deliberate improvement: the VBA source's
BuildSections checks for an analysis literally named "Dissolved and Total
Si" (in its Total/DissolvedSi flags) but its CanBuildSections' allow-list
never includes that name — a real inconsistency between the two methods in
the same class. Included here in the supported set so the two functions
agree, rather than reproduced verbatim.
"""

from __future__ import annotations

from slim_domain.domain.analysis.analysis_service import AnalysisService
from slim_domain.domain.element.element_service import ElementService
from slim_domain.domain.tr.enums import RequestType
from slim_domain.domain.tr.tr_sample import TRSample

from slim_report_engine.reporting import sop_codes
from slim_report_engine.reporting.presets import analyte_presets, ion_presets
from slim_report_engine.reporting.report_section import ReportSection
from slim_report_engine.reporting.section_builders import (
    analyte_list_section_builder,
    electrical_section_builder,
    ion_list_section_builder,
    misc_analysis_section_builder,
    silicon_section_builder,
    simple_test_section_builder,
    titrations_section_builder,
)

_UNCONDITIONALLY_SUPPORTED = {
    "36 Elements", "26 Elements", "10 Elements", "67 Elements", "USP Elements", "List #2 36 Elements",
    "Hardness",  # confirmed real: always an add-on to one of the panels above, never standalone
    "4 Anions", "5 Anions", "7 Anions", "Anions",
    "4 Anions + MS Confirmation", "5 Anions + MS Confirmation", "7 Anions + MS Confirmation",
    "Cl", "Acetate and Formate", "Organic Anions",
    "6 Cations", "NH4", "Methylamines", "Cations", "GBP", "GBP + MS Confirmation",
    "Total Silicon", "Dissolved Silicon", "Dissolved and Total Si",
    "TOC", "Alkalinity", "Bacteria Count",
    "Conductivity", "Density", "Liquid Particle Count", "APHA Color",
    "pH", "Assay", "GC-FID", "Moisture (Karl Fischer)", "Moisture",
    "Sn+2 Iodine Titration", "Determination of Free Acid", "Analysis of TS-SLG",
}


def can_build_sections(sample: TRSample, analysis_service: AnalysisService) -> bool:
    """Lets a caller check before committing to this path — e.g. falling
    back to legacy handling for a sample whose analyses this doesn't (yet)
    fully cover, rather than raising mid-build.

    Its "nothing to build at all" branch (no resolved analyses and no
    additional elements) is also enforced directly inside build_sections()
    now — confirmed real gap (2026-09-24 code review): a Testing Request
    row can have a Sample ID with no analysis checkboxes checked at all (a
    realistic data-entry slip), and without that guard build_sections()
    silently returned an empty section list, producing a "successful"
    report tab with a title and no analytical content whatsoever. Kept as
    a narrower inline check there rather than calling this function
    outright, since this function's OTHER branch (an unsupported analysis
    name) needs to keep surfacing build_sections()'s own more specific
    per-name error instead.
    """
    if sample.water_package:
        return sample.water_package in (_PREMIUM_PACKAGE, _STANDARD_PACKAGE)

    names = _resolved_names_in_order(sample, analysis_service)
    if not names:
        # No named analysis at all is still buildable when the sample's
        # only request is the free-text "Additional Elements" field --
        # confirmed real (a real Water customer's report) -- see build_sections.
        return bool(sample.additional_element_ids)
    return all(name in _UNCONDITIONALLY_SUPPORTED for name in names)


def build_sections(
    sample: TRSample,
    analysis_service: AnalysisService,
    element_service: ElementService,
    metals_prep_text: str = "Evaporation",
    additional_elements_prep_text: str | None = None,
    metals_instrument: str = "ICPMS",
    ions_prep_text: str | None = None,
    metals_specs: dict[str, float] | None = None,
    has_ked_elements: bool = False,
    ked_element_ids: frozenset[int] = frozenset(),
    date_of_analysis: str | None = None,
    request_type: RequestType = RequestType.CHEMICAL,
) -> list[ReportSection]:
    """Returns one (or more, for Silicon's calculated Colloidal Silica row,
    or the additional-elements block) ReportSection per resolved analysis
    on the sample, in request order — except Conductivity+pH, which
    collapse into ONE combined section.

    metals_specs: element symbol -> real spec threshold for the metals
    panel (and any additional-elements block), from the resolved
    customer+chemical's real Specification data (slim-domain) -- None/{}
    means no real spec on file, which simply omits the column-1 value
    (never guessed). The caller (submission_report_builder.py) resolves
    this from SpecificationService; this module has no DB dependency of
    its own.

    metals_prep_text: the metals panel's footer method text -- see module
    docstring's PREP TEXT section. The caller (submission_report_builder.py)
    computes this from the resolved Chemical's catalog prep (Chemical/Water
    request-type dependent); this module has no DB dependency of its own.

    additional_elements_prep_text: a separate prep-text override for the
    additional-elements block specifically -- None (the default) means
    "no override, reuse metals_prep_text" (current behavior). Confirmed
    real: at least one customer's additional elements are run by a
    different method than their main panel; see Customer.additional_elements_prep
    (slim-domain) -- deliberately customer-agnostic here too, this
    function has no idea which customer it's building for, just whatever
    text the caller resolved.

    metals_instrument: the footer's instrument name ("Analysis by
    <this> (<prep>)") -- see Chemical.metals_instrument (slim-domain) and
    analyte_list_section_builder.build_metals_panel's own docstring.
    Applied identically to the main panel AND any additional-elements
    block -- unlike prep_text, it's a property of the sample's physical
    matrix, not something that varies per block.

    ions_prep_text: the ion panels' own footer method text -- see module
    docstring's PREP TEXT section. NOT the same as metals_prep_text: this
    was previously (incorrectly) reused from the metals panel, but
    Chemical.ions_prep (slim-domain) is its own separate catalog field --
    confirmed real (direct user correction against a real completed
    report): only the one real chemical whose real ions_prep happens to
    also be "Evaporation" should show a parenthesized prep at all; every
    other real ion panel checked has NO parenthesized prep, just a bare
    "Analysis by IC". None (the default, when the resolved chemical has no
    ions_prep on file) renders the bare form -- never guessed.

    has_ked_elements: whether the resolved Chemical has KED-flagged
    elements on file (Chemical.ked_element_ids, slim-domain) -- passed
    straight through to the metals panel (see
    analyte_list_section_builder.build_metals_panel); irrelevant to every
    other section built here.

    ked_element_ids: the actual set of KED-flagged element IDs (same
    source, Chemical.ked_element_ids) -- added 2026-09-25 alongside the
    pre-existing boolean above, which only says whether ANY exist, not
    which ones. Used to mark the specific affected rows (bold red) so
    there's a real visible link back to the footer's "Note 1: ICPMS-KEDS
    mode..." line -- confirmed real gap (direct user correction): the
    note text existed with nothing on the actual element rows referencing
    it.

    request_type: confirmed real (2026-09-23, two live production
    reports): Water's ion panels (Anions/Cations/GBP) list analytes
    alphabetically by name; Chemical's list them in elution order (see
    _maybe_alphabetize) -- a real, deliberate difference between the two
    request types, not an inconsistency to unify. Defaults to CHEMICAL
    (the order every ion-panel test already assumes) so existing callers
    that don't care about this distinction are unaffected.

    date_of_analysis: pre-formatted "MM-DD-YY" text (see
    submission_report_builder._date_of_analysis_text / date_of_analysis.py)
    -- passed straight through to every section built here that has a
    "Date of Analysis: " footer placeholder (everything except SX5, which
    doesn't use row_builders.add_footer_row at all).
    """
    if sample.water_package:
        # Confirmed real (2026-09-28, a real Water dummy TR run through
        # the legacy macro): a "Water testing package" selection bundles
        # a FIXED set of panels, entirely independent of (and, in every
        # real example checked, used INSTEAD of) the normal individual-
        # checkbox analysis_ids -- checked first, short-circuiting the
        # rest of this function, rather than trying to merge it into the
        # per-name dispatch loop below. Deliberate rule (direct user
        # decision, 2026-09-30): when a package is selected, any other
        # analyses or additional elements on the same row are ignored.
        return _build_water_package_sections(sample.water_package, element_service, date_of_analysis)

    names = _resolved_names_in_order(sample, analysis_service)
    if not names and not sample.additional_element_ids:
        raise ValueError(
            f"sample {sample.sample_name!r} has no analyses selected -- nothing to build. "
            "The Testing Request row has a Sample ID but no analysis checkboxes and no "
            "additional elements; check the source form rather than generating a blank report."
        )
    names_set = set(names)

    has_conductivity = "Conductivity" in names_set
    has_acetate_formate = "Acetate and Formate" in names_set
    include_total_si = "Total Silicon" in names_set or "Dissolved and Total Si" in names_set
    include_dissolved_si = "Dissolved Silicon" in names_set or "Dissolved and Total Si" in names_set
    # Confirmed real (2026-09-23, Folder b65a8 evidence): Acetate/Formate
    # is NOT its own panel when a core Anions selection is ALSO requested
    # -- the real legacy report merges both into ONE alphabetized panel
    # (Acetate, Bromide, Chloride, ... Formate, ...). Only renders as its
    # own standalone panel (the 2026-09-17 confirmed case) when no core
    # Anions selection is present to merge into. Computed up front (not a
    # flag set while iterating) so it's correct regardless of which name
    # the dispatch loop below visits first.
    acetate_formate_merged = has_acetate_formate and bool(
        names_set & {
            "4 Anions", "5 Anions", "7 Anions", "Anions",
            "4 Anions + MS Confirmation", "5 Anions + MS Confirmation", "7 Anions + MS Confirmation",
        }
    )

    sections: list[ReportSection] = []
    silicon_added = False
    conductivity_and_ph_handled = False
    # Tracks the one metals-panel section a sample can have (36/26/10/67/
    # USP/List#2 36 -- mutually exclusive real form selections), so a
    # trailing additional-elements block can be attached to it below,
    # after the dispatch loop -- see module docstring's ADDITIONAL
    # ELEMENTS section.
    metals_panel_section: ReportSection | None = None

    for name in names:
        if name in ("36 Elements", "26 Elements", "10 Elements"):
            # The 10/26/36-Elements selections render the SAME 36-element
            # list -- only the AVERAGE/TOTAL summary label differs.
            summary_label = name.replace("Elements", "Tr.Elts")
            metals_panel_section = analyte_list_section_builder.build_metals_panel(
                name, analyte_presets.trace_elements_36(), summary_label, element_service, metals_prep_text,
                instrument=metals_instrument, specs=metals_specs, has_ked_elements=has_ked_elements,
                ked_element_ids=ked_element_ids,
                date_of_analysis=date_of_analysis, include_hardness="Hardness" in names_set,
            )
            sections.append(metals_panel_section)
        elif name == "67 Elements":
            metals_panel_section = analyte_list_section_builder.build_metals_panel(
                name, analyte_presets.trace_elements_67(), "67 Tr.Elts", element_service, metals_prep_text,
                instrument=metals_instrument, specs=metals_specs, has_ked_elements=has_ked_elements,
                ked_element_ids=ked_element_ids,
                date_of_analysis=date_of_analysis, include_hardness="Hardness" in names_set,
            )
            sections.append(metals_panel_section)
        elif name == "USP Elements":
            metals_panel_section = analyte_list_section_builder.build_metals_panel(
                name, analyte_presets.trace_elements_usp(), "USP Tr.Elts", element_service, metals_prep_text,
                instrument=metals_instrument, specs=metals_specs, has_ked_elements=has_ked_elements,
                ked_element_ids=ked_element_ids,
                date_of_analysis=date_of_analysis, include_hardness="Hardness" in names_set,
            )
            sections.append(metals_panel_section)
        elif name == "List #2 36 Elements":
            metals_panel_section = analyte_list_section_builder.build_metals_panel(
                name, analyte_presets.trace_elements_36_list2(), "36 Tr.Elts", element_service, metals_prep_text,
                instrument=metals_instrument, specs=metals_specs, has_ked_elements=has_ked_elements,
                ked_element_ids=ked_element_ids,
                date_of_analysis=date_of_analysis, include_hardness="Hardness" in names_set,
            )
            sections.append(metals_panel_section)
        elif name == "Hardness":
            # Confirmed real: never its own section -- always an add-on to
            # whichever metals panel selection is ALSO present (see the
            # branches above, which each check "Hardness" in names_set and
            # append the live-formula row themselves). Nothing to do here;
            # this case exists only so the dispatch loop doesn't fall
            # through to the "not yet supported" error for it.
            pass
        elif name == "4 Anions":
            analytes = ion_presets.anions_4()
            if acetate_formate_merged:
                analytes = analytes + ion_presets.acetate_and_formate()
            sections.append(_ion_panel(name, "Anion", _maybe_alphabetize(analytes, request_type), ions_prep_text, date_of_analysis))
        elif name == "4 Anions + MS Confirmation":
            # Confirmed real (2026-09-28, dummy "test all analyses" TR run
            # through the real legacy macro and diffed): identical panel
            # content to plain "4 Anions", same as "5 Anions + MS
            # Confirmation" below.
            analytes = ion_presets.anions_4()
            if acetate_formate_merged:
                analytes = analytes + ion_presets.acetate_and_formate()
            sections.append(_ion_panel(name, "Anion", _maybe_alphabetize(analytes, request_type), ions_prep_text, date_of_analysis))
        elif name == "5 Anions":
            analytes = ion_presets.anions_5()
            if acetate_formate_merged:
                analytes = analytes + ion_presets.acetate_and_formate()
            sections.append(_ion_panel(name, "Anion", _maybe_alphabetize(analytes, request_type), ions_prep_text, date_of_analysis))
        elif name == "5 Anions + MS Confirmation":
            # Confirmed real: identical panel content to plain "5 Anions"
            # -- see module docstring's "5 ANIONS + MS CONFIRMATION"
            # section for why the appendix isn't reproduced here.
            analytes = ion_presets.anions_5()
            if acetate_formate_merged:
                analytes = analytes + ion_presets.acetate_and_formate()
            sections.append(_ion_panel(name, "Anion", _maybe_alphabetize(analytes, request_type), ions_prep_text, date_of_analysis))
        elif name == "7 Anions":
            analytes = ion_presets.anions_7()
            if acetate_formate_merged:
                analytes = analytes + ion_presets.acetate_and_formate()
            sections.append(_ion_panel(name, "Anion", _maybe_alphabetize(analytes, request_type), ions_prep_text, date_of_analysis))
        elif name == "7 Anions + MS Confirmation":
            # Confirmed real (2026-09-28, same dummy-TR diff as "4 Anions
            # + MS Confirmation" above): identical panel content to plain
            # "7 Anions".
            analytes = ion_presets.anions_7()
            if acetate_formate_merged:
                analytes = analytes + ion_presets.acetate_and_formate()
            sections.append(_ion_panel(name, "Anion", _maybe_alphabetize(analytes, request_type), ions_prep_text, date_of_analysis))
        elif name == "Anions":
            analytes = ion_presets.anions_master()
            if acetate_formate_merged:
                analytes = analytes + ion_presets.acetate_and_formate()
            sections.append(_ion_panel(name, "Anion", _maybe_alphabetize(analytes, request_type), ions_prep_text, date_of_analysis))
        elif name == "Cl":
            # Confirmed real (2026-09-17, direct user correction, real
            # Customer 436f6 Water intake form): a standalone Chlorine/Chloride
            # selection -- same rendering as any other Anion panel, just
            # with one row. Same shape as the "NH4" cation case below.
            # No real evidence Acetate/Formate ever co-occurs with this
            # single-ion selection -- not merged here, unlike the core
            # Anions sizes below, rather than guessing.
            sections.append(_ion_panel(name, "Anion", _maybe_alphabetize(ion_presets.anions_cl(), request_type), ions_prep_text, date_of_analysis))
        elif name == "Acetate and Formate":
            # Confirmed real (2026-09-17, direct user correction): organic
            # anions, rendered exactly like any other Anion panel -- but
            # ONLY when no core Anions selection is also present to merge
            # into (see acetate_formate_merged comment above; confirmed
            # real 2026-09-23 against a Folder b65a8 report that DOES
            # combine both).
            if not acetate_formate_merged:
                sections.append(
                    _ion_panel(name, "Anion", _maybe_alphabetize(ion_presets.acetate_and_formate(), request_type), ions_prep_text, date_of_analysis)
                )
        elif name == "6 Cations":
            sections.append(_ion_panel(name, "Cation", _maybe_alphabetize(ion_presets.cations_6(), request_type), ions_prep_text, date_of_analysis))
        elif name == "NH4":
            sections.append(_ion_panel(name, "Cation", _maybe_alphabetize(ion_presets.cations_nh4(), request_type), ions_prep_text, date_of_analysis))
        elif name == "Methylamines":
            sections.append(
                _ion_panel(name, "Cation", _maybe_alphabetize(ion_presets.cations_methylamines(), request_type), ions_prep_text, date_of_analysis)
            )
        elif name == "Cations":
            sections.append(_ion_panel(name, "Cation", _maybe_alphabetize(ion_presets.cations_master(), request_type), ions_prep_text, date_of_analysis))
        elif name == "GBP":
            # category_label corrected 2026-09-25 (direct real-evidence
            # diff against real completed Folder b65a8 and Folder 3da91 Animal
            # Health reports): "Anion", not "Analyte" -- matches direct
            # user confirmation the same day ("GBP is same as regular
            # anions") and every other real GBP table found.
            sections.append(_ion_panel(name, "Anion", _maybe_alphabetize(ion_presets.gbp_group(), request_type), ions_prep_text, date_of_analysis))
        elif name == "GBP + MS Confirmation":
            # Confirmed real (2026-09-28, dummy "test all analyses" TR run
            # through the real legacy macro and diffed): identical panel
            # content to plain "GBP", same pattern as the Anions "+ MS
            # Confirmation" variants above.
            sections.append(_ion_panel(name, "Anion", _maybe_alphabetize(ion_presets.gbp_group(), request_type), ions_prep_text, date_of_analysis))
        elif name == "Organic Anions":
            # Direct user instruction (2026-09-28, no real customer/report
            # evidence available yet -- implemented on direct confirmation
            # after flagging the lack of evidence): the catalog's own
            # description pairs "Organic Anions" ("Anions (organic)")
            # against "Anions + Organic Anions" ("Anions (organic and
            # inorganic)"), i.e. bare "Organic Anions" is the organic-only
            # half -- GBP (Glycolate/Butyrate/Propionate) plus Acetate/
            # Formate, the only two organic-anion presets this system has.
            # Two separate panels, same shape as selecting "GBP" and
            # "Acetate and Formate" independently.
            sections.append(_ion_panel("GBP", "Anion", _maybe_alphabetize(ion_presets.gbp_group(), request_type), ions_prep_text, date_of_analysis))
            sections.append(
                _ion_panel(name, "Anion", _maybe_alphabetize(ion_presets.acetate_and_formate(), request_type), ions_prep_text, date_of_analysis)
            )
        elif name in ("Total Silicon", "Dissolved Silicon", "Dissolved and Total Si"):
            # Total/Dissolved Silicon share ONE build_silicon call (it
            # decides internally whether to add the Colloidal Silica row)
            # -- guard against calling it twice when a sample requests both.
            if not silicon_added:
                sections.append(
                    silicon_section_builder.build_silicon(
                        "Silicon", include_total_si, include_dissolved_si, date_of_analysis, request_type
                    )
                )
                silicon_added = True
        elif name == "TOC":
            sections.append(simple_test_section_builder.build_toc(name, date_of_analysis))
        elif name == "Alkalinity":
            sections.append(simple_test_section_builder.build_alkalinity(name, date_of_analysis))
        elif name == "Bacteria Count":
            sections.append(simple_test_section_builder.build_bacteria(name, date_of_analysis))
        elif name == "Conductivity":
            if "pH" in names_set:
                if not conductivity_and_ph_handled:
                    sections.append(electrical_section_builder.build_conductivity_and_ph(name, date_of_analysis))
                    conductivity_and_ph_handled = True
                # else: already added when "pH" was processed (or will be) -- skip duplicate
            else:
                sections.append(electrical_section_builder.build_conductivity(name, date_of_analysis))
        elif name == "pH":
            if has_conductivity:
                if not conductivity_and_ph_handled:
                    sections.append(electrical_section_builder.build_conductivity_and_ph(name, date_of_analysis))
                    conductivity_and_ph_handled = True
            else:
                sections.append(misc_analysis_section_builder.build_ph(name, date_of_analysis))
        elif name == "Density":
            sections.append(misc_analysis_section_builder.build_density(name, date_of_analysis))
        elif name == "Liquid Particle Count":
            sections.append(misc_analysis_section_builder.build_lpc(name, date_of_analysis))
        elif name == "APHA Color":
            sections.append(misc_analysis_section_builder.build_apha(name, date_of_analysis))
        elif name == "Assay":
            sections.append(titrations_section_builder.build_assay(name, date_of_analysis))
        elif name == "GC-FID":
            # Confirmed real (a real Chemical customer's intake form uses
            # "GC-FID" verbatim as a Titrations selection) -- see
            # titrations_section_builder.py's DISPATCH STATUS note, now
            # updated: this is no longer a guess.
            sections.append(titrations_section_builder.build_gc_fid(name, date_of_analysis))
        elif name in ("Moisture (Karl Fischer)", "Moisture"):
            # Confirmed real (same real Chemical customer's intake form,
            # verbatim Titrations selection alongside "GC-FID" above).
            # "Moisture" (2026-09-17, direct user correction) is the SAME
            # Karl Fischer content under the catalog's shorter name --
            # not a different method, just a different label for it.
            sections.append(titrations_section_builder.build_kf_water(name, date_of_analysis))
        elif name == "Sn+2 Iodine Titration":
            # Confirmed real (S:\Reports\Customer d53ad's real "Ag-Sn Plating"/
            # "SnAg" reports) -- see titrations_section_builder.py's
            # DISPATCH STATUS note.
            sections.append(titrations_section_builder.build_sn2_iodine_titration(name, date_of_analysis))
        elif name == "Determination of Free Acid":
            sections.append(titrations_section_builder.build_free_acid(name, date_of_analysis))
        elif name == "Analysis of TS-SLG":
            sections.append(titrations_section_builder.build_ts_slg(name, date_of_analysis))
        else:
            raise ValueError(
                f"analysis {name!r} is not yet supported by this architecture -- "
                "add a case for it once a matching section builder exists "
                "(see module docstring for the deferred list)."
            )

    additional_element_names = _resolve_additional_element_names(sample, element_service)
    if additional_element_names:
        prep_text = additional_elements_prep_text if additional_elements_prep_text is not None else metals_prep_text
        # A customer whose Additional Elements are run by a different
        # method (Customer.additional_elements_prep -- e.g. Folder 6c581
        # Houston's Organic Dilute and Shoot, by agreement) gets no limits
        # on those rows: the limits on file belong to the main method.
        # Direct user confirmation 2026-10-01; the chemist used to delete
        # them by hand.
        different_method = bool(additional_elements_prep_text) and additional_elements_prep_text != metals_prep_text
        if metals_panel_section is not None:
            rows_before = len(metals_panel_section.rows)
            analyte_list_section_builder.add_additional_elements_block(
                metals_panel_section, additional_element_names, element_service, prep_text, metals_instrument,
                metals_specs, has_ked_elements, date_of_analysis, ked_element_ids,
            )
            if different_method:
                _exclude_limits(metals_panel_section.rows[rows_before:])
        else:
            # Confirmed real (2026-09-23, live production report, Customer 436f6):
            # metals leads the sheet regardless of which column on the
            # intake form the request came from -- an appended-at-the-end
            # additional-elements-only panel put it AFTER Silicon and
            # Anion sections instead. Insert at the front, matching every
            # other real case where a full metals-preset panel is
            # naturally built first because "# of Elements" sits at the
            # very start of the analysis columns.
            only_panel = analyte_list_section_builder.build_additional_elements_only_panel(
                "Additional Elements", additional_element_names, element_service, prep_text, metals_instrument,
                metals_specs, has_ked_elements, date_of_analysis, ked_element_ids,
            )
            if different_method:
                _exclude_limits(only_panel.rows)
            sections.insert(0, only_panel)

    return sections


_PREMIUM_PACKAGE = "Premium package"
_STANDARD_PACKAGE = "Standard package"


def _build_water_package_sections(
    package_name: str, element_service: ElementService, date_of_analysis: str | None
) -> list[ReportSection]:
    """Confirmed real (2026-09-28, a real Water dummy TR run through the
    real legacy macro): "Water testing package" bundles a FIXED set of
    panels. Only 2 real packages confirmed so far -- an unrecognized
    package name raises rather than guessing, same policy as an
    unsupported analysis name. Neither real example checked has any
    customer+chemical specs, KED elements, or additional elements on
    file, so none of those are wired in here yet -- revisit if a real
    package sample ever does. id/name strings passed to each builder
    match exactly what the normal per-analysis-name dispatch loop above
    would use for the same content, so SOP-code lookups (keyed by name,
    not by content) still resolve correctly.
    """
    if package_name == _PREMIUM_PACKAGE:
        return [
            analyte_list_section_builder.build_metals_panel(
                "Elements", analyte_presets.trace_elements_67(), "67 Tr.Elts", element_service,
                prep_text="Dilute and Shoot", date_of_analysis=date_of_analysis,
            ),
            misc_analysis_section_builder.build_standalone_hardness("Hardness"),
            silicon_section_builder.build_silicon(
                "Silicon", True, True, date_of_analysis=date_of_analysis, request_type=RequestType.WATER,
            ),
            _ion_panel(
                "Anions", "Anion", _maybe_alphabetize(ion_presets.anions_master(), RequestType.WATER),
                None, date_of_analysis,
            ),
            _ion_panel(
                "6 Cations", "Cation", _maybe_alphabetize(ion_presets.cations_6(), RequestType.WATER),
                None, date_of_analysis,
            ),
            simple_test_section_builder.build_toc("TOC", date_of_analysis),
            simple_test_section_builder.build_alkalinity("Alkalinity", date_of_analysis),
            simple_test_section_builder.build_bacteria("Bacteria Count", date_of_analysis),
        ]
    if package_name == _STANDARD_PACKAGE:
        return [
            analyte_list_section_builder.build_metals_panel(
                "Elements", analyte_presets.trace_elements_36(), "36 Tr.Elts", element_service,
                prep_text="Dilute and Shoot", date_of_analysis=date_of_analysis,
            ),
            silicon_section_builder.build_silicon(
                "Silicon", True, False, date_of_analysis=date_of_analysis, request_type=RequestType.WATER,
            ),
            _ion_panel(
                "Anions", "Anion", _maybe_alphabetize(ion_presets.anions_master(), RequestType.WATER),
                None, date_of_analysis,
            ),
            _ion_panel(
                "NH4", "Cation", _maybe_alphabetize(ion_presets.cations_nh4(), RequestType.WATER),
                None, date_of_analysis,
            ),
            simple_test_section_builder.build_toc("TOC", date_of_analysis),
            simple_test_section_builder.build_bacteria("Bacteria Count", date_of_analysis),
        ]
    raise ValueError(
        f"water testing package {package_name!r} is not yet supported -- "
        "add a case for it once its real panel composition is confirmed."
    )


def _exclude_limits(rows) -> None:
    for row in rows:
        row.excludes_limits = True


def apply_limits(sections: list[ReportSection], limits_by_kind: dict[str, dict[str, float]]) -> None:
    """Records each limit (kind -> symbol -> value, e.g. "specification",
    "warning_limit") on every row, in every section, whose column 2 or 3
    matches the limit's symbol -- ported from the legacy macro's Get_Specs
    (modReportCreator.bas), which scans every non-empty cell in columns
    B:C of the whole sheet, case-insensitively (the module is Option
    Compare Text), for both its specification and warning-limit tables.
    So limits print on whichever panel lists the analyte: metals, silicon
    ("Si"), anion ("Cl")..., not only the metals panel. Confirmed real:
    the legacy Customer 436f6 Water report prints Na 5 (metals), Si 3 (silicon) and
    Cl 5 (anion). Where a row matches in both columns, column 3 wins, as
    in the macro's left-to-right scan.

    Records, doesn't place: the writer puts each kind in its own limit
    column (see report_writer.write_sections). Mutates rows in place.
    """
    for kind, limits in limits_by_kind.items():
        if not limits:
            continue
        by_key = {symbol.upper(): value for symbol, value in limits.items()}
        for section in sections:
            for row in section.rows:
                if row.excludes_limits:
                    continue
                for col in (2, 3):
                    if col > row.max_columns:
                        continue
                    value = row.get_value(col)
                    if isinstance(value, str) and value.upper() in by_key:
                        row.set_limit(kind, by_key[value.upper()])


def _maybe_alphabetize(analytes: list, request_type: RequestType) -> list:
    """Confirmed real (2026-09-23, two live production reports): Water's
    ion panels list analytes alphabetically by name; Chemical's list them
    in a fixed, somewhat-arbitrary-looking order that's actually elution
    order off the IC column (see Analyte.elute_order) -- a real, deliberate
    difference between the two request types, not an inconsistency to
    unify. Chemical's order is untouched; only Water gets re-sorted."""
    if request_type == RequestType.WATER:
        return sorted(analytes, key=lambda a: a.name)
    return analytes


def _ion_panel(
    name: str, category_label: str, analytes, prep_text: str | None, date_of_analysis: str | None = None
) -> ReportSection:
    # Confirmed real: "Analysis by IC (<prep>)" ONLY for a chemical with
    # its own real Chemical.ions_prep on file (one real confirmed
    # instance); every other real ion panel checked is a bare
    # "Analysis by IC" -- see module docstring's ION PANEL PREP TEXT note.
    # "Dilute and Shoot" gets the same bare treatment as None/blank --
    # confirmed real (direct user correction): it's the implied default
    # prep for ion panels by current lab convention, so calling it out
    # explicitly in the footer is redundant, not informative, the same
    # way a Chemical with no ions_prep on file gets no parenthetical.
    show_prep = bool(prep_text) and prep_text != "Dilute and Shoot"
    footer_text = f"Analysis by IC ({prep_text})" if show_prep else "Analysis by IC"
    return ion_list_section_builder.build_ion_panel(
        name, category_label, analytes, footer_text,
        sop_codes=sop_codes.ION_PANEL_SOP_CODES.get(name), date_of_analysis=date_of_analysis,
    )


def _resolve_additional_element_names(sample: TRSample, element_service: ElementService) -> list[str]:
    names: list[str] = []
    for element_id in sample.additional_element_ids:
        element = element_service.load_element(element_id)
        if element is not None:
            names.append(element.name)
    return names


def _resolved_names_in_order(sample: TRSample, analysis_service: AnalysisService) -> list[str]:
    """Distinct analysis names, in first-requested order."""
    names: list[str] = []
    seen: set[str] = set()
    for analysis_id in sample.analysis_ids:
        analysis = analysis_service.load_analysis(analysis_id)
        if analysis is None:
            continue
        if analysis.name not in seen:
            seen.add(analysis.name)
            names.append(analysis.name)
    return names
