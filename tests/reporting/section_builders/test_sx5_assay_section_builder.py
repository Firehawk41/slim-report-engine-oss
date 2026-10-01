from slim_report_engine.reporting.section_builders import sx5_assay_section_builder as builder


def test_cslx001_shape_no_note():
    section = builder.build_assay("CSLX001", "CSLX001", "1.1 - 1.3", "Assay")
    title = section.rows[0]
    assert title.get_value(1) == "CSLX001"
    # title, blank, blank, sample#, header, data -- no note row
    assert section.row_count == 6
    sample_row = section.rows[3]
    assert sample_row.get_value(2) == "Sample #"
    assert sample_row.get_value(3) is None  # stamp left blank
    header = section.rows[4]
    assert header.get_value(3) == "% H2O2"
    data = section.rows[5]
    assert data.get_value(1) == "1.1 - 1.3"
    assert data.get_value(2) == "Assay"


def test_wx2000_shape_has_note_row_and_results_column():
    section = builder.build_assay(
        "WX2000", "2to1WX2000", "1.916 - 2.173   H2O2 % ", "% H2O2",
        result_col_label="Results",
        note_text="Bold Red Font: Indicates data outside specification limits",
    )
    # title, blank, blank, NOTE, sample#, header, data
    assert section.row_count == 7
    note_row = section.rows[3]
    assert note_row.get_value(1) == "Bold Red Font: Indicates data outside specification limits"
    header = section.rows[5]
    assert header.get_value(3) == "Results"
    data = section.rows[6]
    assert data.get_value(1) == "1.916 - 2.173   H2O2 % "
    assert data.get_value(2) == "% H2O2"


def test_embedded_assay_has_no_title_or_sample_row():
    section = builder.build_embedded_assay("0.49%HF_Assay", "0.495 % - 0.515 %")
    assert section.row_count == 2  # just header + data row
    header, data = section.rows
    assert header.get_value(3) == "% HF"
    assert data.get_value(1) == "0.495 % - 0.515 %"
    assert data.get_value(2) == "ASSAY"
    assert data.get_value(5) is None


def test_embedded_assay_note_lands_in_column_5_of_data_row():
    section = builder.build_embedded_assay(
        "0.49%HF_Assay", "0.495 % - 0.515 %",
        note_text="FC not longer wants North assay.  This left for XML program use only.",
    )
    data = section.rows[-1]
    assert data.get_value(5) == "FC not longer wants North assay.  This left for XML program use only."
