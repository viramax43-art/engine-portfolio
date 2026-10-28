"""Тесты расчётного ядра шнекового конвейера.

Эталонные значения рассчитаны вручную по формулам методики, поэтому тесты
проверяют не «совпадение с самим собой», а корректность реализации формул.
"""

from __future__ import annotations

import math

import pytest

from screw_conveyor import catalog as cat
from screw_conveyor import core


# --------------------------------------------------------------- производительность
def test_capacity_reference_value():
    """Q = 47·D²·S·n·ψ·ρ·c: 47·0,25²·0,25·60·0,35·0,75·1,0 = 11,57 т/ч."""
    q = core.capacity_formula(0.25, 0.25, 60, 0.35, 0.75, 1.0)
    assert q == pytest.approx(11.5664, abs=1e-3)


def test_capacity_is_linear_in_rpm_and_density():
    base = core.capacity_formula(0.25, 0.25, 60, 0.35, 0.75, 1.0)
    assert core.capacity_formula(0.25, 0.25, 120, 0.35, 0.75, 1.0) == pytest.approx(base * 2)
    assert core.capacity_formula(0.25, 0.25, 60, 0.35, 1.50, 1.0) == pytest.approx(base * 2)
    assert core.capacity_formula(0.50, 0.50, 60, 0.35, 0.75, 1.0) == pytest.approx(base * 8)


# ---------------------------------------------------------------------- наклон
@pytest.mark.parametrize("beta,expected", [(0, 1.00), (5, 0.90), (10, 0.80), (15, 0.70),
                                           (20, 0.65), (30, 0.65)])
def test_incline_factor_table(beta, expected):
    assert cat.incline_factor(beta) == pytest.approx(expected)


def test_incline_factor_interpolates():
    assert cat.incline_factor(12.5) == pytest.approx(0.75)
    assert cat.incline_factor(7.5) == pytest.approx(0.85)


# ------------------------------------------------------------ предельная частота
def test_max_rpm_groups():
    wheat = cat.MATERIALS["wheat"]
    sand = cat.MATERIALS["sand"]
    assert core.max_rpm(0.25, wheat) == pytest.approx(60 / math.sqrt(0.25))
    assert core.max_rpm(0.25, sand) == pytest.approx(30 / math.sqrt(0.25))
    assert core.max_rpm(0.25, sand) == pytest.approx(60.0)


def test_max_rpm_decreases_with_diameter():
    wheat = cat.MATERIALS["wheat"]
    assert core.max_rpm(0.80, wheat) < core.max_rpm(0.16, wheat)


# ------------------------------------------------------------------- мощности
def test_shaft_power_reference_value():
    """N = Q·(L·w + H)/367 = 10·(10·1,2 + 0)/367 = 0,327 кВт."""
    res = core.example_result("Зерно, 10 т/ч, L=10 м")
    assert res.shaft_power == pytest.approx(10 * 10 * 1.2 / 367, rel=1e-9)
    assert res.shaft_power == pytest.approx(0.3270, abs=1e-3)


def test_torque_reference_value():
    """M = 9550·N/n = 9550·0,32698/60 = 52,0 Н·м."""
    res = core.example_result("Зерно, 10 т/ч, L=10 м")
    assert res.torque == pytest.approx(9550 * res.shaft_power / 60, rel=1e-9)
    assert res.torque == pytest.approx(52.0, abs=0.1)


def test_motor_required_includes_margin_and_efficiency():
    """N_дв = N·k/η = 0,327·1,15/0,9 = 0,418 кВт."""
    res = core.example_result("Зерно, 10 т/ч, L=10 м")
    assert res.motor_required == pytest.approx(0.32698 * 1.15 / 0.9, rel=1e-3)


def test_motor_is_picked_from_catalog_with_minimum_power():
    res = core.example_result("Зерно, 10 т/ч, L=10 м")
    assert res.motor is not None
    assert res.motor.power >= max(res.motor_required, cat.MIN_MOTOR_POWER) - 1e-9
    assert res.motor.power == pytest.approx(cat.MIN_MOTOR_POWER)


def test_lift_increases_power():
    flat = core.ScrewInput(material_code="cement", capacity=30, length=12, incline_deg=0,
                           diameter=0.32, rpm=50, fill=0.30)
    slope = core.ScrewInput(material_code="cement", capacity=30, length=12, incline_deg=10,
                            diameter=0.32, rpm=50, fill=0.30)
    assert core.calculate(slope).shaft_power > core.calculate(flat).shaft_power
    assert core.calculate(slope).lift_height == pytest.approx(12 * math.sin(math.radians(10)))
