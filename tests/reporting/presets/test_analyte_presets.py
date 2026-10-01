from slim_report_engine.reporting.presets import analyte_presets


def test_trace_elements_36_has_36_symbols_no_duplicates():
    symbols = analyte_presets.trace_elements_36()
    assert len(symbols) == 36
    assert len(set(symbols)) == 36


def test_trace_elements_67_has_67_symbols_no_duplicates():
    symbols = analyte_presets.trace_elements_67()
    assert len(symbols) == 67
    assert len(set(symbols)) == 67


def test_trace_elements_usp_has_24_symbols():
    assert len(analyte_presets.trace_elements_usp()) == 24


def test_list2_36_is_genuinely_different_from_trace_elements_36():
    """Confirmed real: List #2 36 drops Bi/Nb/Pt/Tl and adds Ce/Hf/In/La/Y
    relative to the standard 36-element list -- not a duplicate."""
    standard = set(analyte_presets.trace_elements_36())
    list2 = set(analyte_presets.trace_elements_36_list2())
    assert len(list2) == 36
    assert list2 != standard
    assert not {"Bi", "Nb", "Pt", "Tl"} & list2
    assert {"Ce", "Hf", "In", "La", "Y"} <= list2
