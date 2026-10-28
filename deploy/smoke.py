"""Дымовой тест опубликованного сайта: страницы, расчёт по форме, отчёты.

    python deploy/smoke.py --url https://<login>.pythonanywhere.com

Проверяет, что отдаются `/`, `/screw/`, `/hydro/`, `/healthz`, что формы
считают пример по умолчанию и что выгрузка PDF и Word возвращает файл.
Код возврата 0 — всё работает, 1 — есть проблемы.
"""

from __future__ import annotations

import argparse
import html
import re
import sys

import requests

PAGES = ("/", "/screw/", "/hydro/", "/healthz")
CALCULATORS = ("/screw/", "/hydro/")


def form_fields(page: str) -> dict[str, str]:
    """Значения формы по умолчанию: все input и выбранные пункты select."""
    fields: dict[str, str] = {}
    for tag in re.findall(r"<input\b[^>]*>", page):
        name = re.search(r'name="([^"]+)"', tag)
        if not name:
            continue
        value = re.search(r'value="([^"]*)"', tag)
        fields[name.group(1)] = html.unescape(value.group(1)) if value else ""
    for tag in re.findall(r"<select\b.*?</select>", page, re.S):
        name = re.search(r'name="([^"]+)"', tag)
        if not name:
            continue
        selected = re.search(r'<option[^>]*value="([^"]*)"[^>]*selected', tag)
        options = re.findall(r'<option[^>]*value="([^"]*)"', tag)
        if selected:
            fields[name.group(1)] = html.unescape(selected.group(1))
        elif options:
            fields[name.group(1)] = html.unescape(options[0])
    return fields


def check_pages(session: requests.Session, base: str) -> bool:
    """Проверить доступность основных страниц."""
    ok = True
    for path in PAGES:
        try:
            response = session.get(base + path, timeout=180)
        except requests.RequestException as exc:
            print(f"  {path}: ошибка запроса {type(exc).__name__}")
            ok = False
            continue
        print(f"  {path}: HTTP {response.status_code}, {len(response.text)} символов")
        ok &= response.status_code == 200
    return ok


def check_calculator(session: requests.Session, base: str, prefix: str) -> bool:
    """Отправить форму с примером по умолчанию и скачать отчёты."""
    ok = True
    page = session.get(base + prefix, timeout=180)
    if page.status_code != 200:
        print(f"  {prefix}: форма недоступна (HTTP {page.status_code})")
        return False
    result = session.post(base + prefix, data=form_fields(page.text), timeout=600)
    print(f"  {prefix}: расчёт HTTP {result.status_code}, {len(result.text)} символов")
    ok &= result.status_code == 200
    links = list(dict.fromkeys(re.findall(r'href="([^"]*/download/[^"]+)"', result.text)))
    if not links:
        print(f"  {prefix}: ссылок на отчёты нет — расчёт не выполнился")
        return False
    for link in links:
        url = link if link.startswith("http") else base + link
        report = session.get(url, timeout=600)
        kind = report.headers.get("Content-Type", "")
        print(f"  {prefix}: {link} → HTTP {report.status_code}, {kind}, {len(report.content)} байт")
        ok &= report.status_code == 200 and len(report.content) > 1000
    return ok


def main() -> int:
    """Проверить опубликованный сайт и вернуть код результата."""
    parser = argparse.ArgumentParser(description="Дымовой тест опубликованного сайта")
    parser.add_argument("--url", required=True, help="адрес сайта, например https://login.pythonanywhere.com")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    session = requests.Session()
    print(f"Сайт: {base}")
    print("1) страницы")
    ok = check_pages(session, base)
    print("2) калькуляторы")
    for prefix in CALCULATORS:
        ok &= check_calculator(session, base, prefix)
    print("Итог:", "всё работает" if ok else "есть проблемы")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
