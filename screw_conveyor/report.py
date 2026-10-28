"""Формирование отчётов по расчёту конвейера в PDF и Word.

Оба отчёта наполняются из одной функции :func:`fill_report`, поэтому состав
разделов и числа в PDF и Word всегда совпадают.
"""

from __future__ import annotations

import os
import shutil
import tempfile

from common import plotkit
from common.docx_kit import ReportDocx
from common.fmt import num, pct_signed
from common.pdf_kit import Report
from screw_conveyor import catalog as cat
from screw_conveyor import charts
from screw_conveyor.core import ScrewResult, Selection, recommended_steel

PROGRAM = "SCREW-CALC 1.0"
TITLE = "Расчёт шнекового конвейера"


def fill_report(rep: Report | ReportDocx, res: ScrewResult,
                selection: Selection | None = None,
                images: dict[str, str] | None = None) -> None:
    """Наполняет документ отчёта (PDF или Word) разделами по расчёту."""
    images = images or {}
    material = res.material
    steel = cat.STEEL_GRADES[res.steel_grade]

    # 1. Исходные данные
    rep.h1("Исходные данные")
    rep.p(f"Транспортируемый груз: {material.name} (группа «{material.group}»). "
          f"Требуемая производительность {num(res.capacity_required, 1, 'т/ч')}, "
          f"длина конвейера {num(res.length, 2, 'м')}, угол наклона "
          f"{num(res.incline_deg, 0, '°')}.")
    rep.params([
        ("Транспортируемый груз", "—", material.name),
        ("Насыпная плотность", "ρ", num(res.density, 2, "т/м³")),
        ("Коэффициент сопротивления", "w", num(res.res_coef, 2)),
        ("Производительность требуемая", "Q", num(res.capacity_required, 1, "т/ч")),
        ("Длина конвейера", "L", num(res.length, 2, "м")),
        ("Угол наклона", "β", num(res.incline_deg, 0, "°")),
        ("Диаметр винта", "D", num(res.diameter * 1000, 0, "мм")),
        ("Шаг винта", "S", num(res.pitch * 1000, 0, "мм")),
        ("Отношение шага к диаметру", "S/D", num(res.pitch_ratio, 2)),
        ("Частота вращения", "n", num(res.rpm, 0, "об/мин")),
        ("Коэффициент заполнения", "ψ", num(res.fill, 2)),
        ("Марка стали", "—", res.steel_grade),
        ("КПД привода", "η", num(res.drive_efficiency, 2)),
        ("Запас мощности", "k", num(res.power_margin, 2)),
    ], caption="Параметры расчёта")

    # 2. Результаты
    rep.h1("Результаты расчёта")
    rep.p("Производительность определена по геометрии винта и частоте вращения; "
          "запас — относительно требуемой производительности.")
    rep.params([
        ("Производительность расчётная", "Q", num(res.capacity, 2, "т/ч")),
        ("Запас по производительности", "δQ", pct_signed(res.reserve_pct)),
        ("Предельная частота вращения", "n_max", num(res.rpm_max, 0, "об/мин")),
        ("Осевая скорость груза", "v", num(res.axial_speed, 2, "м/с")),
        ("Коэффициент наклона", "c", num(res.incline_factor, 2)),
        ("Высота подъёма", "H", num(res.lift_height, 2, "м")),
        ("Число витков", "z", num(res.length / res.pitch, 0)),
        ("Число секций винта", "—", num(res.sections, 0)),
    ], caption="Производительность и режим работы")


    # 3. Привод
    rep.h1("Привод")
    rep.params([
        ("Мощность на валу винта", "N", num(res.shaft_power, 3, "кВт")),
        ("Расчётная мощность двигателя", "N_дв", num(res.motor_required, 3, "кВт")),
        ("Принятый двигатель", "—",
         f"{res.motor.model}, {num(res.motor.power, 2, 'кВт')}, "
         f"{num(res.motor.rpm, 0, 'об/мин')}" if res.motor else "—"),
        ("Масса двигателя", "—", num(res.motor.mass, 1, "кг") if res.motor else "—"),
        ("Передаточное отношение", "i", num(res.gear_ratio, 1)),
        ("Тип редуктора", "—", res.gearbox_type),
        ("Крутящий момент на валу", "M", num(res.torque, 1, "Н·м")),
        ("Минимальная мощность привода", "—", num(cat.MIN_MOTOR_POWER, 2, "кВт")),
    ], caption="Энергетика и комплектация привода")
    rep.note("Минимальная мощность привода 1,1 кВт принята по условию пуска винта под "
             "завалом: при расчётной мощности ниже этого значения двигатель выбирается "
             "из условия пускового момента.")

    # 4. Вал и конструкция
    rep.h1("Вал и конструктивные параметры")
    rep.params([
        ("Труба вала", "—",
         f"Ø{num(res.shaft_outer_mm, 0, 'мм')} × {num(res.shaft_wall_mm, 0, 'мм')}"),
        ("Крутящий момент", "M", num(res.torque, 1, "Н·м")),
        ("Напряжение кручения", "τ", num(res.shaft_tau, 2, "МПа")),
        ("Допускаемое напряжение", "[τ]", num(float(steel["tau_allow"]), 0, "МПа")),
        ("Требуемый диаметр вала", "d", num(res.shaft_d_calc * 1000, 1, "мм")),
        ("Критическая частота вращения", "n_кр", num(res.n_critical, 0, "об/мин")),
        ("Толщина лопасти", "δ", num(res.blade_thickness_mm, 1, "мм")),
        ("Толщина листа желоба", "δ_ж", num(res.trough_thickness_mm, 1, "мм")),
        ("Промежуточные опоры вала", "—", num(res.supports, 0, "шт")),
        ("Число секций винта", "—", num(res.sections, 0, "шт")),
    ], caption="Вал, лопасть и корпус")

    # 5. Материалы
    rep.h1("Материалы")
    rep.table(
        ["Узел", "Материал", "Обоснование"],
        [
            ["Винт (лопасть)", res.steel_grade, str(steel["use"])],
            ["Труба вала", res.steel_grade, "равнопрочность с лопастью, свариваемость"],
            ["Желоб и крышки",
             f"Ст3сп, δ = {num(res.trough_thickness_mm, 1, 'мм')}",
             "воспринимает абразивный износ, заменяется по мере износа"],
            ["Опоры вала", "Ст45 + подшипниковые узлы",
             "концевые и промежуточные подвесные опоры"],
        ],
        widths_mm=[40, 45, 90], aligns=["l", "l", "l"],
        caption="Материалы основных узлов")
    rec = recommended_steel(material)
    if rec != res.steel_grade:
        rep.note(f"Для груза «{material.name}» рекомендуется сталь {rec}.")

    # 6. Масса
    rep.h1("Масса конвейера")
    rows = [[name, num(value, 1, "кг")] for name, value in res.masses.items()]
    rows.append(["Итого (с крепежом +3 %)", num(res.total_mass, 1, "кг")])
    rep.table(["Узел", "Масса"], rows, widths_mm=[125, 50], aligns=["l", "r"],
              caption="Масса по узлам (оценка по геометрии и каталогу, ±15 %)",
              total_last=True)


    # 7. Проверки
    rep.h1("Проверки условий работоспособности")
    rep.table(["Условие", "Фактически", "Норма", "Результат"],
              [[c.name, c.actual, c.norm, "да" if c.ok else "НЕТ"] for c in res.checks],
              widths_mm=[62, 44, 40, 29], aligns=["l", "r", "r", "c"],
              caption="Проверки работоспособности")
    if res.warnings:
        rep.h2("Замечания")
        rep.bullet(res.warnings)
    else:
        rep.p("Замечаний нет: параметры находятся в рекомендуемых пределах.")

    # 8. Схема и графики
    if images:
        rep.h1("Схема и графики")
        if images.get("scheme"):
            rep.figure(images["scheme"],
                       f"Продольная схема конвейера Ø{num(res.diameter * 1000, 0, 'мм')}, "
                       f"L = {num(res.length, 2, 'м')}")
        if images.get("capacity"):
            rep.figure(images["capacity"],
                       "Производительность в зависимости от частоты вращения")
        if images.get("selection") and selection:
            rep.figure(images["selection"], "Сравнение типоразмеров по металлоёмкости")

    # 9. Выводы
    rep.h1("Выводы")
    motor_text = (f"двигатель {res.motor.model} мощностью {num(res.motor.power, 2, 'кВт')} "
                  f"({num(res.motor.rpm, 0, 'об/мин')})" if res.motor
                  else "двигатель подбирается индивидуально")
    rep.bullet([
        f"Принят конвейер с винтом Ø{res.diameter * 1000:.0f} мм, шаг "
        f"{res.pitch * 1000:.0f} мм, частота вращения {res.rpm:.0f} об/мин.",
        f"Расчётная производительность {res.capacity:.2f} т/ч при требуемой "
        f"{res.capacity_required:.2f} т/ч — запас {res.reserve_pct:+.1f} %.",
        f"Привод: {motor_text}, редуктор {res.gearbox_type.split(' (')[0]}, "
        f"i = {res.gear_ratio:.1f}.",
        f"Масса конвейера {res.total_mass:.1f} кг, материал винта {res.steel_grade}, "
        f"толщина лопасти {res.blade_thickness_mm:.0f} мм.",
    ])
    if selection and selection.best is not None:
        rep.p("Рекомендуемый типоразмер получен перебором стандартного ряда диаметров: "
              "выбран наименьший диаметр, обеспечивающий требуемую производительность "
              "с запасом не менее 10 % при частоте вращения не выше предельной.")

    # 10. Методика
    rep.h1("Методика расчёта и допущения")
    rep.bullet([
        "Производительность: Q = 47·D²·S·n·ψ·ρ·c, где 47 = 3600/60·π/4; "
        "c — коэффициент снижения производительности от наклона.",
        "Предельная частота вращения: n_max = A/√D (A = 60 — лёгкие, 45 — средние, "
        "30 — тяжёлые абразивные грузы).",
        "Мощность на валу: N = Q·(L·w + H)/367, где w — коэффициент сопротивления "
        "перемещению, H — высота подъёма.",
        f"Мощность двигателя: N_дв = N·k/η (k = {res.power_margin:.2f}, "
        f"η = {res.drive_efficiency:.2f} в данном расчёте).",
        "Крутящий момент M = 9550·N/n; вал проверяется на кручение, дополнительно "
        "контролируется критическая частота вращения пролёта.",
        "Массы узлов — геометрический расчёт (лист, труба) с оценкой по каталогу "
        "(двигатель, редуктор); точность ±15 %, уточняется по КД.",
    ])
    rep.note("Расчёт выполнен по методике Спиваковского–Дьячкова для винтовых "
             "конвейеров общего назначения. Справочные данные по грузам и приводам "
             "приведены в каталоге программы и подлежат замене на данные изготовителя "
             "при выпуске рабочей документации.")


def _render_images(res: ScrewResult, selection: Selection | None,
                   out_dir: str) -> dict[str, str]:
    """Отрисовать схему и графики во временный каталог."""
    images: dict[str, str] = {}
    figure = charts.schematic_fig(res)
    images["scheme"] = plotkit.save_png(figure, os.path.join(out_dir, "scheme.png"))
    plotkit.close(figure)
    figure = charts.capacity_fig(res)
    images["capacity"] = plotkit.save_png(figure, os.path.join(out_dir, "capacity.png"))
    plotkit.close(figure)
    if selection is not None:
        figure = charts.selection_fig(selection)
        images["selection"] = plotkit.save_png(figure, os.path.join(out_dir, "selection.png"))
        plotkit.close(figure)
    return images


def _subtitle(res: ScrewResult) -> str:
    return (f"{res.material.name}, Q = {res.capacity_required:.1f} т/ч, "
            f"L = {res.length:.2f} м, β = {res.incline_deg:.0f}°")


def build_pdf(res: ScrewResult, path: str, selection: Selection | None = None) -> str:
    """Сформировать PDF-отчёт."""
    tmp_dir = tempfile.mkdtemp(prefix="screwcalc_")
    try:
        images = _render_images(res, selection, tmp_dir)
        rep = Report(TITLE, PROGRAM, subtitle=_subtitle(res),
                     doc_no=f"SC-{res.diameter * 1000:.0f}-{res.capacity:.0f}")
        fill_report(rep, res, selection, images)
        return rep.save(path)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def build_docx(res: ScrewResult, path: str, selection: Selection | None = None) -> str:
    """Сформировать отчёт Word."""
    tmp_dir = tempfile.mkdtemp(prefix="screwcalc_")
    try:
        images = _render_images(res, selection, tmp_dir)
        rep = ReportDocx(TITLE, PROGRAM, subtitle=_subtitle(res),
                         doc_no=f"SC-{res.diameter * 1000:.0f}-{res.capacity:.0f}")
        fill_report(rep, res, selection, images)
        return rep.save(path)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
