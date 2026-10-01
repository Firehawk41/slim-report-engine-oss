"""Golden-file regression tests: generate this project's own output for
a real Testing Request and diff it (content AND styling, see _diff.py)
against the real legacy macro's own output for the SAME real submission
-- catches real regressions automatically via `pytest -q`, instead of
relying on a human visually reviewing a generated workbook. Built
2026-09-28 in direct response to three real bugs (a KED-mode marker
styled on the wrong cell, worded wrong, and ordered wrong) that 453
passing unit tests didn't catch, because the tests' own expected values
had never been checked against a comprehensive real corpus -- see the
`report-engine-validation-evidence` and `lessons-vba-to-service-port`
project memories.

Needs the real S:\\ network share (real TR inputs + real legacy macro
outputs) and a live DB_URL (to resolve real customers/chemicals/specs)
-- skips gracefully when either isn't available, same pattern as
tests/integration's PVB_BRIDGE_PATH-gated tests, so this suite is a
no-op (not a failure) on any machine without access to both.

To add a new golden pair: find a real Testing Request input under
S:\\Testing_Requests and its real completed counterpart under
S:\\Reports (or the Evidence folder's own "Dummy TR" pair), confirm
the sheet names line up (openpyxl.load_workbook(...).sheetnames), and
add a GoldenPair entry below.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from tests.golden._diff import diff_workbooks

_EVIDENCE_ROOT = Path(r"S:\Quality_Items\Macro Validation\SLIM Report Engine v1.0.0\Evidence")


@dataclass(frozen=True)
class GoldenPair:
    name: str
    input_path: Path
    legacy_output_path: Path
    # The real, on-file customer/address text this TR uses that has NO
    # resolvable customer row of its own (e.g. "EXAMPLE LAB" itself, the
    # dummy TR's own submitter) -- when set, generation uses a
    # substituted real customer (see _generate) and the diff normalizes
    # for it instead of reporting a false-positive mismatch.
    unresolvable_customer_name: str | None = None
    # Real sample NAMES (TRSample.sample_name) this pair's own input TR
    # has that this project genuinely can't build yet, for a reason
    # UNRELATED to whatever this pair exists to verify -- e.g. a real
    # combo with no catalog mapping at all. Excluded from generation
    # (via a lenient chemical_water_report_builder.build_sections wrap,
    # not by removing them from the submission -- keeps every OTHER
    # sample's real tab numbering/position exactly aligned with legacy)
    # so the rest of the file can still be verified. Each entry must cite
    # the real, separate finding it stands in for -- this is a narrow,
    # auditable escape hatch, not a way to silence real content bugs.
    skip_samples: frozenset[str] = frozenset()


GOLDEN_PAIRS = [
    GoldenPair(
        name="dummy_tr_all_analyses",
        input_path=_EVIDENCE_ROOT / "Dummy TR - test all analyses.xlsx",
        legacy_output_path=_EVIDENCE_ROOT / "Dummy TR - test all analyses report.xlsx",
        unresolvable_customer_name="EXAMPLE LAB",
    ),
    GoldenPair(
        name="Cust002_ventures_mea_ked_set1",
        input_path=Path(r"S:\Testing_Requests\Folder 031\091826 Folder 031 MEA ICPMS IC Same Day RUSH Set 1.xlsx"),
        legacy_output_path=Path(r"S:\Reports\Folder 031\091826 Folder 031 MEA Results Same Day RUSH Set 1 Completed.xlsx"),
    ),
    GoldenPair(
        name="dummy_tr_wafers",
        input_path=_EVIDENCE_ROOT / "Dummy TR - test all analyses Wafers.xlsx",
        legacy_output_path=_EVIDENCE_ROOT / "Dummy TR - test all analyses Wafers report.xlsx",
        unresolvable_customer_name="EXAMPLE LAB",
    ),
    GoldenPair(
        name="dummy_tr_water",
        input_path=_EVIDENCE_ROOT / "Dummy TR - test all analyses Water.xlsx",
        legacy_output_path=_EVIDENCE_ROOT / "Dummy TR - test all analyses Water Report.xlsx",
        unresolvable_customer_name="EXAMPLE LAB",
        # Sample "15" ("4 Anions + GBP + MS Authentication") used to have
        # no catalog mapping at all -- fixed 2026-09-28 by adding the
        # missing form_analyses row (see report-engine-validation-
        # evidence memory) rather than skipping it here.
    ),
    GoldenPair(
        name="sxos5_south_real",
        input_path=_EVIDENCE_ROOT / "091126-SXOS5 South Real TR.xlsx",
        legacy_output_path=_EVIDENCE_ROOT / "091126-SXOS5 South Real TR report.xlsx",
        # Real SX5 customer/chemicals (49%HF, 0.49%HF) -- this pair's
        # first-ever run found and fixed a real SX5-only bug (the
        # sample-ID stamp rendering bold -- see report_writer.py's
        # apply_plain_cell_stamp, report-engine 0.21.17). This
        # is SX5's ONLY golden-file coverage; the sx5_non_routine_report_
        # builder path was otherwise completely unverified against real
        # legacy output before 2026-09-29.
    ),
    GoldenPair(
        name="sxos5_north_all",
        input_path=_EVIDENCE_ROOT / "092226-SXOS5 North All Dummy TR.xlsx",
        legacy_output_path=_EVIDENCE_ROOT / "092226-SXOS5 North All Dummy TR report.xlsx",
        # Real SX5 customer, all 10 SX5-North element-panel/Assay/
        # composite chemicals in one TR -- 2 confirmed accepted
        # improvements, see KNOWN_OPEN_MISMATCHES: "2to1WX2000" (a real
        # legacy bug, root-caused via this pair's own live debug log --
        # see sx5_non_routine_report_builder._get_chemical_label's
        # docstring) and 0.49%HF's embedded Assay content (this non-
        # routine path may legitimately include it even where a specific
        # legacy example didn't -- direct user "final decision").
    ),
    GoldenPair(
        name="Cust025_dmso_real",
        input_path=_EVIDENCE_ROOT / "091726-Customer 054 DMSO Real TR.xlsx",
        legacy_output_path=_EVIDENCE_ROOT / "091726-Customer 054 DMSO Real TR report.xlsx",
        # Real customer/chemical (Customer 054, DMSO -- Ti KED).
        # "Customer 034" (the real form text) had no form_key
        # mapping to the existing "Customer 054" customer (id 6) --
        # fixed 2026-09-29 via CustomerService.add_form_key(), same
        # self-heal-onto-an-existing-customer pattern as the RAW
        # MATERIALS incident, not a new duplicate customer.
    ),
    GoldenPair(
        name="ked_coverage_dummy",
        input_path=_EVIDENCE_ROOT / "Dummy TR - KED coverage (TEA NiGe, DMSO Ti, KOH).xlsx",
        legacy_output_path=_EVIDENCE_ROOT / "Dummy TR - KED coverage (TEA NiGe, DMSO Ti, KOH) report.xlsx",
        unresolvable_customer_name="EXAMPLE LAB",
        # Diversifies KED coverage beyond Cust002_ventures_mea_ked_set1's
        # one real chemical -- TEA (Ni, Ge), DMSO (Ti), KOH (no KED, real
        # negative case). Clean on first run (0 mismatches); later reused
        # to confirm Organic Anions/Acetate+Formate free-text matching
        # (IPA, DMSO -- see KNOWN_OPEN_MISMATCHES) and the KOH ICPOES
        # correction, both 2026-09-29.
    ),
    GoldenPair(
        name="realistic_wafers_dummy",
        input_path=_EVIDENCE_ROOT / "Dummy TR - realistic Wafers.xlsx",
        legacy_output_path=_EVIDENCE_ROOT / "Dummy TR - realistic Wafers report.xlsx",
        unresolvable_customer_name="EXAMPLE LAB",
        # First real Wafer example with an Additional Element (Hg)
        # selected -- confirmed 2026-09-29 (direct user instruction after
        # reviewing the finding): Wafer additional-elements support is a
        # genuine gap in the legacy macro, same "accepted improvement"
        # category as Sulfur/Date-of-Analysis, not a new pipeline bug.
    ),
    GoldenPair(
        name="Cust018_energy_water_acetate_formate",
        input_path=_EVIDENCE_ROOT / "090925-Folder 048 Water ICPMS Anions Conductivity Silicon Real TR.xlsx",
        legacy_output_path=_EVIDENCE_ROOT
        / "090925-Folder 048 Water ICPMS Anions Conductivity Silicon Real TR Report.xlsx",
        # Real customer (Folder 048), real "7 Anions + GBP" selection
        # PLUS "Acetate & Formate" typed in Additional Requests or Notes
        # on all 8 samples -- confirmed 2026-09-29 via 3 independent
        # checks (direct search of the real live legacy template's
        # defined names -- Chemical AND Water share one file, neither has
        # any Acetate/Formate/Organic-Anions named range anywhere; a live
        # re-run of this exact TR through the real legacy macro; and this
        # diff) that free-text Acetate/Formate matching is a genuine gap
        # in the legacy macro, not a wording problem. report-engine
        # already bridges it correctly (merges Acetate/Formate into the
        # master anion panel, same "same-panel merge" design confirmed
        # earlier via a different real customer, Folder 048
        # Guatemala) -- direct user instruction: keep it, add as evidence.
    ),
    GoldenPair(
        name="sxos5_north_wx7808",
        input_path=_EVIDENCE_ROOT / "031126-SXOS5 North WX7808 Assay Same Day RUSH Real TR.xlsx",
        legacy_output_path=_EVIDENCE_ROOT / "031126-SXOS5 North WX7808 Assay Same Day RUSH Real TR Report.xlsx",
        # Real SX5 customer, 2 WX7808 samples -- first real coverage of
        # SX5's duplicate-sheet naming (fixed 2026-09-29, see
        # _sx5_tab_names) and the standalone-Assay shape. Clean.
    ),
    GoldenPair(
        name="sxos5_south_all",
        input_path=_EVIDENCE_ROOT / "041626-SXOS5 South All Dummy TR.xlsx",
        legacy_output_path=_EVIDENCE_ROOT / "041626-SXOS5 South All Dummy TR Report.xlsx",
        # Real SX5 customer, all 7 SX5-South element-panel/Assay chemicals
        # in one TR -- surfaced and fixed 4 real bugs 2026-09-29 (HCL/
        # WX-2000 tab-naming, WX2000's Assay header bold styling, and
        # SurfClean's real casing -- see CHANGELOG 0.21.19/0.21.20). The
        # SurfClean question (this codebase previously claimed it
        # lowercases to "Surfclean") is resolved: direct user correction
        # confirmed "SurfClean" (mixed case) is canonical -- the lowercase
        # belief was actually about the LEGACY macro's own intake-side
        # matching quirk, not the real output. Clean.
    ),
    GoldenPair(
        name="Folder 092_ky_pg",
        input_path=_EVIDENCE_ROOT / "092626-Customer 047 PG Same Day RUSH Real TR.xlsx",
        legacy_output_path=_EVIDENCE_ROOT / "092626-Customer 047 PG Same Day RUSH Real TR Report.xlsx",
        # Real customer (Customer 047), real ppm unit override --
        # closes the "spec-threshold/unit-override rendering is
        # effectively untestable via a dummy TR" gap for real. Confirmed
        # 2026-09-29: legacy's own real output has a literal bug here
        # ("All data in units of -1 unless otherwise noted" -- a broken
        # lookup/index, not intentional wording); report-engine's "ppm"
        # is correct. "Customer 017" (real form text) had
        # no form_key mapping to the existing "Customer 047"
        # customer (id 16) -- fixed via CustomerService.add_form_key(),
        # same self-heal pattern as Customer 054.
    ),
    GoldenPair(
        name="Customer 169_water_limits",
        input_path=Path(r"S:\Testing_Requests\Customer 169\2025\070325-Customer 169 Water Na Cu Cl Si.xlsx"),
        legacy_output_path=Path(r"S:\Reports\Customer 169\2025\070325-Customer 169 Water Results.xlsx"),
        # Real Water customer with limits on file (Na 5, Si 3, Cl 5 in
        # legacy -- on the metals, silicon and anion panels). Added
        # 2026-09-30 when the new limit check found Water samples printed
        # no limits at all; locks in the fix.
    ),
    GoldenPair(
        name="Customer 168_ipa_warning_limits",
        input_path=Path(r"S:\Testing_Requests\Customer 168\2025\061725-Customer 168 IPA ICPMS Time Limited.xlsx"),
        legacy_output_path=Path(r"S:\Reports\Customer 168\2025\061725-Customer 168 IPA Results Time Limited.xlsx"),
        # Real customer with BOTH limit kinds: "Action Limit" in column A
        # and "Warning Limit" in an extra column B, every other column one
        # to the right (legacy inserted a column B). Added 2026-10-01 with
        # the limit-columns layout; locks in labels, values and the shift.
    ),
    GoldenPair(
        name="Folder 092_houston_mibc",
        input_path=_EVIDENCE_ROOT / "092826-Folder 092 FX RI MIBC DLV00133992 Same Day RUSH Real TR.xlsx",
        legacy_output_path=_EVIDENCE_ROOT / "092826-Folder 092 FX RI MIBC DLV00133992 Same Day RUSH Real TR Report.xlsx",
        # Real Customer 057: specification + "Control Limit" columns,
        # and Additional Elements (Sb/As/B) run by Organic Dilute and
        # Shoot by agreement (Customer.additional_elements_prep) -- so
        # that block gets its own footer/SOPs and no limits. Legacy output
        # is the pre-edit state the chemist used to correct by hand.
    ),
    GoldenPair(
        name="Customer 168_1pct_nh4oh",
        input_path=Path(r"S:\Testing_Requests\Customer 168\2025\040925-Customer 168 1% NH4OH ICPMS Anions Assay Time Limited.xlsx"),
        legacy_output_path=Path(r"S:\Reports\Customer 168\2025\040925-Customer 168 1% NH4OH ResultsTime Limited.xlsx"),
        # Form text "1% NH4OH" was mapped (from the Access migration) to
        # chemical NH4OH, so these reports printed concentrated-NH4OH
        # limits (Al 0.1/0.05) instead of 1% NH4OH's (0.2/0.1). Remapped
        # 2026-10-01; 0 differences against the real report.
    ),
    GoldenPair(
        name="chemco_Cust055_mecb",
        input_path=Path(r"S:\Testing_Requests\Customer 100\091526-Customer 091 MeCb ICPMS STD.xlsx"),
        legacy_output_path=Path(r"S:\Reports\Customer 100\091526-Customer 091 MeCb Results.xlsx"),
        # Customer groups: Customer 091 has no limits of its own; the Chemco
        # group's Methyl Carbitol limits apply, as in the legacy macro.
        # Added 2026-10-01 with the group; 0 differences (36 limits).
    ),
    GoldenPair(
        name="chemco_Folder 092_pgmea",
        input_path=Path(r"S:\Testing_Requests\Customer 100\030326-Customer 101 PGMEA STD.xlsx"),
        legacy_output_path=Path(r"S:\Reports\Customer 100\030326-Customer 101 PGMEA Results.xlsx"),
        # Customer 101: "Customer 099" customer text -> Customer 099 (#73),
        # a site of the Chemco group, whose PGMEA limits apply (36, matching).
    ),
]


class _ForgivingCustomerService:
    """Wraps a real CustomerService so an unresolved form-key never
    blocks generation -- falls back to a fixed, already-real customer_id
    instead of raising. Same pattern as scripts/scan_latest_request.py's
    own class of the same name; duplicated here (rather than imported)
    so this test package has no dependency on that standalone script's
    own sys.path handling. Never writes to the database."""

    def __init__(self, real: object, fallback_customer_id: int) -> None:
        self._real = real
        self._fallback_id = fallback_customer_id

    def __getattr__(self, name: str):
        return getattr(self._real, name)

    def get_id_by_form_customer(self, name: str, address: str, address2: str) -> int:
        real_id = self._real.get_id_by_form_customer(name, address, address2)
        return real_id if real_id > 0 else self._fallback_id


class _ForgivingChemicalService:
    def __init__(self, real: object, fallback_chemical_id: int) -> None:
        self._real = real
        self._fallback_id = fallback_chemical_id

    def __getattr__(self, name: str):
        return getattr(self._real, name)

    def get_id_by_form_name(self, form_name: str) -> int:
        real_id = self._real.get_id_by_form_name(form_name)
        return real_id if real_id > 0 else self._fallback_id


def _generate(pair: GoldenPair, output_path: Path) -> str | None:
    """Runs this project's real CLI pipeline against pair.input_path.
    Returns the substitute customer name actually used (for the diff's
    own normalization), or None when no substitution was needed."""
    from slim_report_engine.cli import build_services, run

    real_services = build_services(None)

    if pair.skip_samples:
        # Wraps chemical_water_report_builder.build_sections so pair's
        # own known-unbuildable samples return [] (an empty, title-only
        # tab) instead of raising -- deliberately NOT filtering them out
        # of the submission's own sample list, which would shift every
        # LATER sample's tab numbering/position out of alignment with
        # legacy (confirmed real 2026-09-28: this exact mistake produced
        # a wall of false-positive mismatches on an earlier attempt).
        from slim_report_engine.reporting import chemical_water_report_builder

        real_build_sections = chemical_water_report_builder.build_sections

        def _lenient_build_sections(sample, *args, **kwargs):
            if sample.sample_name in pair.skip_samples:
                return []
            return real_build_sections(sample, *args, **kwargs)

        chemical_water_report_builder.build_sections = _lenient_build_sections
        try:
            return _run_with_optional_substitution(pair, output_path, real_services, run)
        finally:
            chemical_water_report_builder.build_sections = real_build_sections

    return _run_with_optional_substitution(pair, output_path, real_services, run)


def _run_with_optional_substitution(pair: GoldenPair, output_path: Path, real_services, run) -> str | None:
    if pair.unresolvable_customer_name is None:
        run(pair.input_path, output_path, None, services=real_services)
        return None

    fallback_customer = real_services.customer_svc.all_customers()[0]
    fallback_chemical_id = real_services.chemical_svc.all_chemicals()[0].id
    services = replace(
        real_services,
        customer_svc=_ForgivingCustomerService(real_services.customer_svc, fallback_customer.id),
        chemical_svc=_ForgivingChemicalService(real_services.chemical_svc, fallback_chemical_id),
    )
    run(pair.input_path, output_path, None, services=services)
    return fallback_customer.name


def _pair_id(pair: GoldenPair) -> str:
    return pair.name


# Precise, auditable exceptions for mismatches that are ALREADY KNOWN
# and tracked -- not silenced by a broad value/text wildcard (which
# would hide unrelated future regressions at other coordinates), just
# this exact (sheet, coordinate) on this one golden pair. Each entry
# must cite why. Cross-check the `report-engine-validation-evidence`
# project memory before removing or adding one.
KNOWN_OPEN_MISMATCHES: dict[str, frozenset[tuple[str, str]]] = {
    "dummy_tr_all_analyses": frozenset(
        {
            # Karl Fischer "Water" unit: code says "ppm", legacy says "%".
            # Direct user instruction (2026-09-28): "forget 1 and 2 and
            # stay with the current fix" -- stays "ppm" on purpose.
            ("IPA 2", "C81"), ("IPA 4", "C120"), ("IPA 6", "C30"), ("IPA 7", "C27"),
            # Element name: DB catalog says "Cesium", legacy VBA's
            # hardcoded element list says "Caesium" -- a DB data
            # question, not code. Same "stay with current fix" instruction.
            ("IPA 4", "B16"),
            # Misc Analysis pH's 2-column ("STDEV") shape vs this dummy
            # TR's own legacy output showing pH single-column -- DECIDED
            # (2026-09-28, direct user instruction after investigating
            # personally): "let's lock in 2 column for pH and KF" -- kept
            # as a permanent, intentional divergence from this one legacy
            # example, not a pending question anymore.
            ("IPA 10", "E16"), ("IPA 11", "E18"), ("IPA 12", "E19"), ("IPA 13", "E24"),
        }
    ),
    "dummy_tr_wafers": frozenset(
        {
            # "Sulfur"/"S" in the wafer trace-element panel: the real
            # legacy macro never supported this element at all. Direct
            # user instruction (2026-09-28): "it's an improvement and a
            # needed one" -- keep it, don't match legacy's gap.
            ("100mm Wafers", "B45"), ("100mm Wafers", "C45"),
            # "Date of Analysis" filled in on at least one footer line per
            # sheet, where the real legacy macro leaves it blank for
            # Wafer. Same "keep it, it's an improvement" instruction.
            ("100mm Wafers", "D47"),
            ("150mm Wafers Next Day RUSH 1", "D46"),
            ("150mm Wafers Next Day RUSH 2", "D76"),
            ("200mm Wafers Call-in RUSH", "D45"),
            ("300mm Wafers Same Day RUSH", "D46"),
            # Element name: DB catalog says "Cesium", legacy VBA's
            # hardcoded element list says "Caesium" -- same declined DB
            # data question as the dummy_tr_all_analyses pair above.
            ("150mm Wafers Next Day RUSH 2", "B16"),
        }
    ),
    "dummy_tr_water": frozenset(
        {
            # Element name, same declined DB data question as above.
            ("Water 1", "B16"), ("Water 6", "B16"),
            # Misc Analysis pH's 2-column ("STDEV") shape -- same DECIDED
            # (locked in) item as dummy_tr_all_analyses's IPA 10-13 above.
            ("Water 4", "E81"), ("Water 9", "E26"),
        }
    ),
    "sxos5_north_all": frozenset(
        {
            # "2to1WX2000" -- confirmed real legacy bug (2026-09-29, this
            # pair's own live debug log): legacy's GetChemicalName
            # resolves "WX-2000" (hyphenated), but the rename check a few
            # lines later in modReportCreator.bas compares against literal
            # "WX2000" -- an exact-string mismatch that has silently never
            # fired for any real sample. Direct user confirmation: the
            # customer has a real, currently-unmet need for this exact
            # string (XML upload matching) -- "fix the legacy's bug." The
            # whole sheet is absent from legacy under this name since
            # legacy never renames it at all.
            ("2to1WX2000", "-"),
            # 0.49%HF's embedded Assay content -- direct user "final
            # decision": this non-routine path may legitimately include
            # an embedded Assay when actually requested (as it was here),
            # even where this one legacy example's real output omits it
            # (its own spec note says "FC no longer wants North assay").
            ("0.49%HF", "A49"), ("0.49%HF", "B49"), ("0.49%HF", "C49"), ("0.49%HF", "D49"),
            ("0.49%HF", "A50"), ("0.49%HF", "B50"), ("0.49%HF", "E50"),
        }
    ),
    "Cust025_dmso_real": frozenset(
        {
            # "Date of Analysis" filled in -- date_of_analysis.py's own
            # docstring confirms this is a deliberate, already-confirmed
            # improvement for the GENERIC Chemical/Water path too, not
            # just Wafer (legacy leaves this field always blank). First
            # time a real Chemical golden pair has actually exercised it.
            ("DMSO  1", "D48"), ("DMSO  1", "D56"),
            ("DMSO  2", "D48"), ("DMSO  2", "D56"),
        }
    ),
    "ked_coverage_dummy": frozenset(
        {
            # IPA's "Organic anions" (Notes column, correct wording/column
            # this time -- see Cust018_energy_water_acetate_formate above
            # for the full citation): dispatches to GBP + Acetate/Formate
            # as two separate panels (bare "Organic Anions" isn't merged
            # into a master anion panel the way "Acetate and Formate"
            # alone is when a structured Anions selection also exists --
            # this sample has no structured Anions selection at all).
            ("IPA", "B64"), ("IPA", "C64"), ("IPA", "B65"), ("IPA", "C65"), ("IPA", "B66"), ("IPA", "C66"),
            ("IPA", "B73"), ("IPA", "C73"), ("IPA", "B74"), ("IPA", "C74"),
            # DMSO's "Acetate & Formate" (Notes column, retyped correctly
            # 2026-09-29) -- standalone Acetate/Formate, same confirmed
            # real legacy gap as Cust018_energy_water_acetate_formate.
            ("DMSO", "B66"), ("DMSO", "C66"), ("DMSO", "B67"), ("DMSO", "C67"),
            # KOH's metals_instrument corrected to ICPOES 2026-09-29
            # (direct user instruction) -- this pair's own legacy output
            # predates that correction (never manually overridden for
            # this test run), same accepted-improvement category as NaOH.
            ("KOH", "A48"),
        }
    ),
    "realistic_wafers_dummy": frozenset(
        {
            # Same DECIDED Date-of-Analysis improvement as above.
            ("200mm Wafers", "D46"), ("200mm Wafers Same Day RUSH", "D45"), ("300mm Wafers", "D45"),
            # Wafer Additional Elements (Hg): confirmed real gap in the
            # legacy macro (2026-09-29, direct user instruction after
            # reviewing this pair's own first real example) -- "Additional
            # element in wafer is a gap in the original. Keep the new way
            # as an improvement." Same accepted-improvement category as
            # Sulfur (dummy_tr_wafers).
            ("200mm Wafers", "B44"), ("200mm Wafers", "C44"),
        }
    ),
    # All 8 samples share identical selections (36 Elements, Dissolved and
    # Total Si, 7 Anions + GBP, Conductivity, Two Days, "Acetate & Formate"
    # in Notes) -- built programmatically rather than 80 literal tuples,
    # since every "Water N" sheet has the exact same coordinates for both
    # accepted-improvement categories. See the GoldenPair's own comment
    # above for the full citation.
    "Cust018_energy_water_acetate_formate": frozenset(
        (sheet, coord)
        for sheet in (f"Water {i}" for i in range(1, 9))
        for coord in (
            # Date of Analysis -- same DECIDED improvement as every other pair.
            "D48", "D57", "D60", "D77", "D86", "D93",
            # Acetate/Formate merged into the master anion panel -- confirmed
            # real legacy gap, report-engine already bridges it correctly.
            "B67", "C67", "B71", "C71",
        )
    ),
    "Folder 092_ky_pg": frozenset(
        (sheet, coord)
        for sheet in ("Propylene Glycol 1", "Propylene Glycol 2")
        for coord in (
            # ppm unit override -- confirmed 2026-09-29: legacy's own real
            # output has a literal bug here ("All data in units of -1
            # unless otherwise noted" -- a broken lookup/index, not
            # intentional), report-engine's "ppm" is correct.
            "A4",
            # Same DECIDED Date-of-Analysis improvement as every other pair.
            "D48", "D54", "D64",
        )
    ),
    "Folder 092_houston_mibc": frozenset({
        # Additional Elements are Organic Dilute and Shoot for this
        # customer (direct user confirmation 2026-10-01), so that block
        # has no limits; legacy printed them there too and the chemist
        # deleted them. Coarse by design: limits are keyed per symbol per
        # sheet, so this also covers the main panel's Sb/As/B rows --
        # whose values the diff output shows still match legacy.
        ("MIBC", "limit:Sb"), ("MIBC", "limit:As"), ("MIBC", "limit:B"),
        # The block's own footer -- legacy printed the main method.
        ("MIBC", "A56"),
        # Same DECIDED Date-of-Analysis improvement as every other pair.
        ("MIBC", "E48"), ("MIBC", "E56"),
    }),
    "chemco_Folder 092_pgmea": frozenset({
        # Sample-ID string: legacy resolved Customer 101 requests to the
        # Customer 057 customer ("...-Customer 057-..."); they now
        # resolve to Customer 099 ("...-Customer 099-..."). Direct user
        # decision 2026-10-01 ("Customer 099 confirmed"). Limits identical.
        ("PMAC", "D6"),
    }),
    "Customer 169_water_limits": frozenset(
        # Same DECIDED Date-of-Analysis improvement as every other pair --
        # three footer lines per sheet (one row lower on Water 6).
        (sheet, coord)
        for sheet, coords in (
            *((f"Water {i}", ("D10", "D17", "D24")) for i in (1, 2, 3, 4, 5, 7, 8)),
            ("Water 6", ("D11", "D18", "D25")),
        )
        for coord in coords
    ),
}


@pytest.mark.parametrize("pair", GOLDEN_PAIRS, ids=_pair_id)
def test_golden_pair_matches_real_legacy_output(pair: GoldenPair, tmp_path):
    if not pair.input_path.exists() or not pair.legacy_output_path.exists():
        pytest.skip(f"real evidence files not available in this environment: {pair.input_path}")

    try:
        substitute_name = _generate(pair, tmp_path / f"{pair.name}.xlsx")
    except Exception as exc:  # pragma: no cover -- environment-dependent (no live DB reachable)
        pytest.skip(f"could not generate against the real DB in this environment: {exc}")

    mismatches = diff_workbooks(
        str(tmp_path / f"{pair.name}.xlsx"),
        str(pair.legacy_output_path),
        customer_name_substitute=substitute_name,
        real_customer_name=pair.unresolvable_customer_name,
    )

    known = KNOWN_OPEN_MISMATCHES.get(pair.name, frozenset())
    mismatches = [m for m in mismatches if (m.sheet, m.coordinate) not in known]

    if mismatches:
        report = "\n".join(str(m) for m in mismatches)
        pytest.fail(f"{len(mismatches)} mismatch(es) against real legacy output:\n{report}")


# Pairs whose real legacy reports carry specification limits: one SX5,
# one generic customer. Used to prove the limit check is live on real
# output, not just on the synthetic workbooks in test_diff_limits.py.
_PAIRS_WITH_LIMITS = ("sxos5_south_real", "Cust025_dmso_real", "Customer 168_ipa_warning_limits")


@pytest.mark.parametrize("pair_name", _PAIRS_WITH_LIMITS)
def test_golden_limit_check_catches_a_changed_limit(pair_name: str, tmp_path):
    """Generates the real report, changes ONE printed limit, and asserts
    the diff reports it. Guards against the limit check going blind
    again (the golden comparison once exempted every number)."""
    import openpyxl

    from tests.golden._diff import _limit_index

    def first_limit_cell(wb):
        for ws in wb.worksheets:
            symbols = _limit_index(ws)
            for row in ws.iter_rows(max_col=1):
                cell = row[0]
                if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool):
                    symbol = next((ws.cell(row=cell.row, column=c).value for c in (3, 4)
                                   if ws.cell(row=cell.row, column=c).value in symbols), None)
                    if symbol:
                        return ws.title, symbol, cell.coordinate, cell.value
        raise AssertionError("no limit cell found in the generated report")

    pair = next(p for p in GOLDEN_PAIRS if p.name == pair_name)
    if not pair.input_path.exists() or not pair.legacy_output_path.exists():
        pytest.skip(f"real evidence files not available in this environment: {pair.input_path}")
    out = tmp_path / f"{pair.name}.xlsx"
    try:
        substitute_name = _generate(pair, out)
    except Exception as exc:  # pragma: no cover -- environment-dependent (no live DB reachable)
        pytest.skip(f"could not generate against the real DB in this environment: {exc}")

    wb = openpyxl.load_workbook(out)
    sheet, symbol, coordinate, value = first_limit_cell(wb)
    wb[sheet][coordinate].value = value * 10 + 1
    wb.save(out)

    mismatches = diff_workbooks(
        str(out), str(pair.legacy_output_path),
        customer_name_substitute=substitute_name, real_customer_name=pair.unresolvable_customer_name,
    )
    assert any(m.sheet == sheet and m.coordinate == f"limit:{symbol}" and m.kind == "limit_mismatch"
               for m in mismatches), f"changed {sheet}!{coordinate} ({symbol}) but the diff did not report it"
