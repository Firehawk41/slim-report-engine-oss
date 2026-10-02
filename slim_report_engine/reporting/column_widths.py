"""Real per-column widths (points) for each report family, confirmed via
openpyxl against each family's own real template. Plain data, no openpyxl
dependency, so the Transform-stage orchestrators (submission_report_builder,
sx5_non_routine_report_builder) can attach the right preset to an
OutputSheet without pulling in a Worksheet dependency -- only
report_writer.apply_column_widths (Write stage) actually touches a
Worksheet with these values.

Column widths are a sheet-wide Excel property, not a per-row one, which is
why these live here as one dict per family rather than per row/style.
Columns not listed are left at Excel's own default; the real templates
themselves don't customize them consistently either.
"""

from __future__ import annotations

STANDARD = {1: 17.14, 2: 16.71, 3: 6.57, 4: 11.57, 5: 10.86, 6: 9.14}  # metals/ion/silicon/electrical/misc/simple
SX5_ELEMENT = {1: 14.43, 2: 12.14, 3: 4.14, 4: 10.29}  # SX5 element-panel + composite shapes
SX5_ASSAY = {1: 20.14, 2: 11.57, 3: 10.29}  # SX5 standalone Assay shape
WAFER = {1: 14.29, 2: 14.86, 3: 5.29, 4: 15.86}  # Wafer's label columns; slot columns are unset in the real template too


def wafer(sample_count: int) -> dict[int, float]:
    """WAFER plus the same width for every sample column (D onward) --
    direct user correction 2026-10-02: only D had a width, so the
    sample-ID string in E, F, ... was squeezed into Excel's narrow default
    and couldn't be read."""
    return {**WAFER, **{4 + i: WAFER[4] for i in range(sample_count)}}
