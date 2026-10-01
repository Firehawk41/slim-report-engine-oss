from slim_report_engine.reporting.section_builders import misc_analysis_section_builder as builder


def test_ph_block_is_distinct_from_electrical_ph():
    """This Misc Analysis pH block is a separate TR-form entry point from
    electrical_section_builder.build_ph -- different header category label
    and includes a dimensionless-quantity note row electrical's doesn't.
    Both are confirmed (2026-09-28, direct user correction) to be different
    pathways to the same real pH test, so they share Electrical's own
    confirmed 2-column "STDEV" shape."""
    section = builder.build_ph("Misc pH")
    header = section.rows[1]
    assert header.get_value(2) == "pH"
    assert header.get_value(4) == "EXAMPLE LAB Result"
    assert header.get_value(5) == "STDEV"
    note = section.rows[3]
    assert note.get_value(1) == "Dimensionless quantity"
    footer = section.rows[-2]
    assert footer.get_value(1) == "Analysis by pH Electrode"


def test_density():
    section = builder.build_density("Density")
    data = section.rows[2]
    assert data.get_value(2) == "Density of solution"
    assert data.get_value(3) == "(g/mL)"
    footer = section.rows[-3]
    assert footer.get_value(1) == "Analysis by Gay-Lussac Pycnometer"
    # Confirmed real SOP code (2026-09-25, direct user correction): SOP-53.
    assert section.rows[-2].get_value(1) == "Test Methods: SOP-53."


def test_lpc_has_six_threshold_rows_in_ascending_order():
    section = builder.build_lpc("LPC")
    labels = [r.get_value(2) for r in section.rows if r.style_name == "DataLabel"]
    assert labels == [
        "≥ 0.10 µm",
        "≥ 0.15 µm",
        "≥ 0.20 µm",
        "≥ 0.30 µm",
        "≥ 0.50 µm",
        "≥ 1.00 µm",
    ]


def test_apha():
    section = builder.build_apha("APHA")
    data = section.rows[2]
    assert data.get_value(2) == "APHA number"
    footer = section.rows[-2]
    assert footer.get_value(1) == "Analysis by UV-Vis (average of six replicates)"


def test_standalone_hardness():
    """Confirmed real (2026-09-28, a real Water "Premium package" bundle
    run through the real legacy macro): genuinely distinct from the
    metals-panel-embedded live-formula Hardness add-on -- bare "Results"
    result label (not "EXAMPLE LAB Result(s)"), and NO "Analysis by ..."
    footer line at all."""
    section = builder.build_standalone_hardness("Hardness")
    header = section.rows[1]
    assert header.get_value(2) == "Hardness"
    assert header.get_value(4) == "Results"
    data = section.rows[2]
    assert data.get_value(2) == "Hardness"
    assert data.get_value(3) == "ppb"
    assert not any(r.get_value(1) and "Analysis by" in str(r.get_value(1)) for r in section.rows)
    assert section.rows[-1].values == {}  # ends in exactly one blank row
