"""Weekend-aware "expected date of analysis" inference -- confirmed real
(direct user request): stamp an inferred date, computed from check-in
(date_received) plus the sample's own turnaround time, into the
currently-always-blank "Date of Analysis: " placeholder (row_builders.
add_footer_row / wafer_panel_builder's own footer), rather than leaving it
for staff to fill in entirely by hand.

Standalone module (no dependency on submission_report_builder or the
wafer builders) so both the generic Chemical/Water path and the Wafer
path -- which has date_received/processing_time as plain values, not a
TRSubmission/TRSample, by the time it reaches this computation -- can call
it without a circular import.
"""

from __future__ import annotations

from datetime import date, timedelta

from slim_domain.domain.tr.enums import ProcessingTime


def compute(date_received: date, processing_time: ProcessingTime) -> date:
    """ProcessingTime.days is stated in BUSINESS days (confirmed: the lab
    doesn't operate weekends), so this advances one calendar day at a time
    and only counts weekdays down, rather than a flat
    date_received + timedelta(days=N). A 0-day turnaround (Same Day/
    Call-in RUSH) returns date_received unchanged -- "mindful of weekends"
    governs counting the turnaround, not whether check-in itself fell on
    one, which is real historical fact, not something to correct.
    """
    remaining = processing_time.days
    current = date_received
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Monday=0 .. Sunday=6; Saturday/Sunday excluded
            remaining -= 1
    return current


def compute_text(date_received: date, processing_time: ProcessingTime) -> str:
    """"MM-DD-YY" -- confirmed real majority format across every real
    completed report's own "Date of Analysis: <date>" text (a few use a
    4-digit year or a trailing period; this codebase standardizes on the
    majority form, same "pick one for consistency" precedent already set
    for Test Methods' trailing period -- see sop_codes.py)."""
    return compute(date_received, processing_time).strftime("%m-%d-%y")
