import pytest

from slim_report_engine.report_filename import report_filename

# Real before/after examples pulled (with explicit one-time permission)
# from S:\Testing_Requests and S:\Reports on 2026-09-16, for four real
# customers -- not invented. Each tuple is (TR filename, real Reports
# filename actually saved by a technician for that same request).
REAL_EXAMPLES = [
    (
        "091526-Customer 131 Cust020 Choline Hydroxide MDEA ICPMS STD.xlsx",
        "091526-Customer 131 Cust020 Choline Hydroxide MDEA Results.xlsx",
    ),
    (
        "091126-Customer 131 Cust020 DETA ICPMS STD.xlsx",
        "091126-Customer 131 Cust020 DETA Results.xlsx",
    ),
    (
        "090826-Customer 131 Petrochemical Cust020 EDGA ICPMS STD.xlsx",
        "090826-Customer 131 Petrochemical Cust020 EDGA Results.xlsx",
    ),
    (
        "090326-Customer 131 Cust020 MEA XTA-250 ICPMS Same Day RUSH.xlsx",
        "090326-Customer 131 Cust020 MEA XTA-250 Results Same Day RUSH.xlsx",
    ),
    (
        "091626-Folder 092 FX RI MIBC DLV00133475 Same Day RUSH.xlsx",
        "091626-Folder 092 FX RI MIBC DLV00133475 Results Same Day RUSH.xlsx",
    ),
    (
        "091526 Customer 057 PMAC MIBC.xlsx",
        "091526 Customer 057 PMAC MIBC Results.xlsx",
    ),
    (
        "091626-Folder 031 MEA Morpholine DGA TEA ICPMS IC Same Day RUSH.xlsx",
        "091626-Folder 031 MEA Morpholine DGA TEA Results Same Day RUSH.xlsx",
    ),
    (
        "090926 Folder 031 DGA ICPMS STD.xlsx",
        "090926 Folder 031 DGA Results.xlsx",
    ),
    # Real live-Excel test, 2026-09-17: a real Customer 060 TR file
    # with "Anions" but no ICPMS/GC/STD token at all -- confirmed by Jamie
    # that "Anions" should still be stripped on its own, not just when it
    # happens to trail a recognized method token.
    (
        "091526-Customer 060 NMP Anions Call In RUSH.xlsx",
        "091526-Customer 060 NMP Results Call In RUSH.xlsx",
    ),
]


@pytest.mark.parametrize("tr_name, expected", REAL_EXAMPLES)
def test_report_filename_matches_real_convention(tr_name: str, expected: str) -> None:
    assert report_filename(tr_name) == expected


def test_no_method_token_or_rush_phrase_just_appends_results() -> None:
    # Fxfilm's TR names carry no analyte/method words at all -- just a
    # sequence number -- so the rule reduces to appending " Results".
    assert report_filename("090426 Fxfilm UPX TX 4972.xlsx") == "090426 Fxfilm UPX TX 4972 Results.xlsx"


def test_bare_rush_with_no_method_token_is_preserved() -> None:
    assert report_filename("Customer 130 Widgets RUSH.xlsx") == "Customer 130 Widgets Results RUSH.xlsx"


def test_call_in_rush_variant_preserved() -> None:
    assert report_filename("022626-Customer 071 THEMAH ICPMS Call In RUSH.xlsx") == (
        "022626-Customer 071 THEMAH Results Call In RUSH.xlsx"
    )


def test_is_case_insensitive_for_method_tokens_and_rush() -> None:
    assert report_filename("Customer 130 Widgets icpms same day rush.xlsx") == "Customer 130 Widgets Results same day rush.xlsx"


def test_xls_and_xlsm_extensions_normalized_to_xlsx() -> None:
    assert report_filename("Customer 130 DGA STD.xls") == "Customer 130 DGA Results.xlsx"
    assert report_filename("Customer 130 DGA STD.xlsm") == "Customer 130 DGA Results.xlsx"


def test_does_not_false_match_inside_longer_words() -> None:
    # "MIBC" contains "IC" as a substring but not as a whole word --
    # must not be treated as the "IC" method token.
    assert report_filename("Folder 092 FX RI MIBC DLV00133475.xlsx") == (
        "Folder 092 FX RI MIBC DLV00133475 Results.xlsx"
    )


def test_method_token_at_very_start_has_no_leading_space() -> None:
    # Edge case: nothing precedes the method token match, so the naive
    # prefix is "" -- must not leave a leading space in front of
    # "Results" (every real TR filename seen starts with a date, but
    # nothing guarantees that will always be true).
    assert report_filename("STD Sample.xlsx") == "Results.xlsx"
    assert report_filename("ICPMS.xlsx") == "Results.xlsx"
