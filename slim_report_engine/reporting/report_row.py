"""One row of assembled report content — ported from clsReportRow.cls.

Pure data, no Worksheet/Range dependency. Values are a fixed-width 1-based
column map; formulas are a sparse map (column index -> R1C1-relative formula
text) for the few cells that must stay live Excel formulas (e.g. AVERAGE/SUM
over technician-entered results) instead of a baked value. Everything else
is written as a plain value.

StyleName references a named style the writer (report_writer.apply_style)
knows how to apply. No per-cell font/border/fill logic lives
here or in any section builder.
"""

from __future__ import annotations

from typing import Any

DEFAULT_MAX_COLUMNS = 6


class ReportRow:
    """MaxColumns defaults to 6 -- confirmed real (every single-result-
    column report shape checked: generic Chemical/Water metals/ion
    panels, SX5 element panels): border/fill never extends past column 6
    in the real templates. (Previously defaulted to 12, which was never
    confirmed against real evidence and caused borders/fills to bleed
    into 6 genuinely blank, unstyled columns -- see project memory.)
    Wafer's multi-sample-column layout is the one exception -- it needs
    up to column 19 for a bare MDL/QL header past as many as 13
    side-by-side sample columns -- so it's a per-row constructor
    parameter, not this default, to avoid widening every other report
    type's row writes to columns it has no content for.
    """

    def __init__(
        self,
        style_name: str = "Normal",
        max_columns: int = DEFAULT_MAX_COLUMNS,
        row_height: float | None = None,
        blank_columns: frozenset[int] = frozenset(),
    ) -> None:
        """row_height: this row's real template height in points, when it's
        confirmed to differ meaningfully from Excel's default -- e.g. the
        sample-ID echo row, which needs extra height for its wrapped
        "Specification" label. None (the default) leaves the row at
        whatever height it already has.

        blank_columns: column indices within [1, max_columns] that should
        be left with NO border/fill/font -- i.e. genuinely blank, not just
        empty-valued -- even though this row's own style would otherwise
        apply uniformly across the whole range. Added 2026-09-25 (direct
        user correction, Wafer's multi-sample-column header row): the
        deliberate one-column gap between the last real sample column and
        the bare MDL/QL header was still getting the SAME fill/border as
        every other header cell, so it read as just another unlabeled
        colored cell instead of an intentional spacer.
        """
        self.style_name = style_name
        self.max_columns = max_columns
        self.row_height = row_height
        self.blank_columns = blank_columns
        self._values: dict[int, Any] = {}
        self._formulas: dict[int, str] = {}
        self._merges: list[tuple[int, int]] = []
        self._superscript_runs: dict[int, tuple[tuple[str, bool], ...]] = {}
        self._notes: dict[int, str] = {}
        self._limits: dict[str, float] = {}
        # True on a panel's column-header row: the writer puts each limit
        # column's header label (e.g. "Action Limit") in its limit columns.
        self.is_limit_header = False
        # True on an analyte row whose method differs from the limits on
        # file (a customer's Additional Elements run by another method):
        # apply_limits leaves it without limits.
        self.excludes_limits = False

    def set_value(self, col_index: int, value: Any) -> None:
        self._require_valid_column(col_index)
        self._values[col_index] = value

    def get_value(self, col_index: int) -> Any:
        return self._values.get(col_index)

    def set_superscript_runs(self, col_index: int, runs: tuple[tuple[str, bool], ...]) -> None:
        """Marks this cell as needing real superscript rich-text
        formatting at write time -- runs is a sequence of (text,
        is_superscript) segments that must concatenate to exactly this
        column's own set_value() text (the plain, flattened
        representation stays the source of truth for get_value()/tests;
        this is purely an extra write-time instruction). Added
        2026-09-26, direct user request, Wafer's units-note row (e.g.
        "Results in units of atoms/cm2" -- confirmed real, the trailing
        "2" is genuinely superscript in the real template; the scaled
        "10^10" variant has two such runs -- see wafer_report_builder.py).
        """
        self._require_valid_column(col_index)
        self._superscript_runs[col_index] = runs

    @property
    def superscript_runs(self) -> dict[int, tuple[tuple[str, bool], ...]]:
        return dict(self._superscript_runs)

    def set_note(self, col_index: int, text: str) -> None:
        """Marks a bold-red footnote marker (e.g. "Note 1") at col_index,
        written with NO border/fill -- confirmed real (2026-09-28, direct
        user correction, a real Folder 3978d Z-report): the KED-mode
        marker for an element row lives in a column just past the panel's
        own bordered box (column 7, one past the metals panel's MDL
        column), not as bold-red styling ON the element's own symbol cell.
        Deliberately NOT constrained by max_columns like set_value/
        set_formula -- this is an annotation outside the row's own
        bordered shape, not part of it.
        """
        if col_index < 1:
            raise ValueError(f"column {col_index} must be >= 1")
        self._notes[col_index] = text

    @property
    def notes(self) -> dict[int, str]:
        return dict(self._notes)

    def set_limit(self, kind: str, value: float) -> None:
        """Records a limit for this row's analyte by type ("specification",
        "warning_limit") instead of writing it into a fixed column -- the
        writer decides which column each limit type lands in, from the
        sheet's limit columns (see report_writer.write_sections). A row
        that only ever has one limit ends up exactly where column 1 put it.
        """
        self._limits[kind] = value

    @property
    def limits(self) -> dict[str, float]:
        return dict(self._limits)

    def set_formula(self, col_index: int, formula_r1c1: str) -> None:
        """formula_r1c1: relative R1C1 notation (e.g. "=AVERAGE(R[-36]C:R[-1]C)")
        so the formula is correct regardless of which absolute row this row
        ends up written to -- the builder that computes this never knows
        final sheet placement, only relative offsets to other rows in the
        same section, which is exactly what R1C1-relative expresses.
        """
        self._require_valid_column(col_index)
        self._formulas[col_index] = formula_r1c1

    def has_formula(self, col_index: int) -> bool:
        return col_index in self._formulas

    def get_formula(self, col_index: int) -> str:
        return self._formulas[col_index]

    @property
    def values(self) -> dict[int, Any]:
        return dict(self._values)

    @property
    def formula_columns(self) -> list[int]:
        return list(self._formulas.keys())

    def add_merge(self, start_col: int, end_col: int) -> None:
        """Marks [start_col, end_col] (inclusive, 1-based) as one merged
        cell on this row once written -- a structural property of the
        row's real template shape (e.g. the sample-ID echo value always
        spans 3 columns), independent of whatever value later lands there.
        """
        self._require_valid_column(start_col)
        self._require_valid_column(end_col)
        if end_col <= start_col:
            raise ValueError(f"merge range must span more than one column: {start_col}..{end_col}")
        self._merges.append((start_col, end_col))

    @property
    def merges(self) -> list[tuple[int, int]]:
        return list(self._merges)

    def _require_valid_column(self, col_index: int) -> None:
        if not 1 <= col_index <= self.max_columns:
            raise ValueError(f"column {col_index} out of range 1..{self.max_columns}")
