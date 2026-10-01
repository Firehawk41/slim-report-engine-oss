"""Computes the Reports destination filename from a Testing Request
form's filename, matching the lab's existing manual convention. Derived
from real before/after examples pulled (with explicit one-time
permission) from S:\\Testing_Requests and S:\\Reports for four real
customers (Customer ca83b, Fxfilm TX, Folder 6c581, Folder 3978d), not
guessed -- see the real fixtures in
tests/test_report_filename.py.

The rule: find where the first analytical-method/technique token
(ICPMS, GC, STD, Anions, ...) appears and cut the name there, replacing
everything from that point with the word "Results" -- but if a
turnaround-urgency phrase ("RUSH", "Same Day RUSH", ...) is present, it
survives, moved to just after "Results" rather than being dropped, since
it's a still-relevant flag (unlike "STD" -- standard turnaround -- which
the lab drops entirely once results are in). When no method token is
present at all (e.g. Fxfilm's TR names are just a sequence number, no
analyte/method words), "Results" is simply appended.

This is a heuristic, confirmed correct for 4 real customers' recent
files, not exhaustively for every customer folder on the share.
Deliberately NOT backed by a per-customer learning table on top of the
folder-mapping one (see ReportFolderService in slim-domain): when this
guess is wrong for some customer's naming quirk, the technician just
renames the saved file -- the same one-time cost as fixing a folder
mapping, and cheaper than building/maintaining a second "teach it"
system for something this easy to fix by hand.
"""

from __future__ import annotations

import re

_KNOWN_EXTENSIONS = (".xlsx", ".xlsm", ".xls")

_METHOD_TOKEN_RE = re.compile(
    r"\b(?:ICP-?MS|ICP-?OES|GC-?FID|GC-?MS|GC|IC|STD|Anions)\b",
    re.IGNORECASE,
)

_RUSH_PHRASE_RE = re.compile(
    r"\b(?:Same Day RUSH|Call-in RUSH|Call In RUSH|RUSH)\b",
    re.IGNORECASE,
)


def report_filename(tr_filename: str) -> str:
    """Return the Reports destination filename for a TR form's filename.

    >>> report_filename("090426 Fxfilm UPX TX 4972.xlsx")
    '090426 Fxfilm UPX TX 4972 Results.xlsx'
    >>> report_filename("091526-Customer ca83b Custb3b14 Choline Hydroxide MDEA ICPMS STD.xlsx")
    '091526-Customer ca83b Custb3b14 Choline Hydroxide MDEA Results.xlsx'
    >>> report_filename("091626-Folder 6c581 FX RI MIBC DLV00133475 Same Day RUSH.xlsx")
    '091626-Folder 6c581 FX RI MIBC DLV00133475 Results Same Day RUSH.xlsx'
    """
    stem = tr_filename
    for ext in _KNOWN_EXTENSIONS:
        if stem.lower().endswith(ext):
            stem = stem[: -len(ext)]
            break

    method_match = _METHOD_TOKEN_RE.search(stem)
    rush_match = _RUSH_PHRASE_RE.search(stem)

    if method_match is not None:
        cut_point = method_match.start()
    elif rush_match is not None:
        cut_point = rush_match.start()
    else:
        cut_point = None

    prefix = stem[:cut_point].rstrip(" -") if cut_point is not None else stem.rstrip()
    suffix = f" {rush_match.group(0)}" if rush_match is not None else ""
    # Edge case: a method token right at the start of the name (cut_point
    # == 0, e.g. a TR filename that's just "STD Sample.xlsx") leaves
    # prefix == "" -- without this guard the naive f-string below would
    # produce a filename with a leading space (" Results.xlsx"), which
    # Windows accepts but silently mangles in some contexts (drag/drop,
    # some network-share tooling strips or preserves it inconsistently).
    # Every real TR filename seen so far starts with a date, so this
    # hasn't happened in practice -- cheap to guard against regardless.
    return f"{prefix} Results{suffix}.xlsx".lstrip()
