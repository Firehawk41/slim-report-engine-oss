from slim_report_engine.reporting.section_builders import titrations_section_builder as builder


def test_build_assay_shape():
    section = builder.build_assay("Assay")
    header, data = section.rows[1], section.rows[2]
    assert header.get_value(2) == "Assay"
    assert header.get_value(4) == "EXAMPLE LAB Result"
    assert header.get_value(5) == "STDEV"
    assert data.get_value(2) == ""
    assert data.get_value(3) == "%"
    # confirmed real SOP mapping -> Test Methods row precedes the trailing blank
    assert section.rows[-3].get_value(1) == "Analysis by Auto-Titrator"
    assert section.rows[-2].get_value(1) == "Test Methods: SOP-04."


def test_build_kf_water_shape():
    # id passed as "Moisture (Karl Fischer)" -- one of the two real
    # dispatch analysis names (chemical_water_report_builder.py), also
    # the SIMPLE_SHAPE_SOP_CODES key, so this exercises the real Test
    # Methods wiring too.
    section = builder.build_kf_water("Moisture (Karl Fischer)")
    header, data = section.rows[1], section.rows[2]
    assert header.get_value(2) == "Karl Fischer"
    # Confirmed real 2026-09-28 (direct user correction): "2 column"
    # means Result + STDEV, not a single bare result column -- the
    # 2026-09-25 fix that dropped this was itself wrong.
    assert header.get_value(5) == "STDEV"
    assert data.get_value(2) == "Water"
    assert data.get_value(3) == "ppm"
    assert section.rows[-3].get_value(1) == "Analysis by KF-Titration"
    # Confirmed real SOP code (2026-09-25, direct user correction): SOP-18.
    assert section.rows[-2].get_value(1) == "Test Methods: SOP-18."


def test_build_gc_fid_shape():
    section = builder.build_gc_fid("GC-FID")
    header = section.rows[1]
    assert header.get_value(2) == "GC-FID"
    assert header.get_value(4) == "EXAMPLE LAB Results"
    # Confirmed real 2026-09-28 (direct user correction): "2 column"
    # means Results + STDEV, not a single bare result column -- the
    # 2026-09-25 fix that dropped this was itself wrong.
    assert header.get_value(5) == "STDEV"
    chem1, chem2 = section.rows[2], section.rows[3]
    assert chem1.get_value(2) == "Chemical 1"
    assert chem1.get_value(3) == "%/Vol"
    assert chem2.get_value(2) == "Chemical 2"
    assert chem2.get_value(3) == "%/Vol"
    assert section.rows[-3].get_value(1) == "Analysis by GC-FID (average of triplicates)"
    # Confirmed real SOP code (2026-09-25, direct user correction): SOP-55.
    assert section.rows[-2].get_value(1) == "Test Methods: SOP-55."


def test_build_sn2_iodine_titration_shape():
    """Confirmed real (S:\\Reports\\Customer d53ad's "Ag-Sn Plating"/"SnAg"
    reports)."""
    section = builder.build_sn2_iodine_titration("Sn+2 Iodine Titration")
    header, data = section.rows[1], section.rows[2]
    assert header.get_value(1) == "Determination of Sn+"
    assert header.get_value(2) == "Assay"
    assert header.get_value(4) == "EXAMPLE LAB Result"
    assert header.get_value(5) == "STDEV"
    assert data.get_value(2) == "Sn2+"
    assert data.get_value(3) == "(g/L)"
    assert section.rows[-2].get_value(1) == "Analysis by Hand Titration"


def test_build_free_acid_shape():
    section = builder.build_free_acid("Determination of Free Acid")
    header, data = section.rows[1], section.rows[2]
    assert header.get_value(1) == "Free Acid"
    assert data.get_value(2) == "Free Acid"
    assert data.get_value(3) == "(g/L)"
    assert section.rows[-2].get_value(1) == "Analysis by Hand Titration"


def test_build_ts_slg_shape():
    section = builder.build_ts_slg("Analysis of TS-SLG")
    header, data = section.rows[1], section.rows[2]
    assert header.get_value(1) == "TS-SLG"
    assert data.get_value(2) == "TS-SLG"
    assert data.get_value(3) == "(g/L)"
    assert section.rows[-2].get_value(1) == "Analysis by Hand Titration"


def test_build_uv_vis_shape():
    """Confirmed real (S:\\Reports\\Folder 2b00f's real Acetonitrile report,
    matching its intake form's free-text request for these exact 7
    wavelengths)."""
    wavelengths = ["190 nm", "200 nm", "210 nm", "220 nm", "230 nm", "254 nm", "400 nm"]
    section = builder.build_uv_vis("UV-Vis", wavelengths)
    header = section.rows[1]
    assert header.get_value(2) == "Wavelength"
    assert header.get_value(4) == "EXAMPLE LAB Results"
    assert header.get_value(7) == "Replicate 1"
    assert header.get_value(8) == "Replicate 2"
    assert header.get_value(9) == "Replicate 3"

    data_rows = section.rows[2:9]
    assert [r.get_value(2) for r in data_rows] == wavelengths
    # Value cells left blank -- staff fill in real readings after running it.
    assert all(r.get_value(4) is None for r in data_rows)

    assert section.rows[-2].get_value(1) == "Analysis by UV-Vis (Abs)"


def test_build_uv_vis_one_row_per_wavelength_any_count():
    section = builder.build_uv_vis("UV-Vis", ["254 nm"])
    data_rows = [r for r in section.rows if r.style_name == "DataLabel"]
    assert len(data_rows) == 1
    assert data_rows[0].get_value(2) == "254 nm"
