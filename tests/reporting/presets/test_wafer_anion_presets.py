from slim_report_engine.reporting.presets import ion_presets, wafer_anion_presets


def _symbols(analytes):
    return [a.symbol for a in analytes]


def test_wafer_anions_4_alphabetical():
    assert _symbols(wafer_anion_presets.wafer_anions_4()) == ["Cl", "NO3", "PO4", "SO4"]


def test_wafer_anions_5_inserts_fluoride_alphabetically():
    assert _symbols(wafer_anion_presets.wafer_anions_5()) == ["Cl", "F", "NO3", "PO4", "SO4"]


def test_wafer_anions_7_inserts_bromide_and_nitrite_alphabetically():
    assert _symbols(wafer_anion_presets.wafer_anions_7()) == ["Br", "Cl", "F", "NO3", "NO2", "PO4", "SO4"]


def test_elute_order_always_zero_unlike_generic_ion_presets():
    for analyte in wafer_anion_presets.wafer_anions_7():
        assert analyte.elute_order == 0


def test_wafer_order_genuinely_differs_from_generic_elution_order():
    """A third, distinct convention -- confirmed not unified with
    presets/ion_presets.py's elution-order list."""
    assert _symbols(wafer_anion_presets.wafer_anions_4()) != _symbols(ion_presets.anions_4())
