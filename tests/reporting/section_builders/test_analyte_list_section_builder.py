from dataclasses import dataclass

import pytest

from slim_report_engine.reporting.section_builders import analyte_list_section_builder as builder


@dataclass(frozen=True)
class _FakeElement:
    name: str
    symbol: str
    id: int = 0


class _FakeElementService:
    """Duck-types ElementService.get_by_symbol without a real DB session."""

    _CATALOG = {
        "Al": _FakeElement("Aluminum", "Al", id=13),
        "Sb": _FakeElement("Antimony", "Sb", id=51),
        "As": _FakeElement("Arsenic", "As", id=33),
        "Ba": _FakeElement("Barium", "Ba", id=56),
        "Ca": _FakeElement("Calcium", "Ca", id=20),
        "Fe": _FakeElement("Iron", "Fe", id=26),
        "Pb": _FakeElement("Lead", "Pb", id=82),
        "Mg": _FakeElement("Magnesium", "Mg", id=12),
    }

    def get_by_symbol(self, symbol: str):
        return self._CATALOG.get(symbol)

    def get_by_name(self, name: str):
        return next((e for e in self._CATALOG.values() if e.name == name), None)


def _footer_row(section):
    """(ICPMS, Evaporation) has a confirmed real Test Methods mapping, so
    the footer text row is no longer always second-to-last -- find it by
    content instead of a fixed offset from the end."""
    return next(r for r in section.rows if r.get_value(1) and "Analysis by" in str(r.get_value(1)))


def test_build_metals_panel_header_and_footer():
    section = builder.build_metals_panel(
        "36 Elements", ["Al", "Sb"], "36 Tr.Elts", _FakeElementService()
    )
    top, header = section.rows[0], section.rows[1]
    assert top.get_value(1) == "Specification"
    assert header.get_value(2) == "Element"
    assert header.get_value(6) == "MDL"
    assert _footer_row(section).get_value(1) == "Analysis by ICPMS (Evaporation)"
    assert section.rows[-1].values == {}  # trailing blank


def test_build_metals_panel_adds_one_row_per_symbol_in_order():
    section = builder.build_metals_panel(
        "36 Elements", ["Al", "Sb", "As"], "36 Tr.Elts", _FakeElementService()
    )
    # rows: top, header, Al, Sb, As, blank, AVERAGE, TOTAL, blank, footer
    data_rows = section.rows[2:5]
    assert [r.get_value(3) for r in data_rows] == ["Al", "Sb", "As"]
    assert [r.get_value(2) for r in data_rows] == ["Aluminum", "Antimony", "Arsenic"]


def test_build_metals_panel_renders_real_spec_values_by_symbol():
    section = builder.build_metals_panel(
        "36 Elements", ["Al", "Sb", "As"], "36 Tr.Elts", _FakeElementService(),
        specs={"Al": 0.3, "As": 10.0},
    )
    al_row, sb_row, as_row = section.rows[2:5]
    assert al_row.get_value(1) == 0.3
    assert sb_row.get_value(1) is None  # no spec on file for Sb -- omitted, not guessed
    assert as_row.get_value(1) == 10.0


def test_build_metals_panel_no_specs_leaves_column_1_blank():
    section = builder.build_metals_panel("36 Elements", ["Al"], "36 Tr.Elts", _FakeElementService())
    assert section.rows[2].get_value(1) is None


def test_build_metals_panel_unknown_symbol_raises():
    with pytest.raises(ValueError):
        builder.build_metals_panel("x", ["Xx"], "label", _FakeElementService())


def test_summary_rows_use_summary_label():
    section = builder.build_metals_panel(
        "10 Elements", ["Al"], "10 Tr.Elts", _FakeElementService()
    )
    avg_row = next(r for r in section.rows if r.style_name == "SummaryRow" and r.get_value(2) and "AVERAGE" in r.get_value(2))
    total_row = next(r for r in section.rows if r.style_name == "SummaryRow" and r.get_value(2) and "TOTAL" in r.get_value(2))
    assert avg_row.get_value(2) == "AVERAGE / 10 Tr.Elts"
    assert total_row.get_value(2) == "TOTAL / 10 Tr.Elts"


def test_summary_formulas_are_relative_r1c1_and_cover_the_data_rows():
    """With 3 analyte rows starting right after the 2 header rows, the
    AVERAGE row (logical row 6, 1-based: top=1,header=2,Al=3,Sb=4,As=5,
    blank=6? -- actually blank comes first) should reference back to the
    first/last data rows via relative offsets."""
    section = builder.build_metals_panel(
        "36 Elements", ["Al", "Sb", "As"], "36 Tr.Elts", _FakeElementService()
    )
    # logical rows: 1 top, 2 header, 3 Al, 4 Sb, 5 As, 6 blank, 7 AVERAGE, 8 TOTAL, 9 blank, 10 footer
    avg_row = section.rows[6]
    assert avg_row.get_formula(4) == "=AVERAGE(R[-4]C:R[-2]C)"
    total_row = section.rows[7]
    assert total_row.get_formula(4) == "=SUM(R[-5]C:R[-3]C)"


def test_build_metals_panel_default_prep_text_is_evaporation():
    section = builder.build_metals_panel("36 Elements", ["Al"], "36 Tr.Elts", _FakeElementService())
    assert _footer_row(section).get_value(1) == "Analysis by ICPMS (Evaporation)"


def test_build_metals_panel_custom_prep_text():
    section = builder.build_metals_panel(
        "36 Elements", ["Al"], "36 Tr.Elts", _FakeElementService(), prep_text="Dilute and Shoot"
    )
    assert _footer_row(section).get_value(1) == "Analysis by ICPMS (Dilute and Shoot)"


def test_build_metals_panel_custom_instrument():
    """Confirmed real: Chemical.metals_instrument stores "ICPOES" (no
    hyphen) but the real report footer text hyphenates it."""
    section = builder.build_metals_panel(
        "36 Elements", ["Al"], "36 Tr.Elts", _FakeElementService(), instrument="ICPOES"
    )
    assert _footer_row(section).get_value(1) == "Analysis by ICP-OES (Evaporation)"


def test_build_metals_panel_instrument_applies_to_additional_elements_block_too():
    """Confirmed real: ICPOES's real report text hyphenates ("ICP-OES")
    even though the stored value doesn't."""
    section = builder.build_metals_panel(
        "36 Elements", ["Al"], "36 Tr.Elts", _FakeElementService(),
        additional_element_names=["Antimony"], instrument="ICPOES",
    )
    footers = [r.get_value(1) for r in section.rows if r.get_value(1) and "Analysis by" in str(r.get_value(1))]
    assert footers == ["Analysis by ICP-OES (Evaporation)", "Analysis by ICP-OES (Evaporation)"]


def _test_methods_rows(section):
    return [r.get_value(1) for r in section.rows if r.get_value(1) and "Test Methods" in str(r.get_value(1))]


def test_build_metals_panel_has_ked_elements_inserts_pr_in45():
    """Confirmed real (lab's own SOP master list): every ICPMS "with KEDS"
    variant is its non-KEDS counterpart's codes with SOP-45 inserted
    right after the first code."""
    section = builder.build_metals_panel(
        "36 Elements", ["Al"], "36 Tr.Elts", _FakeElementService(),
        prep_text="Dilute and Shoot", has_ked_elements=True,
    )
    assert _test_methods_rows(section) == ["Test Methods: SOP-14, SOP-45 and SOP-48."]


def test_build_metals_panel_default_has_no_ked_pr_in45():
    section = builder.build_metals_panel(
        "36 Elements", ["Al"], "36 Tr.Elts", _FakeElementService(), prep_text="Dilute and Shoot",
    )
    assert _test_methods_rows(section) == ["Test Methods: SOP-14 and SOP-48."]


def test_build_metals_panel_has_ked_elements_adds_note_1():
    """Confirmed real against a live production report (2026-09-23) --
    previously dropped entirely during the port from VBA."""
    section = builder.build_metals_panel(
        "36 Elements", ["Al"], "36 Tr.Elts", _FakeElementService(),
        prep_text="Dilute and Shoot", has_ked_elements=True,
    )
    notes = [r.get_value(1) for r in section.rows if r.get_value(1) and "KEDS" in str(r.get_value(1))]
    assert notes == ["Note 1: ICPMS-KEDS used for the reduction of interferences"]


def test_build_metals_panel_default_has_no_ked_note():
    section = builder.build_metals_panel(
        "36 Elements", ["Al"], "36 Tr.Elts", _FakeElementService(), prep_text="Dilute and Shoot",
    )
    assert not any("KEDS" in str(r.get_value(1)) for r in section.rows)


def test_build_metals_panel_has_ked_elements_applies_to_additional_elements_block_too():
    """has_ked_elements is a per-chemical property -- confirmed real: the
    same value applies to the main panel and any additional-elements block."""
    section = builder.build_metals_panel(
        "36 Elements", ["Al"], "36 Tr.Elts", _FakeElementService(),
        prep_text="Evaporation", additional_element_names=["Antimony"], has_ked_elements=True,
    )
    assert _test_methods_rows(section) == [
        "Test Methods: SOP-14, SOP-45, SOP-48 and SOP-52.",
        "Test Methods: SOP-14, SOP-45, SOP-48 and SOP-52.",
    ]


def test_organic_dilute_and_shoot_ampersand_variant_matches_same_codes():
    """Confirmed real: at least one real chemical's metals_prep is stored
    with an ampersand ("Organic Dilute & Shoot") instead of "and" -- same
    real method, same codes, not a different prep."""
    section = builder.build_metals_panel(
        "36 Elements", ["Al"], "36 Tr.Elts", _FakeElementService(), prep_text="Organic Dilute & Shoot",
    )
    assert _test_methods_rows(section) == ["Test Methods: SOP-14 and SOP-58."]


def test_add_additional_elements_block_default_instrument_is_icpms():
    section = builder.build_metals_panel("36 Elements", ["Al"], "36 Tr.Elts", _FakeElementService())
    builder.add_additional_elements_block(section, ["Antimony"], _FakeElementService(), "Evaporation")
    footers = [r for r in section.rows if r.get_value(1) and "Analysis by" in str(r.get_value(1))]
    assert footers[-1].get_value(1) == "Analysis by ICPMS (Evaporation)"


def test_build_additional_elements_only_panel_custom_instrument():
    """(ICPOES, "Dilute and Shoot") has no confirmed real SOP mapping, so
    no Test Methods row here -- but the hyphenation fix still applies."""
    section = builder.build_additional_elements_only_panel(
        "Additional Elements", ["Antimony"], _FakeElementService(), "Dilute and Shoot", instrument="ICPOES"
    )
    assert section.rows[-2].get_value(1) == "Analysis by ICP-OES (Dilute and Shoot)"


def test_add_additional_elements_block_renders_real_spec_values():
    section = builder.build_metals_panel("36 Elements", ["Al"], "36 Tr.Elts", _FakeElementService())
    builder.add_additional_elements_block(
        section, ["Antimony"], _FakeElementService(), "Evaporation", specs={"Sb": 0.5}
    )
    sb_row = next(r for r in section.rows if r.get_value(2) == "Antimony")
    assert sb_row.get_value(1) == 0.5


def test_build_additional_elements_only_panel_renders_real_spec_values():
    section = builder.build_additional_elements_only_panel(
        "Additional Elements", ["Antimony", "Arsenic"], _FakeElementService(), "Dilute and Shoot",
        specs={"Sb": 0.5},
    )
    sb_row, as_row = section.rows[2], section.rows[3]
    assert sb_row.get_value(1) == 0.5
    assert as_row.get_value(1) is None


def test_build_metals_panel_with_additional_elements_appends_labeled_block():
    section = builder.build_metals_panel(
        "36 Elements", ["Al"], "36 Tr.Elts", _FakeElementService(),
        additional_element_names=["Antimony", "Arsenic"],
    )
    footers = [r for r in section.rows if r.get_value(1) and "Analysis by" in str(r.get_value(1))]
    assert len(footers) == 2
    assert footers[0].get_value(1) == "Analysis by ICPMS (Evaporation)"  # main panel's own footer
    assert footers[1].get_value(1) == "Analysis by ICPMS (Evaporation)"  # additional-elements block's footer
    label_index = next(i for i, r in enumerate(section.rows) if r.get_value(4) == "Additional Elements")
    sb_row, as_row = section.rows[label_index + 1], section.rows[label_index + 2]
    assert (sb_row.get_value(2), sb_row.get_value(3)) == ("Antimony", "Sb")
    assert (as_row.get_value(2), as_row.get_value(3)) == ("Arsenic", "As")
    assert section.rows[-1].values == {}  # trailing blank


def test_build_metals_panel_without_additional_elements_has_no_extra_block():
    section = builder.build_metals_panel("36 Elements", ["Al"], "36 Tr.Elts", _FakeElementService())
    assert _footer_row(section).get_value(1) == "Analysis by ICPMS (Evaporation)"
    # top, header, Al, blank, AVERAGE, TOTAL, blank, footer, Test Methods, blank == 10 rows
    assert len(section.rows) == 10


def test_add_additional_elements_block_unknown_name_raises():
    section = builder.build_metals_panel("36 Elements", ["Al"], "36 Tr.Elts", _FakeElementService())
    with pytest.raises(ValueError):
        builder.add_additional_elements_block(section, ["Not A Real Element"], _FakeElementService(), "Evaporation")


def test_build_additional_elements_only_panel_has_no_summary_or_label_row():
    section = builder.build_additional_elements_only_panel(
        "Additional Elements", ["Antimony", "Arsenic"], _FakeElementService(), "Dilute and Shoot"
    )
    # top, header, Sb, As, blank (auto), footer, Test Methods, blank (trailing)
    # == 8 rows -- no AVERAGE/TOTAL/label; (ICPMS, "Dilute and Shoot") has a
    # confirmed real SOP mapping.
    assert len(section.rows) == 8
    sb_row, as_row = section.rows[2], section.rows[3]
    assert (sb_row.get_value(2), sb_row.get_value(3)) == ("Antimony", "Sb")
    assert (as_row.get_value(2), as_row.get_value(3)) == ("Arsenic", "As")
    assert _footer_row(section).get_value(1) == "Analysis by ICPMS (Dilute and Shoot)"


def test_build_additional_elements_only_panel_unknown_name_raises():
    with pytest.raises(ValueError):
        builder.build_additional_elements_only_panel(
            "x", ["Not A Real Element"], _FakeElementService(), "Evaporation"
        )


def test_summary_rows_only_have_formulas_on_expected_columns():
    section = builder.build_metals_panel(
        "36 Elements", ["Al"], "36 Tr.Elts", _FakeElementService()
    )
    # rows: top, header, Al, blank, AVERAGE, TOTAL, blank, footer
    avg_row = section.rows[4]
    total_row = section.rows[5]
    assert set(avg_row.formula_columns) == {4, 5, 6}
    assert set(total_row.formula_columns) == {4, 6}


# ---------------------------------------------------------------------------
# Hardness -- confirmed real (modReportCreator.bas Set_Hardness_Formula/
# Formula_To_Sum_Elements): a live SUM formula over Ba/Ca/Fe/Pb/Mg, added
# as an extra row when the sample also selected "Hardness" alongside a
# metals panel -- never its own section.
# ---------------------------------------------------------------------------

def test_include_hardness_adds_row_after_summary_with_sum_formula():
    section = builder.build_metals_panel(
        "36 Elements", ["Al", "Ba", "Ca"], "36 Tr.Elts", _FakeElementService(), include_hardness=True
    )
    # rows: top, header, Al, Ba, Ca, blank, AVERAGE, TOTAL, blank, Hardness, footer...
    hardness_row = next(r for r in section.rows if r.get_value(2) == "Hardness")
    assert hardness_row.has_formula(4)
    # top, header, Al, Ba, Ca, blank, AVERAGE, TOTAL, blank, Hardness --
    # Ba (row 4) and Ca (row 5) are 6 and 5 rows before Hardness (row 10).
    assert hardness_row.get_formula(4) == "=SUM(R[-6]C,R[-5]C)"
    # Confirmed placed AFTER the AVERAGE/TOTAL summary, not swept into it.
    total_row_index = next(i for i, r in enumerate(section.rows) if r.get_value(2) == "TOTAL / 36 Tr.Elts")
    hardness_row_index = next(i for i, r in enumerate(section.rows) if r.get_value(2) == "Hardness")
    assert hardness_row_index > total_row_index


def test_include_hardness_omits_elements_not_present_in_this_panel():
    """Confirmed real: the legacy macro searches for each of Ba/Ca/Fe/Pb/Mg
    and simply skips any it can't find in this specific panel -- doesn't
    error, doesn't include a blank/zero placeholder for a missing one."""
    section = builder.build_metals_panel(
        "36 Elements", ["Al", "Ba"], "36 Tr.Elts", _FakeElementService(), include_hardness=True
    )
    hardness_row = next(r for r in section.rows if r.get_value(2) == "Hardness")
    # top, header, Al, Ba, blank, AVERAGE, TOTAL, blank, Hardness -- Ba
    # (row 4) is 5 rows before Hardness (row 9).
    assert hardness_row.get_formula(4) == "=SUM(R[-5]C)"


def test_include_hardness_false_by_default_adds_no_row():
    section = builder.build_metals_panel("36 Elements", ["Al", "Ba"], "36 Tr.Elts", _FakeElementService())
    assert not any(r.get_value(2) == "Hardness" for r in section.rows)


def test_include_hardness_true_but_no_matching_elements_adds_no_row():
    """None of Ba/Ca/Fe/Pb/Mg happen to be in this panel -- confirmed real
    edge case, the legacy formula would end up an empty/no-op SUM()."""
    section = builder.build_metals_panel(
        "36 Elements", ["Al", "Sb"], "36 Tr.Elts", _FakeElementService(), include_hardness=True
    )
    assert not any(r.get_value(2) == "Hardness" for r in section.rows)
