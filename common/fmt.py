"""Форматирование чисел в русской инженерной нотации.

Во всех отчётах и в веб-интерфейсе числа выводятся единообразно:
разделитель дробной части - запятая, разделитель тысяч - неразрывный пробел.
"""

from __future__ import annotations

NBSP = "\u00a0"


def num(value: float, digits: int = 2, unit: str = "") -> str:
    """Число с фиксированным количеством знаков: 1 234,56 мм."""
    if value is None:
        return "—"
    text = f"{value:,.{digits}f}"
    text = text.replace(",", "\u0000").replace(".", ",").replace("\u0000", NBSP)
    return f"{text}{NBSP}{unit}".rstrip() if unit else text


def num_sig(value: float, digits: int = 4, unit: str = "") -> str:
    """Число с заданным количеством значащих цифр (для широкого диапазона)."""
    if value is None:
        return "—"
    text = f"{value:,.{digits}g}"
    text = text.replace(",", "\u0000").replace(".", ",").replace("\u0000", NBSP)
    if "e" in text:
        return f"{num(value, 4)}{NBSP}{unit}".rstrip()
    return f"{text}{NBSP}{unit}".rstrip() if unit else text


def money(value: float, unit: str = "₽") -> str:
    """Сумма с округлением до рубля: 1 234 567 ₽."""
    if value is None:
        return "—"
    text = f"{value:,.0f}".replace(",", NBSP)
    return f"{text}{NBSP}{unit}"


def pct(value: float, digits: int = 1) -> str:
    """Процент: 12,5 %."""
    return num(value, digits) + NBSP + "%"


def pct_signed(value: float, digits: int = 1) -> str:
    """Процент со знаком: +12,5 %."""
    sign = "+" if value >= 0 else "−"
    return sign + num(abs(value), digits) + NBSP + "%"
