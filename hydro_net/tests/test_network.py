"""Тесты расчёта сети и подбора насоса."""

from __future__ import annotations

import math

import pytest

from common import hydraulics as hyd
from hydro_net import catalog as cat
from hydro_net import core


def simple_network(flow: float = 36.0, static: float = 10.0, length: float = 50.0,
                   dn: int = 100) -> core.NetworkInput:
    """Один всасывающий и один напорный участок без местных сопротивлений."""
    return core.NetworkInput(
        fluid="water", temperature=20.0, flow_m3h=flow, static_head=static,
        back_pressure_bar=0.0, suction_lift=2.0,
        sections=[
            core.Section("Всасывание", 5.0, dn, "steel", {}, suction=True),
            core.Section("Напор", length, dn, "steel", {}),
        ],
    )


def test_pipe_size_geometry():
    size = cat.PIPES[100]
    assert size.inner_mm == pytest.approx(100.0)
    assert size.area == pytest.approx(math.pi * 0.1 ** 2 / 4)


def test_section_losses_match_hand_calculation():
    inp = simple_network()
    res = core.calculate(inp)
    section = res.sections[1]
    diameter = cat.PIPES[100].inner_m
    speed = (36.0 / 3600.0) / cat.PIPES[100].area
    assert section.velocity == pytest.approx(speed)
    lam = hyd.friction_factor(section.reynolds, 0.045 / 1000.0 / diameter)
    assert section.lambda_ == pytest.approx(lam)
    assert section.loss_friction == pytest.approx(lam * 50.0 / diameter * speed ** 2 / (2 * hyd.G))
    assert section.loss == pytest.approx(section.loss_friction)


def test_pressure_drop_and_specific_loss_are_consistent():
    res = core.calculate(simple_network())
    density = res.fluid.density
    for section in res.sections:
        assert section.pressure_drop_kpa == pytest.approx(
            section.loss * density * hyd.G / 1000.0)
        assert section.specific_loss == pytest.approx(
            section.loss_friction * density * hyd.G / section.length_m)


def test_required_head_is_sum_of_parts():
    res = core.calculate(simple_network(static=12.0))
    assert res.total_loss == pytest.approx(res.loss_friction + res.loss_local)
    assert res.required_head == pytest.approx(12.0 + res.total_loss)
    assert res.static_head == 12.0
    assert res.back_pressure_head == 0.0


def test_back_pressure_adds_head():
    inp = simple_network()
    inp.back_pressure_bar = 1.0
    res = core.calculate(inp)
    expected = 1e5 / (res.fluid.density * hyd.G)
    assert res.back_pressure_head == pytest.approx(expected)
    assert res.required_head == pytest.approx(10.0 + expected + res.total_loss)


def test_quadratic_network_law():
    """Потери растут как λ·Q²: при удвоении расхода — почти вчетверо."""

    def build(flow: float) -> core.NetworkResult:
        inp = simple_network(flow=flow)
        inp.sections[0].fittings = {"inlet": 1}
        inp.sections[1].fittings = {"elbow90": 4}
        return core.calculate(inp)

    low, high = build(20.0), build(40.0)
    for lo, hi in zip(low.sections, high.sections):
        assert hi.loss_friction / lo.loss_friction == pytest.approx(
            4.0 * hi.lambda_ / lo.lambda_, rel=1e-9)
        assert hi.loss_local / lo.loss_local == pytest.approx(4.0, rel=1e-9)
    assert 3.4 < high.total_loss / low.total_loss < 4.0


def test_local_losses_increase_total():
    plain = core.calculate(simple_network())
    inp = simple_network()
    inp.sections[1].fittings = {"elbow90": 4, "valve": 1}
    with_fittings = core.calculate(inp)
    zeta = 4 * cat.FITTINGS["elbow90"][1] + cat.FITTINGS["valve"][1]
    speed = with_fittings.sections[1].velocity
    assert with_fittings.sections[1].zeta == pytest.approx(zeta)
    assert with_fittings.total_loss - plain.total_loss == pytest.approx(
        zeta * speed ** 2 / (2 * hyd.G))


def test_npsh_decreases_with_suction_lift_and_losses():
    base = core.calculate(simple_network())
    lifted = simple_network()
    lifted.suction_lift = 5.0
    assert core.calculate(lifted).npsh_available < base.npsh_available
    assert base.npsh_available == pytest.approx(
        (base.atmosphere_kpa * 1000 - base.fluid.vapor_pressure)
        / (base.fluid.density * hyd.G) - 2.0 - base.suction_loss)


def test_checks_include_velocity_and_specific_loss():
    res = core.calculate(simple_network())
    names = [check.name for check in res.checks]
    assert "Скорость на напорном участке" in names
    assert "Удельные потери напора" in names


def test_validate_reports_problems():
    inp = simple_network(flow=-5.0)
    inp.sections[0].dn = 999
    inp.sections[1].fittings = {"unknown": 2}
    errors = core.validate(inp)
    text = " ".join(errors)
    assert "Расчётный расход" in text
    assert "DN999" in text
    assert "unknown" in text
    with pytest.raises(core.CalculationError):
        core.calculate(inp)


def test_validate_requires_suction_section():
    inp = simple_network()
    for section in inp.sections:
        section.suction = False
    assert any("всасывающий" in message for message in core.validate(inp))


def test_operating_point_satisfies_both_curves():
    network = core.calculate(simple_network())
    pump = cat.PUMPS["НК 65-160"]
    flow, head = core.operating_point(pump, network)
    assert head == pytest.approx(pump.head(flow))
    assert head == pytest.approx(network.static_head + network.resistance * flow ** 2)


def test_operating_point_falls_with_static_head():
    pump = cat.PUMPS["НК 65-160"]
    low = core.operating_point(pump, core.calculate(simple_network(static=5.0)))[0]
    high = core.operating_point(pump, core.calculate(simple_network(static=25.0)))[0]
    assert high < low


def test_pump_with_low_head_has_no_operating_point():
    network = core.calculate(simple_network(static=60.0))
    assert core.operating_point(cat.PUMPS["НК 32-125"], network)[0] == 0.0


def test_select_motor_rounds_up():
    assert core.select_motor(3.2).power == 4.0
    assert core.select_motor(0.5).power == 0.55
    assert core.select_motor(1000.0) is None


def test_pump_curves_are_monotonic():
    pump = cat.PUMPS["НК 80-160"]
    assert pump.head(0.0) == pytest.approx(pump.head_shutoff)
    assert pump.head(0.3 * pump.q_opt) > pump.head(0.7 * pump.q_opt)
    assert pump.efficiency_at(pump.q_opt) == pytest.approx(pump.efficiency)
    assert pump.npsh_required(pump.q_opt) == pytest.approx(pump.npsh_r)
