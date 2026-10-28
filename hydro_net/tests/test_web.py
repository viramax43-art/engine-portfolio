"""Тесты веб-интерфейса гидравлической сети (Flask test client)."""

from __future__ import annotations

import re

import pytest

from hydro_net import catalog as cat
from hydro_net import web
from hydro_net.core import EXAMPLES


@pytest.fixture()
def client():
    web.CACHE.clear()
    web.app.config.update(TESTING=True)
    return web.app.test_client()


def _form(index: int = 0, **overrides: str) -> dict[str, str]:
    """Данные формы по примеру каталога с возможностью подмены полей."""
    values = web._values_from_input(list(EXAMPLES.values())[index])
    values.update(overrides)
    return values


def test_index_page_has_form_and_pump_list(client):
    page = client.get("/")
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "Исходные данные" in html
    assert '<select name="pump">' in html
    assert "Автоподбор по каталогу" in html
    for model in cat.PUMPS:
        assert model in html


def test_examples_prefill_form(client):
    for index, inp in enumerate(EXAMPLES.values()):
        page = client.get(f"/?example={index}")
        html = page.get_data(as_text=True)
        assert page.status_code == 200
        pressure = re.search(r'<select name="dn">(.*?)</select>', html, re.S).group(1)
        suction = re.search(r'<select name="suction_dn">(.*?)</select>', html, re.S).group(1)
        assert f'<option value="{inp.sections[1].dn}" selected>' in pressure
        assert f'<option value="{inp.sections[0].dn}" selected>' in suction


def test_calculate_with_catalog_selection(client):
    page = client.post("/", data=_form(0, pump="auto"))
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "Результат расчёта" in html
    assert "Гидравлический расчёт участков" in html
    assert "Подбор насоса по каталогу" in html
    assert html.count("data:image/png;base64,") == 3


def test_calculate_with_fixed_pump(client):
    model = "НК 50-160"
    page = client.post("/", data=_form(1, pump=model))
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "Подбор насоса по каталогу" not in html
    assert model in html
    assert "Результат расчёта" in html


def test_unknown_pump_falls_back_to_autoselect(client):
    page = client.post("/", data=_form(0, pump="нет такого насоса"))
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "Подбор насоса по каталогу" in html


def test_invalid_number_shows_error(client):
    page = client.post("/", data=_form(0, flow="много"))
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "Проверьте исходные данные" in html
    assert "Расход, м³/ч" in html


def test_download_reports(client, tmp_path, monkeypatch):
    monkeypatch.setattr(web, "OUT_DIR", str(tmp_path))
    page = client.post("/", data=_form(0, pump="auto"))
    html = page.get_data(as_text=True)
    match = re.search(r"/download/([^/]+)/pdf", html)
    assert match is not None
    token = match.group(1)

    pdf = client.get(f"/download/{token}/pdf")
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    assert pdf.data.startswith(b"%PDF")

    docx = client.get(f"/download/{token}/docx")
    assert docx.status_code == 200
    assert docx.data.startswith(b"PK")


def test_download_unknown_token_or_format(client):
    page = client.post("/", data=_form(0))
    token = re.search(r"/download/([^/]+)/pdf",
                      page.get_data(as_text=True)).group(1)
    assert client.get("/download/nope/pdf").status_code == 404
    assert client.get(f"/download/{token}/txt").status_code == 404
