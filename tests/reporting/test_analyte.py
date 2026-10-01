import dataclasses

import pytest

from slim_report_engine.reporting.analyte import Analyte


def test_default_elute_order_is_zero():
    a = Analyte(name="Fluoride", symbol="F")
    assert a.elute_order == 0


def test_elute_order_can_be_set():
    a = Analyte(name="Fluoride", symbol="F", elute_order=1)
    assert a.elute_order == 1


def test_is_frozen():
    a = Analyte(name="Fluoride", symbol="F")
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.name = "Chloride"
