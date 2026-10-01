"""Immutable value object for one analyte row's display identity (name +
symbol) — ported from clsAnalyte.cls. Independent of whether it came from
the DB-backed elements catalog (metals) or a static reference list (ions —
anions/cations/GBP aren't in the schema at all; there's no "add a new
anion" business process the way there is for customers/chemicals, so
they're plain data, not a DB-backed service).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Analyte:
    name: str
    symbol: str
    # 0 = not applicable. Used only by the Anions MS-Authentication
    # rendering (not yet ported) to sort the IC-MS results table by
    # elution order, matching column L in the real template.
    elute_order: int = 0
