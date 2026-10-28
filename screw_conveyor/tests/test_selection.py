"""Тесты подбора типоразмера и отрисовки схем (smoke-тесты графики)."""

from __future__ import annotations

import os

import pytest

from common import plotkit
from screw_conveyor import charts, core


def test_select_returns_feasible_best_for_grain():
    """10 т/ч зерна на 10 м закрывается ближайшим типоразмером Ø200 при n ≤ 120 об/мин."""
    selection = core.select(core.ScrewInput(material_code="wheat", capacity=10, length=10))
    assert selection.best is not None
    assert selection.best.diameter == pytest.approx(0.20)
    assert selection.best.reserve_pct >= 10.0
    assert selection.best.reserve_pct <= 40.0
    assert selection.candidates[selection.best_index].note == "рекомендуемый вариант"


def test_select_candidates_cover_standard_row():
    selection = core.select(core.ScrewInput(material_code="sand", capacity=60, length=18))
    assert [c.diameter for c in selection.candidates] == list(core.cat.STANDARD_DIAMETERS)
    assert any(c.feasible for c in selection.candidates)
    infeasible = [c for c in selection.candidates if not c.feasible]
    for cand in infeasible:
        assert cand.note != ""


def test_select_bigger_capacity_needs_bigger_screw():
    small = core.select(core.ScrewInput(material_code="sand", capacity=10, length=10))
    large = core.select(core.ScrewInput(material_code="sand", capacity=80, length=10))
    assert large.best.diameter > small.best.diameter


def test_select_marks_infeasible_when_capacity_too_high():
    selection = core.select(core.ScrewInput(material_code="wheat", capacity=500, length=10))
    assert not any(c.feasible for c in selection.candidates)


@pytest.mark.parametrize("example", list(core.EXAMPLES))
def test_charts_render(example, tmp_path):
    """Схема, график производительности и диаграмма подбора строятся без ошибок."""
    inp = core.EXAMPLES[example]
    res = core.calculate(inp)
    for name, fig in (
        ("scheme", charts.schematic_fig(res)),
        ("capacity", charts.capacity_fig(res)),
        ("selection", charts.selection_fig(core.select(inp))),
    ):
        path = os.path.join(tmp_path, f"{name}.png")
        plotkit.save_png(fig, path)
        plotkit.close(fig)
        assert os.path.getsize(path) > 5000


def test_schematic_handles_inclined_conveyor():
    res = core.calculate(core.EXAMPLES["Цемент, 30 т/ч, L=12 м, 10°"])
    fig = charts.schematic_fig(res)
    plotkit.close(fig)
