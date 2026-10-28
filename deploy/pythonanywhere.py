"""Публикация проекта на PythonAnywhere (бесплатный тариф) через Web API.

Нужны имя пользователя и API-токен (Account → API token):

    python deploy/pythonanywhere.py --username <login> --token <token>

Что делает скрипт:
 1) загружает код в /home/<login>/engine-portfolio;
 2) создаёт веб-приложение https://<login>.pythonanywhere.com (если его ещё нет);
 3) прописывает WSGI-файл, который подключает app.py;
 4) в bash-консоли ставит зависимости (pip install --user -r requirements.txt);
 5) перезагружает приложение и проверяет /healthz.

Повторный запуск обновляет код и перезагружает приложение (идемпотентно).
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

WSGI_TEMPLATE = '''"""WSGI-конфигурация PythonAnywhere для проекта {project}."""
import os
import sys

PROJECT = "{remote}"
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)

# На PythonAnywhere приложение отдаётся с корня домена: / — портфолио,
# /screw/ и /hydro/ — калькуляторы (префиксы задаёт сам app.py).
os.environ.setdefault("MPLCONFIGDIR", os.path.join(PROJECT, ".mplconfig"))

from app import app as application  # noqa: E402
'''


def _api(user: str, tail: str) -> str:
    return API_ROOT.format(user=user) + tail


def _check(response: requests.Response, action: str) -> requests.Response:
    if response.status_code >= 400:
        raise SystemExit(f"{action}: HTTP {response.status_code} {response.text[:400]}")
    return response


def upload_code(session: requests.Session, user: str, remote_root: str, dry_run: bool) -> None:
    """Загрузить файлы проекта через Files API."""
    for name in CODE_FILES:
        local = ROOT / name
        if not local.is_file():
            raise SystemExit(f"нет файла {local}")
        if dry_run:
            print("  upload", name)
            continue
        with local.open("rb") as handle:
            files = {"content": (local.name, handle)}
            response = session.post(_api(user, f"files/path{remote_root}/{name}"), files=files,
                                    timeout=180)
        _check(response, f"загрузка {name}")
        print("  загружено:", name)


def ensure_webapp(session: requests.Session, user: str, domain: str, python_version: str) -> None:
    """Создать веб-приложение, если его ещё нет."""
    response = _check(session.get(_api(user, "webapps/"), timeout=60), "список web apps")
    if any(app.get("domain_name") == domain for app in response.json()):
        print("  web app уже существует:", domain)
        return
    response = session.post(_api(user, "webapps/"), timeout=120,
                            data={"domain_name": domain, "python_version": python_version})
    if response.status_code >= 400 and "exist" in response.text.lower():
        print("  web app уже существует:", domain)
        return
    _check(response, "создание web app")
    print("  создано web app:", domain)


def write_wsgi(session: requests.Session, user: str, domain: str, remote_root: str,
               dry_run: bool) -> None:
    """Записать WSGI-файл, подключающий app.py."""
    wsgi_path = f"/var/www/{domain.replace('.', '_')}_wsgi.py"
    content = WSGI_TEMPLATE.format(project=PROJECT_NAME, remote=remote_root)
    if dry_run:
        print("  wsgi", wsgi_path)
        return
    response = session.post(_api(user, f"files/path{wsgi_path}"),
                            files={"content": ("wsgi.py", content.encode("utf-8"))}, timeout=120)
    _check(response, "запись WSGI")
    print("  WSGI обновлён:", wsgi_path)



def install_deps(session: requests.Session, user: str, remote_root: str, python_bin: str,
                 dry_run: bool, timeout_s: int = 900) -> None:
    """Поставить зависимости в bash-консоли (у PythonAnywhere нет API для команд)."""
    command = (f"cd {remote_root} && {python_bin} -m pip install --user --upgrade pip "
               f"-r requirements.txt && echo __DEPS_OK__")
    if dry_run:
        print("  console:", command)
        return
    response = _check(session.post(_api(user, "consoles/"),
                                   json={"executable": "bash", "arguments": []}, timeout=120),
                      "создание консоли")
    console_id = response.json()["id"]
    _check(session.post(_api(user, f"consoles/{console_id}/send_stdin/"),
                        data={"input": command + "\n"}, timeout=60), "отправка команды")
    print("  установка зависимостей в консоли", console_id, "(может занять 2-5 минут)")
    deadline = time.time() + timeout_s
    seen = ""
    while time.time() < deadline:
        time.sleep(10)
        response = session.get(_api(user, f"consoles/{console_id}/get_latest_output/"), timeout=60)
        if response.status_code >= 400:
            continue
        seen = response.json().get("output", seen)
        if "__DEPS_OK__" in seen:
            print("  зависимости установлены")
            return
        if "ERROR: " in seen:
            print(seen[-1500:])
            raise SystemExit("pip завершился с ошибкой")
    print(seen[-1500:])
    raise SystemExit("не дождались окончания установки зависимостей")


def reload_webapp(session: requests.Session, user: str, domain: str, dry_run: bool) -> None:
    """Перезагрузить веб-приложение."""
    if dry_run:
        print("  reload", domain)
        return
    _check(session.post(_api(user, f"webapps/{domain}/reload/"), timeout=120), "перезагрузка")
    print("  приложение перезагружено")


def check_site(url: str, attempts: int = 12) -> bool:
    """Дождаться ответа /healthz после перезагрузки."""
    for _ in range(attempts):
        try:
            response = requests.get(url.rstrip("/") + "/healthz", timeout=30)
            if response.status_code == 200:
                print("  /healthz:", response.text[:120])
                return True
        except requests.RequestException:
            pass
        time.sleep(5)
    return False



def main() -> int:
    """Выполнить деплой по шагам."""
    parser = argparse.ArgumentParser(description="Деплой на PythonAnywhere через Web API")
    parser.add_argument("--username", required=True, help="логин PythonAnywhere")
    parser.add_argument("--token", required=True, help="API-токен (Account → API token)")
    parser.add_argument("--python", default="python310",
                        help="версия Python для web app: python310 или python313")
    parser.add_argument("--dry-run", action="store_true", help="только показать шаги")
    args = parser.parse_args()

    digits = args.python.removeprefix("python")
    python_bin = f"python{digits[0]}.{digits[1:]}"
    domain = f"{args.username}.pythonanywhere.com"
    remote_root = f"/home/{args.username}/{PROJECT_NAME}"

    session = requests.Session()
    session.headers["Authorization"] = f"Token {args.token}"

    print(f"PythonAnywhere: {domain}  (Python {args.python}, каталог {remote_root})")
    print("1) загрузка кода")
    upload_code(session, args.username, remote_root, args.dry_run)
    print("2) веб-приложение")
    if args.dry_run:
        print("  webapp", domain, args.python)
    else:
        ensure_webapp(session, args.username, domain, args.python)
    print("3) WSGI")
    write_wsgi(session, args.username, domain, remote_root, args.dry_run)
    print("4) зависимости")
    install_deps(session, args.username, remote_root, python_bin, args.dry_run)
    print("5) перезапуск")
    reload_webapp(session, args.username, domain, args.dry_run)
    url = f"https://{domain}"
    if args.dry_run:
        print("Сайт:", url)
        return 0
    print("6) проверка")
    ok = check_site(url)
    print("Сайт:", url, "-", "работает" if ok else "проверьте логи web app")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

