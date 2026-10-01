from slim_report_engine.reporting.sx5 import chemical_rules


def test_name_cell_address_plain_wx2000():
    assert chemical_rules.name_cell_address("WX2000") == "C5"


def test_name_cell_address_2to1_wx2000_override_also_matches():
    assert chemical_rules.name_cell_address("2to1WX2000") == "C5"


def test_name_cell_address_cslx001_and_wx7808():
    assert chemical_rules.name_cell_address("CSLX001") == "C4"
    assert chemical_rules.name_cell_address("WX7808") == "C4"


def test_name_cell_address_default():
    assert chemical_rules.name_cell_address("NH4OH") == "D5"


def test_translate_sheet_name_known_overrides():
    assert chemical_rules.translate_sheet_name("2.5%HF") == "2.5%HF-5%"
    assert chemical_rules.translate_sheet_name("WX2000") == "WX-2000"
    assert chemical_rules.translate_sheet_name("WX7808") == "WX-7808"


def test_translate_sheet_name_passthrough_for_everything_else():
    assert chemical_rules.translate_sheet_name("NH4OH") == "NH4OH"
