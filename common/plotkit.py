"""Единый стиль графиков (matplotlib, бэкенд Agg) для отчётов и веб-интерфейса."""

from __future__ import annotations

import io
import os

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402  (после выбора бэкенда)

from matplotlib import rcParams  # noqa: E402

FONT_DIR = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
FONT_PATH = os.path.join(FONT_DIR, "DejaVuSans.ttf")
FONT_BOLD_PATH = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")

rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.labelsize": 9,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "grid.linewidth": 0.6,
        "axes.edgecolor": "#4a5568",
        "axes.labelcolor": "#1a202c",
        "xtick.color": "#2d3748",
        "ytick.color": "#2d3748",
        "figure.dpi": 170,
        "savefig.dpi": 170,
        "legend.fontsize": 8,
        "legend.framealpha": 0.9,
    }
)

INK = "#1a202c"
ACCENT = "#1f5fa9"
ACCENT_2 = "#c2410c"
MUTED = "#718096"


def new_figure(width_in: float = 6.4, height_in: float = 3.4):
    """Новая фигура заданного размера (в дюймах)."""
    fig, ax = plt.subplots(figsize=(width_in, height_in))
    fig.patch.set_facecolor("white")
    return fig, ax


def to_png_bytes(fig, dpi: int = 170) -> bytes:
    """Сохранить фигуру в PNG-байты (для вставки в HTML/PDF без временных файлов)."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    return buf.getvalue()


def save_png(fig, path: str, dpi: int = 170) -> str:
    """Сохранить фигуру в файл PNG и вернуть путь."""
    fig.savefig(path, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    return path


def close(fig) -> None:
    plt.close(fig)
