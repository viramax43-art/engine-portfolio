"""Формирование отчётов по гидравлической сети в PDF и Word.

Наполнение общее для обоих форматов (функция :func:`fill_report`), поэтому
состав разделов и числа в PDF и Word совпадают.
"""

from __future__ import annotations

import os
import shutil
import tempfile

from common import plotkit
from common.docx_kit import ReportDocx
from common.fmt import num, pct, pct_signed
from common.pdf_kit import Report
from hydro_net import catalog as cat
from hydro_net import charts
from hydro_net.core import PumpResult, Selection

PROGRAM = "HYDRO-NET 1.0"
TITLE = "Расчёт гидравлической сети и подбор насоса"


def _motor_text(res: PumpResult) -> str:
    if res.motor is None:
        return "не подобран (вне каталога)"
    return (f"{res.motor.model}, {num(res.motor.power, 2, 'кВт')}, "
            f"{num(res.motor.rpm, 0, 'об/мин')}, η = {num(res.motor.efficiency, 3)}")


def fill_report(rep: Report | ReportDocx, res: PumpResult, selection: Selection | None = None,
                images: dict[str, str] | None = None) -> None:
    """Наполнить документ отчёта разделами расчёта."""
    images = images or {}
    net = res.network
    fluid = net.fluid

    # 1. Исходные данные
    rep.h1("Исходные данные")
    rep.p(f"Теплоноситель — {fluid.name.lower()} с температурой {fluid.temperature:.0f} °C. "
          f"Расчётный расход {net.flow_m3h:.2f} м³/ч, геометрическая высота подъёма "
          f"{net.static_head:.2f} м, избыточное давление в конечной точке "
          f"{net.back_pressure_head * fluid.density * 9.81 / 1e5:.2f} бар.")
    rep.params([
        ("Теплоноситель", "—", fluid.name),
        ("Температура", "t", num(fluid.temperature, 0, "°C")),
        ("Плотность", "ρ", num(fluid.density, 1, "кг/м³")),
        ("Вязкость динамическая", "μ", num(fluid.viscosity * 1e3, 3, "мПа·с")),
        ("Давление насыщенных паров", "p_в", num(fluid.vapor_pressure / 1000.0, 2, "кПа")),
        ("Расчётный расход", "Q", num(net.flow_m3h, 2, "м³/ч")),
        ("Геометрический подъём", "H_ст", num(net.static_head, 2, "м")),
        ("Избыточное давление в конце сети", "p_изб",
         num(net.back_pressure_head * fluid.density * 9.81 / 1e5, 2, "бар")),
        ("Высота всасывания", "H_вс", num(net.suction_lift, 2, "м")),
        ("Атмосферное давление", "p_атм", num(net.atmosphere_kpa, 1, "кПа")),
        ("Число часов работы", "T", num(net.hours_per_year, 0, "ч/год")),
        ("Цена электроэнергии", "c", num(net.energy_price, 2, "руб/(кВт·ч)")),
    ], caption="Параметры расчёта")

    # 2. Участки сети
    rep.h1("Гидравлический расчёт участков")
    rows = []
    for index, section in enumerate(net.sections, start=1):
        rows.append([
            f"{index}. {section.name}" + (" (всас.)" if section.suction else ""),
            f"DN{section.dn}",
            num(section.length_m, 1),
            num(section.velocity, 2),
            f"{section.reynolds:.0f}",
            num(section.lambda_, 4),
            num(section.loss_friction, 3),
            num(section.zeta, 2),
            num(section.loss_local, 3),
            num(section.pressure_drop_kpa, 1),
            f"{section.specific_loss:.0f}",
        ])
    rows.append(["Итого по сети", "—", num(sum(s.length_m for s in net.sections), 1), "—",
                 "—", "—", num(net.loss_friction, 3), "—", num(net.loss_local, 3),
                 num(sum(s.pressure_drop_kpa for s in net.sections), 1), "—"])
    rep.table(["Участок", "D, мм", "L, м", "v, м/с", "Re", "λ", "h_дл, м", "Σζ",
               "h_мс, м", "Δp, кПа", "Па/м"], rows,
              widths_mm=[40, 15, 12, 13, 18, 13, 14, 11, 14, 15, 12],
              aligns=["l", "c", "r", "r", "r", "r", "r", "r", "r", "r", "r"],
              caption="Потери напора по участкам (Дарси–Вейсбах + местные сопротивления)",
              total_last=True)
    rep.note("Коэффициент трения λ определён по уравнению Колбрука–Уайта; шероховатость "
             "принята по материалу трубы из каталога программы.")

    # 3. Потребный напор и кавитация
    rep.h1("Потребный напор сети")
    rep.p("Потребный напор складывается из геометрической высоты подъёма, давления "
          "в конечной точке и суммарных потерь напора во всасывающей и напорной линиях.")
    rep.params([
        ("Геометрический подъём", "H_ст", num(net.static_head, 2, "м")),
        ("Напор на преодоление давления", "p_изб/(ρg)", num(net.back_pressure_head, 2, "м")),
        ("Потери по длине", "Σh_дл", num(net.loss_friction, 3, "м")),
        ("Местные потери", "Σh_мс", num(net.loss_local, 3, "м")),
        ("Потери во всасывающей линии", "Σh_вс", num(net.suction_loss, 3, "м")),
        ("Потребный напор", "H_потр", num(net.required_head, 2, "м")),
        ("Гидравлическая мощность при Q_расч", "N_гидр", num(net.hydraulic_power, 2, "кВт")),
        ("Кавитационный запас допустимый", "NPSH_доп", num(net.npsh_available, 2, "м")),
        ("Давление во всасывающем патрубке", "p_вс", num(net.suction_pressure_kpa, 1, "кПа")),
    ], caption="Составляющие потребного напора")
    rep.note(f"NPSH_доп = (p_атм − p_в)/(ρg) − H_вс − Σh_вс при p_атм = "
             f"{num(net.atmosphere_kpa, 1, 'кПа')}. Требуемый запас насоса должен быть "
             f"не менее NPSH_доп − {num(cat.MIN_NPSH_MARGIN, 1, 'м')}.")

    # 4. Выбранный насос и рабочая точка
    rep.h1("Подбор насоса и рабочая точка")
    pump = res.pump
    rep.p(f"Принят консольный насос {pump.model} (n = {pump.rpm:.0f} об/мин, "
          f"оптимум Q = {pump.q_opt:.1f} м³/ч, H = {pump.head_opt:.1f} м). "
          f"Рабочая точка найдена как пересечение характеристики насоса "
          f"H = H₀ − a·Q² с характеристикой сети H = H_ст + S·Q².")
    rep.params([
        ("Марка насоса", "—", pump.model),
        ("Частота вращения", "n", num(pump.rpm, 0, "об/мин")),
        ("Подача в рабочей точке", "Q_р", num(res.flow_op, 2, "м³/ч")),
        ("Напор в рабочей точке", "H_р", num(res.head_op, 2, "м")),
        ("КПД насоса", "η", num(res.efficiency, 3)),
        ("Запас по подаче", "—", pct_signed(res.flow_reserve_pct)),
        ("Запас по напору", "—", pct_signed(res.head_reserve_pct)),
        ("Кавитационный запас требуемый", "NPSH_треб", num(res.npsh_required, 2, "м")),
        ("Кавитационный запас располагаемый", "NPSH_доп", num(net.npsh_available, 2, "м")),
        ("Запас по кавитации", "—", num(res.npsh_margin, 2, "м")),
        ("Масса насоса", "m", num(pump.mass, 1, "кг")),
    ], caption="Параметры рабочей точки")

    # 5. Мощность и двигатель
    rep.h1("Мощность привода и энергопотребление")
    rep.params([
        ("Гидравлическая мощность", "N_гидр", num(res.power_hydraulic, 2, "кВт")),
        ("Мощность на валу насоса", "N_вал", num(res.power_shaft, 2, "кВт")),
        ("Мощность, потребляемая из сети", "N_потр", num(res.power_input, 2, "кВт")),
        ("Электродвигатель", "—", _motor_text(res)),
        ("Запас по мощности двигателя", "k", num(net.motor_margin, 2)),
        ("Загрузка двигателя", "—", pct(res.load_factor * 100.0, 0)),
        ("Годовой расход электроэнергии", "W", num(res.energy_kwh, 0, "кВт·ч/год")),
        ("Годовая стоимость электроэнергии", "C", num(res.energy_cost, 0, "руб/год")),
    ], caption="Энергетические показатели")

    # 6. Проверки
    rep.h1("Проверочные условия")
    rows = [[check.name, check.actual, check.norm,
             "выполняется" if check.ok else "не выполняется"] for check in res.checks]
    rep.table(["Проверка", "Фактически", "Норма", "Результат"], rows,
              widths_mm=[64, 42, 42, 27], aligns=["l", "r", "r", "c"],
              caption="Проверка рабочей точки, кавитации и двигателя")
    if res.warnings:
        rep.h1("Замечания")
        rep.bullet(res.warnings)
    if not res.feasible:
        rep.note("Для рекомендуемого варианта не все проверочные условия выполнены: "
                 "см. таблицу и замечания выше.")

    # 7. Схема и графики
    if images:
        rep.h1("Схема установки и характеристики")
        if "scheme" in images:
            rep.figure(images["scheme"], "Схема насосной установки")
    # 8. Сравнение вариантов
    if selection is not None:
        rep.h1("Сравнение насосов каталога")
        rep.p("Перебраны все насосы каталога: для каждого найдена рабочая точка с "
              "характеристикой сети, рассчитаны КПД, мощность и кавитационный запас. "
              "Рекомендуется вариант с наименьшей потребляемой мощностью среди "
              "удовлетворяющих проверочным условиям.")
        rows = []
        for index, cand in enumerate(selection.candidates):
            rows.append([
                ("→ " if index == selection.best_index else "") + cand.pump.model,
                num(cand.flow_op, 1),
                num(cand.head_op, 1),
                num(cand.efficiency * 100, 0, "%"),
                num(cand.power_input, 2),
                cand.motor.model if cand.motor else "—",
                num(cand.npsh_margin, 2),
                "да" if cand.feasible else "нет",
                cand.note,
            ])
        rep.table(["Насос", "Q, м³/ч", "H, м", "η", "N_потр, кВт", "Двигатель",
                   "NPSH запас, м", "Годен", "Примечание"], rows,
                  widths_mm=[26, 16, 13, 12, 19, 24, 20, 13, 32],
                  aligns=["l", "r", "r", "r", "r", "l", "r", "c", "l"],
                  caption="Результаты перебора насосов")
        if "selection" in images:
            rep.figure(images["selection"], "Сравнение вариантов по мощности и подаче")

    # 9. Выводы
    rep.h1("Выводы")
    rep.bullet([
        f"Потребный напор сети при расходе {num(net.flow_m3h, 2, 'м³/ч')} составляет "
        f"{num(net.required_head, 2, 'м')}, в том числе потери "
        f"{num(net.total_loss, 2, 'м')}.",
        f"Принят насос {pump.model}: рабочая точка {num(res.flow_op, 2, 'м³/ч')} / "
        f"{num(res.head_op, 2, 'м')}, КПД {num(res.efficiency * 100, 0, '%')}, "
        f"запас по подаче {pct_signed(res.flow_reserve_pct)}.",
        f"Электродвигатель: {_motor_text(res)}, загрузка "
        f"{num(res.load_factor * 100, 0, '%')}, потребление из сети "
        f"{num(res.power_input, 2, 'кВт')}.",
        f"Кавитационный запас: NPSH_треб {num(res.npsh_required, 2, 'м')} при "
        f"NPSH_доп {num(net.npsh_available, 2, 'м')} — запас "
        f"{num(res.npsh_margin, 2, 'м')}.",
        f"Годовое энергопотребление {num(res.energy_kwh, 0, 'кВт·ч')} при "
        f"{num(net.hours_per_year, 0, 'ч/год')} работы.",
    ])

    # 10. Методика
    rep.h1("Методика расчёта и допущения")
    rep.bullet([
        "Скорость и число Рейнольдса: v = 4Q/(πd²), Re = v·d·ρ/μ; внутренние диаметры "
        "труб приняты по сортаменту каталога (ГОСТ 8732).",
        "Коэффициент трения: уравнение Колбрука–Уайта; при Re < 2300 — λ = 64/Re, "
        "в переходной зоне 2300 < Re < 4000 — линейное сглаживание.",
        "Потери напора: h = λ·(L/d)·v²/(2g) + Σζ·v²/(2g); коэффициенты местных "
        "сопротивлений — по каталогу программы.",
        "Потребный напор: H = H_ст + p_изб/(ρg) + Σh_дл + Σh_мс.",
        "Рабочая точка: аналитическое решение H₀ − a·Q² = H_ст + S·Q², где "
        "S = Σh/Q_расч²; характеристика насоса аппроксимирована как "
        "H = 1,25·H_опт − 0,25·H_опт·Q²/Q_опт².",
        "КПД насоса: η(Q) = η_max·(1 − 0,35·(Q/Q_опт − 1)²); мощность на валу "
        "N_вал = ρgQH/η, потребляемая N_потр = N_вал/η_дв.",
        "Двигатель подбирается по каталогу с запасом по мощности "
        f"k = {num(net.motor_margin, 2)}; проверяется загрузка 60…100 %.",
        "Кавитация: NPSH_доп = (p_атм − p_в)/(ρg) − H_вс − Σh_вс; условие "
        f"NPSH_доп − NPSH_треб ≥ {num(cat.MIN_NPSH_MARGIN, 1, 'м')}.",
    ])
    rep.note("Расчёт является проектным оценочным: характеристики насосов взяты из "
             "типового каталога консольных насосов, потери в арматуре учтены "
             "осреднёнными коэффициентами. При выпуске рабочей документации "
             "характеристики насоса и двигателя принимаются по данным изготовителя, "
             "а сеть уточняется по аксонометрической схеме.")


def _render_images(res: PumpResult, selection: Selection | None, out_dir: str) -> dict[str, str]:
    """Отрисовать схему и графики во временный каталог."""
    images: dict[str, str] = {}
    figure = charts.system_fig(res)
    images["scheme"] = plotkit.save_png(figure, os.path.join(out_dir, "scheme.png"))
    plotkit.close(figure)
    figure = charts.curves_fig(res)
    images["curves"] = plotkit.save_png(figure, os.path.join(out_dir, "curves.png"))
    plotkit.close(figure)
    if selection is not None:
        figure = charts.selection_fig(selection)
        images["selection"] = plotkit.save_png(figure, os.path.join(out_dir, "selection.png"))
        plotkit.close(figure)
    return images


def _subtitle(res: PumpResult) -> str:
    net = res.network
    return (f"{net.fluid.name}, Q = {net.flow_m3h:.1f} м³/ч, "
            f"H = {net.required_head:.1f} м, {res.pump.model}")


def _doc_no(res: PumpResult) -> str:
    return f"HN-{res.network.flow_m3h:.0f}-{res.network.required_head:.0f}"


def build_pdf(res: PumpResult, path: str, selection: Selection | None = None) -> str:
    """Сформировать PDF-отчёт."""
    tmp_dir = tempfile.mkdtemp(prefix="hydronet_")
    try:
        images = _render_images(res, selection, tmp_dir)
        rep = Report(TITLE, PROGRAM, subtitle=_subtitle(res), doc_no=_doc_no(res))
        fill_report(rep, res, selection, images)
        return rep.save(path)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def build_docx(res: PumpResult, path: str, selection: Selection | None = None) -> str:
    """Сформировать отчёт Word."""
    tmp_dir = tempfile.mkdtemp(prefix="hydronet_")
    try:
        images = _render_images(res, selection, tmp_dir)
        rep = ReportDocx(TITLE, PROGRAM, subtitle=_subtitle(res), doc_no=_doc_no(res))
        fill_report(rep, res, selection, images)
        return rep.save(path)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


