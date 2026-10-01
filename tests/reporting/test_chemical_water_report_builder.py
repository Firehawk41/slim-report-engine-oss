from dataclasses import dataclass

import pytest

from slim_domain.domain.tr.enums import ProcessingTime, RequestType
from slim_domain.domain.tr.tr_sample import TRSample

from slim_report_engine.reporting import chemical_water_report_builder as orchestrator


@dataclass(frozen=True)
class _FakeAnalysis:
    name: str


class _FakeAnalysisService:
    """Maps analysis_id -> name via a plain dict, no DB session needed."""

    def __init__(self, id_to_name: dict[int, str]) -> None:
        self._id_to_name = id_to_name

    def load_analysis(self, analysis_id: int):
        name = self._id_to_name.get(analysis_id)
        return _FakeAnalysis(name) if name is not None else None


@dataclass(frozen=True)
class _FakeElement:
    name: str
    symbol: str
    id: int = 0


class _FakeElementService:
    """Resolves ANY symbol to an element named after itself -- good enough
    for dispatch tests, which only care that the right builder ran, not
    real periodic-table names. get_by_name/load_element resolve a small
    fixed catalog for the additional-elements tests specifically."""

    _BY_ID = {101: _FakeElement("Antimony", "Sb", id=101), 102: _FakeElement("Arsenic", "As", id=102)}

    def get_by_symbol(self, symbol: str):
        return _FakeElement(name=symbol, symbol=symbol)

    def get_by_name(self, name: str):
        return next((e for e in self._BY_ID.values() if e.name == name), None)

    def load_element(self, element_id: int):
        return self._BY_ID.get(element_id)


def _footer_text(section):
    """Some analysis types have a confirmed real SOP mapping (see
    reporting/sop_codes.py), which inserts a "Test Methods: ..." row
    between the footer text and the trailing blank -- find the footer row
    by content instead of assuming it's always second-to-last."""
    return next(r.get_value(1) for r in section.rows if r.get_value(1) and "Analysis by" in str(r.get_value(1)))


def _sample(
    analysis_ids: tuple[int, ...], additional_element_ids: tuple[int, ...] = (), water_package: str = ""
) -> TRSample:
    return TRSample(
        sample_name="S-1",
        form_chemical_name="Test Matrix",
        processing_time=ProcessingTime.NEXT_DAY,
        additional_notes="",
        requested_time="",
        chemical_id=1,
        analysis_ids=analysis_ids,
        additional_element_ids=additional_element_ids,
        water_package=water_package,
    )


# ---------------------------------------------------------------------------
# can_build_sections
# ---------------------------------------------------------------------------

def test_can_build_sections_false_for_no_analyses():
    svc = _FakeAnalysisService({})
    assert orchestrator.can_build_sections(_sample(()), svc) is False


def test_can_build_sections_true_for_all_supported():
    svc = _FakeAnalysisService({1: "36 Elements", 2: "TOC"})
    assert orchestrator.can_build_sections(_sample((1, 2)), svc) is True


def test_can_build_sections_false_for_any_unsupported():
    svc = _FakeAnalysisService({1: "36 Elements", 2: "UV-Vis"})
    assert orchestrator.can_build_sections(_sample((1, 2)), svc) is False


def test_can_build_sections_true_for_hardness_alongside_metals_panel():
    """Regression: Hardness/Cl were missing from _UNCONDITIONALLY_SUPPORTED
    when first added -- can_build_sections would have wrongly reported
    False for an otherwise fully-buildable sample."""
    svc = _FakeAnalysisService({1: "36 Elements", 2: "Hardness"})
    assert orchestrator.can_build_sections(_sample((1, 2)), svc) is True


def test_can_build_sections_true_for_cl():
    svc = _FakeAnalysisService({1: "Cl"})
    assert orchestrator.can_build_sections(_sample((1,)), svc) is True


def test_build_sections_raises_for_sample_with_nothing_selected():
    """Confirmed real gap (2026-09-24 code review): a Testing Request row
    can have a Sample ID with no analysis checkboxes and no additional
    elements -- a realistic data-entry slip. Without this guard,
    build_sections() silently returned [] and the caller
    (submission_report_builder.py) still emitted a "successful" report
    tab with a title/preamble and zero analytical content -- no error
    anywhere. can_build_sections() already reported False for this via
    its own dedicated test above; this confirms build_sections() itself
    now actually enforces it, not just the (previously unused) checker."""
    svc = _FakeAnalysisService({})
    with pytest.raises(ValueError, match="no analyses selected"):
        orchestrator.build_sections(_sample(()), svc, _FakeElementService())


def test_build_sections_does_not_raise_for_additional_elements_only():
    """The same guard must NOT fire for a sample whose only request is the
    free-text Additional Elements field -- already-confirmed real and
    buildable (see can_build_sections's own docstring)."""
    svc = _FakeAnalysisService({})
    sections = orchestrator.build_sections(_sample((), additional_element_ids=(101,)), svc, _FakeElementService())
    assert len(sections) == 1


# ---------------------------------------------------------------------------
# water_package -- "Water testing package" (Premium/Standard), confirmed
# real 2026-09-28 against a real Water dummy TR run through the legacy
# macro. Bundles a fixed set of panels, entirely independent of (and
# checked BEFORE) the normal per-analysis-name dispatch -- these samples
# have EMPTY analysis_ids in every real example checked.
# ---------------------------------------------------------------------------

def test_can_build_sections_true_for_premium_package():
    svc = _FakeAnalysisService({})
    assert orchestrator.can_build_sections(_sample((), water_package="Premium package"), svc) is True


def test_can_build_sections_true_for_standard_package():
    svc = _FakeAnalysisService({})
    assert orchestrator.can_build_sections(_sample((), water_package="Standard package"), svc) is True


def test_can_build_sections_false_for_unrecognized_package():
    svc = _FakeAnalysisService({})
    assert orchestrator.can_build_sections(_sample((), water_package="Deluxe package"), svc) is False


def test_build_sections_premium_package_has_confirmed_real_shape():
    """Confirmed real (67-element panel, standalone Hardness, Total+
    Dissolved+Colloidal Silicon combo, master Anions, 6 Cations, TOC,
    Alkalinity, Bacteria -- in this order)."""
    svc = _FakeAnalysisService({})
    sections = orchestrator.build_sections(_sample((), water_package="Premium package"), svc, _FakeElementService())
    category_labels = [s.rows[1].get_value(2) for s in sections]
    assert category_labels == ["Element", "Hardness", "Compound", "Anion", "Cation", "TOC", "Alkalinity", "Bacteria"]


def test_build_sections_standard_package_has_confirmed_real_shape():
    """Confirmed real (36-element panel, Total-Silicon-only ICP-OES panel
    -- plain "Element"/"Silicon" naming since it's NOT the combo case --
    master Anions, NH4-only Cation, TOC, Bacteria -- no Hardness, no
    Alkalinity, no Dissolved Silicon, in this order)."""
    svc = _FakeAnalysisService({})
    sections = orchestrator.build_sections(_sample((), water_package="Standard package"), svc, _FakeElementService())
    category_labels = [s.rows[1].get_value(2) for s in sections]
    assert category_labels == ["Element", "Element", "Anion", "Cation", "TOC", "Bacteria"]
    silicon_section = sections[1]
    assert silicon_section.rows[1].get_value(2) == "Element"  # NOT "Compound" -- Total-only, not the combo
    labels = [r.get_value(2) for r in silicon_section.rows if r.style_name == "DataLabel"]
    assert labels == ["Silicon"]


def test_build_sections_unrecognized_package_raises():
    svc = _FakeAnalysisService({})
    with pytest.raises(ValueError, match="not yet supported"):
        orchestrator.build_sections(_sample((), water_package="Deluxe package"), svc, _FakeElementService())


def test_build_sections_water_package_checked_before_empty_analyses_guard():
    """A package sample legitimately has empty analysis_ids -- confirms
    the water_package check runs BEFORE the "no analyses selected" guard
    would otherwise incorrectly reject it."""
    svc = _FakeAnalysisService({})
    sections = orchestrator.build_sections(_sample((), water_package="Premium package"), svc, _FakeElementService())
    assert len(sections) == 8


def test_can_build_sections_true_for_standalone_ph():
    """The pH fix: standalone pH is supported now, not conditionally
    rejected like the VBA source."""
    svc = _FakeAnalysisService({1: "pH"})
    assert orchestrator.can_build_sections(_sample((1,)), svc) is True


def test_can_build_sections_true_for_dissolved_and_total_si():
    """The Silicon gap fix: CanBuildSections and BuildSections now agree."""
    svc = _FakeAnalysisService({1: "Dissolved and Total Si"})
    assert orchestrator.can_build_sections(_sample((1,)), svc) is True


# ---------------------------------------------------------------------------
# build_sections -- metals
# ---------------------------------------------------------------------------

def test_10_26_36_elements_all_use_the_same_36_symbol_list_different_labels():
    for name, expected_label in (("10 Elements", "10 Tr.Elts"), ("26 Elements", "26 Tr.Elts"), ("36 Elements", "36 Tr.Elts")):
        svc = _FakeAnalysisService({1: name})
        sections = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
        assert len(sections) == 1
        section = sections[0]
        data_rows = [r for r in section.rows if r.style_name == "DataLabel" and r.get_value(3)]
        assert len(data_rows) == 36
        avg_row = next(r for r in section.rows if r.get_value(2) and "AVERAGE" in str(r.get_value(2)))
        assert avg_row.get_value(2) == f"AVERAGE / {expected_label}"


def test_67_elements_uses_67_symbol_list():
    svc = _FakeAnalysisService({1: "67 Elements"})
    sections = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
    data_rows = [r for r in sections[0].rows if r.style_name == "DataLabel" and r.get_value(3)]
    assert len(data_rows) == 67


def test_hardness_alongside_36_elements_collapses_into_the_metals_panel():
    """Confirmed real (2 real submissions checked): "Hardness" is its own
    separately-resolved analysis selection, but always accompanies a
    metals-panel selection -- never its own section."""
    svc = _FakeAnalysisService({1: "36 Elements", 2: "Hardness"})
    sections = orchestrator.build_sections(_sample((1, 2)), svc, _FakeElementService())
    assert len(sections) == 1
    hardness_row = next(r for r in sections[0].rows if r.get_value(2) == "Hardness")
    assert hardness_row.has_formula(4)


def test_hardness_order_reversed_still_collapses_into_the_metals_panel():
    svc = _FakeAnalysisService({1: "Hardness", 2: "67 Elements"})
    sections = orchestrator.build_sections(_sample((1, 2)), svc, _FakeElementService())
    assert len(sections) == 1
    assert any(r.get_value(2) == "Hardness" for r in sections[0].rows)


def test_36_elements_alone_has_no_hardness_row():
    svc = _FakeAnalysisService({1: "36 Elements"})
    sections = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
    assert not any(r.get_value(2) == "Hardness" for r in sections[0].rows)


# ---------------------------------------------------------------------------
# build_sections -- ions
# ---------------------------------------------------------------------------

def test_4_anions_panel_has_4_rows_labeled_anion():
    svc = _FakeAnalysisService({1: "4 Anions"})
    sections = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
    section = sections[0]
    header = section.rows[1]
    assert header.get_value(2) == "Anion"
    data_rows = [r for r in section.rows if r.style_name == "DataLabel"]
    assert len(data_rows) == 4


def test_4_anions_chemical_request_uses_elution_order_by_default():
    """Confirmed real (Customer d53ad, a Chemical sample): ion panels list analytes
    in a fixed, elution-off-the-IC-column order, not alphabetically."""
    svc = _FakeAnalysisService({1: "4 Anions"})
    sections = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
    data_rows = [r for r in sections[0].rows if r.style_name == "DataLabel"]
    assert [r.get_value(2) for r in data_rows] == ["Chloride", "Sulfate", "Nitrate", "Phosphate"]


def test_4_anions_water_request_uses_alphabetical_order():
    """Confirmed real (Customer 846be, a Water sample): ion panels list analytes
    alphabetically by name -- a real, deliberate difference from Chemical's
    elution order, not an inconsistency to unify."""
    svc = _FakeAnalysisService({1: "4 Anions"})
    sections = orchestrator.build_sections(
        _sample((1,)), svc, _FakeElementService(), request_type=RequestType.WATER
    )
    data_rows = [r for r in sections[0].rows if r.style_name == "DataLabel"]
    assert [r.get_value(2) for r in data_rows] == ["Chloride", "Nitrate", "Phosphate", "Sulfate"]


def test_6_cations_water_request_uses_alphabetical_order():
    svc = _FakeAnalysisService({1: "6 Cations"})
    sections = orchestrator.build_sections(
        _sample((1,)), svc, _FakeElementService(), request_type=RequestType.WATER
    )
    data_rows = [r for r in sections[0].rows if r.style_name == "DataLabel"]
    assert [r.get_value(2) for r in data_rows] == [
        "Ammonium", "Calcium", "Lithium", "Magnesium", "Potassium", "Sodium",
    ]


def test_ion_panel_footer_bare_by_default_no_ions_prep_given():
    """Confirmed real (direct correction): most real ion panels have NO
    parenthesized prep at all -- only a chemical with its own real
    Chemical.ions_prep on file gets one (see ions_prep_text)."""
    svc = _FakeAnalysisService({1: "4 Anions"})
    sections = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService(), metals_prep_text="Evaporation")
    footer = next(r for r in sections[0].rows if r.get_value(1) and "Analysis by IC" in str(r.get_value(1)))
    assert footer.get_value(1) == "Analysis by IC"


def test_ion_panel_footer_includes_own_ions_prep_text_when_given():
    """Confirmed real (one real Chemical customer's 4-Anions report):
    "Analysis by IC (<prep>)" -- ions_prep_text is a SEPARATE catalog
    field from the metals panel's own prep, not reused from it."""
    svc = _FakeAnalysisService({1: "4 Anions"})
    sections = orchestrator.build_sections(
        _sample((1,)), svc, _FakeElementService(), metals_prep_text="Dilute and Shoot", ions_prep_text="Evaporation"
    )
    footer = next(r for r in sections[0].rows if r.get_value(1) and "Analysis by IC" in str(r.get_value(1)))
    assert footer.get_value(1) == "Analysis by IC (Evaporation)"


def test_4_anions_panel_has_confirmed_test_methods_row():
    """Confirmed real (cross-referenced against the intake form's own
    selection for a real sample) -- see sop_codes.ION_PANEL_SOP_CODES."""
    svc = _FakeAnalysisService({1: "4 Anions"})
    sections = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
    test_methods = next(r for r in sections[0].rows if r.get_value(1) and "Test Methods" in str(r.get_value(1)))
    assert test_methods.get_value(1) == "Test Methods: SOP-46 and SOP-06."


def test_5_anions_panel_has_confirmed_test_methods_row():
    """Confirmed real 2026-09-25 (direct user instruction, a real
    Customer a13e6 Water intake form's own plain "5 Anions"
    selection) -- same codes as "4 Anions", not a different method, just
    a differently-labeled selection off the same real panel. NOT the
    same as "5 Anions + MS Confirmation", a genuinely different,
    separately-confirmed code pair."""
    svc = _FakeAnalysisService({1: "5 Anions"})
    sections = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
    test_methods = next(r for r in sections[0].rows if r.get_value(1) and "Test Methods" in str(r.get_value(1)))
    assert test_methods.get_value(1) == "Test Methods: SOP-46 and SOP-06."


def test_cl_panel_has_1_row_labeled_anion():
    """Confirmed real (2026-09-17, direct user correction, matching a
    real Customer 436f6 Water intake form): "Cl" is a standalone single-ion Anion
    selection, same rendering as any other Anion panel just with one
    row. SOP mapping (2026-09-25, direct user correction): Cl gets the
    SAME SOP codes as the other anion panels ("4 Anions" etc), not a bare
    footer -- it's just as much a real anion panel as they are."""
    svc = _FakeAnalysisService({1: "Cl"})
    sections = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
    section = sections[0]
    header = section.rows[1]
    assert header.get_value(2) == "Anion"
    data_rows = [r for r in section.rows if r.style_name == "DataLabel"]
    assert len(data_rows) == 1
    test_methods = next((r for r in section.rows if r.get_value(1) and "Test Methods" in str(r.get_value(1))), None)
    assert test_methods is not None
    assert test_methods.get_value(1) == "Test Methods: SOP-46 and SOP-06."


def test_gbp_panel_labeled_anion():
    """Confirmed real 2026-09-25 (direct real-evidence diff against real
    completed Folder b65a8 and Folder 3da91 Animal Health reports, plus direct
    user confirmation "GBP is same as regular anions"): "Anion", not
    "Analyte" -- this was a real bug, not just an SOP-code gap."""
    svc = _FakeAnalysisService({1: "GBP"})
    sections = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
    header = sections[0].rows[1]
    assert header.get_value(2) == "Anion"


def test_organic_anions_renders_gbp_and_acetate_formate_as_two_panels():
    """Direct user instruction (2026-09-28, no real customer/report
    evidence available yet -- explicitly confirmed after flagging the
    lack of evidence): bare "Organic Anions" is GBP + Acetate/Formate,
    the only two organic-anion presets this system has -- matching the
    catalog's own description pairing ("Anions (organic)" vs "Anions +
    Organic Anions" = "Anions (organic and inorganic)")."""
    svc = _FakeAnalysisService({1: "Organic Anions"})
    sections = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
    assert len(sections) == 2
    gbp_rows = [r.get_value(2) for r in sections[0].rows if r.style_name == "DataLabel"]
    formate_rows = [r.get_value(2) for r in sections[1].rows if r.style_name == "DataLabel"]
    assert gbp_rows == ["Glycolate", "Propionate", "Butyrate"]
    assert formate_rows == ["Acetate", "Formate"]
    assert sections[0].rows[1].get_value(2) == "Anion"
    assert sections[1].rows[1].get_value(2) == "Anion"


def test_can_build_sections_true_for_organic_anions():
    svc = _FakeAnalysisService({1: "Organic Anions"})
    assert orchestrator.can_build_sections(_sample((1,)), svc) is True


def test_acetate_and_formate_is_a_2_row_anion_panel():
    """Confirmed real (2026-09-17, direct user correction): "Acetate and
    Formate" are organic anions, rendered exactly like any other Anion
    panel -- not their own special case."""
    svc = _FakeAnalysisService({1: "Acetate and Formate"})
    sections = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
    section = sections[0]
    header = section.rows[1]
    assert header.get_value(2) == "Anion"
    data_rows = [r for r in section.rows if r.style_name == "DataLabel"]
    assert [r.get_value(2) for r in data_rows] == ["Acetate", "Formate"]


def test_can_build_sections_true_for_acetate_and_formate():
    svc = _FakeAnalysisService({1: "Acetate and Formate"})
    assert orchestrator.can_build_sections(_sample((1,)), svc) is True


def test_acetate_and_formate_merges_into_core_anions_panel_not_a_second_section():
    """Confirmed real (2026-09-23, Folder b65a8 Water report): when a
    core Anions selection is ALSO requested (here "7 Anions"), Acetate and
    Formate do NOT get their own section -- they merge into the SAME
    alphabetized panel as the core anions. Only stand alone (the
    2026-09-17 case above) when nothing to merge into is present."""
    svc = _FakeAnalysisService({1: "7 Anions", 2: "Acetate and Formate"})
    sections = orchestrator.build_sections(_sample((1, 2)), svc, _FakeElementService(), request_type=RequestType.WATER)

    assert len(sections) == 1
    data_rows = [r for r in sections[0].rows if r.style_name == "DataLabel"]
    assert [r.get_value(2) for r in data_rows] == [
        "Acetate", "Bromide", "Chloride", "Fluoride", "Formate", "Nitrate", "Nitrite", "Phosphate", "Sulfate",
    ]


def test_acetate_and_formate_merge_is_order_independent():
    """Same as above but with Acetate/Formate resolved BEFORE the core
    Anions selection in analysis_ids -- the merge must not depend on
    which one the dispatch loop visits first (see
    chemical_water_report_builder.py's acetate_formate_merged comment)."""
    svc = _FakeAnalysisService({1: "Acetate and Formate", 2: "7 Anions"})
    sections = orchestrator.build_sections(_sample((1, 2)), svc, _FakeElementService(), request_type=RequestType.WATER)

    assert len(sections) == 1
    data_rows = [r for r in sections[0].rows if r.style_name == "DataLabel"]
    assert len(data_rows) == 9


# ---------------------------------------------------------------------------
# build_sections -- silicon
# ---------------------------------------------------------------------------

def test_total_silicon_alone():
    svc = _FakeAnalysisService({1: "Total Silicon"})
    sections = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
    assert len(sections) == 1
    labels = [r.get_value(2) for r in sections[0].rows if r.style_name == "DataLabel"]
    assert labels == ["Silicon"]


def test_total_and_dissolved_silicon_collapse_into_one_section_with_colloidal_row():
    svc = _FakeAnalysisService({1: "Total Silicon", 2: "Dissolved Silicon"})
    sections = orchestrator.build_sections(_sample((1, 2)), svc, _FakeElementService())
    assert len(sections) == 1
    labels = [r.get_value(2) for r in sections[0].rows if r.style_name == "DataLabel"]
    assert labels == ["Silicon", "Dissolved Silica", "Colloidal Silica *"]


# ---------------------------------------------------------------------------
# build_sections -- electrical / pH fix
# ---------------------------------------------------------------------------

def test_conductivity_alone():
    svc = _FakeAnalysisService({1: "Conductivity"})
    sections = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
    assert len(sections) == 1
    footer = sections[0].rows[-3]
    assert footer.get_value(1) == "Analysis by Conductivity Electrode"
    # Confirmed real SOP code (2026-09-25, direct user correction): SOP-39.
    assert sections[0].rows[-2].get_value(1) == "Test Methods: SOP-39."


def test_standalone_ph_dispatches_to_misc_analysis_not_electrical():
    """The pH fix under test: no Conductivity present -> Misc Analysis's
    own pH block, not the Electrical Testing one, and NOT a raise."""
    svc = _FakeAnalysisService({1: "pH"})
    sections = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
    assert len(sections) == 1
    header = sections[0].rows[1]
    assert header.get_value(2) == "pH"  # Misc Analysis's category label, not "Electrical Testing"
    footer = sections[0].rows[-3]
    assert footer.get_value(1) == "Analysis by pH Electrode"
    # Confirmed real SOP code (2026-09-25, direct user correction): SOP-20.
    assert sections[0].rows[-2].get_value(1) == "Test Methods: SOP-20."


def test_conductivity_and_ph_together_collapse_into_one_electrical_section():
    svc = _FakeAnalysisService({1: "Conductivity", 2: "pH"})
    sections = orchestrator.build_sections(_sample((1, 2)), svc, _FakeElementService())
    assert len(sections) == 1
    header = sections[0].rows[1]
    assert header.get_value(2) == "Electrical Testing"
    footer = sections[0].rows[-3]
    assert footer.get_value(1) == "Analysis by pH/Conductivity Electrode"
    assert sections[0].rows[-2].get_value(1) == "Test Methods: SOP-39 and SOP-20."


def test_conductivity_and_ph_order_reversed_still_collapses_into_one_section():
    """Whichever of Conductivity/pH is processed first, the pair still
    collapses into exactly one section, not two."""
    svc = _FakeAnalysisService({1: "pH", 2: "Conductivity"})
    sections = orchestrator.build_sections(_sample((1, 2)), svc, _FakeElementService())
    assert len(sections) == 1
    assert sections[0].rows[1].get_value(2) == "Electrical Testing"


# ---------------------------------------------------------------------------
# build_sections -- misc analysis combine freely
# ---------------------------------------------------------------------------

def test_density_lpc_apha_combine_freely_with_no_special_logic():
    svc = _FakeAnalysisService({1: "Density", 2: "Liquid Particle Count", 3: "APHA Color"})
    sections = orchestrator.build_sections(_sample((1, 2, 3)), svc, _FakeElementService())
    assert len(sections) == 3
    footers = [_footer_text(s) for s in sections]
    assert footers == [
        "Analysis by Gay-Lussac Pycnometer",
        "Analysis by Liquid Particle Counter.",
        "Analysis by UV-Vis (average of six replicates)",
    ]


# ---------------------------------------------------------------------------
# ordering, dedup, and error path
# ---------------------------------------------------------------------------

def test_sections_preserve_first_requested_order():
    svc = _FakeAnalysisService({1: "TOC", 2: "Alkalinity", 3: "Bacteria Count"})
    sections = orchestrator.build_sections(_sample((1, 2, 3)), svc, _FakeElementService())
    assert [s.id for s in sections] == ["TOC", "Alkalinity", "Bacteria Count"]


def test_duplicate_analysis_ids_resolving_to_the_same_name_are_deduplicated():
    svc = _FakeAnalysisService({1: "TOC", 2: "TOC"})
    sections = orchestrator.build_sections(_sample((1, 2)), svc, _FakeElementService())
    assert len(sections) == 1


def test_unsupported_analysis_raises_clear_error():
    svc = _FakeAnalysisService({1: "UV-Vis"})
    with pytest.raises(ValueError, match="UV-Vis"):
        orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())


# ---------------------------------------------------------------------------
# build_sections -- Assay / Titrations (confirmed real: 3 different real
# Chemical customers' reports)
# ---------------------------------------------------------------------------

def test_assay_dispatches_to_titrations_builder():
    svc = _FakeAnalysisService({1: "Assay"})
    sections = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
    assert len(sections) == 1
    assert _footer_text(sections[0]) == "Analysis by Auto-Titrator"


def test_can_build_sections_true_for_assay():
    svc = _FakeAnalysisService({1: "Assay"})
    assert orchestrator.can_build_sections(_sample((1,)), svc) is True


def test_gc_fid_dispatches_to_titrations_builder():
    """Confirmed real: a real Chemical customer's intake form uses
    "GC-FID" verbatim as a Titrations selection."""
    svc = _FakeAnalysisService({1: "GC-FID"})
    sections = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
    assert len(sections) == 1
    assert sections[0].rows[-3].get_value(1) == "Analysis by GC-FID (average of triplicates)"
    # Confirmed real SOP code (2026-09-25, direct user correction): SOP-55.
    assert sections[0].rows[-2].get_value(1) == "Test Methods: SOP-55."


def test_can_build_sections_true_for_gc_fid():
    svc = _FakeAnalysisService({1: "GC-FID"})
    assert orchestrator.can_build_sections(_sample((1,)), svc) is True


def test_moisture_karl_fischer_dispatches_to_titrations_builder():
    """Confirmed real: the same real Chemical customer's intake form that
    confirmed "GC-FID" also uses "Moisture (Karl Fischer)" verbatim as a
    Titrations selection."""
    svc = _FakeAnalysisService({1: "Moisture (Karl Fischer)"})
    sections = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
    assert len(sections) == 1
    assert sections[0].rows[-3].get_value(1) == "Analysis by KF-Titration"
    # Confirmed real SOP code (2026-09-25, direct user correction): SOP-18.
    assert sections[0].rows[-2].get_value(1) == "Test Methods: SOP-18."


def test_can_build_sections_true_for_moisture_karl_fischer():
    svc = _FakeAnalysisService({1: "Moisture (Karl Fischer)"})
    assert orchestrator.can_build_sections(_sample((1,)), svc) is True


def test_sn2_iodine_titration_dispatches_with_real_title_and_footer():
    """Confirmed real (S:\\Reports\\Customer d53ad, real "Ag-Sn Plating"/"SnAg"
    reports, one-time permission granted 2026-09-17)."""
    svc = _FakeAnalysisService({1: "Sn+2 Iodine Titration"})
    sections = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
    assert len(sections) == 1
    header_row = sections[0].rows[1]
    assert header_row.get_value(1) == "Determination of Sn+"
    assert header_row.get_value(2) == "Assay"
    assert header_row.get_value(4) == "EXAMPLE LAB Result"
    data_row = sections[0].rows[2]
    assert (data_row.get_value(2), data_row.get_value(3)) == ("Sn2+", "(g/L)")
    assert sections[0].rows[-2].get_value(1) == "Analysis by Hand Titration"


def test_can_build_sections_true_for_sn2_iodine_titration():
    svc = _FakeAnalysisService({1: "Sn+2 Iodine Titration"})
    assert orchestrator.can_build_sections(_sample((1,)), svc) is True


def test_determination_of_free_acid_dispatches_with_real_shape():
    svc = _FakeAnalysisService({1: "Determination of Free Acid"})
    sections = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
    assert len(sections) == 1
    data_row = sections[0].rows[2]
    assert (data_row.get_value(2), data_row.get_value(3)) == ("Free Acid", "(g/L)")
    assert sections[0].rows[-2].get_value(1) == "Analysis by Hand Titration"


def test_can_build_sections_true_for_determination_of_free_acid():
    svc = _FakeAnalysisService({1: "Determination of Free Acid"})
    assert orchestrator.can_build_sections(_sample((1,)), svc) is True


def test_analysis_of_ts_slg_dispatches_with_real_shape():
    svc = _FakeAnalysisService({1: "Analysis of TS-SLG"})
    sections = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
    assert len(sections) == 1
    data_row = sections[0].rows[2]
    assert (data_row.get_value(2), data_row.get_value(3)) == ("TS-SLG", "(g/L)")
    assert sections[0].rows[-2].get_value(1) == "Analysis by Hand Titration"


def test_can_build_sections_true_for_analysis_of_ts_slg():
    svc = _FakeAnalysisService({1: "Analysis of TS-SLG"})
    assert orchestrator.can_build_sections(_sample((1,)), svc) is True


def test_moisture_plain_name_dispatches_to_same_titrations_builder():
    """Confirmed real (2026-09-17, direct user correction): the catalog's
    plain "Moisture" name is the same Karl Fischer content, not a
    different method."""
    svc = _FakeAnalysisService({1: "Moisture"})
    sections = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
    assert len(sections) == 1
    assert sections[0].rows[-3].get_value(1) == "Analysis by KF-Titration"
    # Confirmed real SOP code (2026-09-25, direct user correction): SOP-18.
    assert sections[0].rows[-2].get_value(1) == "Test Methods: SOP-18."


def test_can_build_sections_true_for_plain_moisture():
    svc = _FakeAnalysisService({1: "Moisture"})
    assert orchestrator.can_build_sections(_sample((1,)), svc) is True


# ---------------------------------------------------------------------------
# build_sections -- "5 Anions + MS Confirmation" (confirmed real: one
# real Chemical customer's report)
# ---------------------------------------------------------------------------

def test_5_anions_plus_ms_authentication_renders_the_same_panel_as_plain_5_anions():
    svc = _FakeAnalysisService({1: "5 Anions + MS Confirmation"})
    with_ms = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
    svc2 = _FakeAnalysisService({1: "5 Anions"})
    plain = orchestrator.build_sections(_sample((1,)), svc2, _FakeElementService())
    with_ms_rows = [(r.get_value(2), r.get_value(3)) for r in with_ms[0].rows if r.style_name == "DataLabel"]
    plain_rows = [(r.get_value(2), r.get_value(3)) for r in plain[0].rows if r.style_name == "DataLabel"]
    assert with_ms_rows == plain_rows


@pytest.mark.parametrize(
    ("with_ms_name", "plain_name"),
    [
        ("4 Anions + MS Confirmation", "4 Anions"),
        ("7 Anions + MS Confirmation", "7 Anions"),
        ("GBP + MS Confirmation", "GBP"),
    ],
)
def test_ms_confirmation_variants_render_the_same_panel_as_their_plain_counterpart(with_ms_name, plain_name):
    """Confirmed real (2026-09-28, direct user instruction after a fresh
    dummy "test all analyses" TR was run through the real legacy macro
    and diffed): same treatment as "5 Anions + MS Confirmation" above --
    every "+ MS Confirmation" variant renders identically to its plain
    counterpart."""
    svc = _FakeAnalysisService({1: with_ms_name})
    with_ms = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
    svc2 = _FakeAnalysisService({1: plain_name})
    plain = orchestrator.build_sections(_sample((1,)), svc2, _FakeElementService())
    with_ms_rows = [(r.get_value(2), r.get_value(3)) for r in with_ms[0].rows if r.style_name == "DataLabel"]
    plain_rows = [(r.get_value(2), r.get_value(3)) for r in plain[0].rows if r.style_name == "DataLabel"]
    assert with_ms_rows == plain_rows


# ---------------------------------------------------------------------------
# build_sections -- metals_prep_text (confirmed real: a real Chemical
# customer's report used "Evaporation"; real Water customers' reports use
# "Dilute and Shoot")
# ---------------------------------------------------------------------------

def test_metals_panel_uses_default_prep_text_when_not_given():
    svc = _FakeAnalysisService({1: "36 Elements"})
    sections = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
    footer = next(r for r in sections[0].rows if r.get_value(1) and "Analysis by ICPMS" in str(r.get_value(1)))
    assert footer.get_value(1) == "Analysis by ICPMS (Evaporation)"


def test_metals_panel_uses_caller_supplied_prep_text():
    svc = _FakeAnalysisService({1: "36 Elements"})
    sections = orchestrator.build_sections(
        _sample((1,)), svc, _FakeElementService(), metals_prep_text="Dilute and Shoot"
    )
    footer = next(r for r in sections[0].rows if r.get_value(1) and "Analysis by ICPMS" in str(r.get_value(1)))
    assert footer.get_value(1) == "Analysis by ICPMS (Dilute and Shoot)"


def test_metals_panel_uses_default_instrument_icpms_when_not_given():
    svc = _FakeAnalysisService({1: "36 Elements"})
    sections = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
    assert "ICPMS" in _footer_text(sections[0])


def test_metals_specs_thread_through_to_the_panel_column_1():
    svc = _FakeAnalysisService({1: "36 Elements"})
    sections = orchestrator.build_sections(
        _sample((1,)), svc, _FakeElementService(), metals_specs={"Al": 0.3}
    )
    al_row = next(r for r in sections[0].rows if r.get_value(3) == "Al")
    assert al_row.get_value(1) == 0.3


def test_metals_specs_default_none_leaves_column_1_blank():
    svc = _FakeAnalysisService({1: "36 Elements"})
    sections = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
    al_row = next(r for r in sections[0].rows if r.get_value(3) == "Al")
    assert al_row.get_value(1) is None


def test_metals_panel_uses_caller_supplied_instrument():
    """Confirmed real: a very dirty/nasty matrix, or one that itself
    contains a metal (e.g. NaOH), is manually switched to ICPOES during
    the quote process -- the stored value has no hyphen, but the real
    report text does ("ICP-OES")."""
    svc = _FakeAnalysisService({1: "36 Elements"})
    sections = orchestrator.build_sections(
        _sample((1,)), svc, _FakeElementService(), metals_instrument="ICPOES"
    )
    assert _footer_text(sections[0]) == "Analysis by ICP-OES (Evaporation)"


def test_caller_supplied_instrument_applies_to_additional_elements_block_too():
    svc = _FakeAnalysisService({1: "36 Elements"})
    sections = orchestrator.build_sections(
        _sample((1,), additional_element_ids=(101, 102)), svc, _FakeElementService(), metals_instrument="ICPOES"
    )
    footers = [r.get_value(1) for r in sections[0].rows if r.get_value(1) and "Analysis by" in str(r.get_value(1))]
    assert footers == ["Analysis by ICP-OES (Evaporation)", "Analysis by ICP-OES (Evaporation)"]


# ---------------------------------------------------------------------------
# build_sections -- additional elements (confirmed real: several different
# real customers' reports -- previously silently dropped entirely)
# ---------------------------------------------------------------------------

def test_additional_elements_attach_to_existing_metals_panel_as_second_block():
    svc = _FakeAnalysisService({1: "36 Elements"})
    sections = orchestrator.build_sections(_sample((1,), additional_element_ids=(101, 102)), svc, _FakeElementService())
    assert len(sections) == 1  # still one section, not a separate one
    section = sections[0]
    label_row = next(r for r in section.rows if r.get_value(4) == "Additional Elements")
    idx = section.rows.index(label_row)
    sb_row, as_row = section.rows[idx + 1], section.rows[idx + 2]
    assert (sb_row.get_value(2), sb_row.get_value(3)) == ("Antimony", "Sb")
    assert (as_row.get_value(2), as_row.get_value(3)) == ("Arsenic", "As")
    # two independent footers: the main panel's, then the additional block's
    footers = [r.get_value(1) for r in section.rows if r.get_value(1) and "Analysis by" in str(r.get_value(1))]
    assert footers == ["Analysis by ICPMS (Evaporation)", "Analysis by ICPMS (Evaporation)"]


def test_additional_elements_alone_build_a_standalone_minimal_panel():
    """Confirmed real (a real Water customer's sample requesting only
    free-text elements): no catalog panel selected at all, just additional
    elements."""
    svc = _FakeAnalysisService({})
    sections = orchestrator.build_sections(
        _sample((), additional_element_ids=(101, 102)), svc, _FakeElementService(),
        metals_prep_text="Dilute and Shoot",
    )
    assert len(sections) == 1
    section = sections[0]
    assert not any(r.get_value(4) == "Additional Elements" for r in section.rows)  # no label -- standalone shape
    assert not any(r.get_value(2) and "AVERAGE" in str(r.get_value(2)) for r in section.rows)  # no summary
    assert _footer_text(section) == "Analysis by ICPMS (Dilute and Shoot)"


def test_standalone_additional_elements_panel_comes_first_not_last():
    """Confirmed real (2026-09-23, live production report, Customer 436f6): metals
    leads the sheet regardless of which column on the intake form the
    request came from. A real sample requested Silicon (col 7), Anions
    (col 8), and metals only via the free-text Additional Elements column
    (col 5, no "# of Elements" preset) -- since the additional-elements-
    only panel used to build after the main per-name loop, it ended up
    LAST (Silicon, Anion, Metals) instead of the correct legacy order
    (Metals, Silicon, Anion)."""
    svc = _FakeAnalysisService({1: "4 Anions"})
    sections = orchestrator.build_sections(
        _sample((1,), additional_element_ids=(101, 102)), svc, _FakeElementService(),
    )
    assert len(sections) == 2
    assert sections[0].id == "Additional Elements"
    assert sections[1].id == "4 Anions"


# ---------------------------------------------------------------------------
# build_sections -- additional_elements_prep_text override (customer-level
# flag, confirmed real: at least one customer's additional elements are
# run by a different method than their main panel)
# ---------------------------------------------------------------------------

def test_additional_elements_prep_override_applies_only_to_the_second_footer():
    svc = _FakeAnalysisService({1: "36 Elements"})
    sections = orchestrator.build_sections(
        _sample((1,), additional_element_ids=(101, 102)), svc, _FakeElementService(),
        metals_prep_text="Evaporation", additional_elements_prep_text="Alternate Method",
    )
    footers = [r.get_value(1) for r in sections[0].rows if r.get_value(1) and "Analysis by" in str(r.get_value(1))]
    assert footers == ["Analysis by ICPMS (Evaporation)", "Analysis by ICPMS (Alternate Method)"]


def test_additional_elements_prep_override_applies_to_standalone_panel_too():
    svc = _FakeAnalysisService({})
    sections = orchestrator.build_sections(
        _sample((), additional_element_ids=(101, 102)), svc, _FakeElementService(),
        metals_prep_text="Dilute and Shoot", additional_elements_prep_text="Alternate Method",
    )
    assert sections[0].rows[-2].get_value(1) == "Analysis by ICPMS (Alternate Method)"


def test_no_additional_elements_prep_override_falls_back_to_metals_prep_text():
    svc = _FakeAnalysisService({1: "36 Elements"})
    sections = orchestrator.build_sections(
        _sample((1,), additional_element_ids=(101, 102)), svc, _FakeElementService(),
        metals_prep_text="Evaporation",
    )
    footers = [r.get_value(1) for r in sections[0].rows if r.get_value(1) and "Analysis by" in str(r.get_value(1))]
    assert footers == ["Analysis by ICPMS (Evaporation)", "Analysis by ICPMS (Evaporation)"]


def test_no_additional_elements_no_change_in_section_count():
    svc = _FakeAnalysisService({1: "36 Elements"})
    sections = orchestrator.build_sections(_sample((1,)), svc, _FakeElementService())
    assert len(sections) == 1
    assert not any(r.get_value(4) == "Additional Elements" for r in sections[0].rows)


def test_can_build_sections_true_for_additional_elements_only():
    svc = _FakeAnalysisService({})
    assert orchestrator.can_build_sections(_sample((), additional_element_ids=(101,)), svc) is True


# ---------------------------------------------------------------------------
# additional elements run by a different method get no limits (2026-10-01,
# direct user confirmation: Customer e6c40's Organic Dilute and Shoot
# additional elements -- the limits on file belong to the main method)
# ---------------------------------------------------------------------------

def _additional_rows(section):
    label = next(i for i, r in enumerate(section.rows) if r.get_value(4) == "Additional Elements")
    return [r for r in section.rows[label:] if isinstance(r.get_value(3), str) and r.get_value(3)]


def _main_rows(section):
    label = next(i for i, r in enumerate(section.rows) if r.get_value(4) == "Additional Elements")
    return [r for r in section.rows[:label] if isinstance(r.get_value(3), str) and r.get_value(3)]


def test_different_method_additional_elements_get_no_limits_main_panel_keeps_them():
    svc = _FakeAnalysisService({1: "36 Elements"})
    sections = orchestrator.build_sections(
        _sample((1,), additional_element_ids=(101, 102)), svc, _FakeElementService(),
        metals_prep_text="Evaporation", additional_elements_prep_text="Organic Dilute and Shoot",
    )
    extra = _additional_rows(sections[0])
    symbols = {r.get_value(3) for r in extra}
    limits = {s: 1.0 for s in symbols} | {"Al": 0.5}
    orchestrator.apply_limits(sections, {"specification": limits, "warning_limit": limits})
    assert extra and all(r.limits == {} for r in extra)
    main = {r.get_value(3): r.limits for r in _main_rows(sections[0])}
    assert main["Al"] == {"specification": 0.5, "warning_limit": 0.5}


def test_different_method_additional_elements_only_panel_gets_no_limits():
    svc = _FakeAnalysisService({})
    sections = orchestrator.build_sections(
        _sample((), additional_element_ids=(101, 102)), svc, _FakeElementService(),
        metals_prep_text="Dilute and Shoot", additional_elements_prep_text="Organic Dilute and Shoot",
    )
    rows = [r for r in sections[0].rows if isinstance(r.get_value(3), str) and r.get_value(3)]
    orchestrator.apply_limits(sections, {"specification": {r.get_value(3): 1.0 for r in rows}})
    assert rows and all(r.limits == {} for r in rows)


@pytest.mark.parametrize("override", [None, "Evaporation"])
def test_same_method_additional_elements_keep_their_limits(override):
    svc = _FakeAnalysisService({1: "36 Elements"})
    sections = orchestrator.build_sections(
        _sample((1,), additional_element_ids=(101, 102)), svc, _FakeElementService(),
        metals_prep_text="Evaporation", additional_elements_prep_text=override,
    )
    extra = _additional_rows(sections[0])
    orchestrator.apply_limits(sections, {"specification": {r.get_value(3): 1.0 for r in extra}})
    assert extra and all(r.limits == {"specification": 1.0} for r in extra)
