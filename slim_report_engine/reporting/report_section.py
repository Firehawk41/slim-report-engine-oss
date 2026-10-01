"""A named, orderable block of ReportRow destined for one report sheet —
ported from clsReportSection.cls.

Pure data, no Worksheet/Range dependency. Built by a section-builder class
per block type (e.g. a metals-panel builder); written by report_writer.py,
the only thing that touches Excel. One ReportSection instance IS the
content a VBA named range used to represent, but as inspectable data
instead of hidden Excel state.
"""

from __future__ import annotations

from slim_report_engine.reporting.report_row import ReportRow


class ReportSection:
    def __init__(self, id: str) -> None:
        self.id = id
        self._rows: list[ReportRow] = []

    def add_row(self, row: ReportRow) -> None:
        self._rows.append(row)

    @property
    def rows(self) -> list[ReportRow]:
        return list(self._rows)

    @property
    def row_count(self) -> int:
        """Row count BEFORE adding a new row tells a builder the logical row
        index of the row it's about to add (1-based) -- used to compute
        correct relative R1C1 formula offsets without knowing final sheet
        placement.
        """
        return len(self._rows)
