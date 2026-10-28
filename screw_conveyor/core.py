"""Расчётное ядро шнекового (винтового) конвейера.

Методика
--------
1. Производительность (Спиваковский, Дьячков):
   Q = 47 · D² · S · n · ψ · ρ · c,  т/ч
   (D, S - м; n - об/мин; ρ - насыпная плотность, т/м³; ψ - коэффициент
   заполнения; c - коэффициент наклона; 47 = 3600/60 · π/4)
2. Предельная частота вращения: n_max = A / √D, где A зависит от группы груза.
3. Мощность на валу винта: N = Q·(L·w ± H)/367, кВт (H - высота подъёма, м;
   w - коэффициент сопротивления перемещению).
4. Крутящий момент: M = 9550·N/n; проверка вала на кручение.
5. Массы узлов - по геометрии (лист, труба) и по каталогу (двигатель, редуктор).

Ядро не зависит от веб-интерфейса и отчётов, что позволяет покрыть его тестами.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from screw_conveyor import catalog as cat
G = 9.81
E_STEEL = 2.1e11          # модуль упругости стали, Па
SECTION_LENGTH = 3.0      # максимальная длина секции винта, м


class CalculationError(ValueError):
    """Ошибка исходных данных с перечнем сообщений."""

    def __init__(self, messages: list[str]) -> None:
        self.messages = messages
        super().__init__("; ".join(messages))


@dataclass
class ScrewInput:
    """Исходные данные для расчёта конвейера."""

    material_code: str = "wheat"
    capacity: float = 10.0            # требуемая производительность, т/ч
    length: float = 10.0              # длина конвейера по оси, м
    incline_deg: float = 0.0          # угол наклона к горизонту, °
    diameter: float = 0.25            # диаметр винта, м
    rpm: float = 60.0                 # частота вращения винта, об/мин
    fill: float = 0.35                # коэффициент заполнения ψ
    pitch_ratio: float = 1.0          # шаг винта S/D
    steel_grade: str = "Ст3сп"
    drive_efficiency: float = 0.90    # КПД привода (редуктор + муфта)
    power_margin: float = 1.15        # запас мощности при подборе двигателя
    density: float | None = None      # насыпная плотность (переопределение), т/м3
    res_coef: float | None = None     # коэффициент w (переопределение)


@dataclass
class Check:
    """Результат проверки условия."""

    name: str
    actual: str
    norm: str
    ok: bool


@dataclass
class ScrewResult:
    """Результаты расчёта конвейера."""

    # исходное
    material: cat.BulkMaterial
    density: float
    res_coef: float
    capacity_required: float
    length: float
    incline_deg: float
    drive_efficiency: float
    power_margin: float
    # геометрия и режим
    diameter: float
    pitch: float
    pitch_ratio: float
    fill: float
    rpm: float
    rpm_max: float
    incline_factor: float
    axial_speed: float
    lift_height: float
    # производительность
    capacity: float
    reserve_pct: float
    # энергетика
    shaft_power: float
    motor_required: float
    motor: cat.Motor | None
    gear_ratio: float
    gearbox_type: str
    torque: float
    # вал
    shaft_outer_mm: float
    shaft_wall_mm: float
    shaft_d_calc: float          # требуемый диаметр по кручению, м
    shaft_tau: float             # фактическое напряжение кручения, МПа
    n_critical: float            # критическая частота вращения, об/мин
    # конструкция
    sections: int
    supports: int
    blade_thickness_mm: float
    trough_thickness_mm: float
    steel_grade: str
    masses: dict[str, float] = field(default_factory=dict)
    total_mass: float = 0.0
    checks: list[Check] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)



# --------------------------------------------------------------------- проверки
def validate(inp: ScrewInput) -> list[str]:
    """Проверка исходных данных; возвращает список сообщений об ошибках."""
    errors: list[str] = []
    if inp.material_code not in cat.MATERIALS:
        errors.append(f"Неизвестный материал: {inp.material_code}")
    if inp.capacity <= 0:
        errors.append("Производительность должна быть больше нуля")
    if inp.length <= 0:
        errors.append("Длина конвейера должна быть больше нуля")
    if not (0.0 <= abs(inp.incline_deg) <= 30.0):
        errors.append("Угол наклона должен быть в диапазоне 0…30°")
    if inp.diameter <= 0:
        errors.append("Диаметр винта должен быть больше нуля")
    if inp.rpm <= 0:
        errors.append("Частота вращения должна быть больше нуля")
    if not (0.05 <= inp.fill <= 0.60):
        errors.append("Коэффициент заполнения должен быть в диапазоне 0,05…0,60")
    if not (0.5 <= inp.pitch_ratio <= 1.5):
        errors.append("Отношение шага к диаметру должно быть в диапазоне 0,5…1,5")
    if inp.steel_grade not in cat.STEEL_GRADES:
        errors.append(f"Неизвестная марка стали: {inp.steel_grade}")
    if not (0.50 <= inp.drive_efficiency <= 0.99):
        errors.append("КПД привода должен быть в диапазоне 0,50…0,99")
    if inp.power_margin < 1.0:
        errors.append("Запас мощности не может быть меньше 1,0")
    return errors


# ------------------------------------------------------------------- формулы
def capacity_formula(diameter: float, pitch: float, rpm: float, fill: float,
                     density: float, incline_c: float) -> float:
    """Производительность шнека по геометрии, т/ч."""
    return 47.0 * diameter ** 2 * pitch * rpm * fill * density * incline_c


def max_rpm(diameter: float, material: cat.BulkMaterial) -> float:
    """Предельная частота вращения из условия допустимой окружной скорости, об/мин."""
    rpm_const = float(cat.GROUP_PROPS[material.group]["rpm_const"])
    return rpm_const / math.sqrt(diameter)


def required_rpm(inp: ScrewInput, diameter: float, pitch: float, fill: float,
                 density: float, incline_c: float) -> float:
    """Частота вращения под заданную производительность, об/мин."""
    denominator = 47.0 * diameter ** 2 * pitch * fill * density * incline_c
    if denominator <= 0:
        return float("inf")
    return inp.capacity / denominator


def round_up_rpm(value: float) -> float:
    """Ближайшее большее значение из рекомендуемого ряда частот вращения."""
    for rpm in cat.STANDARD_RPM:
        if rpm >= value - 1e-9:
            return float(rpm)
    return float(cat.STANDARD_RPM[-1])




# ------------------------------------------------------------------- расчёт
def calculate(inp: ScrewInput) -> ScrewResult:
    """Полный расчёт конвейера по исходным данным."""
    errors = validate(inp)
    if errors:
        raise CalculationError(errors)

    material = cat.MATERIALS[inp.material_code]
    props = cat.GROUP_PROPS[material.group]
    density = inp.density if inp.density else material.density
    res_coef = inp.res_coef if inp.res_coef else material.res_coef
    beta = abs(inp.incline_deg)
    c_incline = cat.incline_factor(beta)

    diameter = inp.diameter
    pitch = inp.pitch_ratio * diameter
    rpm = inp.rpm
    fill = inp.fill

    capacity = capacity_formula(diameter, pitch, rpm, fill, density, c_incline)
    reserve = (capacity / inp.capacity - 1.0) * 100.0
    n_max = max_rpm(diameter, material)
    axial_speed = pitch * rpm / 60.0            # м/с
    lift = inp.length * math.sin(math.radians(beta))

    # --- энергетика -------------------------------------------------------
    power_shaft = inp.capacity * (inp.length * res_coef + lift) / 367.0
    power_shaft = max(power_shaft, 0.30 * inp.capacity * inp.length * res_coef / 367.0)
    motor_required = power_shaft * inp.power_margin / inp.drive_efficiency
    # привод не выполняют меньше 1,1 кВт: пуск под завалом и возможное заклинивание
    motor = cat.select_motor(max(motor_required, cat.MIN_MOTOR_POWER))
    torque = 9550.0 * power_shaft / rpm            # Н·м на валу винта
    gear_ratio = (motor.rpm / rpm) if motor else float("nan")

    # --- вал --------------------------------------------------------------
    steel = cat.STEEL_GRADES[inp.steel_grade]
    tau_allow = float(steel["tau_allow"])          # МПа
    shaft_od_mm, shaft_wall_mm = cat.SHAFT_TUBE_MM.get(diameter, (57.0, 4.0))
    d_out = shaft_od_mm / 1000.0
    d_in = (shaft_od_mm - 2 * shaft_wall_mm) / 1000.0
    shaft_d_calc = (16.0 * torque / (math.pi * tau_allow * 1e6)) ** (1.0 / 3.0)
    wp = math.pi * (d_out ** 4 - d_in ** 4) / (16.0 * d_out)
    shaft_tau = torque / wp / 1e6                  # МПа

    # --- конструкция ------------------------------------------------------
    blade_t = cat.BLADE_THICKNESS_MM.get(diameter, 4.0)
    trough_t = cat.TROUGH_THICKNESS_MM.get(diameter, 3.0)
    sections = max(1, math.ceil(inp.length / SECTION_LENGTH))
    support_step = float(props["support_step"])
    supports = max(0, math.ceil(inp.length / support_step) - 1)

    rho_steel = float(steel["density"])
    masses, total_mass = _masses(
        diameter=diameter, pitch=pitch, length=inp.length, blade_t=blade_t,
        trough_t=trough_t, shaft_od_mm=shaft_od_mm, shaft_wall_mm=shaft_wall_mm,
        rho_steel=rho_steel, supports=supports, motor=motor, torque=torque,
    )

    # --- критическая частота вращения (промежуточный пролёт вала) ----------
    inertia = math.pi / 64.0 * (d_out ** 4 - d_in ** 4)
    material_per_m = inp.capacity * 1000.0 / 3600.0 / max(axial_speed, 0.01)
    span_mass = (masses["Винт (лопасть)"] + masses["Труба вала"]) / inp.length + material_per_m
    omega = math.pi ** 2 * math.sqrt(E_STEEL * inertia / (span_mass * support_step ** 4))
    n_critical = 30.0 * omega / math.pi

    result = ScrewResult(
        material=material, density=density, res_coef=res_coef,
        capacity_required=inp.capacity, length=inp.length, incline_deg=beta,
        drive_efficiency=inp.drive_efficiency, power_margin=inp.power_margin,
        diameter=diameter, pitch=pitch, pitch_ratio=inp.pitch_ratio, fill=fill,
        rpm=rpm, rpm_max=n_max, incline_factor=c_incline,
        axial_speed=axial_speed, lift_height=lift,
        capacity=capacity, reserve_pct=reserve,
        shaft_power=power_shaft, motor_required=motor_required, motor=motor,
        gear_ratio=gear_ratio, gearbox_type=gearbox_for(gear_ratio), torque=torque,
        shaft_outer_mm=shaft_od_mm, shaft_wall_mm=shaft_wall_mm,
        shaft_d_calc=shaft_d_calc, shaft_tau=shaft_tau, n_critical=n_critical,
        sections=sections, supports=supports,
        blade_thickness_mm=blade_t, trough_thickness_mm=trough_t,
        steel_grade=inp.steel_grade, masses=masses, total_mass=total_mass,
    )
    result.checks, result.warnings = _checks(inp, result, props)
    return result

def gearbox_for(ratio: float) -> str:
    """Тип редуктора по передаточному отношению."""
    if ratio <= 6.3:
        return "Ц1У (одноступенчатый цилиндрический)"
    if ratio <= 40.0:
        return "Ц2У (двухступенчатый цилиндрический)"
    if ratio <= 80.0:
        return "Ч (червячный)"
    return "комбинированный привод (редуктор + открытая передача)"



# ------------------------------------------------------------------ массы узлов
def _masses(*, diameter: float, pitch: float, length: float, blade_t: float,
            trough_t: float, shaft_od_mm: float, shaft_wall_mm: float,
            rho_steel: float, supports: int, motor: cat.Motor | None,
            torque: float) -> tuple[dict[str, float], float]:
    """Оценка массы конвейера по узлам, кг."""
    turns = length / pitch
    d_shaft = shaft_od_mm / 1000.0
    d_mean = (diameter + d_shaft) / 2.0
    alpha = math.atan(pitch / (math.pi * d_mean))
    annulus = math.pi / 4.0 * (diameter ** 2 - d_shaft ** 2)
    area_per_turn = annulus / math.cos(alpha)
    m_blade = area_per_turn * turns * (blade_t / 1000.0) * rho_steel

    m_shaft = cat.tube_mass_per_meter(shaft_od_mm, shaft_wall_mm, rho_steel) * (length + 0.4)

    gap = 0.010 if diameter < 0.40 else 0.015
    radius = diameter / 2.0 + gap
    developed = math.pi * radius + 2.0 * 0.35 * diameter + 0.05
    m_trough = developed * length * (trough_t / 1000.0) * rho_steel * 1.25

    m_supports = 2.0 * 14.0 + supports * 7.0
    m_frame = 25.0
    m_motor = motor.mass if motor else 0.0
    m_gearbox = 1.6 * torque ** 0.6

    masses = {
        "Винт (лопасть)": round(m_blade, 1),
        "Труба вала": round(m_shaft, 1),
        "Желоб с крышками и фланцами": round(m_trough, 1),
        "Опоры и подшипниковые узлы": round(m_supports, 1),
        "Рама привода": round(m_frame, 1),
        "Электродвигатель": round(m_motor, 1),
        "Редуктор": round(m_gearbox, 1),
    }
    total = round(sum(masses.values()) * 1.03, 1)  # 3 % - крепёж и мелкие детали
    return masses, total


# --------------------------------------------------------------------- проверки
def recommended_steel(material: cat.BulkMaterial) -> str:
    """Рекомендуемая марка стали для груза."""
    if material.food:
        return "AISI 304"
    if material.abrasive:
        return "09Г2С"
    return "Ст3сп"


def _checks(inp: ScrewInput, res: ScrewResult,
            props: dict[str, float]) -> tuple[list[Check], list[str]]:
    fill_max = float(props["fill_max"])
    tau_allow = float(cat.STEEL_GRADES[inp.steel_grade]["tau_allow"])
    motor_ok = bool(res.motor and res.motor.power >= res.motor_required - 1e-9)

    checks = [
        Check("Производительность", f"{res.capacity:.2f} т/ч",
              f"≥ {res.capacity_required:.2f} т/ч", res.capacity >= res.capacity_required - 1e-9),
        Check("Частота вращения винта", f"{res.rpm:.0f} об/мин",
              f"≤ {res.rpm_max:.0f} об/мин", res.rpm <= res.rpm_max + 1e-9),
        Check("Осевая скорость груза", f"{res.axial_speed:.2f} м/с", "≤ 0,50 м/с",
              res.axial_speed <= 0.50),
        Check("Коэффициент заполнения", f"{res.fill:.2f}", f"≤ {fill_max:.2f}",
              res.fill <= fill_max + 1e-9),
        Check("Напряжение кручения вала", f"{res.shaft_tau:.1f} МПа",
              f"≤ {tau_allow:.0f} МПа", res.shaft_tau <= tau_allow),
        Check("Критическая частота вращения", f"{res.rpm:.0f} об/мин",
              f"≤ 0,7·{res.n_critical:.0f} об/мин", res.rpm <= 0.7 * res.n_critical),
        Check("Угол наклона", f"{res.incline_deg:.0f}°", "≤ 20°", res.incline_deg <= 20.0 + 1e-9),
        Check("Мощность двигателя",
              f"{res.motor.model} / {res.motor.power:.2f} кВт" if res.motor else "нет в каталоге",
              f"≥ {max(res.motor_required, cat.MIN_MOTOR_POWER):.2f} кВт", motor_ok),
    ]

    warnings: list[str] = []
    if res.reserve_pct < 10.0:
        warnings.append(
            f"Запас по производительности {res.reserve_pct:+.1f} % (< 10 %): "
            "нет резерва на колебания насыпной плотности и влажности груза.")
    if res.reserve_pct > 70.0:
        warnings.append(
            f"Запас по производительности {res.reserve_pct:+.1f} % (> 70 %): "
            "завышены металлоёмкость и установленная мощность привода.")
    if res.rpm > res.rpm_max + 1e-9:
        warnings.append(
            f"Частота вращения {res.rpm:.0f} об/мин выше предельной {res.rpm_max:.0f} об/мин "
            f"для группы «{res.material.group}»: возможен интенсивный износ.")
    if res.incline_deg > 20.0:
        warnings.append("При наклоне более 20° шнековый конвейер не рекомендуется — "
                        "используйте ленточный или скребковый конвейер.")
    if res.motor is None:
        warnings.append("Требуемая мощность выше каталожного ряда (30 кВт) — "
                        "требуется индивидуальный привод.")
    if res.gear_ratio > 80.0:
        warnings.append(f"Передаточное отношение {res.gear_ratio:.0f} слишком велико "
                        "для одного редуктора.")
    rec = recommended_steel(res.material)
    if inp.steel_grade != rec:
        warnings.append(f"Для груза «{res.material.name}» рекомендуется сталь {rec}, "
                        f"выбрана {inp.steel_grade}.")
    if res.axial_speed > 0.5:
        warnings.append("Осевая скорость груза выше 0,5 м/с: растёт износ лопасти и пыление.")
    return checks, warnings



# ---------------------------------------------------------------- подбор типоразмера
@dataclass
class Candidate:
    """Вариант типоразмера конвейера (строка таблицы подбора)."""

    diameter: float
    pitch: float
    rpm: float
    fill: float
    capacity: float
    reserve_pct: float
    shaft_power: float
    motor_model: str
    motor_power: float
    total_mass: float
    feasible: bool
    note: str


@dataclass
class Selection:
    """Результат подбора: варианты и лучший из них."""

    candidates: list[Candidate]
    best: ScrewResult | None
    best_index: int


def select(inp: ScrewInput, target_reserve: float = 0.10) -> Selection:
    """Перебор стандартных диаметров с подбором частоты вращения под производительность."""
    from dataclasses import replace

    errors = validate(inp)
    if errors:
        raise CalculationError(errors)

    material = cat.MATERIALS[inp.material_code]
    props = cat.GROUP_PROPS[material.group]
    density = inp.density or material.density
    c_incline = cat.incline_factor(abs(inp.incline_deg))
    fill_max = float(props["fill_max"])
    fill = min(material.fill, fill_max)
    pitch_ratio = float(props["pitch_ratio"])

    candidates: list[Candidate] = []
    results: list[ScrewResult] = []
    for diameter in cat.STANDARD_DIAMETERS:
        pitch = diameter * pitch_ratio
        n_max = max_rpm(diameter, material)
        n_need = required_rpm(inp, diameter, pitch, fill, density, c_incline)
        within_speed = n_need <= n_max + 1e-9
        rpm = round_up_rpm(n_need) if within_speed else float(int(n_max))
        res = calculate(replace(inp, diameter=diameter, rpm=rpm, fill=fill,
                                pitch_ratio=pitch_ratio))
        feasible = within_speed and res.capacity >= inp.capacity - 1e-9
        if not within_speed:
            note = f"требуется {n_need:.0f} об/мин, допустимо {n_max:.0f}"
        elif not feasible:
            note = "производительность ниже требуемой"
        else:
            note = ""
        candidates.append(Candidate(
            diameter=diameter, pitch=pitch, rpm=rpm, fill=fill,
            capacity=res.capacity, reserve_pct=res.reserve_pct,
            shaft_power=res.shaft_power,
            motor_model=res.motor.model if res.motor else "—",
            motor_power=res.motor.power if res.motor else 0.0,
            total_mass=res.total_mass, feasible=feasible, note=note,
        ))
        results.append(res)

    best_index = -1
    for index, cand in enumerate(candidates):
        if cand.feasible and cand.reserve_pct >= target_reserve * 100.0:
            best_index = index
            break
    if best_index < 0:
        feasible_idx = [i for i, c in enumerate(candidates) if c.feasible]
        best_index = feasible_idx[0] if feasible_idx else -1
    if best_index >= 0:
        candidates[best_index].note = "рекомендуемый вариант"

    best = results[best_index] if best_index >= 0 else None
    return Selection(candidates=candidates, best=best, best_index=best_index)


# ------------------------------------------------------------------- примеры
EXAMPLES: dict[str, ScrewInput] = {
    "Зерно, 10 т/ч, L=10 м": ScrewInput(
        material_code="wheat", capacity=10.0, length=10.0, incline_deg=0.0,
        diameter=0.25, rpm=60, fill=0.35, pitch_ratio=1.0, steel_grade="AISI 304"),
    "Цемент, 30 т/ч, L=12 м, 10°": ScrewInput(
        material_code="cement", capacity=30.0, length=12.0, incline_deg=10.0,
        diameter=0.32, rpm=50, fill=0.30, pitch_ratio=1.0, steel_grade="09Г2С"),
    "Песок, 60 т/ч, L=18 м": ScrewInput(
        material_code="sand", capacity=60.0, length=18.0, incline_deg=0.0,
        diameter=0.40, rpm=60, fill=0.25, pitch_ratio=0.8, steel_grade="09Г2С"),
}


def example_result(key: str | None = None) -> ScrewResult:
    """Готовый расчёт на демонстрационном примере (для быстрой проверки)."""
    inp = EXAMPLES[key] if key else next(iter(EXAMPLES.values()))
    return calculate(inp)
