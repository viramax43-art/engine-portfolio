"""Тесты ядра и графиков шнекового конвейера (часть 2: вал, конструкция, подбор)."""

from __future__ import annotations

import math

import pytest

from screw_conveyor import catalog as cat
from screw_conveyor import core


# ------------------------------------------------------------------------- вал
def test_shaft_torsion_stress_reference_value():
    """τ = M/Wp для трубы 76×4: Wp = π(D⁴-d⁴)/(16D) = 3,10e-5 м³, τ ≈ 1,68 МПа."""
    res = core.example_result("Зерно, 10 т/ч, L=10 м")
    d_out, d_in = 0.076, 0.068
    wp = math.pi * (d_out ** 4 - d_in ** 4) / (16 * d_out)
    assert res.shaft_tau == pytest.approx(res.torque / wp / 1e6, rel=1e-9)
    assert res.shaft_tau == pytest.approx(1.68, abs=0.01)


def test_shaft_required_diameter_formula():
    """d = куб.корень(16M/(π[τ])) для M = 52 Н·м, [τ] = 20 МПа ⇒ 23,7 мм."""
    res = core.example_result("Зерно, 10 т/ч, L=10 м")
    expected = (16 * res.torque / (math.pi * 20e6)) ** (1 / 3)
    assert res.shaft_d_calc == pytest.approx(expected, rel=1e-9)
    assert res.shaft_d_calc * 1000 == pytest.approx(23.7, abs=0.1)
    assert res.shaft_outer_mm - 2 * res.shaft_wall_mm >= res.shaft_d_calc * 1000 - 1e-6


def test_stronger_steel_allows_smaller_shaft():
    inp = core.ScrewInput(material_code="sand", capacity=40, length=12, diameter=0.40,
                          rpm=50, fill=0.25, steel_grade="Ст3сп")
    st3 = core.calculate(inp)
    inp2 = core.ScrewInput(material_code="sand", capacity=40, length=12, diameter=0.40,
                           rpm=50, fill=0.25, steel_grade="09Г2С")
    g2 = core.calculate(inp2)
    assert g2.shaft_d_calc < st3.shaft_d_calc


# ----------------------------------------------------------------- конструкция
def test_sections_and_supports():
    res = core.example_result("Песок, 60 т/ч, L=18 м")
    assert res.sections == 6                      # 18 / 3 м
    assert res.supports == math.ceil(18 / 2.0) - 1  # шаг опор 2 м для тяжёлого груза


def test_masses_are_consistent():
    res = core.example_result("Цемент, 30 т/ч, L=12 м, 10°")
    assert res.total_mass > 0
    assert res.total_mass == pytest.approx(sum(res.masses.values()) * 1.03, abs=0.1)
    assert all(value >= 0 for value in res.masses.values())
    # лопасть не может весить больше трубы вала на порядок
    assert res.masses["Винт (лопасть)"] < res.masses["Желоб с крышками и фланцами"] * 3


def test_blade_mass_reference_value():
    """Лопасть: площадь витка (кольцо 250/76, растянутое на шаг) × число витков × δ × ρ."""
    res = core.example_result("Зерно, 10 т/ч, L=10 м")
    rho = float(cat.STEEL_GRADES[res.steel_grade]["density"])
    d_mean = (0.25 + 0.076) / 2
    alpha = math.atan(0.25 / (math.pi * d_mean))
    annulus = math.pi / 4 * (0.25 ** 2 - 0.076 ** 2)
    expected = annulus / math.cos(alpha) * (10 / 0.25) * 0.004 * rho
    assert res.masses["Винт (лопасть)"] == pytest.approx(round(expected, 1), abs=0.11)


# --------------------------------------------------------------------- проверки
def test_checks_pass_for_reference_case():
    res = core.example_result("Зерно, 10 т/ч, L=10 м")
    failed = [c.name for c in res.checks if not c.ok]
    assert failed == [], f"не прошли проверки: {failed}"
    assert res.warnings == []


def test_low_capacity_produces_reserve_warning():
    res = core.calculate(core.ScrewInput(material_code="wheat", capacity=10, length=10,
                                         diameter=0.50, rpm=90, fill=0.35))
    assert res.reserve_pct > 70
    assert any("запас" in w.lower() for w in res.warnings)


def test_validation_collects_all_errors():
    bad = core.ScrewInput(material_code="unknown", capacity=-1, length=0, incline_deg=45,
                          diameter=0, rpm=0, fill=1.5, pitch_ratio=5, steel_grade="Х")
    errors = core.validate(bad)
    assert len(errors) >= 8
    with pytest.raises(core.CalculationError):
        core.calculate(bad)


def test_density_override_changes_capacity():
    base = core.calculate(core.ScrewInput(material_code="wheat", capacity=10, length=10,
                                          diameter=0.25, rpm=60, fill=0.35))
    dense = core.calculate(core.ScrewInput(material_code="wheat", capacity=10, length=10,
                                           diameter=0.25, rpm=60, fill=0.35, density=0.90))
    assert dense.capacity == pytest.approx(base.capacity * 0.90 / 0.75, rel=1e-6)
