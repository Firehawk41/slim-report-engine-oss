from datetime import date

from slim_domain.domain.tr.enums import ProcessingTime

from slim_report_engine.reporting import date_of_analysis


def test_zero_day_turnaround_returns_date_received_unchanged():
    """Same Day RUSH (0 days) -- no adjustment, even mindful of weekends:
    the check-in date is real historical fact, not something to correct."""
    received = date(2026, 9, 8)  # a Tuesday
    assert date_of_analysis.compute(received, ProcessingTime.SAME_DAY_RUSH) == received


def test_one_business_day_skips_nothing_mid_week():
    received = date(2026, 9, 8)  # Tuesday
    assert date_of_analysis.compute(received, ProcessingTime.NEXT_DAY) == date(2026, 9, 9)  # Wednesday


def test_one_business_day_from_friday_skips_the_weekend():
    received = date(2026, 9, 4)  # Friday
    assert date_of_analysis.compute(received, ProcessingTime.NEXT_DAY) == date(2026, 9, 7)  # Monday


def test_multi_day_turnaround_skips_weekend_in_the_middle():
    """THREE_DAYS from a Thursday: Fri (1), skip Sat/Sun, Mon (2), Tue (3)."""
    received = date(2026, 9, 3)  # Thursday
    assert date_of_analysis.compute(received, ProcessingTime.THREE_DAYS) == date(2026, 9, 8)  # Tuesday


def test_received_on_a_weekend_still_counts_forward_correctly():
    """Received on a Saturday (real historical fact, not corrected) --
    business-day counting starts from the next real weekday."""
    received = date(2026, 9, 5)  # Saturday
    assert date_of_analysis.compute(received, ProcessingTime.NEXT_DAY) == date(2026, 9, 7)  # Monday


def test_compute_text_format_is_mm_dd_yy():
    received = date(2026, 9, 8)
    assert date_of_analysis.compute_text(received, ProcessingTime.SAME_DAY_RUSH) == "09-08-26"
