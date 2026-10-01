"""Builds the standard sample-ID string — "mmddyy-Chemical-Customer-SampleID"
— ported from clsSampleStringBuilder.cls (itself pulled out of the legacy
macro's SetSampleString). NOT SX5-specific: this is the SAME format every
Chemical/Water sample gets, and non-routine SX5 samples get this exact
string too (not the routine path's predictable format) — they arrive via a
normal testing request like every other sample.

The legacy macro's two hardcoded display overrides are not carried here:
  - Customer "UPX" -> "FXFILM UPX": the customer records are already
    named "FXFILM UPX TX"/"FXFILM UPX CA", so the rule could never
    fire.
  - SX5-North's WX2000 -> "2to1WX2000": now a display label in the
    database (chemical_report_settings), passed in as chemical_name by
    sx5_non_routine_report_builder.
"""

from __future__ import annotations

from datetime import date


def build_sample_string(
    date_received: date, chemical_name: str, customer: str, sample_id: str
) -> str:
    return f"{date_received.strftime('%m%d%y')}-{chemical_name}-{customer}-{sample_id}"
