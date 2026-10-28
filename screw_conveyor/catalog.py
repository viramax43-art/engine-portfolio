"""Справочные данные для расчёта шнековых (винтовых) конвейеров.

Источники: Спиваковский А.О., Дьячков В.К. «Транспортирующие машины»;
Зенков Р.Л. и др. «Машины непрерывного транспорта»; каталоги мотор-редукторов.
Значения насыпной плотности, коэффициентов заполнения и сопротивления взяты
из таблиц для соответствующих групп грузов.
"""

from __future__ import annotations

from dataclasses import dataclass

STEEL_DENSITY = 7850.0  # кг/м3, конструкционная сталь


@dataclass(frozen=True)
class BulkMaterial:
    """Транспортируемый сыпучий груз."""

    code: str
    name: str
    density: float          # насыпная плотность, т/м3
    fill: float             # рекомендуемый коэффициент заполнения ψ
    res_coef: float         # коэффициент сопротивления перемещению w
    group: str              # группа груза: лёгкий / средний / тяжёлый
    food: bool = False      # пищевой груз (рекомендуется нержавеющая сталь)
    abrasive: bool = False  # абразивный груз


MATERIALS: dict[str, BulkMaterial] = {
    m.code: m
    for m in (
        BulkMaterial("wheat", "Пшеница (зерно)", 0.75, 0.35, 1.2, "лёгкий", food=True),
        BulkMaterial("corn", "Кукуруза (зерно)", 0.75, 0.35, 1.3, "лёгкий", food=True),
        BulkMaterial("meal", "Комбикорм, гранулы", 0.65, 0.35, 1.5, "лёгкий", food=True),
        BulkMaterial("bran", "Отруби", 0.35, 0.30, 2.0, "лёгкий", food=True),
        BulkMaterial("sugar", "Сахар-песок", 0.80, 0.35, 1.5, "лёгкий", food=True),
        BulkMaterial("sawdust", "Опилки древесные", 0.25, 0.30, 2.2, "лёгкий"),
        BulkMaterial("ash", "Зола уноса", 0.80, 0.30, 2.5, "средний", abrasive=True),
        BulkMaterial("cement", "Цемент", 1.20, 0.30, 3.0, "средний", abrasive=True),
        BulkMaterial("gypsum", "Гипс строительный", 1.15, 0.30, 3.0, "средний", abrasive=True),
        BulkMaterial("sand", "Песок сухой", 1.50, 0.25, 3.5, "тяжёлый", abrasive=True),
        BulkMaterial("clinker", "Клинкер цементный", 1.40, 0.25, 4.0, "тяжёлый", abrasive=True),
        BulkMaterial("gravel", "Щебень мелкий 5…10 мм", 1.45, 0.25, 4.0, "тяжёлый", abrasive=True),
    )
}

#: Свойства групп грузов: A - коэффициент для n_max = A / sqrt(D); S/D - шаг винта.
GROUP_PROPS: dict[str, dict[str, float]] = {
    "лёгкий": {"rpm_const": 60.0, "pitch_ratio": 1.0, "fill_max": 0.45, "support_step": 3.0},
    "средний": {"rpm_const": 45.0, "pitch_ratio": 1.0, "fill_max": 0.40, "support_step": 2.5},
    "тяжёлый": {"rpm_const": 30.0, "pitch_ratio": 0.8, "fill_max": 0.30, "support_step": 2.0},
}

#: Стандартный ряд диаметров винта, м.
STANDARD_DIAMETERS: tuple[float, ...] = (0.16, 0.20, 0.25, 0.32, 0.40, 0.50, 0.63, 0.80)

#: Толщина лопасти винта по диаметру, мм.
BLADE_THICKNESS_MM: dict[float, float] = {
    0.16: 3.0, 0.20: 4.0, 0.25: 4.0, 0.32: 5.0,
    0.40: 5.0, 0.50: 6.0, 0.63: 8.0, 0.80: 8.0,
}

#: Толщина листа желоба по диаметру винта, мм.
TROUGH_THICKNESS_MM: dict[float, float] = {
    0.16: 2.0, 0.20: 3.0, 0.25: 3.0, 0.32: 3.0,
    0.40: 4.0, 0.50: 4.0, 0.63: 5.0, 0.80: 5.0,
}

#: Труба вала (наружный диаметр, толщина стенки), мм.
SHAFT_TUBE_MM: dict[float, tuple[float, float]] = {
    0.16: (57.0, 4.0), 0.20: (57.0, 4.0), 0.25: (76.0, 4.0), 0.32: (89.0, 5.0),
    0.40: (108.0, 5.0), 0.50: (133.0, 6.0), 0.63: (159.0, 6.0), 0.80: (219.0, 8.0),
}

#: Коэффициент снижения производительности от угла наклона β, °.
INCLINE_FACTORS: tuple[tuple[float, float], ...] = (
    (0.0, 1.00), (5.0, 0.90), (10.0, 0.80), (15.0, 0.70), (20.0, 0.65),
)

#: Рекомендуемый ряд частот вращения винта, об/мин.
STANDARD_RPM: tuple[float, ...] = (10, 15, 20, 25, 30, 40, 50, 60, 75, 90, 100, 120, 150, 190)



@dataclass(frozen=True)
class Motor:
    """Электродвигатель серии АИР (4-полюсный, справочные данные)."""

    power: float  # кВт
    model: str
    rpm: float
    mass: float   # кг


MOTORS: tuple[Motor, ...] = (
    Motor(0.55, "АИР71А4", 1390, 12.5),
    Motor(0.75, "АИР71В4", 1390, 13.5),
    Motor(1.10, "АИР80А4", 1420, 15.8),
    Motor(1.50, "АИР80В4", 1410, 17.5),
    Motor(2.20, "АИР90L4", 1420, 25.0),
    Motor(3.00, "АИР100S4", 1410, 33.0),
    Motor(4.00, "АИР100L4", 1430, 39.0),
    Motor(5.50, "АИР112М4", 1445, 52.0),
    Motor(7.50, "АИР132S4", 1455, 68.0),
    Motor(11.0, "АИР132М4", 1455, 82.0),
    Motor(15.0, "АИР160S4", 1460, 128.0),
    Motor(18.5, "АИР160М4", 1470, 145.0),
    Motor(22.0, "АИР180S4", 1470, 165.0),
    Motor(30.0, "АИР180М4", 1470, 195.0),
)

#: Минимальная мощность привода по условию пуска под завалом, кВт.
MIN_MOTOR_POWER = 1.10

#: Марки стали: допускаемое напряжение кручения [τ], МПа; плотность, кг/м3; назначение.
STEEL_GRADES: dict[str, dict[str, object]] = {
    "Ст3сп": {
        "tau_allow": 20.0,
        "density": 7850.0,
        "use": "лёгкие и средние грузы, умеренная абразивность",
    },
    "09Г2С": {
        "tau_allow": 25.0,
        "density": 7850.0,
        "use": "абразивные грузы, повышенный ресурс лопасти",
    },
    "AISI 304": {
        "tau_allow": 20.0,
        "density": 7900.0,
        "use": "пищевые грузы, коррозионно-активные среды",
    },
}


def incline_factor(beta_deg: float) -> float:
    """Коэффициент c снижения производительности при наклоне β, ° (линейная интерполяция)."""
    beta = abs(beta_deg)
    points = INCLINE_FACTORS
    if beta <= points[0][0]:
        return points[0][1]
    if beta >= points[-1][0]:
        return points[-1][1]
    for (b1, c1), (b2, c2) in zip(points, points[1:]):
        if b1 <= beta <= b2:
            frac = (beta - b1) / (b2 - b1)
            return round(c1 + (c2 - c1) * frac, 4)
    return 1.0


def tube_mass_per_meter(outer_mm: float, wall_mm: float, density: float = STEEL_DENSITY) -> float:
    """Погонная масса трубы, кг/м."""
    import math

    d_out = outer_mm / 1000.0
    d_in = (outer_mm - 2 * wall_mm) / 1000.0
    return math.pi / 4.0 * (d_out ** 2 - d_in ** 2) * density


def select_motor(power: float) -> Motor | None:
    """Первый двигатель из каталога с мощностью не ниже требуемой."""
    for motor in MOTORS:
        if motor.power >= power - 1e-9:
            return motor
    return None
