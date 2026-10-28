"""Веб-интерфейс расчёта гидравлической сети и подбора насоса (Flask).

Запуск:  python -m hydro_net.web   →  http://127.0.0.1:5002
Страница содержит форму исходных данных, результаты расчёта со схемой и
графиками, а также выгрузку отчётов в PDF и Word.
"""

from __future__ import annotations

import os
import secrets
import sys
from collections import OrderedDict

from flask import Flask, Response, abort, request, send_file

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import plotkit, web_kit as wk
from common.fmt import num, pct, pct_signed
from hydro_net import catalog as cat
from hydro_net import charts
from hydro_net.core import (EXAMPLES, CalculationError, NetworkInput, Section,
                            calculate, evaluate, select)
from hydro_net.report import PROGRAM, TITLE, build_docx, build_pdf

OUT_DIR = wk.report_dir(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                     "out"))
PREFIX = os.environ.get("HYDRO_PREFIX", "").rstrip("/")
CACHE: OrderedDict[str, tuple[NetworkInput, str]] = OrderedDict()
CACHE_LIMIT = 32

app = Flask(__name__)


def _section(inp: NetworkInput, suction: bool) -> Section:
    """Участок исходных данных (всасывающий или напорный)."""
    for section in inp.sections:
        if section.suction == suction:
            return section
    return inp.sections[0]


def _values_from_input(inp: NetworkInput) -> dict[str, str]:
    """Значения формы по исходным данным расчёта."""
    suction, pressure = _section(inp, True), _section(inp, False)
    return {
        "fluid": inp.fluid,
        "temperature": f"{inp.temperature:g}",
        "flow": f"{inp.flow_m3h:g}",
        "static": f"{inp.static_head:g}",
        "back": f"{inp.back_pressure_bar:g}",
        "lift": f"{inp.suction_lift:g}",
        "hours": f"{inp.hours_per_year:g}",
        "price": f"{inp.energy_price:g}",
        "motor_margin": f"{inp.motor_margin:g}",
        "suction_dn": str(suction.dn),
        "suction_len": f"{suction.length_m:g}",
        "suction_elbows": str(suction.fittings.get("elbow90", 0)),
        "dn": str(pressure.dn),
        "length": f"{pressure.length_m:g}",
        "elbows": str(pressure.fittings.get("elbow90", 0)),
        "valves": str(pressure.fittings.get("valve", 0)),
        "checks": str(pressure.fittings.get("check", 0)),
        "filters": str(pressure.fittings.get("filter", 0)),
        "reg": str(pressure.fittings.get("valve_reg", 0)),
        "roughness": pressure.roughness,
        "pump": "auto",
    }


def _defaults() -> dict[str, str]:
    return _values_from_input(list(EXAMPLES.values())[0])


def _options(values, current: str, labels=None) -> str:
    """<option> для списка значений."""
    parts = []
    for value in values:
        key = str(value)
        label = labels.get(value, key) if labels else key
        selected = " selected" if key == current else ""
        parts.append(f'<option value="{wk.esc(key)}"{selected}>{wk.esc(label)}</option>')
    return "".join(parts)


def _form(values: dict[str, str], pump: str) -> str:
    fluid_labels = {"water": "Вода", "glycol30": "Раствор этиленгликоля 30 %"}
    rough_labels = {code: name for code, (name, _) in cat.ROUGHNESS.items()}
    dn_values = sorted(cat.PIPES)
    dn_labels = {dn: f"DN{dn}" for dn in dn_values}
    pump_labels = {"auto": "Автоподбор по каталогу"}
    pump_labels.update({model: f"{model} (Q_опт {p.q_opt:g} м³/ч)"
                        for model, p in cat.PUMPS.items()})
    pump_values = ["auto"] + sorted(cat.PUMPS)
    examples = "".join(
        f'<a href="{PREFIX}/?example={index}">{wk.esc(name)}</a>'
        for index, name in enumerate(EXAMPLES)
    )

    def field(name: str, label: str, step: str, extra: str = "") -> str:
        return (f'<div class="grp"><label>{wk.esc(label)}</label>'
                f'<input name="{name}" type="number" step="{step}" {extra} '
                f'value="{wk.esc(values[name])}"></div>')

    return f"""
<form method="post" action="{PREFIX}/">
  <div class="grp"><label>Теплоноситель</label>
    <select name="fluid">{_options(sorted(fluid_labels), values['fluid'], fluid_labels)}</select></div>
  <div class="row2">
    {field("temperature", "Температура, °C", "any", 'min="-20" max="150"')}
    {field("flow", "Расход, м³/ч", "any", 'min="0.1"')}
  </div>
  <div class="row2">
    {field("static", "Подъём H_ст, м", "any", 'min="-50" max="100"')}
    {field("back", "Давление, бар", "any", 'min="0" max="16"')}
  </div>
  <div class="row2">
    {field("lift", "Высота всасывания, м", "any", 'min="-10" max="8"')}
    {field("motor_margin", "Запас двигателя", "any", 'min="1" max="2"')}
  </div>
  <div class="row2">
    <div class="grp"><label>Всасывание: DN</label>
      <select name="suction_dn">{_options(dn_values, values['suction_dn'], dn_labels)}</select></div>
    {field("suction_len", "Длина всасывания, м", "any", 'min="0.5"')}
  </div>
  <div class="row2">
    {field("suction_elbows", "Отводы 90° (всас.)", "1", 'min="0" max="20"')}
    <div class="grp"><label>Материал труб</label>
      <select name="roughness">{_options(sorted(cat.ROUGHNESS), values['roughness'], rough_labels)}</select></div>
  </div>
  <div class="row2">
    <div class="grp"><label>Напорная линия: DN</label>
      <select name="dn">{_options(dn_values, values['dn'], dn_labels)}</select></div>
    {field("length", "Длина линии, м", "any", 'min="0.5"')}
  </div>
  <div class="row2">
    {field("elbows", "Отводы 90°", "1", 'min="0" max="50"')}
    {field("valves", "Задвижки", "1", 'min="0" max="20"')}
  </div>
  <div class="row2">
    {field("checks", "Обратные клапаны", "1", 'min="0" max="10"')}
    {field("reg", "Регул. клапаны", "1", 'min="0" max="10"')}
  </div>
  <div class="row2">
    {field("filters", "Фильтры", "1", 'min="0" max="10"')}
    {field("hours", "Часов/год", "50", 'min="0" max="8760"')}
  </div>
  {field("price", "Цена эл., руб/(кВт·ч)", "any", 'min="0"')}
  <div class="grp"><label>Насос</label>
    <select name="pump">{_options(pump_values, pump, pump_labels)}</select></div>
  <button type="submit">Рассчитать</button>
</form>
<div class="note">Примеры: {examples}</div>
"""


_FIELD_LABELS = {
    "temperature": "Температура, °C",
    "flow": "Расход, м³/ч",
    "static": "Подъём H_ст, м",
    "back": "Избыточное давление, бар",
    "lift": "Высота всасывания, м",
    "motor_margin": "Запас по мощности двигателя",
    "suction_dn": "DN всасывающей линии",
    "suction_len": "Длина всасывающей линии, м",
    "suction_elbows": "Отводы 90° на всасывании",
    "dn": "DN напорной линии",
    "length": "Длина напорной линии, м",
    "elbows": "Отводы 90°",
    "valves": "Задвижки",
    "checks": "Обратные клапаны",
    "reg": "Регулирующие клапаны",
    "filters": "Фильтры",
    "hours": "Часов работы в году",
    "price": "Цена электроэнергии",
}


def _form_values(form) -> dict[str, str]:
    """Значения формы для повторного вывода (с подстановкой по умолчанию)."""
    values = _defaults()
    for key in values:
        raw = (form.get(key) or "").strip()
        if raw:
            values[key] = raw
    return values


def _parse_form(form) -> tuple[NetworkInput, str, list[str]]:
    """Прочитать форму: исходные данные, выбранный насос и ошибки ввода."""
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

    fluid = values["fluid"] if values["fluid"] in ("water", "glycol30") else "water"
    roughness = values["roughness"] if values["roughness"] in cat.ROUGHNESS else "steel"
    suction_dn = int(round(numbers["suction_dn"]))
    pressure_dn = int(round(numbers["dn"]))
    if suction_dn not in cat.PIPES:
        errors.append(f"DN{suction_dn} всасывающей линии отсутствует в сортаменте.")
    if pressure_dn not in cat.PIPES:
        errors.append(f"DN{pressure_dn} напорной линии отсутствует в сортаменте.")

    inp = NetworkInput(
        fluid=fluid, temperature=numbers["temperature"], flow_m3h=numbers["flow"],
        static_head=numbers["static"], back_pressure_bar=numbers["back"],
        suction_lift=numbers["lift"], hours_per_year=numbers["hours"],
        energy_price=numbers["price"], motor_margin=numbers["motor_margin"],
        sections=[
            Section("Всасывающая линия", numbers["suction_len"], suction_dn, roughness,
                    {"inlet": 1, "valve": 1,
                     "elbow90": int(round(numbers["suction_elbows"]))}, suction=True),
            Section("Напорная линия", numbers["length"], pressure_dn, roughness,
                    {"elbow90": int(round(numbers["elbows"])),
                     "valve": int(round(numbers["valves"])),
                     "check": int(round(numbers["checks"])),
                     "valve_reg": int(round(numbers["reg"])),
                     "filter": int(round(numbers["filters"])),
                     "outlet": 1}),
        ],
    )
    pump = values["pump"] if values["pump"] in cat.PUMPS else "auto"
    return inp, pump, errors


def _params(rows) -> str:
    """Таблица «параметр — обозначение — значение»."""
    return wk.table(["Параметр", "Обозн.", "Значение"], rows, aligns=["l", "c", "r"])


def _kpi_card(res, token: str) -> str:
    """Верхняя карточка с главными числами и кнопками выгрузки."""
    motor = res.motor
    return wk.card(
        "Результат расчёта",
        wk.kpis([
            ("Подача в рабочей точке", f"{res.flow_op:.2f}", "м³/ч"),
            ("Напор", f"{res.head_op:.2f}", "м"),
            ("КПД насоса", pct(res.efficiency * 100, 0), ""),
            ("Насос", res.pump.model, f"{res.pump.rpm:.0f} об/мин"),
            ("Мощность из сети", f"{res.power_input:.2f}", "кВт"),
            ("Двигатель", motor.model if motor else "—",
             f"{motor.power:.2f} кВт" if motor else ""),
        ]) + f"""
<div class="btns">
  <a href="{PREFIX}/download/{token}/pdf">Скачать PDF-отчёт</a>
  <a href="{PREFIX}/download/{token}/docx">Скачать отчёт Word</a>
</div>""",
        hint=f"{res.network.fluid.name}, Q = {res.network.flow_m3h:.1f} м³/ч",
    )


def _network_card(res) -> str:
    """Таблица гидравлического расчёта по участкам."""
    net = res.network
    rows = []
    for index, section in enumerate(net.sections, start=1):
        rows.append([
            f"{index}. {section.name}",
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
    rows.append([
        "Итого по сети", "—",
        num(sum(s.length_m for s in net.sections), 1), "—", "—", "—",
        num(net.loss_friction, 3), "—", num(net.loss_local, 3),
        num(sum(s.pressure_drop_kpa for s in net.sections), 1), "—",
    ])
    return wk.card("Гидравлический расчёт участков", wk.table(
        ["Участок", "DN", "L, м", "v, м/с", "Re", "λ", "h_дл, м", "Σζ", "h_мс, м",
         "Δp, кПа", "R, Па/м"], rows,
        aligns=["l", "c", "r", "r", "r", "r", "r", "r", "r", "r", "r"], total_last=True,
        caption="Потери по длине (Дарси–Вейсбах) и в местных сопротивлениях"),
        hint=f"{net.fluid.name}, {net.fluid.temperature:.0f} °C")


def _head_card(res) -> str:
    """Потребный напор и кавитационные условия."""
    net = res.network
    return wk.card("Потребный напор и кавитация", _params([
        ["Геометрический подъём", "H_ст", num(net.static_head, 2, "м")],
        ["Напор от избыточного давления", "p/(ρg)", num(net.back_pressure_head, 2, "м")],
        ["Потери по длине", "Σh_дл", num(net.loss_friction, 3, "м")],
        ["Местные потери", "Σh_мс", num(net.loss_local, 3, "м")],
        ["Потери во всасывающей линии", "Σh_вс", num(net.suction_loss, 3, "м")],
        ["Потребный напор", "H_потр", num(net.required_head, 2, "м")],
        ["Сопротивление сети", "S", num(net.resistance, 5, "м/(м³/ч)²")],
        ["Кавитационный запас располагаемый", "NPSH_расп", num(net.npsh_available, 2, "м")],
        ["Давление во всасывании", "p_вс", num(net.suction_pressure_kpa, 1, "кПа")],
    ]))


def _drive_card(res) -> str:
    """Насос, мощность, двигатель и энергопотребление."""
    motor = res.motor
    return wk.card("Насос, мощность и энергия", _params([
        ["Марка насоса", "—", f"{res.pump.model}, {res.pump.rpm:.0f} об/мин"],
        ["Оптимум характеристики", "Q_опт / H_опт",
         f"{num(res.pump.q_opt, 1)} м³/ч / {num(res.pump.head_opt, 1)} м"],
        ["Запас по подаче", "—", pct_signed(res.flow_reserve_pct)],
        ["Запас по напору", "—", pct_signed(res.head_reserve_pct)],
        ["Мощность гидравлическая", "N_гидр", num(res.power_hydraulic, 2, "кВт")],
        ["Мощность на валу", "N_вал", num(res.power_shaft, 2, "кВт")],
        ["Мощность из сети", "N_потр", num(res.power_input, 2, "кВт")],
        ["Двигатель", "—",
         (f"{motor.model}, {num(motor.power, 2, 'кВт')}, "
          f"{num(motor.rpm, 0, 'об/мин')}" if motor else "не подобран")],
        ["Загрузка двигателя", "k_з", pct(res.load_factor * 100, 0)],
        ["NPSH требуемый / запас", "—",
         f"{num(res.npsh_required, 2)} м / {num(res.npsh_margin, 2)} м"],
        ["Годовое энергопотребление", "W",
         num(res.energy_kwh, 0, "кВт·ч/год")],
        ["Годовая стоимость энергии", "C", num(res.energy_cost, 0, "руб/год")],
    ]))


def _checks_card(res) -> str:
    """Проверочные условия с значками результата."""
    return wk.card("Проверочные условия", wk.table(
        ["Условие", "Фактически", "Норма", "Результат"],
        [[c.name, c.actual, c.norm, wk.badge(c.ok)] for c in res.checks],
        aligns=["l", "r", "r", "c"]))


def _figure_card(res) -> str:
    """Схема установки и совместные характеристики насоса и сети."""
    net = res.network
    scheme = charts.system_fig(res)
    scheme_html = wk.card("Схема установки", wk.figure(
        wk.data_uri(plotkit.to_png_bytes(scheme)),
        f"Подъём {net.static_head:.1f} м, H_потр = {net.required_head:.1f} м, "
        f"насос {res.pump.model}"))
    plotkit.close(scheme)

    curves = charts.curves_fig(res)
    curves_html = wk.card("Характеристики насоса и сети", wk.figure(
        wk.data_uri(plotkit.to_png_bytes(curves)),
        f"Рабочая точка: Q = {res.flow_op:.1f} м³/ч, H = {res.head_op:.1f} м, "
        f"η = {res.efficiency * 100:.0f} %"))
    plotkit.close(curves)
    return scheme_html + curves_html


def _selection_card(selection) -> str:
    """Таблица и график сравнения насосов каталога."""
    rows = []
    for index, cand in enumerate(selection.candidates):
        mark = "★ " if index == selection.best_index else ""
        rows.append([
            mark + cand.pump.model,
            num(cand.flow_op, 1),
            num(cand.head_op, 1),
            num(cand.efficiency * 100, 0),
            num(cand.power_input, 2),
            cand.motor.model if cand.motor else "—",
            num(cand.npsh_margin, 2),
            wk.badge(cand.feasible, "годен", "не годен"),
            cand.note,
        ])
    figure = charts.selection_fig(selection)
    img = wk.figure(wk.data_uri(plotkit.to_png_bytes(figure)),
                    "Подача в рабочей точке и КПД по насосам каталога")
    plotkit.close(figure)
    return wk.card(
        "Подбор насоса по каталогу",
        wk.table(["Насос", "Q, м³/ч", "H, м", "η, %", "N_потр, кВт", "Двигатель",
                  "NPSH запас, м", "Годен", "Примечание"], rows,
                 aligns=["l", "r", "r", "r", "r", "l", "r", "c", "l"]) + img,
        hint="перебор насосов каталога")


def _result_html(res, selection, token: str) -> str:
    """Блок результатов: показатели, таблицы, проверки, графики, выгрузка."""
    warnings_html = ""
    if res.warnings:
        warnings_html = wk.card("Замечания",
                                "".join(wk.warning(w) for w in res.warnings))
    selection_html = _selection_card(selection) if selection is not None else ""
    return "".join([_kpi_card(res, token), warnings_html, _network_card(res),
                    _head_card(res), _drive_card(res), _checks_card(res),
                    _figure_card(res), selection_html])


def _render(values: dict[str, str], right: str, pump: str,
            error_html: str = "") -> Response:
    """Собрать страницу из формы и правой (результатной) колонки."""
    form_card = wk.card("Исходные данные", error_html + _form(values, pump),
                        hint="трубы по ГОСТ 8732")
    html = wk.page(TITLE, "Гидравлический расчёт, рабочая точка и подбор насоса",
                   form_card + right, PROGRAM)
    return Response(html, mimetype="text/html; charset=utf-8")


_EMPTY = wk.card(
    "Результат",
    '<p class="muted">Задайте теплоноситель, расход, высоту подъёма и параметры '
    "трубопроводов, затем нажмите «Рассчитать». Программа посчитает потери напора "
    "по участкам, найдёт рабочую точку, подберёт насос и двигатель и сформирует "
    "отчёты PDF и Word.</p>"
    + wk.bullets([
        "потери: Дарси–Вейсбах и местные сопротивления, λ по Колбруку–Уайту;",
        "потребный напор H = H_ст + p/(ρg) + Σh_дл + Σh_мс;",
        "рабочая точка: пересечение H(Q) насоса и H = H_ст + S·Q²;",
        "проверки: подача, рабочая зона, кавитационный запас, загрузка двигателя.",
    ]))


@app.get("/")
def index() -> Response:
    """Форма с примером исходных данных."""
    values = _defaults()
    example = request.args.get("example")
    if example is not None:
        try:
            inp = list(EXAMPLES.values())[int(example)]
            values = _values_from_input(inp)
        except (ValueError, IndexError):
            pass
    return _render(values, _EMPTY, values["pump"])


@app.post("/")
def calculate_view() -> Response:
    """Расчёт по данным формы."""
    inp, pump, errors = _parse_form(request.form)
    values = _form_values(request.form)
    if errors:
        return _render(values, _EMPTY, pump, wk.errors(errors))
    try:
        if pump == "auto":
            selection = select(inp)
            res = selection.best
            if res is None:
                raise CalculationError(["Подходящий насос в каталоге не найден."])
        else:
            selection = None
            res = evaluate(cat.PUMPS[pump], calculate(inp))
    except CalculationError as exc:
        return _render(values, _EMPTY, pump, wk.errors(exc.messages))
    token = _remember(inp, pump)
    return _render(values, _result_html(res, selection, token), pump)


@app.get("/download/<token>/<fmt>")
def download(token: str, fmt: str):
    """Выгрузка отчёта PDF или Word по ранее выполненному расчёту."""
    if token not in CACHE or fmt not in ("pdf", "docx"):
        abort(404)
    inp, pump = CACHE[token]
    selection = select(inp) if pump == "auto" else None
    res = selection.best if selection is not None else None
    if res is None:
        res = evaluate(cat.PUMPS[pump], calculate(inp))
    os.makedirs(OUT_DIR, exist_ok=True)
    stem = f"hydro_{res.network.flow_m3h:.0f}m3h_{res.pump.head_opt:.0f}m"
    if fmt == "pdf":
        path = build_pdf(res, os.path.join(OUT_DIR, stem + ".pdf"), selection)
        return send_file(path, as_attachment=True, download_name=stem + ".pdf",
                         mimetype="application/pdf")
    path = build_docx(res, os.path.join(OUT_DIR, stem + ".docx"), selection)
    return send_file(path, as_attachment=True, download_name=stem + ".docx",
                     mimetype="application/vnd.openxmlformats-officedocument."
                              "wordprocessingml.document")


def _remember(inp: NetworkInput, pump: str) -> str:
    """Запомнить исходные данные для выгрузки отчёта и вернуть ключ."""
    token = secrets.token_urlsafe(8)
    CACHE[token] = (inp, pump)
    while len(CACHE) > CACHE_LIMIT:
        CACHE.popitem(last=False)
    return token


def main() -> None:
    """Локальный запуск: python -m hydro_net.web."""
    port = int(os.environ.get("HYDRO_PORT", "5002"))
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
