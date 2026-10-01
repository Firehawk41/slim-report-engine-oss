from slim_report_engine.reporting.section_builders import simple_test_section_builder as builder


def test_build_toc():
    section = builder.build_toc("TOC")
    header = section.rows[1]
    assert header.get_value(5) == "STDEV"
    assert header.get_value(6) == "QL"
    data = section.rows[2]
    assert data.get_value(2) == "TOC"
    assert data.get_value(3) == "ppb"
    # confirmed real SOP mapping -> Test Methods row precedes the trailing blank
    assert section.rows[-3].get_value(1) == "Analysis by TOC Instrument"
    assert section.rows[-2].get_value(1) == "Test Methods: SOP-38."


def test_build_alkalinity_has_no_third_column():
    section = builder.build_alkalinity("Alkalinity")
    header = section.rows[1]
    assert header.get_value(5) == "STDEV"
    assert header.get_value(6) is None


def test_build_bacteria():
    # id passed as "Bacteria Count" -- the real dispatch analysis name
    # (chemical_water_report_builder.py), also the SIMPLE_SHAPE_SOP_CODES
    # key, so this exercises the real Test Methods wiring too.
    section = builder.build_bacteria("Bacteria Count")
    header = section.rows[1]
    # 2-column (confirmed real, 2026-09-28, direct user correction): the
    # 2026-09-25 fix that dropped this to a single result column was
    # itself wrong -- Bacteria's own real second column is "1/2 Delta",
    # not "STDEV" (unlike KF/GC-FID/Electrical Testing).
    assert header.get_value(5) == "1/2 Delta"
    data = section.rows[2]
    assert data.get_value(2) == "48 h incubation"
    assert data.get_value(3) == "CFU/L"
    # Confirmed real gap (2026-09-25, direct user correction): both rows
    # were still bordered/filled out to the shared 6-column default with
    # no real content past column 5 -- narrowed to the real width.
    assert header.max_columns == 5
    assert data.max_columns == 5
    footer = section.rows[-3]
    assert footer.get_value(1) == "Heterotrophic Plate Count"
    # Confirmed real SOP code (2026-09-25, direct user correction): SOP-36.
    assert section.rows[-2].get_value(1) == "Test Methods: SOP-36."
