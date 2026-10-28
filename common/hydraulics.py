"""Общая гидравлика: свойства теплоносителя, число Рейнольдса, коэффициент трения.

Модуль используется второй программой (расчёт гидросети и подбор насоса).
Он намеренно не содержит ничего специфичного для сети или насосов — только
физику, которая одинакова в любой гидравлической задаче.

Обозначения: ρ — плотность, кг/м³; μ — динамическая вязкость, Па·с;
p_в — давление насыщенных паров, Па.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

G = 9.81  # ускорение свободного падения, м/с²


class FluidError(ValueError):
    """Недопустимая жидкость или температура."""


@dataclass(frozen=True)
class FluidProps:
    """Свойства жидкости при заданной температуре."""

    code: str
    name: str
    temperature: float      # °C
    density: float          # кг/м³
    viscosity: float        # Па·с
    vapor_pressure: float   # Па

    @property
    def kinematic(self) -> float:
        """Кинематическая вязкость, м²/с."""
        return self.viscosity / self.density


# Справочные свойства воды на линии насыщения: t, °C → (ρ, μ·10³, p_в, Па)
_WATER_TABLE = (
    (0.0, 999.8, 1.792, 611.0),
    (10.0, 999.7, 1.307, 1228.0),
    (20.0, 998.2, 1.002, 2339.0),
    (30.0, 995.7, 0.798, 4246.0),
    (40.0, 992.2, 0.653, 7381.0),
    (50.0, 988.1, 0.547, 12349.0),
    (60.0, 983.2, 0.467, 19946.0),
    (70.0, 977.8, 0.404, 31190.0),
    (80.0, 971.8, 0.355, 47390.0),
    (90.0, 965.3, 0.315, 70110.0),
    (100.0, 958.4, 0.282, 101325.0),
)

FLUIDS = {
    "water": "Вода",
    "glycol30": "Водный раствор этиленгликоля 30 %",
}

# Поправки раствора гликоля 30 % к таблице воды (осреднённые по диапазону 5…90 °C)
_GLYCOL_FACTORS = {"density": 1.043, "viscosity": 2.15, "vapor": 0.80}


def _interpolate(t: float, column: int) -> float:
    """Линейная интерполяция свойства воды по таблице."""
    rows = _WATER_TABLE
    if t <= rows[0][0]:
        return rows[0][column]
    if t >= rows[-1][0]:
        return rows[-1][column]
    for (t1, *c1), (t2, *c2) in zip(rows, rows[1:]):
        if t1 <= t <= t2:
            share = (t - t1) / (t2 - t1)
            return c1[column - 1] + share * (c2[column - 1] - c1[column - 1])
    return rows[-1][column]


def fluid_properties(code: str = "water", temperature: float = 20.0) -> FluidProps:
    """Свойства жидкости при температуре (5…95 °C)."""
    if code not in FLUIDS:
        raise FluidError(f"Неизвестная жидкость: {code}")
    if not 0.0 <= temperature <= 100.0:
        raise FluidError("Температура должна быть в диапазоне 0…100 °C")
    density = _interpolate(temperature, 1)
    viscosity = _interpolate(temperature, 2) * 1e-3
    vapor = _interpolate(temperature, 3)
    if code == "glycol30":
        density *= _GLYCOL_FACTORS["density"]
        viscosity *= _GLYCOL_FACTORS["viscosity"]
        vapor *= _GLYCOL_FACTORS["vapor"]
    return FluidProps(code=code, name=FLUIDS[code], temperature=temperature,
                      density=density, viscosity=viscosity, vapor_pressure=vapor)


def velocity(flow_m3s: float, diameter_m: float) -> float:
    """Средняя скорость в круглой трубе, м/с."""
    if diameter_m <= 0:
        raise FluidError("Диаметр должен быть положительным")
    area = math.pi * diameter_m ** 2 / 4.0
    return flow_m3s / area


def reynolds(props: FluidProps, speed: float, diameter_m: float) -> float:
    """Число Рейнольдса Re = v·d·ρ/μ."""
    return speed * diameter_m * props.density / props.viscosity


def friction_factor(re: float, rel_roughness: float) -> float:
    """Коэффициент гидравлического трения λ.

    Ламинарный режим (Re < 2300) — λ = 64/Re; переходный и турбулентный —
    решение уравнения Колбрука–Уайта итерацией по простой итерации, начальное
    приближение — формула Суами–Джейна.
    """
    if re <= 0:
        raise FluidError("Число Рейнольдса должно быть положительным")
    if rel_roughness < 0:
        raise FluidError("Относительная шероховатость не может быть отрицательной")
    if re < 2300.0:
        return 64.0 / re
    if re < 4000.0:  # переходная зона: сшивка ламинарной и турбулентной ветвей
        lam_lam = 64.0 / re
        lam_turb = _colebrook(re, rel_roughness)
        share = (re - 2300.0) / 1700.0
        return lam_lam + share * (lam_turb - lam_lam)
    return _colebrook(re, rel_roughness)


def _colebrook(re: float, rel_roughness: float) -> float:
    """Итерационное решение уравнения Колбрука–Уайта."""
    arg = rel_roughness / 3.7 + 5.74 / re ** 0.9
    lam = 0.25 / (math.log10(arg) ** 2)  # Суами–Джейн как начальное приближение
    for _ in range(60):
        new = 1.0 / (-2.0 * math.log10(rel_roughness / 3.7 + 2.51 / (re * math.sqrt(lam)))) ** 2
        if abs(new - lam) < 1e-12:
            lam = new
            break
        lam = new
    return lam


def friction_head(lam: float, length_m: float, diameter_m: float, speed: float) -> float:
    """Потери напора по длине (Дарси–Вейсбах), м."""
    return lam * (length_m / diameter_m) * speed ** 2 / (2.0 * G)


def local_head(zeta_sum: float, speed: float) -> float:
    """Потери напора в местных сопротивлениях, м."""
    return zeta_sum * speed ** 2 / (2.0 * G)


def velocity_head(speed: float) -> float:
    """Скоростной напор v²/2g, м."""
    return speed ** 2 / (2.0 * G)
