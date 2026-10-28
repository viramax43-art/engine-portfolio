"""Каталог труб, местных сопротивлений, насосов и двигателей.

Данные собраны из типовых серий (трубы по ГОСТ 8732, насосы консольного типа
n = 2900 об/мин, двигатели АИР 2-полюсные) и предназначены для оценочных
расчётов: при выпуске рабочей документации заменяются на данные изготовителя.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

ROUGHNESS = {
    "steel": ("Сталь новые трубы", 0.045),      # мм
    "steel_old": ("Сталь с отложениями", 0.30),
    "galv": ("Оцинкованная сталь", 0.15),
    "pvc": ("ПВХ/ПП", 0.007),
}


@dataclass(frozen=True)
class PipeSize:
    """Труба: условный проход, наружный диаметр и стенка."""

    dn: int
    outer_mm: float
    wall_mm: float

    @property
    def inner_mm(self) -> float:
        return self.outer_mm - 2.0 * self.wall_mm

    @property
    def inner_m(self) -> float:
        return self.inner_mm / 1000.0

    @property
    def area(self) -> float:
        """Площадь проходного сечения, м²."""
        return math.pi * self.inner_m ** 2 / 4.0


PIPES: dict[int, PipeSize] = {
    size.dn: size
    for size in (
        PipeSize(15, 21.3, 2.8), PipeSize(20, 26.8, 2.8), PipeSize(25, 33.5, 3.2),
        PipeSize(32, 42.3, 3.2), PipeSize(40, 48.0, 3.5), PipeSize(50, 57.0, 3.5),
        PipeSize(65, 76.0, 4.0), PipeSize(80, 89.0, 4.0), PipeSize(100, 108.0, 4.0),
        PipeSize(125, 133.0, 4.0), PipeSize(150, 159.0, 4.5), PipeSize(200, 219.0, 6.0),
        PipeSize(250, 273.0, 7.0), PipeSize(300, 325.0, 8.0),
    )
}

# Местные сопротивления: код → (название, коэффициент ζ)
FITTINGS: dict[str, tuple[str, float]] = {
    "inlet": ("Вход в трубу из резервуара", 0.50),
    "outlet": ("Выход в резервуар", 1.00),
    "elbow90": ("Отвод 90°", 0.30),
    "elbow45": ("Отвод 45°", 0.20),
    "valve": ("Задвижка открытая", 0.40),
    "valve_reg": ("Клапан регулирующий", 4.00),
    "check": ("Обратный клапан", 2.50),
    "tee": ("Тройник на проход", 0.60),
    "tee_branch": ("Тройник на ответвление", 1.50),
    "filter": ("Фильтр сетчатый", 5.00),
    "meter": ("Расходомер", 1.00),
    "confuser": ("Конфузор", 0.10),
    "diffuser": ("Диффузор", 0.25),
}


@dataclass(frozen=True)
class Pump:
    """Консольный насос с квадратичной напорной характеристикой.

    H(Q) = H0 - a·Q², где H0 = 1,25·H_opt, a = 0,25·H_opt/Q_opt²;
    КПД η(Q) = η_max·(1 - 0,35·(Q/Q_opt - 1)²), но не ниже 0,35·η_max.
    """

    model: str
    q_opt: float          # м³/ч
    head_opt: float       # м
    efficiency: float     # максимальный КПД
    npsh_r: float         # кавитационный запас при Q_opt, м
    rpm: float
    mass: float           # кг
    price_index: float    # условная стоимость, тыс. руб. (для сравнения вариантов)

    @property
    def head_shutoff(self) -> float:
        return 1.25 * self.head_opt

    def head(self, flow_m3h: float) -> float:
        """Напор насоса при расходе, м."""
        if flow_m3h < 0:
            raise ValueError("Расход не может быть отрицательным")
        a = 0.25 * self.head_opt / self.q_opt ** 2
        return self.head_shutoff - a * flow_m3h ** 2

    def efficiency_at(self, flow_m3h: float) -> float:
        """КПД насоса при расходе."""
        ratio = flow_m3h / self.q_opt
        eta = self.efficiency * (1.0 - 0.35 * (ratio - 1.0) ** 2)
        return max(eta, 0.35 * self.efficiency)

    def npsh_required(self, flow_m3h: float) -> float:
        """Допустимый кавитационный запас при расходе, м."""
        ratio = max(flow_m3h, 0.05) / self.q_opt
        return self.npsh_r * ratio ** 2

    def max_flow(self) -> float:
        """Расход в безнапорном режиме (H = 0), м³/ч."""
        return math.sqrt(self.head_shutoff / (0.25 * self.head_opt / self.q_opt ** 2))


PUMPS: dict[str, Pump] = {
    p.model: p
    for p in (
        Pump("НК 32-125", 12.5, 20.0, 0.55, 2.0, 2900.0, 24.0, 92.0),
        Pump("НК 40-125", 20.0, 20.0, 0.62, 2.2, 2900.0, 31.0, 108.0),
        Pump("НК 50-125", 32.0, 20.0, 0.68, 2.6, 2900.0, 44.0, 131.0),
        Pump("НК 50-160", 32.0, 32.0, 0.68, 2.8, 2900.0, 51.0, 146.0),
        Pump("НК 65-160", 50.0, 32.0, 0.72, 3.0, 2900.0, 67.0, 178.0),
        Pump("НК 80-160", 80.0, 32.0, 0.75, 3.4, 2900.0, 94.0, 232.0),
        Pump("НК 100-200", 160.0, 50.0, 0.78, 4.2, 2900.0, 158.0, 396.0),
    )
}


@dataclass(frozen=True)
class Motor:
    """Электродвигатель привода насоса."""

    model: str
    power: float      # кВт
    rpm: float
    efficiency: float
    mass: float       # кг


MOTORS: tuple[Motor, ...] = (
    Motor("АИР71В2", 0.55, 2900.0, 0.70, 11.0),
    Motor("АИР80А2", 0.75, 2900.0, 0.74, 13.0),
    Motor("АИР80В2", 1.10, 2900.0, 0.76, 15.0),
    Motor("АИР90L2", 1.50, 2900.0, 0.78, 19.0),
    Motor("АИР100S2", 2.20, 2900.0, 0.80, 23.0),
    Motor("АИР100L2", 3.00, 2900.0, 0.82, 29.0),
    Motor("АИР112М2", 4.00, 2900.0, 0.84, 43.0),
    Motor("АИР132S2", 5.50, 2900.0, 0.855, 58.0),
    Motor("АИР132М2", 7.50, 2900.0, 0.87, 73.0),
    Motor("АИР160S2", 11.00, 2900.0, 0.885, 104.0),
    Motor("АИР160М2", 15.00, 2900.0, 0.895, 124.0),
    Motor("АИР180S2", 18.50, 2900.0, 0.90, 145.0),
    Motor("АИР180М2", 22.00, 2900.0, 0.905, 174.0),
    Motor("АИР200М2", 30.00, 2900.0, 0.915, 238.0),
    Motor("АИР200L2", 37.00, 2900.0, 0.92, 288.0),
    Motor("АИР225М2", 45.00, 2900.0, 0.925, 348.0),
    Motor("АИР250S2", 55.00, 2900.0, 0.93, 418.0),
    Motor("АИР280S2", 75.00, 2900.0, 0.935, 517.0),
)

DEFAULT_ENERGY_PRICE = 5.9     # руб./(кВт·ч)
DEFAULT_ATMOSPHERE = 101.3     # кПа
MIN_NPSH_MARGIN = 0.5          # минимальный запас по кавитации, м
VELOCITY_LIMITS = {"suction": (0.5, 1.5), "pressure": (0.8, 2.5)}
WORK_ZONE = (0.5, 1.3)         # рабочая часть характеристики насоса, доли Q_опт
SPECIFIC_LOSS_LIMIT = 400.0    # максимальные удельные потери, Па/м
