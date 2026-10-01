from datetime import date

from slim_report_engine.reporting.sample_string_builder import build_sample_string


def test_standard_format():
    result = build_sample_string(date(2026, 3, 5), "NH4OH", "Customer 130", "S-001")
    assert result == "030526-NH4OH-Customer 130-S-001"


def test_no_hardcoded_overrides_names_are_used_as_given():
    """The legacy UPX and SX5-North WX2000 overrides are gone from here:
    the UPX customers are already named "FXFILM UPX ..." in the
    database, and "2to1WX2000" is a database display label the SX5 builder
    passes in as the chemical name."""
    assert build_sample_string(date(2026, 3, 5), "Test Acid", "UPX", "S-001") == "030526-Test Acid-UPX-S-001"
    assert build_sample_string(date(2026, 3, 5), "WX2000", "SX5N", "S-001") == "030526-WX2000-SX5N-S-001"
    assert build_sample_string(date(2026, 3, 5), "2to1WX2000", "SX5N", "S-001") == "030526-2to1WX2000-SX5N-S-001"


def test_wx2000_override_is_sx5n_specific_not_sx5s():
    """SX5-S's WX2000 does NOT get the 2to1 prefix -- only SX5-N's does."""
    result = build_sample_string(date(2026, 3, 5), "WX2000", "SX5S", "S-001")
    assert result == "030526-WX2000-SX5S-S-001"


def test_ups_override_does_not_affect_other_customers():
    result = build_sample_string(date(2026, 3, 5), "Test Acid", "Customer 130", "S-001")
    assert "FXFILM" not in result
