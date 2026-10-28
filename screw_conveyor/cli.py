"""Командная строка программы: расчёт без веб-интерфейса и выгрузка отчётов.

Примеры:
    python -m screw_conveyor.cli --example 0 --pdf out/report.pdf --docx out/report.docx
    python -m screw_conveyor.cli --material cement --capacity 30 --length 12 \
        --incline 10 --select --pdf out/cement.pdf
"""

from __future__ import annotations

import argparse
import os
import sys

if __package__ in (None, ""):  # запуск файлом: python screw_conveyor/cli.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from screw_conveyor import catalog as cat
from screw_conveyor.core import EXAMPLES, CalculationError, ScrewInput, calculate, select
from screw_conveyor.report import build_docx, build_pdf


def _console_table(res) -> str:
    lines = [
        "",
        f"  Материал: {res.material.name}, ρ = {res.density:.2f} т/м³, w = {res.res_coef:.2f}",
        f"  Винт: Ø{res.diameter * 1000:.0f} мм, шаг {res.pitch * 1000:.0f} мм, "
        f"n = {res.rpm:.0f} об/мин, ψ = {res.fill:.2f}",
        f"  Производительность: {res.capacity:.2f} т/ч (требуется {res.capacity_required:.2f}), "
        f"запас {res.reserve_pct:+.1f} %",
        f"  Мощность на валу: {res.shaft_power:.3f} кВт; двигатель: "
        f"{res.motor.model if res.motor else '—'} {res.motor.power if res.motor else 0:.2f} кВт; "
        f"i = {res.gear_ratio:.1f}",
        f"  Момент: {res.torque:.1f} Н·м; вал Ø{res.shaft_outer_mm:.0f}×{res.shaft_wall_mm:.0f}, "
        f"τ = {res.shaft_tau:.2f} МПа",
        f"  Масса: {res.total_mass:.1f} кг",
    ]
    for check in res.checks:
        mark = "OK " if check.ok else "!! "
        lines.append(f"  {mark}{check.name}: {check.actual} (норма {check.norm})")
    for warning in res.warnings:
        lines.append(f"  ВНИМАНИЕ: {warning}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Расчёт шнекового конвейера")
    parser.add_argument("--example", type=int, choices=range(len(EXAMPLES)),
                        help="номер демонстрационного примера")
    parser.add_argument("--material", default="wheat", choices=sorted(cat.MATERIALS))
    parser.add_argument("--capacity", type=float, default=10.0, help="т/ч")
    parser.add_argument("--length", type=float, default=10.0, help="м")
    parser.add_argument("--incline", type=float, default=0.0, help="град.")
    parser.add_argument("--diameter", type=float, default=0.25, help="м")
    parser.add_argument("--rpm", type=float, default=60.0)
    parser.add_argument("--fill", type=float, default=0.35)
    parser.add_argument("--pitch", type=float, default=1.0, help="S/D")
    parser.add_argument("--steel", default="Ст3сп", choices=sorted(cat.STEEL_GRADES))
    parser.add_argument("--select", action="store_true",
                        help="выполнить подбор типоразмера по стандартному ряду")
    parser.add_argument("--pdf", help="путь для PDF-отчёта")
    parser.add_argument("--docx", help="путь для отчёта Word")
    args = parser.parse_args(argv)

    if args.example is not None:
        inp = list(EXAMPLES.values())[args.example]
    else:
        inp = ScrewInput(material_code=args.material, capacity=args.capacity,
                         length=args.length, incline_deg=args.incline,
                         diameter=args.diameter, rpm=args.rpm, fill=args.fill,
                         pitch_ratio=args.pitch, steel_grade=args.steel)

    try:
        selection = select(inp) if args.select else None
        res = selection.best if selection and selection.best is not None else calculate(inp)
    except CalculationError as exc:
        for message in exc.messages:
            print(f"Ошибка: {message}", file=sys.stderr)
        return 2

    print(_console_table(res))
    if selection is not None:
        print("  Подбор типоразмеров:")
        for cand in selection.candidates:
            mark = "*" if cand.diameter == res.diameter else " "
            print(f"   {mark} Ø{cand.diameter * 1000:>4.0f} мм  n={cand.rpm:>5.0f}  "
                  f"Q={cand.capacity:>6.2f} т/ч  запас {cand.reserve_pct:>+6.1f} %  "
                  f"{cand.motor_model:>9}  {cand.total_mass:>7.1f} кг  {cand.note}")

    if args.pdf:
        print(f"PDF: {build_pdf(res, args.pdf, selection)}")
    if args.docx:
        print(f"DOCX: {build_docx(res, args.docx, selection)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
