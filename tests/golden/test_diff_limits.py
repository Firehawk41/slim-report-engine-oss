"""Self-check for the golden diff's specification-limit comparison.

The golden comparison once skipped every number, so a wrong limit passed
silently (found 2026-09-30 by putting a wrong SX5 iron limit back and
watching the golden test still pass). These tests prove the limit check
reports each kind of difference, so it can't quietly go blind again.
Needs no network share or database.
"""

import openpyxl
import pytest

from tests.golden._diff import diff_workbooks


def _workbook(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "49%HF"
    for r in rows:
        ws.append(r)
    wb.save(path)
    return str(path)


_LEGACY = [["Specification", "Element", "Symbol"], [0.2, "Iron", "Fe"], [0.1, "Sodium", "Na"]]


def _limit_findings(tmp_path, new_rows):
    legacy = _workbook(tmp_path / "legacy.xlsx", _LEGACY)
    new = _workbook(tmp_path / "new.xlsx", new_rows)
    return [(m.coordinate, m.kind) for m in diff_workbooks(new, legacy) if m.coordinate.startswith("limit:")]


def test_identical_limits_report_nothing(tmp_path):
    assert _limit_findings(tmp_path, _LEGACY) == []


def test_a_changed_limit_is_reported(tmp_path):
    rows = [_LEGACY[0], [0.5, "Iron", "Fe"], _LEGACY[2]]
    assert _limit_findings(tmp_path, rows) == [("limit:Fe", "limit_mismatch")]


def test_a_limit_missing_from_new_is_reported(tmp_path):
    rows = [_LEGACY[0], [None, "Iron", "Fe"], _LEGACY[2]]
    assert _limit_findings(tmp_path, rows) == [("limit:Fe", "missing_limit")]


def test_a_limit_only_in_new_is_reported(tmp_path):
    rows = _LEGACY + [[1.0, "Zinc", "Zn"]]
    assert _limit_findings(tmp_path, rows) == [("limit:Zn", "extra_limit")]


@pytest.mark.parametrize("value", [0.2, 0.20000000001])
def test_float_noise_is_not_a_difference(tmp_path, value):
    rows = [_LEGACY[0], [value, "Iron", "Fe"], _LEGACY[2]]
    assert _limit_findings(tmp_path, rows) == []


_LEGACY_TWO_LIMITS = [
    ["Action Limit", "Warning Limit", "Element", None, "EXAMPLE LAB Results"],
    [0.4, 0.3, "Aluminum", "Al", 0.0146],
]


def test_two_limit_layout_identical_reports_nothing(tmp_path):
    legacy = _workbook(tmp_path / "legacy.xlsx", _LEGACY_TWO_LIMITS)
    new = _workbook(tmp_path / "new.xlsx", _LEGACY_TWO_LIMITS)
    assert [m for m in diff_workbooks(new, legacy) if m.coordinate.startswith("limit:")] == []


def test_two_limit_layout_catches_a_changed_warning_limit(tmp_path):
    legacy = _workbook(tmp_path / "legacy.xlsx", _LEGACY_TWO_LIMITS)
    new = _workbook(tmp_path / "new.xlsx", [_LEGACY_TWO_LIMITS[0], [0.4, 0.9, "Aluminum", "Al", 0.0146]])
    kinds = [m.kind for m in diff_workbooks(new, legacy) if m.coordinate == "limit:Al"]
    assert kinds == ["limit_mismatch"]


def test_missing_column_shift_is_caught(tmp_path):
    """Same numbers, but NEW didn't insert the warning column: the action
    limit and symbol sit one column left of legacy."""
    legacy = _workbook(tmp_path / "legacy.xlsx", _LEGACY_TWO_LIMITS)
    new = _workbook(tmp_path / "new.xlsx", [["Action Limit", "Element", None, "EXAMPLE LAB Results"],
                                              [0.4, "Aluminum", "Al", 0.0146]])
    kinds = [m.kind for m in diff_workbooks(new, legacy) if m.coordinate == "limit:Al"]
    assert kinds == ["limit_mismatch"]


def test_a_result_after_the_name_is_not_read_as_a_limit(tmp_path):
    rows = [["Specification", "Element", "Symbol"], [None, "Iron", "Fe", 0.5]]
    legacy = _workbook(tmp_path / "legacy.xlsx", rows)
    new = _workbook(tmp_path / "new.xlsx", rows)
    assert [m for m in diff_workbooks(new, legacy) if m.coordinate.startswith("limit:")] == []


def test_a_limit_not_shown_to_3_decimals_is_reported(tmp_path):
    legacy = _workbook(tmp_path / "legacy.xlsx", _LEGACY)
    wb = openpyxl.load_workbook(legacy)
    for r in (2, 3):
        wb.active.cell(row=r, column=1).number_format = "0.000"
    wb.save(legacy)
    new = _workbook(tmp_path / "new.xlsx", _LEGACY)  # General format
    kinds = {m.kind for m in diff_workbooks(new, legacy) if m.coordinate.startswith("limit_format:")}
    assert kinds == {"limit_format"}
