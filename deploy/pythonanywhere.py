"""Публикация проекта на PythonAnywhere (бесплатный тариф) через Web API.

    python deploy/pythonanywhere.py --username <login> --token <token>

Шаги:
 1) находит (или создаёт) веб-приложение https://<login>.pythonanywhere.com;
 2) переключает его на каталог /home/<login>/engine-portfolio;
 3) загружает код калькуляторов;
 4) пишет WSGI-файл: он подключает app.py и один раз доставляет зависимости
    в virtualenv приложения (на бесплатном тарифе нельзя запустить команду
    в консоли по API — консоль стартует только из браузера);
 5) перезапускает приложение и ждёт ответа /healthz.

Повторный запуск обновляет код и перезапускает приложение (идемпотентно).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
API_ROOT = "https://www.pythonanywhere.com/api/v0/user/{user}/"
PROJECT_NAME = "engine-portfolio"

CODE_FILES = (
    "app.py",
    "requirements.txt",
    "common/__init__.py",
    "common/docx_kit.py",
    "common/fmt.py",
    "common/hydraulics.py",
    "common/pdf_kit.py",
    "common/plotkit.py",
    "common/web_kit.py",
    "screw_conveyor/__init__.py",
    "screw_conveyor/catalog.py",
    "screw_conveyor/charts.py",
    "screw_conveyor/cli.py",
    "screw_conveyor/core.py",
    "screw_conveyor/report.py",
    "screw_conveyor/web.py",
    "hydro_net/__init__.py",
    "hydro_net/catalog.py",
    "hydro_net/charts.py",
    "hydro_net/cli.py",
    "hydro_net/core.py",
    "hydro_net/report.py",
    "hydro_net/web.py",
)

WSGI_TEMPLATE = '''"""WSGI-конфигурация PythonAnywhere для проекта {project}.

При первом запросе доставляет зависимости в virtualenv приложения: у бесплатного
тарифа нет API для запуска команд, консоль стартует только из браузера, поэтому
установка выполняется из самого WSGI и помечается маркером в /tmp.
"""
import hashlib
import os
import subprocess
import sys

PROJECT = "{remote}"
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)

# На PythonAnywhere приложение отдаётся с корня домена: / — портфолио,
# /screw/ и /hydro/ — калькуляторы (префиксы задаёт сам app.py).
os.environ.setdefault("MPLCONFIGDIR", os.path.join(PROJECT, ".mplconfig"))
os.environ.setdefault("OUT_DIR", "/tmp/out")

DEPS_LOG = "/tmp/engine-portfolio-deps.log"


def _python_bin():
    """Вернуть python текущего интерпретатора (под uwsgi sys.executable — сам uwsgi)."""
    major, minor = sys.version_info[:2]
    candidates = [sys.executable]
    for name in ("python", "python%d.%d" % (major, minor), "python%d" % major):
        candidates.append(os.path.join(sys.prefix, "bin", name))
        candidates.append(os.path.join(PROJECT, ".venv", "bin", name))
    for path in candidates:
        if path and os.path.basename(path).startswith("python") and os.path.exists(path):
            return path
    return "python%d.%d" % (major, minor)


def _ensure_requirements():
    """Один раз поставить зависимости из requirements.txt (маркер по хешу файла)."""
    req = os.path.join(PROJECT, "requirements.txt")
    with open(req, "rb") as handle:
        tag = hashlib.sha1(handle.read()).hexdigest()[:10]
    marker = "/tmp/engine-portfolio-deps-{{tag}}.ok".format(tag=tag)
    if os.path.exists(marker):
        return
    python_bin = _python_bin()
    with open(DEPS_LOG, "ab") as log:
        log.write(b"\\n--- pip install " + tag.encode() + b" via " + python_bin.encode() + b" ---\\n")
        log.flush()
        result = subprocess.run(
            [python_bin, "-m", "pip", "install", "--no-cache-dir",
             "--disable-pip-version-check", "-r", req],
            cwd=PROJECT, stdout=log, stderr=subprocess.STDOUT, timeout=1200,
        )
    if result.returncode != 0:
        raise RuntimeError("pip install завершился с кодом %d" % result.returncode)
    with open(marker, "w", encoding="utf-8") as handle:
        handle.write("ok")


try:
    _ensure_requirements()
except Exception as exc:  # noqa: BLE001  (ошибку видно в логе, следующий запрос повторит)
    with open(DEPS_LOG, "a", encoding="utf-8") as log:
        log.write("\\nWSGI bootstrap error: %r\\n" % (exc,))

from app import app as application  # noqa: E402
'''


def _api(user: str, tail: str) -> str:
    return API_ROOT.format(user=user) + tail


def _check(response: requests.Response, action: str) -> requests.Response:
    if response.status_code >= 400:
        raise SystemExit(f"{action}: HTTP {response.status_code} {response.text[:400]}")
    return response


def _request(session: requests.Session, method: str, url: str, **kwargs) -> requests.Response:
    """Выполнить запрос к API, повторив его при 429 (лимит 40 запросов в минуту)."""
    delay = 5
    response = session.request(method, url, **kwargs)
    for _ in range(5):
        if response.status_code != 429:
            return response
        wait = int(response.headers.get("Retry-After") or 0) or delay
        print(f"  лимит API: пауза {wait} с")
        time.sleep(wait)
        delay = min(delay * 2, 60)
        response = session.request(method, url, **kwargs)
    return response


def _site_page(domain: str, path: str = "/") -> str:
    """Вернуть первые 2 КБ ответа сайта (пустая строка, если недоступен)."""
    try:
        response = requests.get(f"https://{domain}{path}", timeout=60)
    except requests.RequestException:
        return ""
    return response.text[:2048]


def find_webapp(session: requests.Session, user: str, domain: str) -> dict | None:
    """Вернуть описание веб-приложения или None, если его ещё нет."""
    response = _check(_request(session, "GET", _api(user, "webapps/"), timeout=60),
                      "список web apps")
    for app in response.json():
        if app.get("domain_name") == domain:
            return app
    return None


def configure_webapp(session: requests.Session, user: str, domain: str, remote_root: str,
                     python_version: str, venv: str, dry_run: bool) -> dict:
    """Создать приложение или переключить существующее на наш каталог."""
    app = find_webapp(session, user, domain)
    if app is None:
        if dry_run:
            print("  создать web app:", domain, python_version, "->", remote_root)
            return {"python_version": python_version, "virtualenv_path": venv}
        response = _check(_request(session, "POST", _api(user, "webapps/"), timeout=180, data={
            "domain_name": domain,
            "python_version": python_version,
            "source_directory": remote_root,
            "working_directory": remote_root,
        }), "создание web app")
        print("  создано web app:", domain, response.json().get("python_version"))
        app = find_webapp(session, user, domain) or app

    patch = {"source_directory": remote_root, "working_directory": remote_root}
    if venv and (app or {}).get("virtualenv_path") != venv:
        patch["virtualenv_path"] = venv
    if dry_run:
        print("  PATCH", domain, patch)
        return app or {}
    response = _check(_request(session, "PATCH", _api(user, f"webapps/{domain}/"), json=patch,
                               timeout=120), "настройка web app")
    current = response.json() if response.text else (app or {})
    venv_path = current.get("virtualenv_path") or ""
    print("  каталог приложения:", remote_root, "| Python", current.get("python_version"),
          "| venv", venv_path or "системный python")
    if not venv_path:
        print("  внимание: у web app не выбран virtualenv — pip из WSGI не сможет писать в")
        print("  site-packages. Укажите существующий venv через --venv и запустите снова.")
    return current


def write_wsgi(session: requests.Session, user: str, domain: str, remote_root: str,
               dry_run: bool) -> str:
    """Записать WSGI-файл, подключающий app.py (с доставкой зависимостей)."""
    wsgi_path = f"/var/www/{domain.replace('.', '_')}_wsgi.py"
    content = WSGI_TEMPLATE.format(project=PROJECT_NAME, remote=remote_root)
    if dry_run:
        print("  wsgi", wsgi_path)
        return wsgi_path
    response = _request(session, "POST", _api(user, f"files/path{wsgi_path}"),
                        files={"content": ("wsgi.py", content.encode("utf-8"))}, timeout=120)
    _check(response, "запись WSGI")
    print("  WSGI обновлён:", wsgi_path)
    return wsgi_path


def upload_code(session: requests.Session, user: str, remote_root: str, dry_run: bool) -> None:
    """Загрузить файлы проекта через Files API."""
    for name in CODE_FILES:
        local = ROOT / name
        if not local.is_file():
            raise SystemExit(f"нет файла {local}")
        if dry_run:
            continue
        payload = local.read_bytes()
        response = _request(session, "POST", _api(user, f"files/path{remote_root}/{name}"),
                            files={"content": (local.name, payload)}, timeout=180)
        _check(response, f"загрузка {name}")
    print("  загружено файлов:", len(CODE_FILES))



def reload_webapp(session: requests.Session, user: str, domain: str, dry_run: bool,
                  quiet: bool = False) -> bool:
    """Перезагрузить веб-приложение; вернуть True, если PythonAnywhere принял reload."""
    if dry_run:
        print("  reload", domain)
        return True
    response = _request(session, "POST", _api(user, f"webapps/{domain}/reload/"), timeout=300)
    if response.status_code < 400:
        if not quiet:
            print("  приложение перезагружено")
        return True
    if not quiet:
        print(f"  reload: HTTP {response.status_code}")
        if "Coming Soon" in _site_page(domain):
            print("  домен отдаёт заглушку PythonAnywhere — web app не запущен.")
        print("  действие: откройте https://www.pythonanywhere.com/user/"
              f"{user}/webapps/, нажмите «Run until 3 months from today» (если приложение")
        print("  истекло) и затем Reload; после этого запустите скрипт повторно.")
    return False


def warmup(session: requests.Session, user: str, url: str, domain: str, dry_run: bool,
           rounds: int = 3) -> bool:
    """Разбудить приложение и дождаться /healthz.

    Первый запрос ставит зависимости (может занять пару минут), поэтому после
    неудачной попытки приложение перезагружается и запрос повторяется.
    """
    if dry_run:
        print("  warmup", url)
        return True
    for attempt in range(1, rounds + 1):
        print(f"  попытка {attempt}: GET /healthz")
        try:
            response = requests.get(url.rstrip("/") + "/healthz", timeout=600)
            if response.status_code == 200:
                print("  /healthz:", response.text.strip()[:120])
                return True
            print("  /healthz:", response.status_code, response.text.strip()[:160])
        except requests.RequestException as exc:
            print("  /healthz: ошибка запроса", type(exc).__name__)
        if not reload_webapp(session, user, domain, dry_run=False):
            return False
        time.sleep(10)
    return False


def fetch_log(session: requests.Session, user: str, domain: str) -> None:
    """Показать хвост лога ошибок приложения и лога доставки зависимостей.

    Логи PythonAnywhere лежат в /var/log/<домен>.error.log, лог установки пакетов
    пишет сам WSGI в /tmp/engine-portfolio-deps.log.
    """
    paths = ((f"/var/log/{domain}.error.log", "error log"),
             (f"/var/log/{domain}.server.log", "server log"),
             ("/tmp/engine-portfolio-deps.log", "deps log"))
    for path, title in paths:
        response = _request(session, "GET", _api(user, f"files/path{path}"), timeout=60)
        if response.status_code != 200:
            print(f"  {title}: недоступен (HTTP {response.status_code})")
            continue
        lines = [line for line in response.text.splitlines() if line.strip()]
        print(f"  {title} ({path}), последние строки:")
        print("\n".join("    " + line for line in lines[-20:]))


def main() -> int:
    """Выполнить деплой по шагам."""
    parser = argparse.ArgumentParser(description="Деплой на PythonAnywhere через Web API")
    parser.add_argument("--username", required=True, help="логин PythonAnywhere")
    parser.add_argument("--token", required=True, help="API-токен (Account → API token)")
    parser.add_argument("--python", default="python313",
                        help="версия Python для нового web app: python313 (по умолчанию)")
    parser.add_argument("--remote", default="", help="каталог на сервере (~/engine-portfolio)")
    parser.add_argument("--venv", default="",
                        help="virtualenv приложения, например /home/<login>/mysite/venv "
                             "(нужен, чтобы WSGI мог доставить зависимости)")
    parser.add_argument("--dry-run", action="store_true", help="только показать шаги")
    args = parser.parse_args()

    domain = f"{args.username}.pythonanywhere.com"
    remote_root = args.remote or f"/home/{args.username}/{PROJECT_NAME}"
    url = f"https://{domain}"
    session = requests.Session()
    session.headers["Authorization"] = f"Token {args.token}"

    print(f"PythonAnywhere: {url}  (каталог {remote_root})")
    print("1) веб-приложение")
    configure_webapp(session, args.username, domain, remote_root, args.python, args.venv,
                     args.dry_run)
    print("2) загрузка кода")
    upload_code(session, args.username, remote_root, args.dry_run)
    print("3) WSGI")
    write_wsgi(session, args.username, domain, remote_root, args.dry_run)
    print("4) перезапуск и доставка зависимостей")
    reload_webapp(session, args.username, domain, args.dry_run)
    ok = warmup(session, args.username, url, domain, args.dry_run)
    print("Сайт:", url, "-", "работает" if ok else "не поднялся")
    if not ok and not args.dry_run:
        print("5) логи")
        fetch_log(session, args.username, domain)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

