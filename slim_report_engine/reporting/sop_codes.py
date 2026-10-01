"""Real ISO17025 SOP ("Test Methods:") code mappings — confirmed real
(per the user directly: a 2026-08 lab audit finding; recent reports list
which SOPs cover each section). Mined from every "Test Methods:" line
found across every real completed report in real_data/ (2026-09-04),
correlated against each line's own preceding "Analysis by ..." footer
and, where possible, the originating sample's real form selection. Cross-
checked against the lab's own real SOP "Test Methods" master list
(supplied directly 2026-09-04) — see per-table notes below for what that
list confirmed, corrected, or left still open.

DELIBERATELY INCOMPLETE — only combinations with solid, repeated real
evidence are mapped here. Anything not listed renders NO Test Methods
line at all — never guessed — until confirmed.

FORMAT, confirmed real: "Test Methods: " + codes joined
", " ... " and " + ".". Real reports are NOT fully consistent about the
trailing period on a single-code line (some have it, some don't, no
discernible rule — e.g. Chemco's own report has "SOP-04" and "SOP-61"
with no period, while another real customer's report has "SOP-04." and
"SOP-02." WITH one) — this codebase always includes the period for
consistency; revisit if the completed list says the omission was
deliberate.
"""

from __future__ import annotations

# Metals-panel SOPs, keyed by (instrument, prep_text) -- confirmed real
# the codes depend on BOTH, not prep_text alone (ICPMS-Evaporation and
# ICP-OES-Evaporation are completely different code sets).
#
# Keyed on the STORED instrument identifier (Chemical.metals_instrument,
# "ICPMS"/"ICPOES", no hyphen) -- NOT the real report's own display text,
# which hyphenates it ("Analysis by ICP-OES (...)"). Mining this mapping
# surfaced that mismatch as a real, separate, pre-existing bug: the footer
# text was rendering "ICPOES" verbatim with no hyphen. Fixed alongside this
# feature in analyte_list_section_builder.py's _display_instrument.
#
# Cross-referenced against the lab's own SOP master list: the master list
# names its ICPMS methods by digestion temperature ("Cold Only"/"Hot
# Only"/"Hot & Cold") rather than by this codebase's prep_text strings --
# "ICPMS: Cold Only" (SOP-14, SOP-48) and "ICPMS: Hot & Cold" (SOP-14,
# SOP-48, SOP-52) match "Dilute and Shoot" and "Evaporation" here
# EXACTLY, confirming those two prep_text values really do mean "cold
# digestion only" and "both", respectively. "ICPMS: Hot Only" (SOP-14,
# SOP-52, no SOP-48) has no corresponding prep_text here -- no evidence
# yet that any real chemical's metals_prep should resolve to hot-only, so
# not mapped (would need a confirmed real example to know which prep_text
# value it corresponds to). The master list also confirms "ICPMS - TQs2"
# is the SAME real thing as "Organic Dilute and Shoot" (identical codes:
# SOP-14, SOP-58) -- TQs2 is just the instrument's own model name for
# the same method.
#
# "Standard Addition" is a real metals_prep value on file (unlike "Hot
# Only") but the master list splits it into Cold/Hot/Hot & Cold variants
# (SOP-47 plus SOP-48 and/or SOP-52) the same way ICPMS is split --
# with no confirmed real report showing bare "Standard Addition" prep
# text next to a Test Methods line, there's no way to tell which variant
# applies, so it's deliberately left unmapped rather than guessed at.
METALS_PANEL_SOP_CODES: dict[tuple[str, str], list[str]] = {
    ("ICPMS", "Evaporation"): ["SOP-14", "SOP-48", "SOP-52"],
    ("ICPOES", "Evaporation"): ["SOP-02"],
    ("ICPMS", "Dilute and Shoot"): ["SOP-14", "SOP-48"],
    ("ICPMS", "Organic Dilute and Shoot"): ["SOP-14", "SOP-58"],
    # Same real method as "Organic Dilute and Shoot" above -- confirmed
    # real: at least one real chemical's metals_prep is stored with an
    # ampersand instead of "and" (a data-entry inconsistency, not a
    # different method), which would otherwise silently fall through to
    # no Test Methods line for that chemical alone.
    ("ICPMS", "Organic Dilute & Shoot"): ["SOP-14", "SOP-58"],
}

# SOP-45 marks KED (collision-cell) mode. Confirmed real (lab's own SOP
# master list): every ICPMS "with KEDS" variant is exactly its non-KEDS
# counterpart's codes with SOP-45 inserted right after the first code
# ("Cold with KEDS" = SOP-14, SOP-45, SOP-48; "Hot & Cold with KEDS" =
# SOP-14, SOP-45, SOP-48, SOP-52) -- and Wafer's own bare "Wafers"
# entry (SOP-27 alone, no SOP-45) confirms Wafer's real element-panel
# SOP is the same base-plus-conditional-KEDS shape, not a fixed pair.
# Chemical.ked_element_ids (slim-domain) already tracks exactly which
# elements need KED mode per chemical -- confirmed real: 49 real chemicals
# have it populated, overwhelmingly on "Dilute and Shoot" prep. Use
# metals_panel_sop_codes()/wafer_element_panel_sop_codes() below rather
# than the raw dicts/list so this is applied consistently.
_KED_SOP_CODE = "SOP-45"


def metals_panel_sop_codes(instrument: str, prep_text: str, has_ked_elements: bool = False) -> list[str] | None:
    """SOP codes for a metals-panel footer, or None if this (instrument,
    prep_text) combination has no confirmed real mapping at all. Adds
    SOP-45 in the confirmed real position (right after the first code)
    when has_ked_elements is True -- see _KED_SOP_CODE above.
    """
    base = METALS_PANEL_SOP_CODES.get((instrument, prep_text))
    if base is None:
        return None
    if not has_ked_elements:
        return list(base)
    return [base[0], _KED_SOP_CODE, *base[1:]]


# Ion-panel SOPs, keyed by the exact resolved analysis name -- confirmed
# real: the second code (after what looks like a constant "IC" base code,
# SOP-46, seen on every single ion-panel instance checked) varies by the
# EXACT panel selected, not just "Anions" vs "Cations". Confirmed by
# directly cross-referencing the intake form's own selection for that
# exact sample against its Test Methods line, AND by the lab's own SOP
# master list, which separately lists "PPB Anions - System 1"/"System 2"
# with these EXACT same two code pairs -- "System 1"/"System 2" appear to
# name which physical IC instrument runs a panel, not a different panel
# selection, so this doesn't add new resolved-analysis-name entries, just
# corroborates the two already confirmed here.
ION_PANEL_SOP_CODES: dict[str, list[str]] = {
    "4 Anions": ["SOP-46", "SOP-06"],
    "5 Anions + MS Confirmation": ["SOP-46", "SOP-59"],
    # "Cl" (chloride-only), plain "Anions" (Water matrix, no specific
    # count), and plain "5 Anions" (confirmed real 2026-09-25 against a
    # real Customer a13e6 Water intake form's own "5 Anions"
    # selection, direct user instruction) all use the same codes as
    # "4 Anions" -- not a different method, just a smaller/differently-
    # labeled selection off the same real panel. NOT the same as "5
    # Anions + MS Confirmation" above, which is a genuinely different,
    # separately-confirmed code pair.
    "Cl": ["SOP-46", "SOP-06"],
    "Anions": ["SOP-46", "SOP-06"],
    "5 Anions": ["SOP-46", "SOP-06"],
    # "7 Anions" confirmed real 2026-09-25 (found while regenerating
    # Folder 3da91 Animal Health's evidence workbook, which selects all 7 real
    # anions) -- same real panel/method as "4 Anions"/"5 Anions"/"Cl"/
    # "Anions" above, just a larger subset.
    "7 Anions": ["SOP-46", "SOP-06"],
    # "GBP" confirmed real 2026-09-25, direct user instruction ("GBP is
    # same as regular anions") -- same codes as the core Anion subsets
    # above, found while regenerating Folder 3da91 Animal Health's evidence
    # workbook (its own GBP table was rendering with no Test Methods
    # line at all).
    "GBP": ["SOP-46", "SOP-06"],
    # Cation panels: confirmed real 2026-09-25, direct user instruction
    # ("cations/methylamines (21 and 46 ie cations and ions prep,
    # respectively)") -- matches this module's own earlier note below
    # about "PPB Cation (SOP-46, SOP-21)". Applied to all 4 real cation
    # catalog names (chemical_water_report_builder.py) on the same "not a
    # different method, just a differently-labeled selection off the same
    # real panel" reasoning already used for the Anion subsets above.
    "6 Cations": ["SOP-46", "SOP-21"],
    "NH4": ["SOP-46", "SOP-21"],
    "Methylamines": ["SOP-46", "SOP-21"],
    "Cations": ["SOP-46", "SOP-21"],
}
# The lab's own SOP master list gives real codes for several more real ion
# panels/preps -- PPT Anions (SOP-11 alone, no SOP-46 base -- matches a
# previously-observed real Customer 846be Water code with no confirmed panel),
# H2O2 Anions (SOP-46, SOP-16), Caustic (SOP-46, SOP-15), PPT Cations
# (SOP-12 alone) -- but none of "PPT"/"PPB"/"H2O2"/"Caustic" match any
# resolved analysis name in the real catalog (checked directly), and none
# of the Anions master panel currently in this codebase correspond to
# them either. These look like sample-prep/matrix variants
# (a separate axis from which elements are selected, the same way
# Chemical.ions_prep is separate from the panel choice) rather than a
# different panel choice -- needs the user to say which real ions_prep
# value or panel combination each one actually corresponds to before
# these can be wired in; deliberately left unmapped rather than guessed.
# ("PPB Cation" is no longer in this unmapped list -- see "6 Cations"/
# "NH4"/"Methylamines"/"Cations" above, now confirmed real.)

# Simple/misc shapes, keyed by the resolved analysis name -- each
# confirmed by at least one real instance; TOC and Assay by several.
# "Assay"/SOP-04 additionally confirmed by the lab's own SOP master list
# (its "Titrator" entry -- the auto-titrator instrument Assay's own
# footer names, "Analysis by Auto-Titrator" -- lists the same code).
#
# GC-FID/Moisture/Bacteria Count added 2026-09-25, confirmed directly by
# the user (not mined from a report) and cross-checked against the real
# SOP index (S:\...\LAB-SERVER\Quality\Active_Procedures\Instructions
# (SOP), one-time read permission) -- SOP-55 "Thermo GC FID Operation
# Procedure", SOP-18 "Mettler DL32 for KF titration", SOP-36 "Bacteria
# Testing Procedure for Water Samples" all confirmed to exist and match.
# "Moisture (Karl Fischer)" and "Moisture" are the same real content under
# two catalog names (see titrations_section_builder.py dispatch) -- both
# keyed here so either resolves.
SIMPLE_SHAPE_SOP_CODES: dict[str, list[str]] = {
    "TOC": ["SOP-38"],
    "Assay": ["SOP-04"],
    "Liquid Particle Count": ["SOP-61"],
    "GC-FID": ["SOP-55"],
    "Moisture (Karl Fischer)": ["SOP-18"],
    "Moisture": ["SOP-18"],
    "Bacteria Count": ["SOP-36"],
    # pH/Density confirmed real 2026-09-25, direct user instruction (found
    # while regenerating Customer 55a6b's evidence workbook, which
    # was missing both). "pH" here is misc_analysis_section_builder's own
    # block specifically -- NOT the same dict electrical_section_builder
    # reads (see ELECTRICAL_SOP_CODES below), though both happen to use
    # the same real code.
    "pH": ["SOP-20"],
    "Density": ["SOP-53"],
}
# No real evidence found (yet) for: APHA Color, Alkalinity.

# Electrical Testing (Conductivity/pH), confirmed directly by the user
# 2026-09-25, cross-checked against the real SOP index: SOP-39 "FE30
# Conductivity Meter Operating Procedure", SOP-20 "pH Analysis of an Au
# Containing Solution". The combined "Conductivity + pH" footer uses both
# codes together (Conductivity's own code first, matching the row order
# electrical_section_builder.build_conductivity_and_ph already uses) --
# inferred from the two individually-confirmed codes, not itself directly
# confirmed against a real combined-footer example.
ELECTRICAL_SOP_CODES: dict[str, list[str]] = {
    "Conductivity": ["SOP-39"],
    "pH": ["SOP-20"],
    "Conductivity+pH": ["SOP-39", "SOP-20"],
}

# Silicon's Total-Si footer ("Analysis by ICP-OES (Evaporation)") used to
# reuse METALS_PANEL_SOP_CODES[("ICPOES", "Evaporation")] (SOP-02 alone)
# on the assumption it's the same method as the generic metals panel's
# own ICPOES/Evaporation combo. The lab's own SOP master list shows this
# was incomplete: a dedicated "ICP-OES - Water Evaporator + Silicon"
# entry gives SOP-49 AND SOP-02 together -- Silicon has its own
# additional method code (SOP-49) on top of the shared ICP-OES base code
# (SOP-02), the same "shared base + panel-specific extra" shape ion
# panels already have with SOP-46.
SILICON_TOTAL_SOP_CODES: list[str] = ["SOP-49", "SOP-02"]

# Silicon's Dissolved-Si footer ("Dissolved Silica Analysis by UV-VIS
# (Evaporation)") -- confirmed real 2026-09-25, direct user instruction
# ("24 and 33"). A genuinely different method from Total Si's own
# ICP-OES codes above (UV-VIS, not ICP-OES), so it gets its own pair
# rather than reusing SILICON_TOTAL_SOP_CODES.
SILICON_DISSOLVED_SOP_CODES: list[str] = ["SOP-24", "SOP-33"]

# Wafer, keyed by category ("Element" panel only -- the one real instance
# found; no real evidence yet for the Anion panel's own "Analysis by
# LP-IC." SOP code(s)). The lab's own SOP master list's bare "Wafers"
# entry (SOP-27 alone) implies SOP-45 should be conditional on KED
# elements here too, same as the generic metals panel above -- but unlike
# the generic path, nothing in the Wafer report-building chain currently
# looks up a Chemical record at all (Wafer submissions are dispatched
# without a chemical_service, see submission_report_builder.py), so there
# is no has_ked_elements to check yet and no confirmed real counter-example
# of a Wafer sample that should have omitted SOP-45. Left unconditional
# until that's confirmed one way or the other -- see
# wafer_element_panel_sop_codes() below, which already has the
# has_ked_elements parameter ready for when that wiring exists.
WAFER_ELEMENT_PANEL_SOP_CODES: list[str] = ["SOP-27"]


def wafer_element_panel_sop_codes(has_ked_elements: bool = True) -> list[str]:
    """SOP codes for Wafer's element-panel footer. Defaults
    has_ked_elements to True (unlike metals_panel_sop_codes' False)
    because every real Wafer instance found so far includes SOP-45 and
    nothing yet threads a real has_ked_elements value in -- see the
    WAFER_ELEMENT_PANEL_SOP_CODES comment above.
    """
    if has_ked_elements:
        return [*WAFER_ELEMENT_PANEL_SOP_CODES, _KED_SOP_CODE]
    return list(WAFER_ELEMENT_PANEL_SOP_CODES)
