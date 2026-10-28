"""Общие HTML-компоненты для веб-интерфейсов обеих расчётных программ.

Модуль даёт компактный набор функций без шаблонизатора: страница, карточки,
таблица, KPI-плитки, значки проверок и вставка графиков как data-URI.
Всё оформление собрано в одной строке :data:`CSS`, поэтому внешний вид
инженерных калькуляторов одинаковый.
"""

from __future__ import annotations

import html
import os
import tempfile

PROGRAM_FOOTER = ("Расчёт выполнен по инженерной методике; результат носит оценочный "
                  "характер и уточняется по конструкторской документации.")


def report_dir(default: str) -> str:
    """Каталог для готовых отчётов (PDF/Word).

    По умолчанию — подкаталог ``out`` проекта, переопределяется переменной
    окружения ``OUT_DIR``. На хостинге файловая система может быть доступна
    только для чтения, поэтому при невозможности записи берётся временный каталог.
    """
    path = os.environ.get("OUT_DIR") or default
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write-check")
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("ok")
        os.remove(probe)
        return path
    except OSError:
        return tempfile.gettempdir()


class Raw(str):
    """Строка с готовой HTML-разметкой (не экранируется)."""


def esc(value) -> str:
    """Экранировать значение, кроме заранее подготовленной разметки."""
    return value if isinstance(value, Raw) else html.escape(str(value))


CSS = """
:root{
  --ink:#1a202c; --muted:#5a6a80; --line:#d7dee8; --bg:#f4f6fa; --card:#ffffff;
  --accent:#1f5fa9; --accent-dark:#164a86; --ok:#1c7a4a; --ok-bg:#e6f5ec;
  --bad:#b42318; --bad-bg:#fdecea; --warn:#8a5a00; --warn-bg:#fff5e0; --head:#eaf0f8;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);
  font:14px/1.5 "Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
a{color:var(--accent)}
header.top{background:linear-gradient(120deg,#14335c,#1f5fa9 60%,#2b7fc4);
  color:#fff;padding:18px 28px}
header.top .inside{max-width:1240px;margin:0 auto;display:flex;
  align-items:baseline;gap:14px;flex-wrap:wrap}
header.top h1{font-size:20px;margin:0;font-weight:600;letter-spacing:.2px}
header.top .sub{opacity:.85;font-size:13px}
header.top .ver{margin-left:auto;font-size:12px;opacity:.85;
  border:1px solid rgba(255,255,255,.45);border-radius:999px;padding:2px 10px}
main{max-width:1240px;margin:0 auto;padding:22px 28px 60px;
  display:grid;grid-template-columns:352px minmax(0,1fr);gap:22px;align-items:start}
@media (max-width:1000px){main{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:16px 18px;box-shadow:0 1px 2px rgba(16,32,64,.05)}
.card+.card{margin-top:18px}
.card h2{font-size:15px;margin:0 0 12px;padding-bottom:8px;
  border-bottom:1px solid var(--line);color:#14335c;font-weight:600}
.card h2 .hint{font-weight:400;color:var(--muted);font-size:12px;float:right}
form .grp{margin-bottom:12px}
form label{display:block;font-size:12px;color:var(--muted);margin-bottom:4px}
form input,form select{width:100%;padding:7px 9px;border:1px solid var(--line);
  border-radius:8px;font:inherit;color:var(--ink);background:#fcfdff}
form input:focus,form select:focus{outline:2px solid #bcd3ec;border-color:var(--accent)}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.check{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--ink)}
.check input{width:auto}
button{width:100%;margin-top:6px;padding:10px 14px;border:0;border-radius:9px;
  background:var(--accent);color:#fff;font:inherit;font-weight:600;cursor:pointer}
button:hover{background:var(--accent-dark)}
.btns{display:flex;gap:10px;margin-top:14px;flex-wrap:wrap}
.btns a{flex:1 1 150px;text-align:center;padding:9px 12px;border-radius:9px;
  border:1px solid var(--accent);color:var(--accent);text-decoration:none;
  font-weight:600;background:#fff}
.btns a:hover{background:var(--head)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.kpi{border:1px solid var(--line);border-radius:10px;padding:11px 13px;background:#fbfcfe}
.kpi .lab{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.kpi .val{font-size:20px;font-weight:650;margin-top:3px;color:#14335c}
.kpi .val small{font-size:12px;font-weight:500;color:var(--muted);margin-left:3px}
table{width:100%;border-collapse:collapse;font-size:13px}
caption{caption-side:top;text-align:left;font-size:12px;color:var(--muted);padding-bottom:6px}
th,td{padding:7px 9px;border-bottom:1px solid var(--line);vertical-align:top}
th{background:var(--head);text-align:left;font-weight:600;color:#14335c;font-size:12px}
td.r,th.r{text-align:right;font-variant-numeric:tabular-nums}
td.c,th.c{text-align:center}
tr.total td{background:#f2f5f9;font-weight:600}
tr:last-child td{border-bottom:0}
.badge{display:inline-block;padding:1px 9px;border-radius:999px;font-size:11px;font-weight:700}
.badge.ok{color:var(--ok);background:var(--ok-bg)}
.badge.bad{color:var(--bad);background:var(--bad-bg)}
.note{border-left:3px solid var(--accent);background:#f2f7fd;padding:9px 12px;
  border-radius:0 8px 8px 0;font-size:13px;color:#22405f;margin-top:12px}
.warn{border-left:3px solid #d99000;background:var(--warn-bg);padding:9px 12px;
  border-radius:0 8px 8px 0;font-size:13px;color:var(--warn);margin-top:12px}
.err{border-left:3px solid var(--bad);background:var(--bad-bg);padding:10px 12px;
  border-radius:0 8px 8px 0;color:var(--bad);margin-bottom:14px}
ul.plain{margin:8px 0 0;padding-left:18px}
ul.plain li{margin:4px 0}
figure{margin:14px 0 0}
figure img{width:100%;height:auto;border:1px solid var(--line);border-radius:10px;background:#fff}
figcaption{font-size:12px;color:var(--muted);margin-top:6px}
footer.foot{max-width:1240px;margin:0 auto;padding:0 28px 28px;color:var(--muted);font-size:12px}
.muted{color:var(--muted);font-size:13px}
"""



def page(title: str, subtitle: str, body: str, program: str) -> str:
    """Собрать полную HTML-страницу в общем стиле."""
    return f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><style>{CSS}</style></head>
<body>
<header class="top"><div class="inside">
  <h1>{esc(title)}</h1><span class="sub">{esc(subtitle)}</span>
  <span class="ver">{esc(program)}</span>
</div></header>
<main>{body}</main>
<footer class="foot">{esc(PROGRAM_FOOTER)}</footer>
</body></html>"""


def card(title: str, body: str, hint: str = "") -> str:
    """Карточка с заголовком."""
    hint_html = f'<span class="hint">{esc(hint)}</span>' if hint else ""
    return f'<section class="card"><h2>{esc(title)}{hint_html}</h2>{body}</section>'


def kpis(items) -> str:
    """Плитки с главными числами: [(подпись, значение, единица), ...]."""
    cells = ""
    for label, value, unit in items:
        unit_html = f"<small>{esc(unit)}</small>" if unit else ""
        cells += (f'<div class="kpi"><div class="lab">{esc(label)}</div>'
                  f'<div class="val">{esc(value)}{unit_html}</div></div>')
    return f'<div class="kpis">{cells}</div>'


def _cls(align: str) -> str:
    return "c" if align == "c" else ("r" if align == "r" else "")


def table(headers, rows, aligns=None, caption: str = "", total_last: bool = False) -> str:
    """HTML-таблица; значения экранируются, Raw вставляется как разметка."""
    aligns = aligns or ["l"] * len(headers)
    head = "".join(f'<th class="{_cls(a)}">{esc(title)}</th>' for title, a in zip(headers, aligns))
    body = []
    for index, row in enumerate(rows):
        cls = ' class="total"' if total_last and index == len(rows) - 1 else ""
        cells = "".join(f'<td class="{_cls(a)}">{esc(cell)}</td>' for cell, a in zip(row, aligns))
        body.append(f"<tr{cls}>{cells}</tr>")
    cap = f"<caption>{esc(caption)}</caption>" if caption else ""
    return f"<table>{cap}<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def badge(ok: bool, ok_text: str = "соответствует",
          bad_text: str = "не соответствует") -> Raw:
    """Значок результата проверки."""
    cls = "ok" if ok else "bad"
    return Raw(f'<span class="badge {cls}">{esc(ok_text if ok else bad_text)}</span>')


def note(text: str) -> str:
    """Выделенная ремарка."""
    return f'<div class="note">{esc(text)}</div>'


def warning(text: str) -> str:
    """Выделенное предупреждение."""
    return f'<div class="warn">{esc(text)}</div>'


def errors(messages) -> str:
    """Блок ошибок исходных данных."""
    items = "".join(f"<li>{esc(m)}</li>" for m in messages)
    return ('<div class="err"><strong>Проверьте исходные данные:</strong>'
            f'<ul class="plain">{items}</ul></div>')


def bullets(items) -> str:
    """Маркированный список."""
    return '<ul class="plain">' + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul>"


def figure(data_uri: str, caption: str = "") -> str:
    """Вставка графика из data-URI."""
    cap = f"<figcaption>{esc(caption)}</figcaption>" if caption else ""
    return f'<figure><img src="{esc(data_uri)}" alt="{esc(caption)}">{cap}</figure>'


def data_uri(png_bytes: bytes) -> str:
    """PNG-байты в data-URI для <img>."""
    import base64

    return "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
