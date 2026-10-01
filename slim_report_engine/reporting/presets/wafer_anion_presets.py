"""Wafer-specific anion preset lists — data, not code — ported from
modWaferAnionPresets.bas. Confirmed to use ALPHABETICAL order, a THIRD
distinct convention alongside presets/ion_presets.py's elution order and
SX5's own anion order — deliberately not unified with either.

  4 Anions = Chloride, Nitrate, Phosphate, Sulfate
  5 Anions = 4 Anions + Fluoride (alphabetically inserted)
  7 Anions = 5 Anions + Bromide, Nitrite (alphabetically inserted)

elute_order is not applicable to wafer anion sheets — always 0.
"""

from __future__ import annotations

from slim_report_engine.reporting.analyte import Analyte


def wafer_anions_4() -> list[Analyte]:
    return [
        Analyte("Chloride", "Cl"),
        Analyte("Nitrate", "NO3"),
        Analyte("Phosphate", "PO4"),
        Analyte("Sulfate", "SO4"),
    ]


def wafer_anions_5() -> list[Analyte]:
    return [
        Analyte("Chloride", "Cl"),
        Analyte("Fluoride", "F"),
        Analyte("Nitrate", "NO3"),
        Analyte("Phosphate", "PO4"),
        Analyte("Sulfate", "SO4"),
    ]


def wafer_anions_7() -> list[Analyte]:
    return [
        Analyte("Bromide", "Br"),
        Analyte("Chloride", "Cl"),
        Analyte("Fluoride", "F"),
        Analyte("Nitrate", "NO3"),
        Analyte("Nitrite", "NO2"),
        Analyte("Phosphate", "PO4"),
        Analyte("Sulfate", "SO4"),
    ]
