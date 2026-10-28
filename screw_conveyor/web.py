"""Веб-интерфейс расчёта шнекового конвейера (Flask).

Запуск:  python -m screw_conveyor.web   →  http://127.0.0.1:5001
Страница содержит форму исходных данных, результаты расчёта со схемой и
графиками, а также выгрузку отчётов в PDF и Word.
"""

from __future__ import annotations

import os
import sys
from collections import OrderedDict

from flask import Flask, Response, abort, request, send_file

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import plotkit, web_kit as wk
from common.fmt import num, pct_signed
from screw_conveyor import catalog as cat
from screw_conveyor import charts
from screw_conveyor.core import (EXAMPLES, CalculationError, ScrewInput, calculate,
                                 select)
from screw_conveyor.report import PROGRAM, TITLE, build_docx, build_pdf

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out")
CACHE: OrderedDict[str, tuple[ScrewInput, bool]] = OrderedDict()
CACHE_LIMIT = 32

app = Flask(__name__)


def _defaults() -> dict[str, str]:
    inp = list(EXAMPLES.values())[0]
    return {
        "material": inp.material_code,
        "capacity": f"{inp.capacity:g}",
        "length": f"{inp.length:g}",
        "incline": f"{inp.incline_deg:g}",
        "diameter": f"{inp.diameter * 1000:g}",
        "rpm": f"{inp.rpm:g}",
        "fill": f"{inp.fill:g}",
        "pitch": f"{inp.pitch_ratio:g}",
        "steel": inp.steel_grade,
    }


def _options(values, current: str, labels=None) -> str:
    """<option> для списка значений."""
    parts = []
    for value in values:
        key = str(value)
        label = labels.get(value, key) if labels else key
        selected = " selected" if key == current else ""
        parts.append(f'<option value="{wk.esc(key)}"{selected}>{wk.esc(label)}</option>')
    return "".join(parts)


def _form(values: dict[str, str], select_mode: bool) -> str:
    material_labels = {code: f"{m.name} ({m.group})" for code, m in cat.MATERIALS.items()}
    diameter_labels = {d * 1000: f"Ø{d * 1000:.0f} мм" for d in cat.STANDARD_DIAMETERS}
    selected = " checked" if select_mode else ""
    examples = "".join(
        f'<a href="/?example={index}">{wk.esc(name)}</a>'
        for index, name in enumerate(EXAMPLES)
    )
    return f"""
<form method="post" action="/">
  <div class="grp"><label>Транспортируемый груз</label>
    <select name="material">{_options(sorted(cat.MATERIALS), values['material'], material_labels)}</select></div>
  <div class="grp"><label>Производительность, т/ч</label>
    <input name="capacity" type="number" step="0.1" min="0.1" value="{wk.esc(values['capacity'])}"></div>
  <div class="row2">
    <div class="grp"><label>Длина L, м</label>
      <input name="length" type="number" step="0.1" min="0.5" value="{wk.esc(values['length'])}"></div>
    <div class="grp"><label>Угол β, °</label>
      <input name="incline" type="number" step="1" min="0" max="45" value="{wk.esc(values['incline'])}"></div>
  </div>
  <div class="row2">
    <div class="grp"><label>Диаметр винта D</label>
      <select name="diameter">{_options([d * 1000 for d in cat.STANDARD_DIAMETERS], values['diameter'], diameter_labels)}</select></div>
    <div class="grp"><label>Частота n, об/мин</label>
      <input name="rpm" type="number" step="1" min="1" max="300" value="{wk.esc(values['rpm'])}"></div>
  </div>
  <div class="row2">
    <div class="grp"><label>Заполнение ψ</label>
      <input name="fill" type="number" step="0.05" min="0.05" max="0.6" value="{wk.esc(values['fill'])}"></div>
    <div class="grp"><label>Шаг S/D</label>
      <input name="pitch" type="number" step="0.1" min="0.5" max="1.5" value="{wk.esc(values['pitch'])}"></div>
  </div>
  <div class="grp"><label>Марка стали</label>
    <select name="steel">{_options(sorted(cat.STEEL_GRADES), values['steel'])}</select></div>
  <div class="grp check"><input type="checkbox" id="sel" name="autoselect" value="1"{selected}>
    <label for="sel" style="margin:0">Подобрать типоразмер по стандартному ряду</label></div>
  <button type="submit">Рассчитать</button>
</form>
<div class="note">Примеры: {examples}</div>
"""



def _result_html(res, selection, token: str) -> str:
    """Блок результатов: показатели, таблицы, проверки, графики, выгрузка."""
    motor = res.motor
    head = wk.card(
        "Результат расчёта",
        wk.kpis([
            ("Производительность", f"{res.capacity:.2f}", "т/ч"),
            ("Запас", pct_signed(res.reserve_pct), ""),
            ("Мощность на валу", f"{res.shaft_power:.2f}", "кВт"),
            ("Двигатель", motor.model if motor else "—",
             f"{motor.power:.2f} кВт" if motor else ""),
            ("Момент", f"{res.torque:.0f}", "Н·м"),
            ("Масса", f"{res.total_mass:.0f}", "кг"),
        ]) + f"""
<div class="btns">
  <a href="/download/{token}/pdf">Скачать PDF-отчёт</a>
  <a href="/download/{token}/docx">Скачать отчёт Word</a>
</div>""",
        hint=f"{res.material.name}, Ø{res.diameter * 1000:.0f} мм",
    )

    geometry = wk.card("Геометрия и режим работы", wk.table(
        ["Параметр", "Обозн.", "Значение"],
        [
            ["Диаметр винта", "D", num(res.diameter * 1000, 0, "мм")],
            ["Шаг винта", "S", num(res.pitch * 1000, 0, "мм")],
            ["Частота вращения", "n", num(res.rpm, 0, "об/мин")],
            ["Предельная частота", "n_max", num(res.rpm_max, 0, "об/мин")],
            ["Коэффициент заполнения", "ψ", num(res.fill, 2)],
            ["Коэффициент наклона", "c", num(res.incline_factor, 2)],
            ["Осевая скорость груза", "v", num(res.axial_speed, 2, "м/с")],
            ["Высота подъёма", "H", num(res.lift_height, 2, "м")],
            ["Число витков", "z", num(res.length / res.pitch, 0)],
            ["Число секций / опор", "—", f"{res.sections} / {res.supports}"],
        ], aligns=["l", "c", "r"], caption="Принятая геометрия винта и режим"))

    drive = wk.card("Привод и вал", wk.table(
        ["Параметр", "Обозн.", "Значение"],
        [
            ["Мощность на валу винта", "N", num(res.shaft_power, 3, "кВт")],
            ["Расчётная мощность двигателя", "N_дв", num(res.motor_required, 3, "кВт")],
            ["Двигатель", "—", f"{motor.model}, {num(motor.power, 2, 'кВт')}, "
                                f"{num(motor.rpm, 0, 'об/мин')}" if motor else "—"],
            ["Передаточное отношение", "i", num(res.gear_ratio, 1)],
            ["Тип редуктора", "—", res.gearbox_type],
            ["Крутящий момент", "M", num(res.torque, 1, "Н·м")],
            ["Труба вала", "—", f"Ø{num(res.shaft_outer_mm, 0, 'мм')} × "
                                 f"{num(res.shaft_wall_mm, 0, 'мм')}"],
            ["Напряжение кручения", "τ", num(res.shaft_tau, 2, "МПа")],
            ["Критическая частота", "n_кр", num(res.n_critical, 0, "об/мин")],
            ["Толщина лопасти / желоба", "δ", f"{res.blade_thickness_mm:.0f} / "
                                              f"{res.trough_thickness_mm:.0f} мм"],
        ], aligns=["l", "c", "r"], caption="Энергетика, редуктор и вал"))

    checks_rows = [[c.name, c.actual, c.norm, wk.badge(c.ok)] for c in res.checks]
    checks = wk.card("Проверки условий работоспособности", wk.table(
        ["Условие", "Фактически", "Норма", "Результат"], checks_rows,
        aligns=["l", "r", "r", "c"]))

    mass_rows = [[name, num(value, 1, "кг")] for name, value in res.masses.items()]
    mass_rows.append(["Итого (крепёж +3 %)", num(res.total_mass, 1, "кг")])
    mass = wk.card("Масса конвейера", wk.table(
        ["Узел", "Масса"], mass_rows, aligns=["l", "r"], total_last=True,
        caption="Оценка по геометрии и каталогу, точность ±15 %"))

    selection_html = ""
    if selection is not None:
        rows = []
        for cand in selection.candidates:
            best = selection.best is not None and cand.diameter == selection.best.diameter
            rows.append(["★ " + f"Ø{cand.diameter * 1000:.0f}" if best
                         else f"Ø{cand.diameter * 1000:.0f}",
                         num(cand.rpm, 0), num(cand.capacity, 2), pct_signed(cand.reserve_pct),
                         cand.motor_model, num(cand.total_mass, 0), cand.note])
        figure = charts.selection_fig(selection)
        img = wk.figure(wk.data_uri(plotkit.to_png_bytes(figure)),
                        "Металлоёмкость и мощность по типоразмерам")
        plotkit.close(figure)
        selection_html = wk.card(
            "Подбор типоразмера",
            wk.table(["D, мм", "n, об/мин", "Q, т/ч", "Запас", "Двигатель", "Масса, кг",
                      "Примечание"], rows, aligns=["l", "r", "r", "r", "l", "r", "l"]) + img,
            hint="перебор стандартного ряда диаметров")

    scheme = charts.schematic_fig(res)
    scheme_html = wk.card("Схема конвейера", wk.figure(
        wk.data_uri(plotkit.to_png_bytes(scheme)),
        f"Продольная схема: Ø{res.diameter * 1000:.0f} мм, L = {res.length:.2f} м, "
        f"β = {res.incline_deg:.0f}°"))
    plotkit.close(scheme)

    curve = charts.capacity_fig(res)
    curve_html = wk.card("Производительность от частоты вращения", wk.figure(
        wk.data_uri(plotkit.to_png_bytes(curve)),
        "Рабочая точка и предельная частота вращения"))
    plotkit.close(curve)

    warnings_html = ""
    if res.warnings:
        warnings_html = wk.card("Замечания", "".join(wk.warning(w) for w in res.warnings))

    return "".join([head, warnings_html, scheme_html, curve_html, geometry, drive,
                    checks, mass, selection_html])




_FIELD_LABELS = {
    "capacity": "Производительность, т/ч",
    "length": "Длина, м",
    "incline": "Угол наклона, °",
    "diameter": "Диаметр винта, мм",
    "rpm": "Частота вращения, об/мин",
    "fill": "Коэффициент заполнения ψ",
    "pitch": "Шаг S/D",
}


def _form_values(form) -> dict[str, str]:
    """Значения формы для повторного вывода (с подстановкой по умолчанию)."""
    values = _defaults()
    for key in values:
        raw = (form.get(key) or "").strip()
        if raw:
            values[key] = raw
    return values


def _parse_form(form) -> tuple[ScrewInput, list[str]]:
    """Прочитать форму, вернуть исходные данные и список ошибок ввода."""
    values = _form_values(form)
    errors: list[str] = []
    numbers: dict[str, float] = {}
    for key, label in _FIELD_LABELS.items():
        raw = values[key].replace(",", ".")
        try:
            numbers[key] = float(raw)
        except ValueError:
            errors.append(f"«{label}»: ожидается число, получено «{values[key]}».")
            numbers[key] = 0.0
    material = values["material"] if values["material"] in cat.MATERIALS else "wheat"
    steel = values["steel"] if values["steel"] in cat.STEEL_GRADES else "Ст3сп"
    inp = ScrewInput(
        material_code=material, capacity=numbers["capacity"], length=numbers["length"],
        incline_deg=numbers["incline"], diameter=numbers["diameter"] / 1000.0,
        rpm=numbers["rpm"], fill=numbers["fill"], pitch_ratio=numbers["pitch"],
        steel_grade=steel,
    )
    return inp, errors


def _render(values: dict[str, str], right: str, select_mode: bool,
            error_html: str = "") -> Response:
    """Собрать страницу из формы и правой (результатной) колонки."""
    form_card = wk.card("Исходные данные", error_html + _form(values, select_mode),
                        hint="СНиП/справочник грузов")
    body = form_card + right
    html = wk.page(TITLE, "Подбор типоразмера, привода и конструктивных параметров",
                   body, PROGRAM)
    return Response(html, mimetype="text/html; charset=utf-8")


def _values_from_input(inp: ScrewInput) -> dict[str, str]:
    return {
        "material": inp.material_code,
        "capacity": f"{inp.capacity:g}",
        "length": f"{inp.length:g}",
        "incline": f"{inp.incline_deg:g}",
        "diameter": f"{inp.diameter * 1000:g}",
        "rpm": f"{inp.rpm:g}",
        "fill": f"{inp.fill:g}",
        "pitch": f"{inp.pitch_ratio:g}",
        "steel": inp.steel_grade,
    }


_EMPTY = wk.card(
    "Результат",
    '<p class="muted">Задайте груз и требуемую производительность, затем нажмите '
    "«Рассчитать». Программа проверит режим работы, подберёт двигатель и редуктор, "
    "оценит массу и сформирует отчёты PDF и Word.</p>"
    + wk.bullets([
        "производительность по геометрии винта Q = 47·D²·S·n·ψ·ρ·c;",
        "предельная частота вращения n_max = A/√D по группе груза;",
        "мощность привода N = Q·(L·w + H)/367 и подбор двигателя по каталогу;",
        "проверка вала на кручение и по критической частоте вращения.",
    ]))


@app.get("/")
def index() -> Response:
    """Форма с примером исходных данных."""
    values = _defaults()
    select_mode = False
    example = request.args.get("example")
    if example is not None:
        try:
            inp = list(EXAMPLES.values())[int(example)]
            values = _values_from_input(inp)
            select_mode = True
        except (ValueError, IndexError):
            pass
    return _render(values, _EMPTY, select_mode)


@app.post("/")
def calculate_view() -> Response:
    """Расчёт по данным формы."""
    inp, errors = _parse_form(request.form)
    select_mode = request.form.get("autoselect") == "1"
    values = _form_values(request.form)
    if errors:
        return _render(values, _EMPTY, select_mode, wk.errors(errors))
    try:
        selection = select(inp) if select_mode else None
        res = selection.best if selection is not None and selection.best is not None else None
        if res is None:
            res = calculate(inp)
    except CalculationError as exc:
        return _render(values, _EMPTY, select_mode, wk.errors(exc.messages))
    token = _remember(inp if selection is None else _selected_input(inp, res), select_mode)
    return _render(values, _result_html(res, selection, token), select_mode)


def _selected_input(inp: ScrewInput, res) -> ScrewInput:
    """Исходные данные с параметрами, принятыми при подборе (для отчёта)."""
    from dataclasses import replace

    return replace(inp, diameter=res.diameter, rpm=res.rpm, fill=res.fill,
                   pitch_ratio=res.pitch_ratio)


@app.get("/download/<token>/<fmt>")
def download(token: str, fmt: str):
    """Выгрузка отчёта PDF или Word по ранее выполненному расчёту."""
    if token not in CACHE or fmt not in ("pdf", "docx"):
        abort(404)
    inp, select_mode = CACHE[token]
    selection = select(inp) if select_mode else None
    res = selection.best if selection is not None and selection.best is not None else None
    if res is None:
        res = calculate(inp)
    os.makedirs(OUT_DIR, exist_ok=True)
    stem = f"screw_{res.diameter * 1000:.0f}mm_{res.capacity:.0f}tph"
    if fmt == "pdf":
        path = build_pdf(res, os.path.join(OUT_DIR, stem + ".pdf"), selection)
        return send_file(path, as_attachment=True, download_name=stem + ".pdf",
                         mimetype="application/pdf")
    path = build_docx(res, os.path.join(OUT_DIR, stem + ".docx"), selection)
    return send_file(path, as_attachment=True, download_name=stem + ".docx",
                     mimetype="application/vnd.openxmlformats-officedocument."
                              "wordprocessingml.document")


def main() -> None:
    """Локальный запуск: python -m screw_conveyor.web."""
    port = int(os.environ.get("SCREW_PORT", "5001"))
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()

def _remember(inp: ScrewInput, select_mode: bool) -> str:
    """Запомнить исходные данные для выгрузки отчёта и вернуть ключ."""
    import secrets

    token = secrets.token_urlsafe(8)
    CACHE[token] = (inp, select_mode)
    while len(CACHE) > CACHE_LIMIT:
        CACHE.popitem(last=False)
    return token
