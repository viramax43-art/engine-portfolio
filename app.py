"""Единая точка входа для деплоя на бесплатном хостинге (Render и совместимые).

Одно WSGI-приложение отдаёт:
    /         — страница-портфолио со ссылками на оба калькулятора
    /screw/   — расчёт и подбор шнекового конвейера
    /hydro/   — гидравлическая сеть и подбор насоса

Локальный запуск:  python app.py                       →  http://127.0.0.1:8000
Продакшн:          gunicorn app:app --bind 0.0.0.0:$PORT
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Префиксы читаются дочерними приложениями при импорте, поэтому переменные
# окружения выставляются до импорта их модулей.
os.environ.setdefault("SCREW_PREFIX", "/screw")
os.environ.setdefault("HYDRO_PREFIX", "/hydro")

from flask import Flask  # noqa: E402  (после настройки путей и префиксов)
from werkzeug.middleware.dispatcher import DispatcherMiddleware  # noqa: E402
from werkzeug.serving import run_simple  # noqa: E402

from common import web_kit as wk  # noqa: E402
from hydro_net import web as hydro_web  # noqa: E402
from screw_conveyor import web as screw_web  # noqa: E402

PROGRAMS = (
    {
        "href": "/screw/",
        "tag": "Программа 1",
        "title": "Шнековый конвейер",
        "lead": ("Расчёт производительности и мощности привода, подбор типоразмера "
                 "по стандартному ряду диаметров, проверка вала и конструкции."),
        "features": [
            "12 транспортируемых грузов, коэффициенты заполнения и сопротивления",
            "Автоподбор диаметра и частоты вращения, проверка запаса и n_max",
            "Проверка вала на кручение и изгиб, выбор мотор-редуктора",
            "Схема установки, характеристики и отчёт PDF/Word",
        ],
        "badge": "SCREW-CONVEYOR 1.0",
    },
    {
        "href": "/hydro/",
        "tag": "Программа 2",
        "title": "Гидравлическая сеть и подбор насоса",
        "lead": ("Потери по длине (Дарси–Вейсбах, Колбрук–Уайт) и в местных "
                 "сопротивлениях, потребный напор, рабочая точка с характеристикой "
                 "насоса, кавитационный запас и энергопотребление."),
        "features": [
            "Вода и водный раствор этиленгликоля, температура от −20 до 150 °C",
            "Всасывающая и напорная линии: DN по ГОСТ 8732, отводы, задвижки, фильтры",
            "Подбор насоса по каталогу или расчёт на заданном насосе, NPSH и двигатель",
            "Схема установки, совместные характеристики сети и насоса, отчёт PDF/Word",
        ],
        "badge": "HYDRO-NET 1.0",
    },
)

_LANDING_CSS = """
.hero{max-width:1080px;margin:0 auto;padding:30px 28px 0}
.hero h2{margin:0 0 8px;font-size:26px;color:#14335c;letter-spacing:-.2px}
.hero p{margin:0;color:#4a5568;max-width:760px}
.wrap{max-width:1080px;margin:0 auto;padding:22px 28px 60px;
  display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:20px}
.prog{background:#fff;border:1px solid var(--line);border-radius:14px;padding:20px 22px;
  box-shadow:0 2px 10px rgba(16,32,64,.06);display:flex;flex-direction:column}
.prog .tag{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);
  font-weight:700}
.prog h3{margin:6px 0 10px;font-size:19px;color:#14335c}
.prog .lead{margin:0 0 14px;color:#3d4a5c;font-size:13.5px}
.prog ul{margin:0 0 18px;padding-left:18px;color:#2d3748;font-size:13px}
.prog li{margin-bottom:6px}
.prog .go{margin-top:auto;display:inline-block;text-align:center;padding:11px 16px;
  border-radius:10px;background:var(--accent);color:#fff;font-weight:650;text-decoration:none}
.prog .go:hover{background:var(--accent-dark)}
.prog .badge2{margin-top:12px;font-size:11px;color:var(--muted);letter-spacing:.05em}
.stack{max-width:1080px;margin:0 auto;padding:0 28px 40px;color:#4a5568;font-size:13px}
.stack code{background:#eef2f8;border-radius:6px;padding:1px 6px;color:#14335c}
"""


def _program_card(program: dict) -> str:
    """Карточка программы на странице-портфолио."""
    items = "".join(f"<li>{wk.esc(item)}</li>" for item in program["features"])
    return f"""
<article class="prog">
  <span class="tag">{wk.esc(program['tag'])}</span>
  <h3>{wk.esc(program['title'])}</h3>
  <p class="lead">{wk.esc(program['lead'])}</p>
  <ul>{items}</ul>
  <a class="go" href="{program['href']}">Открыть калькулятор</a>
  <span class="badge2">{wk.esc(program['badge'])}</span>
</article>"""


def _landing_html() -> str:
    """HTML страницы-портфолио с двумя калькуляторами."""
    cards = "".join(_program_card(program) for program in PROGRAMS)
    return f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Инженерные калькуляторы: шнековый конвейер и гидравлическая сеть</title>
<style>{wk.CSS}{_LANDING_CSS}</style></head>
<body>
<header class="top"><div class="inside">
  <h1>Инженерные калькуляторы</h1>
  <span class="sub">расчёт оборудования, графики и отчёты PDF/Word</span>
  <span class="ver">PYTHON · FLASK</span>
</div></header>
<div class="hero">
  <h2>Две расчётные программы в одном веб-интерфейсе</h2>
  <p>Каждая программа считает инженерную задачу, подбирает оборудование по каталогу,
     строит схему и характеристики, проверяет условия работоспособности и формирует
     готовый отчёт в PDF и Word.</p>
</div>
<div class="wrap">{cards}</div>
<div class="stack">
  Стек: <code>Python</code> <code>Flask</code> <code>matplotlib</code>
  <code>reportlab</code> <code>python-docx</code> <code>pytest</code>.
  Исходный код и отчёты: <a href="https://github.com/viramax43-art/engine-portfolio">
  github.com/viramax43-art/engine-portfolio</a>.
</div>
<footer class="foot">{wk.esc(wk.PROGRAM_FOOTER)}</footer>
</body></html>"""


landing = Flask("engine-portfolio")


@landing.get("/")
def index() -> str:
    """Страница-портфолио."""
    return _landing_html()


@landing.get("/healthz")
def healthz():
    """Проверка живости для хостинга."""
    return {"status": "ok", "programs": ["/screw/", "/hydro/"]}


class _PrefixSlash:
    """Редирект /screw → /screw/ до маршрутизации по смонтированным префиксам."""

    def __init__(self, wsgi_app, prefixes):
        self.wsgi_app = wsgi_app
        self.prefixes = tuple(prefixes)

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path in self.prefixes:
            location = path + "/"
            if environ.get("QUERY_STRING"):
                location += "?" + environ["QUERY_STRING"]
            start_response("308 Permanent Redirect",
                           [("Location", location),
                            ("Content-Type", "text/plain; charset=utf-8")])
            return [f"Redirecting to {location}".encode("utf-8")]
        return self.wsgi_app(environ, start_response)


app = _PrefixSlash(
    DispatcherMiddleware(landing, {"/screw": screw_web.app, "/hydro": hydro_web.app}),
    ("/screw", "/hydro"),
)


def main() -> None:
    """Локальный запуск общего приложения: python app.py."""
    port = int(os.environ.get("PORT", "8000"))
    run_simple("127.0.0.1", port, app, use_reloader=False)


if __name__ == "__main__":
    main()

