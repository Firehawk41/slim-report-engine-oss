"""The fictional-data demo (demo/demo.py) runs end to end through the real
pipeline, and each demo customer shows the feature it exists for. Runs on
a throwaway SQLite database -- no real data, no network share."""

from __future__ import annotations

import openpyxl
import pytest

from demo.demo import run_demo
from tests.golden._diff import _limit_index


@pytest.fixture(scope="module")
def reports(tmp_path_factory):
    paths = run_demo(tmp_path_factory.mktemp("demo"))
    return {p.name.split("Demo ")[1].replace(" Results.xlsx", ""): openpyxl.load_workbook(p) for p in paths}


def _limits(ws) -> dict[str, list[tuple[int, float]]]:
    return {s: [lim for _c, lims in hits for lim in lims] for s, hits in _limit_index(ws).items()}


def _text(ws) -> list[str]:
    return [str(c.value) for row in ws.iter_rows() for c in row if isinstance(c.value, str)]


def test_customer_without_limits_prints_none(reports):
    assert _limits(reports["A plain"].worksheets[0]) == {}


def test_specification_limits_print(reports):
    assert _limits(reports["B limits"].worksheets[0])["Al"] == [(1, 0.5)]


def test_action_and_warning_limits_get_two_labelled_columns(reports):
    ws = reports["C warning limits"].worksheets[0]
    assert _limits(ws)["Al"] == [(1, 0.4), (2, 0.3)]
    assert {"Action Limit", "Warning Limit"} <= set(_text(ws))


def test_other_method_additional_elements_get_their_own_footer_and_no_limits(reports):
    ws = reports["E other method"].worksheets[0]
    assert "Analysis by ICPMS (Organic Dilute and Shoot)" in _text(ws)
    # Sb/As/B have limits on the main panel only, not on the additional-elements rows
    assert all(len(v) == 1 for k, v in _limits(ws).items() if k in ("Sb", "As", "B"))


def test_water_limits_print_on_every_panel(reports):
    lim = _limits(reports["F water"].worksheets[0])
    assert lim["Na"] == [(1, 5.0)] and lim["Si"] == [(1, 3.0)] and lim["Cl"] == [(1, 5.0)]


def test_group_site_uses_its_groups_limits(reports):
    assert _limits(reports["H group site"].worksheets[0])["Cu"] == [(1, 0.1)]
