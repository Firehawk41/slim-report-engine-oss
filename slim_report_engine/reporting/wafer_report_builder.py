"""Orchestrates ONE wafer report sheet — the group of intake-form rows
sharing one (Reporting Units, Wafer Size, Number of Elements, Processing
Time) combination, which the real template puts on a single sheet with
one sample column per physical wafer. Ported from clsWaferReportBuilder.cls.
Picks the right preset list + category (Element/Anion) from the intake
form's "Number of Elements" selection and builds the panel via
wafer_panel_builder.

REPLACES the legacy macro's copy-the-template-then-delete-unused-columns
mechanism, which depended on a counting function with a confirmed live bug
(comparing a variable to itself, always True) that silently over-counted
matching rows whenever two different element-count groups shared the same
Reporting Units/Wafer Size/Processing Time, leaving stray unused sample
columns in the real output. This builder never has that failure mode: it
writes exactly len(slot_sample_labels) sample columns because that's the
actual list it was given, with no separate count-then-delete step to get
wrong.

Per the Parse -> Transform -> Write pipeline (see project memory
feedback_pipeline_stages), this returns WHAT to write and WHERE as plain
data (WaferReportResult) — the actual worksheet write, including the
atoms/cm^2 superscript rich-text formatting (which needs real
Excel Range/Characters/Font access this content model has no way to
represent), stays out of scope for Python per this project's architecture.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from slim_domain.domain.element.element_service import ElementService
from slim_domain.domain.tr.enums import ProcessingTime

from slim_report_engine.reporting import date_of_analysis
from slim_report_engine.reporting.presets import analyte_presets, wafer_anion_presets
from slim_report_engine.reporting.report_section import ReportSection
from slim_report_engine.reporting.section_builders import wafer_panel_builder

_ATOMS_NOTE = "Results in units of atoms/cm2"
# REAL, confirmed 2026-09-26 (direct real-evidence check, S:\Reports\
# Customer abf1e -- dozens of real completed wafer reports, 2017 through at
# least 2023, every single one using this exact text): the 2026-09-23
# "correction" below (which removed this) was ITSELF wrong -- it was
# checked against only ONE customer (Customer d53ad), who happens to always
# select the PLAIN "atoms/cm^2" reporting unit, never this one. The real
# intake form's "Reporting Unit" field has always offered both as
# genuinely distinct options ("atoms/cm^2" and "atoms/cm^2 x 10^10" --
# confirmed real, Customer abf1e's own real TR forms), and Customer abf1e has
# consistently selected the x10^10 one on every real submission checked.
# The real cell is rich text: "Results in units of 10" + superscript("10")
# + " atoms/cm" + superscript("2") -- i.e. "10 to the power 10 atoms per
# cm squared", a standard semiconductor-surface-contamination unit. This
# flattens to "1010" with no separator once superscript formatting is
# stripped (confirmed directly from the real file's own rich-text runs)
# -- not a guess at how a caret/exponent should render as plain text.
_ATOMS_SCALED_NOTE = "Results in units of 1010 atoms/cm2"
# The real, literal value TRSample.reporting_units holds for this
# selection (confirmed real, Customer abf1e's 2023 TR form: samples with
# this unit selected have this exact string, verbatim, in the
# "Reporting Unit" column).
_ATOMS_SCALED_UNITS_VALUE = "atoms/cm^2 x 10^10"
_IONS_NOTE = "Results in units of ions/cm2"

# Real superscript run structure for each atoms/cm2 note, confirmed
# 2026-09-26 directly from a real completed report's own rich-text runs
# (openpyxl CellRichText/TextBlock inspection, S:\Reports\Customer abf1e)
# -- see report_writer.py's _apply_superscript_runs, which turns these
# into real Excel rich text at write time. Each tuple is (text,
# is_superscript); concatenating the text segments in order must equal
# the corresponding plain _ATOMS_NOTE/_ATOMS_SCALED_NOTE exactly.
_ATOMS_NOTE_RUNS: tuple[tuple[str, bool], ...] = (
    ("Results in units of atoms/cm", False),
    ("2", True),
)
_ATOMS_SCALED_NOTE_RUNS: tuple[tuple[str, bool], ...] = (
    ("Results in units of 10", False),
    ("10", True),
    (" atoms/cm", False),
    ("2", True),
)


@dataclass(frozen=True)
class WaferReportResult:
    section: ReportSection
    sheet_title: str  # goes in A1, e.g. "150mm Wafers"
    # True whenever the real cell needs superscript rich-text formatting
    # at write time (both real "atoms/cm^2" and "atoms/cm^2 x 10^10"
    # selections do -- see _ATOMS_SCALED_NOTE above for the confirmed
    # real rich-text run structure of the scaled case; the plain case's
    # own trailing "2" in "cm2" is genuinely superscript too). Kept as a
    # hook, not yet consumed: no writer code applies real superscript
    # rich-text formatting anywhere in this pipeline yet (this content
    # model has no way to represent it, and report_writer.py only ever
    # writes plain string values) -- this field only signals when it
    # will be needed once that writer support exists.
    apply_atoms_superscript_quirk: bool
    # The group's shared ProcessingTime (part of the grouping key -- see
    # wafer_submission_builder.py -- so every sample on this sheet has the
    # same value). Threaded through so the caller can decide whether/how
    # to stamp it (submission_report_builder.py's _processing_time_stamp)
    # without this module needing to know about report_writer styling.
    processing_time: ProcessingTime


def build_wafer_sheet(
    wafer_size: str,
    reporting_units: str,
    number_of_elements_label: str,
    customer: str,
    date_received: date,
    slot_sample_labels: list[str],
    additional_element_names: list[str],
    element_service: ElementService,
    processing_time: ProcessingTime,
) -> WaferReportResult:
    """number_of_elements_label: the ALREADY-NORMALIZED selection ("10/26
    Elements" folded into "36 Elements" -- same normalization the legacy
    grouping used, done by the caller since it's a grouping concern, not a
    content one). slot_sample_labels: one raw Sample-ID-column text per
    physical wafer sharing this sheet, in TR-row order -- becomes the
    "...-<label>" suffix of each sample column's header (column D's
    "Process Blank" suffix is fixed, not one of these). additional_element_names:
    the resolved element names to add to the sheet -- the UNION across
    every sample sharing this sheet (each physical wafer's own "Additional
    Elements" cell can differ; for a blank report, add the union and let
    the technician leave irrelevant cells blank rather than building N
    different panels). Only meaningful for an Element-category sheet
    (silently ignored for Anion, matching the real behavior: it only ever
    applies before the "Analysis by LP-ICPMS." footer, which doesn't exist
    on an anion sheet). The caller (wafer_submission_builder.py) is
    responsible for resolving raw form text into this list; this function
    no longer does any text parsing itself.
    """
    process_blank_id = _wafer_sample_string(date_received, wafer_size, customer, "Process Blank")
    slot_ids = [_wafer_sample_string(date_received, wafer_size, customer, label) for label in slot_sample_labels]
    date_of_analysis_text = date_of_analysis.compute_text(date_received, processing_time)
    is_scaled = reporting_units == _ATOMS_SCALED_UNITS_VALUE
    atoms_note = _ATOMS_SCALED_NOTE if is_scaled else _ATOMS_NOTE
    atoms_note_runs = _ATOMS_SCALED_NOTE_RUNS if is_scaled else _ATOMS_NOTE_RUNS

    if number_of_elements_label == "36 Elements":
        section = wafer_panel_builder.build_element_panel(
            number_of_elements_label, atoms_note, process_blank_id, slot_ids,
            analyte_presets.trace_elements_36(), element_service, additional_element_names, date_of_analysis_text,
            units_note_superscript_runs=atoms_note_runs,
        )
    elif number_of_elements_label == "67 Elements":
        section = wafer_panel_builder.build_element_panel(
            number_of_elements_label, atoms_note, process_blank_id, slot_ids,
            analyte_presets.trace_elements_67(), element_service, additional_element_names, date_of_analysis_text,
            units_note_superscript_runs=atoms_note_runs,
        )
    elif number_of_elements_label == "List #2 36 Elements":
        section = wafer_panel_builder.build_element_panel(
            number_of_elements_label, atoms_note, process_blank_id, slot_ids,
            analyte_presets.trace_elements_36_list2(), element_service, additional_element_names,
            date_of_analysis_text, units_note_superscript_runs=atoms_note_runs,
        )
    elif number_of_elements_label == "4 Anions":
        section = wafer_panel_builder.build_anion_panel(
            number_of_elements_label, _IONS_NOTE, process_blank_id, slot_ids, wafer_anion_presets.wafer_anions_4()
        )
    elif number_of_elements_label == "5 Anions":
        section = wafer_panel_builder.build_anion_panel(
            number_of_elements_label, _IONS_NOTE, process_blank_id, slot_ids, wafer_anion_presets.wafer_anions_5()
        )
    elif number_of_elements_label == "7 Anions":
        section = wafer_panel_builder.build_anion_panel(
            number_of_elements_label, _IONS_NOTE, process_blank_id, slot_ids, wafer_anion_presets.wafer_anions_7()
        )
    else:
        raise ValueError(f"unknown wafer 'Number of Elements' selection: {number_of_elements_label!r}")

    return WaferReportResult(
        section=section,
        sheet_title=f"{wafer_size} Wafers",
        apply_atoms_superscript_quirk=(reporting_units in ("atoms/cm^2", _ATOMS_SCALED_UNITS_VALUE)),
        processing_time=processing_time,
    )


def _wafer_sample_string(date_received: date, wafer_size: str, customer: str, suffix: str) -> str:
    return f"{date_received.strftime('%m%d%y')}-{wafer_size} Wafers-{customer}-{suffix}"
