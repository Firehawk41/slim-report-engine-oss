"""Named preset analyte lists — data, not code — ported from
modAnalytePresets.bas. Each function returns element symbols in display
order. Adding a new preset means adding one function here, not a new class
or a new template named range.

Symbol lists extracted directly from the real template. Confirmed: the
"10 Elements"/"26 Elements"/"36 Elements" selections all render this SAME
36-symbol list — only the summary label passed to the metals-panel builder
differs. There is no 10-symbol or 26-symbol subset in the real template.
"""

from __future__ import annotations


def trace_elements_36() -> list[str]:
    return [
        "Al", "Sb", "As", "Ba", "Be", "Bi", "B", "Cd", "Ca", "Cr",
        "Co", "Cu", "Ga", "Ge", "Au", "Fe", "Pb", "Li", "Mg", "Mn",
        "Mo", "Ni", "Nb", "Pt", "K", "Ag", "Na", "Sr", "Ta", "Tl",
        "Sn", "Ti", "W", "V", "Zn", "Zr",
    ]


def trace_elements_67() -> list[str]:
    return [
        "Al", "Sb", "As", "Ba", "Be", "Bi", "B", "Cd", "Cs", "Ca",
        "Ce", "Cr", "Co", "Cu", "Dy", "Er", "Eu", "Gd", "Ga", "Ge",
        "Au", "Hf", "Ho", "In", "Ir", "Fe", "La", "Pb", "Li", "Lu",
        "Mg", "Mn", "Hg", "Mo", "Nd", "Ni", "Nb", "Os", "Pd", "Pt",
        "K", "Pr", "Re", "Rh", "Rb", "Ru", "Sm", "Sc", "Se", "Ag",
        "Na", "Sr", "Ta", "Te", "Tb", "Tl", "Th", "Tm", "Sn", "Ti",
        "W", "U", "V", "Yb", "Y", "Zn", "Zr",
    ]


def trace_elements_36_list2() -> list[str]:
    """Wafer's "List #2 36 Elements" sheet — a GENUINELY DIFFERENT
    36-element set from trace_elements_36, not a duplicate: drops
    Bi/Nb/Pt/Tl, adds Ce/Hf/In/La/Y. Order matches the real template's own
    row order exactly.
    """
    return [
        "Al", "Sb", "As", "Ba", "Be", "B", "Cd", "Ca", "Ce", "Cr",
        "Co", "Cu", "Ga", "Ge", "Hf", "In", "Fe", "La", "Pb", "Li",
        "Mg", "Mn", "Mo", "Ni", "K", "Ag", "Na", "Sr", "Ta", "Sn",
        "Ti", "W", "V", "Y", "Zn", "Zr",
    ]


def trace_elements_usp() -> list[str]:
    return [
        "Sb", "As", "Ba", "Cd", "Cr", "Co", "Cu", "Au", "Ir", "Pb",
        "Li", "Hg", "Mo", "Ni", "Os", "Pd", "Pt", "Rh", "Ru", "Se",
        "Ag", "Tl", "Sn", "V",
    ]
