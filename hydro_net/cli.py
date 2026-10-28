"""Командная строка программы «гидравлическая сеть + подбор насоса».

Примеры:
    python -m hydro_net.cli --example 0 --pdf out/hydro.pdf --docx out/hydro.docx
    python -m hydro_net.cli --flow 40 --static 18 --length 90 --dn 100 --pdf out/net.pdf
"""

from __future__ import annotations

import argparse
import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hydro_net.core import (EXAMPLES, CalculationError, NetworkInput, Section, calculate,
                            example_input, select)
from hydro_net.report import build_docx, build_pdf


def _console(selection) -> str:
    """Текстовое представление результата для консоли."""
    res = selection.best
    network = res.network if res else calculate(example_input(list(EXAMPLES)[0]))
    lines = [
        "",
        f"  Жидкость: {network.fluid.name}, t = {network.fluid.temperature:.0f} °C, "
        f"ρ = {network.fluid.density:.1f} кг/м³, μ = {network.fluid.viscosity * 1e3:.2f} мПа·с",
        f"  Расход: {network.flow_m3h:.2f} м³/ч; H_ст = {network.static_head:.2f} м; "
        f"H_потр = {network.required_head:.2f} м (потери {network.total_loss:.2f} м)",
        f"  NPSH доп = {network.npsh_available:.2f} м; p_вс = "
        f"{network.suction_pressure_kpa:.1f} кПа",
        "",
        f"  {'Участок':<22}{'DN':>5}{'v, м/с':>9}{'Re':>11}{'λ':>8}{'h_дл':>8}{'h_мс':>8}"
        f"{'Δp, кПа':>10}",
    ]
    for section in network.sections:
        lines.append(
            f"  {section.name[:22]:<22}{section.dn:>5}{section.velocity:>9.2f}"
            f"{section.reynolds:>11.0f}{section.lambda_:>8.4f}{section.loss_friction:>8.3f}"
            f"{section.loss_local:>8.3f}{section.pressure_drop_kpa:>10.1f}"
            + ("  (всас.)" if section.suction else ""))
    if res is not None:
        motor = f"{res.motor.model} {res.motor.power:.2f} кВт" if res.motor else "—"
        lines += [
            "",
            f"  Насос: {res.pump.model} (Q_опт = {res.pump.q_opt:.1f} м³/ч, "
            f"H_опт = {res.pump.head_opt:.1f} м)",
            f"  Рабочая точка: Q = {res.flow_op:.2f} м³/ч, H = {res.head_op:.2f} м, "
            f"η = {res.efficiency * 100:.0f} %",
            f"  Мощности: гидр. {res.power_hydraulic:.2f} кВт, вал {res.power_shaft:.2f} кВт, "
            f"из сети {res.power_input:.2f} кВт",
            f"  Двигатель: {motor}, загрузка {res.load_factor * 100:.0f} %",
            f"  Кавитация: NPSH_треб = {res.npsh_required:.2f} м, "
            f"запас = {res.npsh_margin:.2f} м",
            f"  Энергия: {res.energy_kwh:.0f} кВт·ч/год, "
            f"стоимость {res.energy_cost:.0f} руб/год",
        ]
        for check in res.checks:
            lines.append(f"  {'OK ' if check.ok else '!! '}{check.name}: {check.actual} "
                         f"(норма {check.norm})")
        for warning in res.warnings:
            lines.append(f"  ВНИМАНИЕ: {warning}")
    lines.append("")
    lines.append(f"  {'Насос':<14}{'Q, м³/ч':>9}{'H, м':>8}{'η':>7}{'N, кВт':>9}"
                 f"{'Двигатель':>12}{'Запас':>9}  Примечание")
    for cand in selection.candidates:
        mark = "*" if selection.best is not None and cand is selection.best else " "
        lines.append(
            f" {mark}{cand.pump.model:<14}{cand.flow_op:>9.2f}{cand.head_op:>8.2f}"
            f"{cand.efficiency * 100:>6.0f}%{cand.power_input:>9.2f}"
            f"{cand.motor.model if cand.motor else '—':>12}"
            f"{cand.flow_reserve_pct:>8.1f}%  {cand.note}")
    return "\n".join(lines) + "\n"



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Расчёт гидравлической сети и подбор насоса")
    parser.add_argument("--example", type=int, choices=range(len(EXAMPLES)),
                        help="номер демонстрационного примера")
    parser.add_argument("--fluid", default="water", choices=["water", "glycol30"])
    parser.add_argument("--temperature", type=float, default=20.0, help="°C")
    parser.add_argument("--flow", type=float, default=50.0, help="м³/ч")
    parser.add_argument("--static", type=float, default=20.0, help="геометрический подъём, м")
    parser.add_argument("--back-pressure", type=float, default=0.0, help="избыточное давление, бар")
    parser.add_argument("--suction-lift", type=float, default=2.5, help="высота всасывания, м")
    parser.add_argument("--suction-dn", type=int, default=100)
    parser.add_argument("--suction-length", type=float, default=6.0, help="м")
    parser.add_argument("--dn", type=int, default=100)
    parser.add_argument("--length", type=float, default=120.0, help="м")
    parser.add_argument("--hours", type=float, default=4000.0, help="ч/год")
    parser.add_argument("--pdf", help="путь для PDF-отчёта")
    parser.add_argument("--docx", help="путь для отчёта Word")
    args = parser.parse_args(argv)

    if args.example is not None:
        inp = example_input(list(EXAMPLES)[args.example])
    else:
        inp = NetworkInput(
            fluid=args.fluid, temperature=args.temperature, flow_m3h=args.flow,
            static_head=args.static, back_pressure_bar=args.back_pressure,
            suction_lift=args.suction_lift, hours_per_year=args.hours,
            sections=[
                Section("Всасывающая линия", args.suction_length, args.suction_dn, "steel",
                        {"inlet": 1, "valve": 1, "elbow90": 2}, suction=True),
                Section("Напорная линия", args.length, args.dn, "steel",
                        {"elbow90": 6, "valve": 1, "check": 1, "outlet": 1}),
            ],
        )

    try:
        selection = select(inp)
    except CalculationError as exc:
        for message in exc.messages:
            print(f"Ошибка: {message}", file=sys.stderr)
        return 2

    print(_console(selection))
    if selection.best is None:
        print("Подходящий насос в каталоге не найден — увеличьте диаметры или снизьте напор.",
              file=sys.stderr)
    if args.pdf and selection.best is not None:
        print(f"PDF: {build_pdf(selection.best, args.pdf, selection)}")
    if args.docx and selection.best is not None:
        print(f"DOCX: {build_docx(selection.best, args.docx, selection)}")
    return 0 if selection.best is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
