"""Скриншоты опубликованного сайта для портфолио (Playwright, Chromium).

    python -m pip install playwright && python -m playwright install chromium
    python deploy/screenshots.py --url https://<login>.pythonanywhere.com

Снимки кладутся в docs/screenshots/: portfolio.png — первый экран портфолио,
screw.png и hydro.png — страницы калькуляторов после расчёта примера
(полная высота страницы, ширина 1440 px).
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from playwright.sync_api import Page, sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "screenshots"
VIEWPORT = {"width": 1440, "height": 1000}


def shoot(page: Page, url: str, path: pathlib.Path, submit: bool = False,
          full_page: bool = True) -> None:
    """Открыть страницу, при необходимости нажать «Рассчитать» и сохранить снимок."""
    page.goto(url, wait_until="load", timeout=180_000)
    page.wait_for_timeout(1500)
    if submit:
        page.locator("button[type=submit]").first.click()
        page.wait_for_load_state("load", timeout=300_000)
        page.wait_for_timeout(2500)
    page.screenshot(path=str(path), full_page=full_page)
    print(f"  {url} → {path.relative_to(ROOT)} ({path.stat().st_size // 1024} КБ)")


def main() -> int:
    """Снять три скриншота живого сайта."""
    parser = argparse.ArgumentParser(description="Скриншоты сайта для портфолио")
    parser.add_argument("--url", required=True, help="адрес сайта, например https://login.pythonanywhere.com")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(viewport=VIEWPORT, device_scale_factor=1, locale="ru-RU")
        page = context.new_page()
        try:
            shoot(page, base + "/", OUT_DIR / "portfolio.png", full_page=False)
            shoot(page, base + "/screw/", OUT_DIR / "screw.png", submit=True)
            shoot(page, base + "/hydro/", OUT_DIR / "hydro.png", submit=True)
        finally:
            browser.close()
    print("Готово:", OUT_DIR.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
