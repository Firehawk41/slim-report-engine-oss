"""Pure, deterministic per-chemical rules for SX5 reports — ported from
modSX5ChemicalRules.bas. No Excel dependency: given a chemical label
string, these return where the sample-ID cell lives and what the template
sheet is actually named.

Deliberately data/lookup, not parsing — the whole point of factoring SX5
out this way is determinism: "if it works once it should work every time."
A lookup table can't have a bug that only shows up on some inputs the way
ad-hoc parsing can.
"""

from __future__ import annotations

import fnmatch


def name_cell_address(chemical_label: str) -> str:
    """chemical_label is the value already stored in the real template
    sheet's own A1 cell (e.g. "WX-2000", "2to1WX2000", "CSLX001", "WX7808",
    "NH4OH") — NOT necessarily the same string as the sheet's tab name.
    Confirmed from the real macro: any label ending in "WX2000" (matches
    both "WX2000" and SX5-N's "2to1WX2000" override) goes in C5,
    "CSLX001"/"WX7808" go in C4, everything else goes in D5.
    """
    if fnmatch.fnmatchcase(chemical_label, "*WX2000"):
        return "C5"
    if chemical_label in ("CSLX001", "WX7808"):
        return "C4"
    return "D5"


def translate_sheet_name(chemical_name: str) -> str:
    """Chemical (as selected on a testing request / schedule grid) to the
    real template sheet tab name — only a few chemicals need translating,
    everything else is used verbatim.
    """
    return {
        "2.5%HF": "2.5%HF-5%",
        "WX2000": "WX-2000",
        "WX7808": "WX-7808",
    }.get(chemical_name, chemical_name)
