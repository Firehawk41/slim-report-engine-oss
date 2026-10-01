import pytest

from slim_domain.domain.tr.enums import RequestType

from slim_report_engine.reporting.section_builders import silicon_section_builder as builder


def test_neither_included_raises():
    with pytest.raises(ValueError):
        builder.build_silicon("Silicon", False, False)


def test_total_only():
    section = builder.build_silicon("Silicon", True, False)
    labels = [r.get_value(2) for r in section.rows if r.style_name == "DataLabel"]
    assert "Silicon" in labels
    assert "Dissolved Silica" not in labels
    assert "Colloidal Silica *" not in labels


def test_dissolved_only():
    section = builder.build_silicon("Silicon", False, True)
    labels = [r.get_value(2) for r in section.rows if r.style_name == "DataLabel"]
    assert "Dissolved Silica" in labels
    assert "Silicon" not in labels
    assert "Colloidal Silica *" not in labels


def test_both_adds_colloidal_silica_row():
    section = builder.build_silicon("Silicon", True, True)
    labels = [r.get_value(2) for r in section.rows if r.style_name == "DataLabel"]
    assert labels == ["Silicon", "Dissolved Silica", "Colloidal Silica *"]


def test_both_adds_the_calculation_footnote():
    section = builder.build_silicon("Silicon", True, True)
    notes = [r.get_value(1) for r in section.rows if r.get_value(1) and "difference" in str(r.get_value(1))]
    assert len(notes) == 1


def test_header_uses_singular_result_not_plural():
    section = builder.build_silicon("Silicon", True, False)
    header = section.rows[1]
    assert header.get_value(4) == "EXAMPLE LAB Result"


def test_total_only_footer_is_icp_oes():
    section = builder.build_silicon("Silicon", True, False)
    footers = [r.get_value(1) for r in section.rows if r.get_value(1) and "Analysis by" in str(r.get_value(1))]
    assert footers == ["Analysis by ICP-OES (Evaporation)"]


def test_both_footers_present_in_order():
    section = builder.build_silicon("Silicon", True, True)
    footers = [r.get_value(1) for r in section.rows if r.get_value(1) and "Analysis by" in str(r.get_value(1))]
    assert footers == [
        "Analysis by ICP-OES (Evaporation)",
        "Dissolved Silica Analysis by UV-VIS (Evaporation)",
    ]


def test_total_si_has_confirmed_test_methods_row():
    """Confirmed real (lab's own SOP master list): Silicon has its own
    dedicated "ICP-OES - Water Evaporator + Silicon" code (SOP-49) on top
    of the shared ICP-OES base code (SOP-02) -- not the same mapping as
    the generic metals panel's own ICP-OES/Evaporation combo, even though
    the footer TEXT is identical (see sop_codes.SILICON_TOTAL_SOP_CODES)."""
    section = builder.build_silicon("Silicon", True, False)
    test_methods = [r.get_value(1) for r in section.rows if r.get_value(1) and "Test Methods" in str(r.get_value(1))]
    assert test_methods == ["Test Methods: SOP-49 and SOP-02."]


def test_dissolved_si_has_confirmed_test_methods_row():
    """Confirmed real 2026-09-25, direct user instruction ("24 and 33"):
    SOP-24 and SOP-33 -- a genuinely different method from Total Si's
    own ICP-OES codes (UV-VIS, not ICP-OES)."""
    section = builder.build_silicon("Silicon", False, True)
    test_methods = [r.get_value(1) for r in section.rows if r.get_value(1) and "Test Methods" in str(r.get_value(1))]
    assert test_methods == ["Test Methods: SOP-24 and SOP-33."]


def test_water_total_and_dissolved_combo_uses_silica_nomenclature():
    """Confirmed real (2026-09-28, direct user correction, the real
    legacy macro's own dummy-TR output): Water customers expect silica
    nomenclature ("Compound" header, "Total Silica"/"SiO2" first row)
    even though the lab is actually testing for elemental silicon --
    since there's exactly one silicon atom per silica molecule, the
    reported value itself never needs adjusting, only the label. This
    is specific to the Total+Dissolved COMBO case -- see the next test."""
    section = builder.build_silicon("Silicon", True, True, request_type=RequestType.WATER)
    header = section.rows[1]
    assert header.get_value(2) == "Compound"
    labels = [r.get_value(2) for r in section.rows if r.style_name == "DataLabel"]
    symbols = [r.get_value(3) for r in section.rows if r.style_name == "DataLabel"]
    assert labels == ["Total Silica", "Dissolved Silica", "Colloidal Silica *"]
    assert symbols == ["SiO2", "SiO2", "SiO2"]
    footers = [r.get_value(1) for r in section.rows if r.get_value(1) and "Analysis by" in str(r.get_value(1))]
    assert footers == [
        "Total Silica Analysis by ICP-OES (Evaporation)",
        "Dissolved Silica Analysis by UV-VIS (Evaporation)",
    ]


def test_water_total_only_keeps_plain_silicon_nomenclature():
    """Confirmed real (2026-09-28, checked against a SECOND real Water
    dummy-TR sample, not just the combo case): a Water sample requesting
    Total Silicon ALONE (no Dissolved) uses the SAME plain "Element"/
    "Silicon"/"Si" convention as Chemical -- the silica nomenclature is
    specific to the Total+Dissolved combo, not to Water in general. An
    earlier version of this fix assumed it applied to Water any time
    Total was included; this one real Total-only example contradicted
    that and narrowed the condition."""
    section = builder.build_silicon("Silicon", True, False, request_type=RequestType.WATER)
    header = section.rows[1]
    assert header.get_value(2) == "Element"
    labels = [r.get_value(2) for r in section.rows if r.style_name == "DataLabel"]
    assert labels == ["Silicon"]
    footers = [r.get_value(1) for r in section.rows if r.get_value(1) and "Analysis by" in str(r.get_value(1))]
    assert footers == ["Analysis by ICP-OES (Evaporation)"]


def test_chemical_default_is_unaffected_by_water_nomenclature():
    """request_type defaults to CHEMICAL -- every existing test above
    (none of which pass request_type) already locks in that the plain
    "Element"/"Silicon"/"Si" convention is unchanged; this test just
    makes the default explicit, including for the Total+Dissolved combo
    (where Water's nomenclature diverges but Chemical must not)."""
    section = builder.build_silicon("Silicon", True, True, request_type=RequestType.CHEMICAL)
    header = section.rows[1]
    assert header.get_value(2) == "Element"
    labels = [r.get_value(2) for r in section.rows if r.style_name == "DataLabel"]
    assert labels == ["Silicon", "Dissolved Silica", "Colloidal Silica *"]


def test_both_included_gets_a_test_methods_row_after_each_analysis_by_line():
    """Confirmed real gap (2026-09-25, direct user correction): each
    footer needs its OWN Test Methods row directly under its own
    "Analysis by ..." line, not just one combined line at the end --
    same "Test Methods sits immediately under its own section's footer"
    convention row_builders.add_footer_row already guarantees per call."""
    section = builder.build_silicon("Silicon", True, True)
    rows = [r.get_value(1) for r in section.rows if r.get_value(1) is not None]
    assert rows.index("Test Methods: SOP-49 and SOP-02.") == rows.index("Analysis by ICP-OES (Evaporation)") + 1
    assert (
        rows.index("Test Methods: SOP-24 and SOP-33.")
        == rows.index("Dissolved Silica Analysis by UV-VIS (Evaporation)") + 1
    )
