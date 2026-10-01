from slim_report_engine.reporting.presets import ion_presets


def _symbols(analytes):
    return [a.symbol for a in analytes]


def test_anions_master_has_7_entries_in_elution_order():
    master = ion_presets.anions_master()
    assert _symbols(master) == ["F", "Cl", "NO2", "SO4", "Br", "NO3", "PO4"]
    assert [a.elute_order for a in master] == [1, 2, 4, 5, 6, 7, 8]


def test_anions_4_is_chloride_sulfate_nitrate_phosphate():
    assert _symbols(ion_presets.anions_4()) == ["Cl", "SO4", "NO3", "PO4"]


def test_acetate_and_formate_symbols():
    # Confirmed real 2026-09-25 (direct real-evidence diff against a real
    # completed Folder 048 report): Formate's symbol is "HCO2", not
    # "CHO2" -- same ion, different notation, and the real template
    # consistently uses "HCO2".
    assert _symbols(ion_presets.acetate_and_formate()) == ["C2H3O2", "HCO2"]


def test_anions_5_is_anions_4_plus_fluoride_preserving_order():
    assert _symbols(ion_presets.anions_5()) == ["F", "Cl", "SO4", "NO3", "PO4"]


def test_anions_7_is_the_full_master_list():
    assert ion_presets.anions_7() == ion_presets.anions_master()


def test_gbp_group_has_no_elution_order():
    for analyte in ion_presets.gbp_group():
        assert analyte.elute_order == 0


def test_cations_6_and_methylamines_partition_the_master_list_with_no_overlap():
    master = set(_symbols(ion_presets.cations_master()))
    six = set(_symbols(ion_presets.cations_6()))
    amines = set(_symbols(ion_presets.cations_methylamines()))
    assert six | amines == master
    assert six & amines == set()


def test_cations_nh4_is_ammonium_alone():
    assert _symbols(ion_presets.cations_nh4()) == ["NH4"]


def test_cations_nh4_methylamines_is_nh4_plus_all_three_amines():
    assert _symbols(ion_presets.cations_nh4_methylamines()) == ["NH4", "MMA", "DMA", "TMA"]
