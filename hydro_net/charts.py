"""Схема насосной установки и графики к отчёту (matplotlib, Agg)."""

from __future__ import annotations

from matplotlib.patches import Circle, FancyArrowPatch, Polygon, Rectangle

from common import plotkit
from hydro_net import catalog as cat
from hydro_net.core import PumpResult, Selection


def system_fig(res: PumpResult, width_in: float = 8.0):
    """Схема установки: резервуар, насос, трубопровод, верхний бак."""
    fig, ax = plotkit.new_figure(width_in, 4.2)
    net = res.network
    lift = max(net.static_head, 2.0)
    top = lift + 3.0

    # нижний резервуар с водой
    ax.add_patch(Rectangle((0.4, 0.0), 2.4, 1.6, facecolor="#f7fafc",
                           edgecolor="#2d3748", linewidth=1.0, zorder=2))
    ax.add_patch(Rectangle((0.4, 0.0), 2.4, 1.2, facecolor="#cfe3f5",
                           edgecolor="none", zorder=3))
    ax.text(1.6, 0.6, "приёмный\nрезервуар", ha="center", va="center", fontsize=7.5,
            color="#1a202c", zorder=4)

    # всасывающий трубопровод
    suction = next((s for s in net.sections if s.suction), net.sections[0])
    ax.plot([2.8, 3.6], [1.2, 1.2], color="#1f5fa9", linewidth=4.0, solid_capstyle="butt",
            zorder=3)
    ax.text(3.2, 0.95, f"DN{suction.dn}", ha="center", fontsize=7, color="#1f5fa9")

    # насос и двигатель
    ax.add_patch(Circle((4.1, 1.2), 0.55, facecolor="#e8eef6", edgecolor="#2d3748",
                        linewidth=1.1, zorder=4))
    ax.add_patch(Polygon([[4.55, 0.95], [4.55, 1.45], [4.95, 1.2]], closed=True,
                         facecolor="#e8eef6", edgecolor="#2d3748", linewidth=1.0, zorder=4))
    ax.add_patch(Rectangle((4.95, 0.9), 0.85, 0.6, facecolor="#f6e3c5",
                           edgecolor="#2d3748", linewidth=1.0, zorder=4))
    ax.text(5.37, 1.2, "М", ha="center", va="center", fontsize=8, zorder=5)
    ax.text(4.1, 0.35, "насос", ha="center", fontsize=7.5, color="#2d3748")
    ax.text(4.9, 0.45, res.pump.model, ha="center", fontsize=7, color="#2d3748")

    # напорный трубопровод: вертикальный подъём и горизонтальный участок
    pressure = next((s for s in net.sections if not s.suction), net.sections[-1])
    pipe_top = max(lift, 1.6)
    ax.plot([4.1, 4.1], [1.75, pipe_top], color="#1f5fa9", linewidth=4.0, zorder=3)
    ax.plot([4.1, 8.2], [pipe_top, pipe_top], color="#1f5fa9", linewidth=4.0, zorder=3)
    ax.text(4.25, (1.75 + pipe_top) / 2.0, f"DN{pressure.dn}\nL = {pressure.length_m:.1f} м",
            fontsize=7, color="#1f5fa9", va="center")

    # верхний бак
    ax.add_patch(Rectangle((8.2, pipe_top - 0.9), 1.5, 1.5, facecolor="#f7fafc",
                           edgecolor="#2d3748", linewidth=1.0, zorder=2))
    ax.add_patch(Rectangle((8.2, pipe_top - 0.9), 1.5, 1.1, facecolor="#cfe3f5",
                           edgecolor="none", zorder=2))
    ax.text(8.95, pipe_top + 0.75, "потребитель", ha="center", fontsize=7.5)

    # размер статического напора
    ax.add_patch(FancyArrowPatch((7.6, 1.2), (7.6, pipe_top), arrowstyle="<|-|>",
                                 mutation_scale=9, color="#c2410c", linewidth=1.0, zorder=6))
    ax.text(7.72, (1.2 + pipe_top) / 2.0, f"H_ст = {net.static_head:.1f} м",
            fontsize=7.5, color="#c2410c", rotation=90, va="center")

    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_xlim(0.0, 10.2)
    ax.set_ylim(-0.4, top + 1.4)
    ax.set_title(f"Схема установки: Q = {net.flow_m3h:.1f} м³/ч, "
                 f"H = {net.required_head:.1f} м, NPSH = {net.npsh_available:.1f} м",
                 fontsize=8.5, color=plotkit.INK)
    fig.tight_layout()
    return fig



def curves_fig(res: PumpResult, width_in: float = 7.2):
    """Характеристики насоса и сети с рабочей точкой и КПД."""
    fig, ax = plotkit.new_figure(width_in, 3.6)
    pump, net = res.pump, res.network
    q_max = max(pump.max_flow(), pump.q_opt * 1.2)
    steps = 120
    flows = [q_max * i / steps for i in range(steps + 1)]
    heads = [max(pump.head(q), 0.0) for q in flows]
    static_total = net.static_head + net.back_pressure_head
    network_heads = [static_total + net.resistance * q ** 2 for q in flows]

    ax.plot(flows, heads, color=plotkit.ACCENT, linewidth=1.7,
            label=f"Насос {pump.model}: H(Q)")
    ax.plot(flows, network_heads, color=plotkit.ACCENT_2, linewidth=1.5, linestyle="--",
            label="Сеть: H = H_ст + S·Q²")
    ax.axvspan(cat.WORK_ZONE[0] * pump.q_opt, cat.WORK_ZONE[1] * pump.q_opt,
               color="#1f5fa9", alpha=0.07, label="рабочая зона насоса")
    ax.axvline(net.flow_m3h, color=plotkit.MUTED, linewidth=0.9, linestyle=":",
               label=f"Q расчётный = {net.flow_m3h:.1f} м³/ч")
    ax.plot([res.flow_op], [res.head_op], "o", color="#c2410c", markersize=7, zorder=6)
    ax.annotate(f"рабочая точка\n{res.flow_op:.1f} м³/ч; {res.head_op:.1f} м",
                xy=(res.flow_op, res.head_op), xytext=(-14, 24),
                textcoords="offset points", fontsize=7.5, color=plotkit.INK,
                arrowprops={"arrowstyle": "-", "linewidth": 0.7, "color": plotkit.MUTED})
    ax.set_xlabel("Подача, м³/ч")
    ax.set_ylabel("Напор, м")
    ax.set_xlim(0, q_max)
    ax.set_ylim(0, max(max(heads), max(network_heads)) * 1.15)
    ax.legend(loc="upper right", fontsize=7.2)

    efficiency_ax = ax.twinx()
    efficiency_ax.plot(flows, [pump.efficiency_at(q) * 100 for q in flows],
                       color="#1c7a4a", linewidth=1.2, linestyle="-.",
                       label="КПД насоса, %")
    efficiency_ax.plot([res.flow_op], [res.efficiency * 100], "s", color="#1c7a4a",
                       markersize=5)
    efficiency_ax.set_ylabel("КПД, %", color="#1c7a4a")
    efficiency_ax.set_ylim(0, 100)
    efficiency_ax.grid(False)
    efficiency_ax.legend(loc="center right", fontsize=7.2)

    ax.set_title(f"Совместная работа насоса и сети: η = {res.efficiency * 100:.0f} %, "
                 f"N = {res.power_input:.2f} кВт", fontsize=8.5)
    fig.tight_layout()
    return fig


def selection_fig(selection: Selection, width_in: float = 7.0):
    """Сравнение насосов каталога по потребляемой мощности."""
    fig, ax = plotkit.new_figure(width_in, 3.2)
    cands = selection.candidates
    labels = [c.pump.model.replace("НК ", "") for c in cands]
    powers = [min(c.power_input, 60.0) for c in cands]
    colors = [plotkit.ACCENT_2 if index == selection.best_index else
              (plotkit.ACCENT if c.feasible else "#cbd5e0") for index, c in enumerate(cands)]
    bars = ax.bar(labels, powers, color=colors, edgecolor="#2d3748", linewidth=0.5)
    for bar, cand in zip(bars, cands):
        ax.text(bar.get_x() + bar.get_width() / 2.0, bar.get_height() + 0.15,
                f"{cand.flow_op:.1f} м³/ч\n{cand.efficiency * 100:.0f} %",
                ha="center", va="bottom", fontsize=6.6, color="#2d3748")
    ax.set_xlabel("Насос (типоразмер НК)")
    ax.set_ylabel("Мощность из сети, кВт")
    ax.set_ylim(0, max(powers) * 1.30 if powers else 1.0)
    ax.set_title("Варианты насосов: подача в рабочей точке и КПД; "
                 "красный — рекомендуемый", fontsize=8.2)
    fig.tight_layout()
    return fig
