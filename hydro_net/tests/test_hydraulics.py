"""Тесты общей гидравлики: свойства жидкости, Рейнольдс, коэффициент трения."""

from __future__ import annotations

import math

import pytest

from common import hydraulics as hyd


def test_water_properties_at_20c():
    props = hyd.fluid_properties("water", 20.0)
    assert props.density == pytest.approx(998.2, abs=0.1)
    assert props.viscosity == pytest.approx(1.002e-3, rel=1e-3)
    assert props.vapor_pressure == pytest.approx(2339.0, rel=1e-3)
    assert props.kinematic == pytest.approx(1.0039e-6, rel=1e-3)


def test_water_properties_interpolated_between_nodes():
    props = hyd.fluid_properties("water", 55.0)
    density = 988.1 + 0.5 * (983.2 - 988.1)
    assert props.density == pytest.approx(density, rel=1e-9)
    assert props.viscosity == pytest.approx((0.547 + 0.5 * (0.467 - 0.547)) * 1e-3)


def test_viscosity_and_vapor_pressure_fall_with_temperature():
    cold = hyd.fluid_properties("water", 20.0)
    hot = hyd.fluid_properties("water", 90.0)
    assert hot.viscosity < cold.viscosity
    assert hot.vapor_pressure > cold.vapor_pressure


def test_glycol_is_denser_and_more_viscous():
    water = hyd.fluid_properties("water", 20.0)
    glycol = hyd.fluid_properties("glycol30", 20.0)
    assert glycol.density > water.density
    assert glycol.viscosity > 2.0 * water.viscosity
    assert glycol.vapor_pressure < water.vapor_pressure


@pytest.mark.parametrize("code,temperature", [("oil", 20.0), ("water", 150.0), ("water", -5.0)])
def test_invalid_fluid_raises(code, temperature):
    with pytest.raises(hyd.FluidError):
        hyd.fluid_properties(code, temperature)


def test_velocity_and_reynolds():
    flow = 36.0 / 3600.0            # 36 м³/ч
    speed = hyd.velocity(flow, 0.1)  # DN100, d = 0.1 м
    assert speed == pytest.approx(1.2732, abs=1e-3)
    props = hyd.fluid_properties("water", 20.0)
    re = hyd.reynolds(props, speed, 0.1)
    assert re == pytest.approx(1.268e5, rel=2e-3)


def test_laminar_friction_is_64_over_re():
    assert hyd.friction_factor(1000.0, 0.0005) == pytest.approx(0.064)
    assert hyd.friction_factor(500.0, 0.0) == pytest.approx(0.128)


@pytest.mark.parametrize("re,rel", [(1e5, 0.0005), (4e6, 0.002), (3e4, 0.0), (1e7, 0.05)])
def test_turbulent_friction_satisfies_colebrook(re, rel):
    lam = hyd.friction_factor(re, rel)
    residual = 1.0 / math.sqrt(lam) + 2.0 * math.log10(rel / 3.7 + 2.51 / (re * math.sqrt(lam)))
    assert abs(residual) < 1e-6


def test_smooth_pipe_matches_reference_value():
    assert hyd.friction_factor(1e6, 0.0) == pytest.approx(0.0116, abs=3e-4)


def test_friction_factor_monotonicity():
    assert hyd.friction_factor(1e5, 0.001) < hyd.friction_factor(1e4, 0.001)
    assert hyd.friction_factor(1e5, 0.001) > hyd.friction_factor(1e5, 0.0001)


def test_transition_zone_is_continuous():
    below = hyd.friction_factor(3999.0, 0.0005)
    above = hyd.friction_factor(4001.0, 0.0005)
    assert abs(above - below) < 1e-3


def test_invalid_inputs_raise():
    with pytest.raises(hyd.FluidError):
        hyd.friction_factor(0.0, 0.001)
    with pytest.raises(hyd.FluidError):
        hyd.friction_factor(1e4, -0.001)
    with pytest.raises(hyd.FluidError):
        hyd.velocity(0.01, 0.0)


def test_friction_and_local_head():
    head = hyd.friction_head(0.02, 100.0, 0.1, 1.5)
    assert head == pytest.approx(0.02 * 1000 * 1.5 ** 2 / (2 * hyd.G))
    assert hyd.local_head(3.0, 1.5) == pytest.approx(3.0 * 1.5 ** 2 / (2 * hyd.G))
    assert hyd.velocity_head(2.0) == pytest.approx(4.0 / (2 * hyd.G))
