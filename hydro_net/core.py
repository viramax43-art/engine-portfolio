"""Расчётное ядро гидравлической сети и подбора насоса.

Методика
--------
1. Скорость и число Рейнольдса по каждому участку: v = Q/A, Re = v·d·ρ/μ.
2. Коэффициент трения λ — Колбрук–Уайт (ламинарная ветвь 64/Re).
3. Потери по длине (Дарси–Вейсбах) и в местных сопротивлениях:
   h = λ·(L/d)·v²/2g + Σζ·v²/2g.
4. Потребный напор сети: H = H_ст + p_изб/(ρg) + Σh.
5. Рабочая точка: пересечение H = H0 - a·Q² с характеристикой сети
   H = H_ст + S·Q², где S = Σh/Q_расч² (аналитическое решение).
6. Мощность: N_гидр = ρgQH, N_вала = N_гидр/η_насоса, N_потр = N_вала/η_двигателя.
7. Кавитация: NPSH_доп ≥ NPSH_треб + запас, где
   NPSH_доп = (p_атм - p_в)/(ρg) - H_вс - Σh_вс.

Ядро не зависит от отчётов и веб-интерфейса.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from common import hydraulics as hyd
from hydro_net import catalog as cat


class CalculationError(ValueError):
    """Ошибка исходных данных с перечнем сообщений."""

    def __init__(self, messages: list[str]) -> None:
        self.messages = messages
        super().__init__("; ".join(messages))


@dataclass
class Section:
    """Участок сети: труба постоянного диаметра с набором местных сопротивлений."""

    name: str = "Участок"
    length_m: float = 10.0
    dn: int = 50
    roughness: str = "steel"
    fittings: dict[str, int] = field(default_factory=dict)
    suction: bool = False

    def copy(self, **changes) -> "Section":
        return replace(self, **changes)


@dataclass
class NetworkInput:
    """Исходные данные гидравлического расчёта."""

    fluid: str = "water"
    temperature: float = 20.0
    flow_m3h: float = 50.0
    static_head: float = 20.0        # геометрическая высота подъёма, м
    back_pressure_bar: float = 0.0   # избыточное давление в конечной точке, бар
    suction_lift: float = 2.0        # высота оси насоса над уровнем жидкости, м
    sections: list[Section] = field(default_factory=lambda: [Section()])
    hours_per_year: float = 4000.0
    energy_price: float = cat.DEFAULT_ENERGY_PRICE
    atmosphere_kpa: float = cat.DEFAULT_ATMOSPHERE
    motor_margin: float = 1.15       # запас по мощности двигателя


@dataclass
class SectionResult:
    """Результат расчёта участка."""

    name: str
    dn: int
    inner_mm: float
    length_m: float
    roughness_mm: float
    velocity: float
    reynolds: float
    lambda_: float
    zeta: float
    loss_friction: float
    loss_local: float
    pressure_drop_kpa: float
    specific_loss: float             # удельные потери на трение R_l, Па/м
    suction: bool

    @property
    def loss(self) -> float:
        """Полные потери участка, м."""
        return self.loss_friction + self.loss_local


@dataclass
class NetworkResult:
    """Гидравлический расчёт сети без привязки к насосу."""

    fluid: hyd.FluidProps
    flow_m3h: float
    static_head: float
    back_pressure_head: float
    suction_lift: float
    sections: list[SectionResult]
    loss_friction: float
    loss_local: float
    suction_loss: float
    npsh_available: float
    suction_pressure_kpa: float
    atmosphere_kpa: float
    hours_per_year: float
    energy_price: float
    motor_margin: float
    checks: list["Check"] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def total_loss(self) -> float:
        """Суммарные потери напора в сети, м."""
        return self.loss_friction + self.loss_local

    @property
    def required_head(self) -> float:
        """Потребный напор сети при расчётном расходе, м."""
        return self.static_head + self.back_pressure_head + self.total_loss

    @property
    def resistance(self) -> float:
        """Удельное сопротивление сети S в H = H_ст + S·Q², м/(м³/ч)²."""
        if self.flow_m3h <= 0:
            return 0.0
        return self.total_loss / self.flow_m3h ** 2

    @property
    def hydraulic_power(self) -> float:
        """Гидравлическая мощность при расчётном расходе, кВт."""
        return (self.fluid.density * hyd.G * (self.flow_m3h / 3600.0)
                * self.required_head / 1000.0)


@dataclass
class Check:
    """Результат проверки условия."""

    name: str
    actual: str
    norm: str
    ok: bool



@dataclass
class PumpResult:
    """Совместная работа насоса и сети (рабочая точка)."""

    network: NetworkResult
    pump: cat.Pump
    flow_op: float
    head_op: float
    efficiency: float
    motor: cat.Motor | None
    power_hydraulic: float
    power_shaft: float
    power_input: float
    load_factor: float
    npsh_required: float
    npsh_margin: float
    energy_kwh: float
    energy_cost: float
    feasible: bool
    note: str
    checks: list[Check] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def flow_reserve_pct(self) -> float:
        """Запас по подаче относительно расчётной, %."""
        if self.network.flow_m3h <= 0:
            return 0.0
        return (self.flow_op / self.network.flow_m3h - 1.0) * 100.0

    @property
    def head_reserve_pct(self) -> float:
        """Запас по напору относительно потребного, %."""
        required = self.network.required_head
        if required <= 0:
            return 0.0
        return (self.head_op / required - 1.0) * 100.0


@dataclass
class Selection:
    """Результат перебора насосов каталога."""

    candidates: list[PumpResult]
    best: PumpResult | None
    best_index: int



# --------------------------------------------------------------------- проверки
def validate(inp: NetworkInput) -> list[str]:
    """Проверка исходных данных; возвращает список сообщений об ошибках."""
    errors: list[str] = []
    try:
        hyd.fluid_properties(inp.fluid, inp.temperature)
    except hyd.FluidError as exc:
        errors.append(str(exc))
    if inp.flow_m3h <= 0:
        errors.append("Расчётный расход должен быть положительным")
    if abs(inp.static_head) > 100:
        errors.append("Геометрическая высота подъёма должна быть в пределах ±100 м")
    if not 0.0 <= inp.back_pressure_bar <= 16.0:
        errors.append("Избыточное давление должно быть в пределах 0…16 бар")
    if not -10.0 <= inp.suction_lift <= 8.0:
        errors.append("Высота всасывания должна быть в пределах −10…8 м")
    if not 1.0 <= inp.motor_margin <= 2.0:
        errors.append("Запас по мощности двигателя должен быть в пределах 1,0…2,0")
    if not 0.0 <= inp.hours_per_year <= 8760.0:
        errors.append("Число часов работы в году должно быть в пределах 0…8760")
    if inp.energy_price < 0:
        errors.append("Цена электроэнергии не может быть отрицательной")
    if not inp.sections:
        errors.append("Не задано ни одного участка сети")
        return errors
    total_length = 0.0
    for index, section in enumerate(inp.sections, start=1):
        prefix = f"Участок {index} ({section.name})"
        if section.dn not in cat.PIPES:
            errors.append(f"{prefix}: условный проход DN{section.dn} отсутствует в сортаменте")
        if section.roughness not in cat.ROUGHNESS:
            errors.append(f"{prefix}: неизвестный материал трубы «{section.roughness}»")
        if section.length_m < 0:
            errors.append(f"{prefix}: длина не может быть отрицательной")
        if section.length_m > 10000:
            errors.append(f"{prefix}: длина более 10 000 м — проверьте исходные данные")
        for code, count in section.fittings.items():
            if code not in cat.FITTINGS:
                errors.append(f"{prefix}: неизвестное местное сопротивление «{code}»")
            if count < 0:
                errors.append(f"{prefix}: количество сопротивлений «{code}» отрицательно")
        total_length += section.length_m
    if total_length <= 0:
        errors.append("Суммарная длина участков должна быть положительной")
    if not any(section.suction for section in inp.sections):
        errors.append("Не отмечен всасывающий участок (нужен для расчёта NPSH)")
    return errors


def section_zeta(section: Section) -> float:
    """Суммарный коэффициент местных сопротивлений участка."""
    return sum(cat.FITTINGS[code][1] * count for code, count in section.fittings.items()
               if code in cat.FITTINGS)


def calculate(inp: NetworkInput) -> NetworkResult:
    """Гидравлический расчёт сети при расчётном расходе."""
    errors = validate(inp)
    if errors:
        raise CalculationError(errors)

    fluid = hyd.fluid_properties(inp.fluid, inp.temperature)
    flow_m3s = inp.flow_m3h / 3600.0
    back_head = inp.back_pressure_bar * 1e5 / (fluid.density * hyd.G)

    results: list[SectionResult] = []
    loss_friction = 0.0
    loss_local = 0.0
    suction_loss = 0.0
    warnings: list[str] = []

    for section in inp.sections:
        if section.length_m <= 0:
            continue
        size = cat.PIPES[section.dn]
        diameter = size.inner_m
        speed = hyd.velocity(flow_m3s, diameter)
        re = hyd.reynolds(fluid, speed, diameter)
        roughness_mm = cat.ROUGHNESS[section.roughness][1]
        rel_rough = roughness_mm / 1000.0 / diameter
        lam = hyd.friction_factor(re, rel_rough)
        h_friction = hyd.friction_head(lam, section.length_m, diameter, speed)
        zeta = section_zeta(section)
        h_local = hyd.local_head(zeta, speed)
        loss = h_friction + h_local
        results.append(SectionResult(
            name=section.name, dn=section.dn, inner_mm=size.inner_mm,
            length_m=section.length_m, roughness_mm=roughness_mm, velocity=speed,
            reynolds=re, lambda_=lam, zeta=zeta, loss_friction=h_friction,
            loss_local=h_local,
            pressure_drop_kpa=loss * fluid.density * hyd.G / 1000.0,
            specific_loss=h_friction * fluid.density * hyd.G / section.length_m,
            suction=section.suction,
        ))
        loss_friction += h_friction
        loss_local += h_local
        if section.suction:
            suction_loss += loss
        if re < 2300.0:
            warnings.append(f"Участок «{section.name}»: ламинарный режим (Re = {re:.0f}), "
                            "коэффициент трения принят по формуле 64/Re.")

    npsh_available = ((inp.atmosphere_kpa * 1000.0 - fluid.vapor_pressure)
                      / (fluid.density * hyd.G) - inp.suction_lift - suction_loss)
    suction_pressure = inp.atmosphere_kpa - (inp.suction_lift + suction_loss) * \
        fluid.density * hyd.G / 1000.0

    if npsh_available < 3.0:
        warnings.append(f"Располагаемый кавитационный запас NPSH = {npsh_available:.2f} м — "
                        "проверьте высоту всасывания и диаметр всасывающей линии.")
    if inp.suction_lift > 6.0:
        warnings.append("Высота всасывания более 6 м: для консольных насосов требуется "
                        "индивидуальная проверка по кавитации.")
    warnings.extend(recommend_diameters(inp))

    return NetworkResult(
        fluid=fluid, flow_m3h=inp.flow_m3h, static_head=inp.static_head,
        back_pressure_head=back_head, suction_lift=inp.suction_lift, sections=results,
        loss_friction=loss_friction, loss_local=loss_local, suction_loss=suction_loss,
        npsh_available=npsh_available, suction_pressure_kpa=suction_pressure,
        atmosphere_kpa=inp.atmosphere_kpa, hours_per_year=inp.hours_per_year,
        energy_price=inp.energy_price, motor_margin=inp.motor_margin,
        checks=_network_checks(results), warnings=warnings,
    )


def _network_checks(results: list[SectionResult]) -> list[Check]:
    """Проверки по скоростям и удельным потерям участков."""
    checks: list[Check] = []
    if not results:
        return checks
    suction = [r for r in results if r.suction]
    pressure = [r for r in results if not r.suction]
    for group, limits, label in (
        (suction, cat.VELOCITY_LIMITS["suction"], "всасывающем"),
        (pressure, cat.VELOCITY_LIMITS["pressure"], "напорном"),
    ):
        if not group:
            continue
        low, high = limits
        speeds = [r.velocity for r in group]
        checks.append(Check(
            f"Скорость на {label} участке",
            f"{min(speeds):.2f}…{max(speeds):.2f} м/с",
            f"{low:.1f}…{high:.1f} м/с",
            min(speeds) >= low - 1e-9 and max(speeds) <= high + 1e-9,
        ))
    worst = max(results, key=lambda r: r.specific_loss)
    checks.append(Check(
        "Удельные потери напора",
        f"{worst.specific_loss:.0f} Па/м ({worst.name})",
        f"≤ {cat.SPECIFIC_LOSS_LIMIT:.0f} Па/м",
        worst.specific_loss <= cat.SPECIFIC_LOSS_LIMIT + 1e-6,
    ))
    return checks


def recommend_diameters(inp: NetworkInput) -> list[str]:
    """Рекомендации по диаметрам участков, не проходящих по допустимой скорости.

    Для участка с завышенной скоростью подбирается ближайший больший условный
    проход, для участка с заниженной скоростью — ближайший меньший.
    """
    messages: list[str] = []
    flow = inp.flow_m3h / 3600.0
    sizes = sorted(cat.PIPES)
    for section in inp.sections:
        low, high = cat.VELOCITY_LIMITS["suction" if section.suction else "pressure"]
        current = hyd.velocity(flow, cat.PIPES[section.dn].inner_m)
        if low - 1e-9 <= current <= high + 1e-9:
            continue
        if current > high:
            fits = [dn for dn in sizes if dn >= section.dn
                    and hyd.velocity(flow, cat.PIPES[dn].inner_m) <= high + 1e-9]
            target = fits[0] if fits else None
        else:
            fits = [dn for dn in sizes if dn <= section.dn
                    and hyd.velocity(flow, cat.PIPES[dn].inner_m) >= low - 1e-9]
            target = fits[-1] if fits else None
        if target is None:
            messages.append(f"Участок «{section.name}»: скорость {current:.2f} м/с вне "
                            f"диапазона {low:.1f}…{high:.1f} м/с — подходящего DN "
                            "в сортаменте нет, измените расход или схему.")
            continue
        new_speed = hyd.velocity(flow, cat.PIPES[target].inner_m)
        messages.append(f"Участок «{section.name}»: при DN{section.dn} скорость "
                        f"{current:.2f} м/с вне диапазона {low:.1f}…{high:.1f} м/с — "
                        f"рекомендуется DN{target} (v = {new_speed:.2f} м/с).")
    return messages


# ------------------------------------------------------------------ подбор насоса
def operating_point(pump: cat.Pump, network: NetworkResult) -> tuple[float, float]:
    """Рабочая точка: пересечение характеристики насоса и характеристики сети.

    H = H0 - a·Q²  и  H = H_ст + S·Q²  ⇒  Q = √((H0 - H_ст)/(a + S)).
    """
    static_total = network.static_head + network.back_pressure_head
    curve_a = 0.25 * pump.head_opt / pump.q_opt ** 2
    resistance = network.resistance
    if pump.head_shutoff <= static_total:
        return 0.0, static_total
    flow = math.sqrt((pump.head_shutoff - static_total) / (curve_a + resistance))
    return flow, static_total + resistance * flow ** 2


def select_motor(power_kw: float) -> cat.Motor | None:
    """Подбор двигателя по мощности (с округлением вверх по каталогу)."""
    for motor in cat.MOTORS:
        if motor.power >= power_kw - 1e-9:
            return motor
    return None


def evaluate(pump: cat.Pump, network: NetworkResult) -> PumpResult:
    """Рассчитать совместную работу конкретного насоса с сетью."""
    flow_op, head_op = operating_point(pump, network)
    efficiency = pump.efficiency_at(flow_op)
    power_hydraulic = (network.fluid.density * hyd.G * (flow_op / 3600.0)
                       * head_op / 1000.0)
    power_shaft = power_hydraulic / efficiency if efficiency > 0 else float("inf")
    motor = select_motor(power_shaft * network.motor_margin)
    motor_eta = motor.efficiency if motor else 0.85
    power_input = power_shaft / motor_eta
    load_factor = power_shaft / motor.power if motor else 0.0
    npsh_required = pump.npsh_required(flow_op)
    npsh_margin = network.npsh_available - npsh_required
    energy = power_input * network.hours_per_year
    cost = energy * network.energy_price

    low_zone = cat.WORK_ZONE[0] * pump.q_opt
    high_zone = cat.WORK_ZONE[1] * pump.q_opt
    pump_checks = [
        Check("Подача в рабочей точке", f"{flow_op:.2f} м³/ч",
              f"≥ {network.flow_m3h:.2f} м³/ч",
              flow_op >= network.flow_m3h - 1e-6),
        Check("Напор в рабочей точке", f"{head_op:.2f} м",
              f"≥ {network.required_head:.2f} м",
              head_op >= network.required_head - 1e-6),
        Check("Рабочая зона насоса", f"{flow_op:.2f} м³/ч",
              f"{low_zone:.1f}…{high_zone:.1f} м³/ч",
              low_zone - 1e-6 <= flow_op <= high_zone + 1e-6),
        Check("Кавитационный запас", f"{npsh_margin:.2f} м",
              f"≥ {cat.MIN_NPSH_MARGIN:.1f} м",
              npsh_margin >= cat.MIN_NPSH_MARGIN - 1e-9),
        Check("Загрузка двигателя", f"{load_factor * 100:.0f} %" if motor else "—",
              "60…100 %", 0.6 <= load_factor <= 1.0 + 1e-9),
    ]
    feasible = all(check.ok for check in pump_checks)
    if flow_op <= 0:
        note = "напор насоса ниже статического напора сети"
    elif flow_op < network.flow_m3h - 1e-6:
        note = "рабочая точка ниже расчётной подачи"
    elif not (low_zone <= flow_op <= high_zone):
        note = "рабочая точка вне рабочей зоны"
    elif npsh_margin < cat.MIN_NPSH_MARGIN:
        note = "недостаточный кавитационный запас"
    elif not feasible:
        note = "двигатель перегружен или недогружен"
    else:
        note = ""

    warnings = list(network.warnings)
    if motor is None:
        warnings.append(f"Мощность {power_shaft * network.motor_margin:.1f} кВт превышает "
                        "каталог двигателей программы — требуется индивидуальный заказ.")
    if load_factor > 1.0:
        warnings.append("Мощность двигателя меньше мощности на валу насоса.")
    if network.flow_m3h > 0 and flow_op > 1.3 * network.flow_m3h:
        warnings.append(f"Рабочая точка смещена вправо от расчётной на "
                        f"{(flow_op / network.flow_m3h - 1.0) * 100:.0f} % — предусмотреть "
                        "регулирование подачи (задвижка, обточка колеса, ЧРП).")

    return PumpResult(
        network=network, pump=pump, flow_op=flow_op, head_op=head_op,
        efficiency=efficiency, motor=motor, power_hydraulic=power_hydraulic,
        power_shaft=power_shaft, power_input=power_input, load_factor=load_factor,
        npsh_required=npsh_required, npsh_margin=npsh_margin, energy_kwh=energy,
        energy_cost=cost, feasible=feasible, note=note,
        checks=list(network.checks) + pump_checks, warnings=warnings,
    )


def _penalty(cand: PumpResult, network: NetworkResult) -> tuple[float, float]:
    """Мера отклонения варианта от требований (для выбора «ближайшего» насоса)."""
    flow_deficit = max(0.0, network.flow_m3h - cand.flow_op) / max(network.flow_m3h, 1e-9)
    npsh_deficit = max(0.0, cat.MIN_NPSH_MARGIN - cand.npsh_margin)
    motor_penalty = 0.0 if 0.6 <= cand.load_factor <= 1.0 else 0.5
    return (flow_deficit + npsh_deficit + motor_penalty, cand.power_input)


def select(inp: NetworkInput, network: NetworkResult | None = None) -> Selection:
    """Перебор каталога насосов: рабочая точка, КПД, мощность, кавитация.

    Если ни один насос не проходит все проверки, возвращается ближайший по
    пенальти вариант (``feasible = False``) — чтобы отчёт можно было выпустить
    с указанием, что именно не выполняется.
    """
    network = network if network is not None else calculate(inp)
    candidates = [evaluate(pump, network) for pump in cat.PUMPS.values()]
    feasible = [(index, cand) for index, cand in enumerate(candidates) if cand.feasible]
    best_index = -1
    if feasible:
        best_index = min(feasible,
                         key=lambda pair: (pair[1].power_input, pair[1].pump.price_index))[0]
        candidates[best_index].note = "рекомендуемый вариант"
    else:
        best_index = min(range(len(candidates)),
                         key=lambda index: _penalty(candidates[index], network))
        closest = candidates[best_index]
        closest.note = "ближайший вариант, требования не выполнены"
        reasons = [check.name for check in closest.checks
                   if not check.ok and check.name != "Подача в рабочей точке"]
        if reasons:
            closest.note += ": " + ", ".join(reasons).lower()
    best = candidates[best_index] if best_index >= 0 else None
    return Selection(candidates=candidates, best=best, best_index=best_index)


# --------------------------------------------------------------------- примеры
EXAMPLES: dict[str, NetworkInput] = {
    "Водоснабжение, Q = 50 м³/ч, подъём 20 м": NetworkInput(
        fluid="water", temperature=20.0, flow_m3h=50.0, static_head=20.0,
        back_pressure_bar=0.0, suction_lift=2.5, hours_per_year=4000.0,
        sections=[
            Section("Всасывающая линия", 6.0, 125, "steel",
                    {"inlet": 1, "valve": 1, "elbow90": 2}, suction=True),
            Section("Напорная линия", 120.0, 100, "steel",
                    {"elbow90": 6, "valve": 1, "check": 1, "outlet": 1}),
        ],
    ),
    "Отопление, Q = 32 м³/ч, 70 °C, H = 14 м": NetworkInput(
        fluid="water", temperature=70.0, flow_m3h=32.0, static_head=14.0,
        back_pressure_bar=0.6, suction_lift=1.5, hours_per_year=5500.0,
        sections=[
            Section("Всасывающая линия", 4.0, 100, "steel",
                    {"inlet": 1, "valve": 1, "filter": 1}, suction=True),
            Section("Магистраль подачи", 180.0, 80, "steel",
                    {"elbow90": 10, "valve_reg": 1, "outlet": 1}),
        ],
    ),
    "Гликолевый контур, Q = 12 м³/ч, 40 °C": NetworkInput(
        fluid="glycol30", temperature=40.0, flow_m3h=12.0, static_head=16.0,
        back_pressure_bar=0.2, suction_lift=1.0, hours_per_year=3000.0,
        sections=[
            Section("Всасывающая линия", 3.0, 65, "galv",
                    {"inlet": 1, "valve": 1, "elbow90": 1}, suction=True),
            Section("Контур потребителя", 60.0, 65, "galv",
                    {"elbow90": 8, "valve": 1, "check": 1, "outlet": 1}),
        ],
    ),
}


def copy_input(inp: NetworkInput) -> NetworkInput:
    """Глубокая копия исходных данных (участки копируются отдельно)."""
    return replace(inp, sections=[section.copy() for section in inp.sections])


def example_input(name: str) -> NetworkInput:
    """Исходные данные примера по названию."""
    if name not in EXAMPLES:
        raise KeyError(f"Нет примера «{name}»")
    return copy_input(EXAMPLES[name])


def example_result(name: str) -> tuple[NetworkInput, Selection]:
    """Исходные данные и результат подбора насоса для примера."""
    inp = example_input(name)
    return inp, select(inp)
