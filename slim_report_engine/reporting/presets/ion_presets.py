"""Named preset ion (Anions/GBP/Cations) lists — data, not code — ported
from modIonPresets.bas. Parallel to analyte_presets, but returns Analyte
objects (not bare symbol strings) since ions carry an elute_order used
later by the Anions MS-Authentication rendering (not yet ported).

Extracted directly from the real template:

  Anions master list (elution order in parens):
    Fluoride/F(1), Chloride/Cl(2), Nitrite/NO2(4), Sulfate/SO4(5),
    Bromide/Br(6), Nitrate/NO3(7), Phosphate/PO4(8).
    Elution order 3 is deliberately absent — it belongs to the
    MS-Authentication-only "Chloride + H2O" analyte, a separate follow-up,
    not part of the base Anions list.

  "4 Anions"/"5 Anions"/"7 Anions" are subset SELECTIONS from this one
  master list, not independent lists:
    4 Anions = Chloride, Sulfate, Nitrate, Phosphate
    5 Anions = 4 Anions + Fluoride
    7 Anions = all 7 (adds Nitrite, Bromide)

  GBP group (no elution order):
    Glycolate/C2H3O3, Propionate/C2H5CO2, Butyrate/C4H7O2

  Cations master list (no elution order):
    Lithium/Li, Sodium/Na, Ammonium/NH4, Monomethylamine/MMA,
    Dimethylamine/DMA, Potassium/K, Trimethylamine/TMA, Magnesium/Mg,
    Calcium/Ca.

    6 Cations = Lithium, Sodium, Ammonium, Potassium, Magnesium, Calcium
                (all EXCEPT the 3 amines)
    Methylamines = Monomethylamine, Dimethylamine, Trimethylamine
                   (the complement of 6 Cations)
    NH4 = Ammonium alone
    NH4 + Methylamines = Ammonium, Monomethylamine, Dimethylamine,
                          Trimethylamine
  All four subsets preserve the master list's row order.
"""

from __future__ import annotations

from slim_report_engine.reporting.analyte import Analyte


def anions_master() -> list[Analyte]:
    return [
        Analyte("Fluoride", "F", 1),
        Analyte("Chloride", "Cl", 2),
        Analyte("Nitrite", "NO2", 4),
        Analyte("Sulfate", "SO4", 5),
        Analyte("Bromide", "Br", 6),
        Analyte("Nitrate", "NO3", 7),
        Analyte("Phosphate", "PO4", 8),
    ]


def anions_4() -> list[Analyte]:
    return [
        Analyte("Chloride", "Cl", 2),
        Analyte("Sulfate", "SO4", 5),
        Analyte("Nitrate", "NO3", 7),
        Analyte("Phosphate", "PO4", 8),
    ]


def anions_5() -> list[Analyte]:
    return [
        Analyte("Fluoride", "F", 1),
        Analyte("Chloride", "Cl", 2),
        Analyte("Sulfate", "SO4", 5),
        Analyte("Nitrate", "NO3", 7),
        Analyte("Phosphate", "PO4", 8),
    ]


def anions_7() -> list[Analyte]:
    return anions_master()


def anions_cl() -> list[Analyte]:
    """Chlorine/Chloride alone -- confirmed real (2026-09-17, direct user
    correction, matching a real Customer 169 Water intake form): same rendering
    as any other Anion panel, just with a single row. Same shape as
    cations_nh4() below (a single-ion "panel")."""
    return [Analyte("Chloride", "Cl", 2)]


def acetate_and_formate() -> list[Analyte]:
    """Confirmed real (2026-09-17, direct user correction): these are
    organic anions, rendered exactly like any other Anion panel (same
    shape as anions_master()/gbp_group() below) -- not their own special
    case. Real catalog entry (analyses_data.txt #53): "Acetate and
    Formate (by IC)", also seen on real intake forms as "Acetate &
    Formate". No elution order confirmed real yet (unlike the master
    Anions list, which has one) -- omitted rather than guessed.

    Formate's symbol corrected 2026-09-25 (direct real-evidence diff
    against a real completed Folder 048 report, S:\\Reports\\Cust018
    Energy Guatemala\\2025\\041025-Folder 048 Water Results Set #1.xlsx):
    "HCO2", not "CHO2" -- both notations represent the same real ion, but
    the real template/legacy output consistently uses "HCO2"."""
    return [
        Analyte("Acetate", "C2H3O2"),
        Analyte("Formate", "HCO2"),
    ]


def gbp_group() -> list[Analyte]:
    return [
        Analyte("Glycolate", "C2H3O3"),
        Analyte("Propionate", "C2H5CO2"),
        Analyte("Butyrate", "C4H7O2"),
    ]


def cations_master() -> list[Analyte]:
    return [
        Analyte("Lithium", "Li"),
        Analyte("Sodium", "Na"),
        Analyte("Ammonium", "NH4"),
        Analyte("Monomethylamine", "MMA"),
        Analyte("Dimethylamine", "DMA"),
        Analyte("Potassium", "K"),
        Analyte("Trimethylamine", "TMA"),
        Analyte("Magnesium", "Mg"),
        Analyte("Calcium", "Ca"),
    ]


def cations_6() -> list[Analyte]:
    return [
        Analyte("Lithium", "Li"),
        Analyte("Sodium", "Na"),
        Analyte("Ammonium", "NH4"),
        Analyte("Potassium", "K"),
        Analyte("Magnesium", "Mg"),
        Analyte("Calcium", "Ca"),
    ]


def cations_methylamines() -> list[Analyte]:
    return [
        Analyte("Monomethylamine", "MMA"),
        Analyte("Dimethylamine", "DMA"),
        Analyte("Trimethylamine", "TMA"),
    ]


def cations_nh4() -> list[Analyte]:
    return [Analyte("Ammonium", "NH4")]


def cations_nh4_methylamines() -> list[Analyte]:
    return [
        Analyte("Ammonium", "NH4"),
        Analyte("Monomethylamine", "MMA"),
        Analyte("Dimethylamine", "DMA"),
        Analyte("Trimethylamine", "TMA"),
    ]
