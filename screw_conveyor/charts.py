"""Схема конвейера и графики к отчёту (matplotlib, Agg)."""

from __future__ import annotations

import math

from matplotlib.patches import Arc, FancyArrowPatch, Polygon, Rectangle

from common import plotkit
from screw_conveyor.core import ScrewResult, Selection


def schematic_fig(res: ScrewResult, width_in: float = 8.0):
    """Продольная схема конвейера с основными размерами."""
    fig, ax = plotkit.new_figure(width_in, 2.9)
    d = res.diameter
    length = res.length
    beta = math.radians(res.incline_deg)
    trough_h = 1.15 * d
    cos_b, sin_b = math.cos(beta), math.sin(beta)

    def pt(t: float, h: float) -> tuple[float, float]:
        """Точка в координатах конвейера: t - вдоль оси, h - по нормали вверх."""
        return (t * cos_b - h * sin_b, t * sin_b + h * cos_b)

    # корпус (желоб) с крышкой
    body = Polygon([pt(0, 0), pt(length, 0), pt(length, trough_h), pt(0, trough_h)],
                   closed=True, facecolor="#eef2f7", edgecolor="#2d3748", linewidth=1.0, zorder=2)
    ax.add_patch(body)

    # витки винта
    pitch = res.pitch
    n_turns = length / pitch
    step = max(1, int(round(n_turns / 26)))  # не более ~26 витков на схеме
    t = 0.0
    while t < length - 1e-6:
        t_end = min(t + pitch / 2.0, length)
        a = pt(t, 0.06 * trough_h)
        b = pt(t_end, 0.94 * trough_h)
        ax.plot([a[0], b[0]], [a[1], b[1]], color="#1f5fa9", linewidth=0.8, zorder=3)
        t += pitch * step

    # вал
    a = pt(0, trough_h / 2.0)
    b = pt(length, trough_h / 2.0)
    ax.plot([a[0], b[0]], [a[1], b[1]], color="#4a5568",
            linewidth=max(1.5, d * 30), solid_capstyle="butt", zorder=4)

    # привод: редуктор и двигатель
    gb_w, gb_h = 0.9 * d + 0.12, 0.75 * d
    ax.add_patch(Rectangle(pt(-gb_w, trough_h / 2.0 - gb_h / 2.0), gb_w, gb_h,
                           angle=res.incline_deg, facecolor="#dbe3ee",
                           edgecolor="#2d3748", linewidth=0.9, zorder=5))
    motor_w, motor_h = 0.75 * d + 0.10, 0.5 * d
    ax.add_patch(Rectangle(pt(-gb_w - motor_w, trough_h / 2.0 - motor_h / 2.0),
                           motor_w, motor_h, angle=res.incline_deg, facecolor="#f6e3c5",
                           edgecolor="#2d3748", linewidth=0.9, zorder=5))
    ax.text(*pt(-gb_w - motor_w / 2.0, trough_h / 2.0), "M", ha="center", va="center",
            fontsize=7.5, zorder=6)
    ax.text(*pt(-gb_w / 2.0, trough_h / 2.0), "Р", ha="center", va="center",
            fontsize=7.5, zorder=6)

    # промежуточные опоры
    if res.supports:
        support_step = length / (res.supports + 1)
        for i in range(1, res.supports + 1):
            x0, y0 = pt(i * support_step, -0.02)
            ax.plot([x0, x0], [y0, y0 - 0.35 * d - 0.05], color="#4a5568", linewidth=1.0, zorder=1)
            ax.plot([x0 - 0.07, x0 + 0.07], [y0 - 0.35 * d - 0.05] * 2,
                    color="#4a5568", linewidth=1.4, zorder=1)


    # размеры: длина
    dim_offset = -0.55 * d - 0.25
    p1, p2 = pt(0, dim_offset), pt(length, dim_offset)
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="<|-|>", mutation_scale=8,
                                 color="#c2410c", linewidth=0.9, zorder=7))
    mid = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
    label = f"L = {length:.2f} м"
    if res.incline_deg:
        label += f"  (β = {res.incline_deg:.0f}°)"
    ax.text(mid[0], mid[1] - 0.12 * d - 0.04, label, ha="center", va="top",
            fontsize=7.5, color="#c2410c")

    # размеры: диаметр винта
    dx = length * 0.72
    a, b = pt(dx, 0.0), pt(dx, d)
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="<|-|>", mutation_scale=8,
                                 color="#1f5fa9", linewidth=0.9, zorder=7))
    ax.text(b[0] + 0.05, (a[1] + b[1]) / 2.0, f"Ø{res.diameter * 1000:.0f}",
            fontsize=7.5, color="#1f5fa9", va="center")

    # размеры: шаг винта
    if n_turns >= 2:
        ts = length * 0.25
        a2, b2 = pt(ts, d * 1.35), pt(ts + pitch, d * 1.35)
        ax.add_patch(FancyArrowPatch(a2, b2, arrowstyle="<|-|>", mutation_scale=7,
                                     color="#2d3748", linewidth=0.8, zorder=7))
        ax.text((a2[0] + b2[0]) / 2.0, (a2[1] + b2[1]) / 2.0 + 0.05,
                f"S = {pitch * 1000:.0f}", ha="center", fontsize=7, color="#2d3748")

    # угол наклона
    if res.incline_deg > 0.5:
        radius = 1.4 * length / 3.0
        ax.add_patch(Arc(pt(0, 0), radius, radius * 0.6, angle=0, theta1=0,
                         theta2=res.incline_deg, color="#c2410c", linewidth=0.8, zorder=7))

    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_xlim(pt(-gb_w - motor_w - 0.25 * d, 0)[0], pt(length + 0.15, 0)[0])
    ymin = min(pt(0, dim_offset)[1], 0.0) - 0.55 * d - 0.15
    ymax = max(pt(length, trough_h)[1], pt(0, trough_h)[1]) + 0.40 * d + 0.20
    ax.set_ylim(ymin, ymax)
    ax.set_title(f"Шнековый конвейер Ø{res.diameter * 1000:.0f} мм, L = {length:.2f} м, "
                 f"n = {res.rpm:.0f} об/мин", fontsize=8.5, color=plotkit.INK)
    fig.tight_layout()
    return fig


def capacity_fig(res: ScrewResult, width_in: float = 6.6):
    """Кривая производительности от частоты вращения для выбранной геометрии."""
    fig, ax = plotkit.new_figure(width_in, 2.9)
    n_max_plot = res.rpm_max * 1.25
    n_values = [n_max_plot * i / 100.0 for i in range(101)]
    q_values = [47.0 * res.diameter ** 2 * res.pitch * n * res.fill * res.density
                * res.incline_factor for n in n_values]

    ax.plot(n_values, q_values, color=plotkit.ACCENT, linewidth=1.6,
            label=f"Q(n), S/D = {res.pitch_ratio:.2f}")
    ax.axhline(res.capacity_required, color=plotkit.ACCENT_2, linewidth=1.0, linestyle="--",
               label=f"Q требуемая = {res.capacity_required:.1f} т/ч")
    ax.axvline(res.rpm_max, color=plotkit.MUTED, linewidth=1.0, linestyle=":",
               label=f"n предельная = {res.rpm_max:.0f} об/мин")
    ax.plot([res.rpm], [res.capacity], "o", color=plotkit.ACCENT_2, markersize=6, zorder=5)
    ax.annotate(f"{res.rpm:.0f} об/мин, {res.capacity:.1f} т/ч",
                xy=(res.rpm, res.capacity), xytext=(8, -20), textcoords="offset points",
                fontsize=7.5, color=plotkit.INK)
    ax.set_xlabel("Частота вращения, об/мин")
    ax.set_ylabel("Производительность, т/ч")
    ax.set_xlim(0, n_max_plot)
    ax.set_ylim(0, max(max(q_values) * 1.05, res.capacity_required * 1.2))
    ax.legend(loc="upper left", fontsize=7.5)
    ax.set_title(f"Производительность Ø{res.diameter * 1000:.0f} мм, "
                 f"S = {res.pitch * 1000:.0f} мм, ψ = {res.fill:.2f}", fontsize=8.5)
    fig.tight_layout()
    return fig


def selection_fig(selection: Selection, width_in: float = 6.8):
    """Диаграмма вариантов подбора: масса конвейера и мощность привода."""
    fig, ax = plotkit.new_figure(width_in, 2.9)
    cands = selection.candidates
    labels = [f"Ø{c.diameter * 1000:.0f}" for c in cands]
    masses = [c.total_mass for c in cands]
    colors = [plotkit.ACCENT_2 if i == selection.best_index else
              (plotkit.ACCENT if c.feasible else "#cbd5e0") for i, c in enumerate(cands)]
    bars = ax.bar(labels, masses, color=colors, edgecolor="#2d3748", linewidth=0.5)
    for bar, cand in zip(bars, cands):
        ax.text(bar.get_x() + bar.get_width() / 2.0, bar.get_height() * 1.02,
                f"{cand.motor_power:.1f} кВт", ha="center", va="bottom", fontsize=7)
    ax.set_xlabel("Диаметр винта, мм")
    ax.set_ylabel("Масса конвейера, кг")
    ax.set_title("Варианты типоразмеров (подпись — мощность привода; "
                 "красный — рекомендуемый)", fontsize=8.2)
    ax.set_ylim(0, max(masses) * 1.20 if masses else 1.0)
    fig.tight_layout()
    return fig
