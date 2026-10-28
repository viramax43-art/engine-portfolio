"""Публикация проекта как Docker Space на Hugging Face (бесплатный CPU-инстанс).

Токен с правами write берётся из аргумента --token или переменной окружения HF_TOKEN:

    $env:HF_TOKEN = "hf_..."      # Windows PowerShell
    python deploy/hf_space.py

Скрипт создаёт (или обновляет) Space с Dockerfile из корня репозитория и загружает
только нужные файлы: код калькуляторов, общие модули, requirements, Dockerfile, скриншоты.
Сборка образа и запуск контейнера выполняются на стороне Hugging Face.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

from huggingface_hub import HfApi, create_repo

ROOT = Path(__file__).resolve().parent.parent
SPACE_TITLE = "Инженерные калькуляторы"
NEEDED = ("app.py", "requirements.txt", "Dockerfile", "common", "screw_conveyor", "hydro_net", "docs")

# Карточка Space: без этого блока front-matter Hugging Face не запустит Docker-контейнер.
CARD = """---
title: {title}
emoji: ⚙️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
short_description: Расчёт конвейера и гидросети с отчётами PDF/Word
---

{readme}
"""


def _staging_dir() -> Path:
    """Собрать временный каталог с файлами, которые уезжают в Space."""
    stage = Path(tempfile.mkdtemp(prefix="hf-space-"))
    for name in NEEDED:
        src = ROOT / name
        dst = stage / name
        if src.is_dir():
            shutil.copytree(src, dst,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests"))
        else:
            shutil.copy2(src, dst)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    (stage / "README.md").write_text(CARD.format(title=SPACE_TITLE, readme=readme),
                                     encoding="utf-8")
    return stage


def main() -> int:
    """Создать/обновить Space и напечатать адреса."""
    parser = argparse.ArgumentParser(description="Развернуть Docker Space на Hugging Face")
    parser.add_argument("--repo", default="engine-portfolio", help="имя Space (по умолчанию engine-portfolio)")
    parser.add_argument("--token", default=os.environ.get("HF_TOKEN"),
                        help="токен Hugging Face с правами write (по умолчанию из HF_TOKEN)")
    parser.add_argument("--private", action="store_true", help="сделать Space приватным")
    args = parser.parse_args()
    if not args.token:
        print("Нужен токен: --token или переменная окружения HF_TOKEN", file=sys.stderr)
        return 2

    api = HfApi(token=args.token)
    user = api.whoami()["name"]
    repo_id = f"{user}/{args.repo}"
    url = create_repo(repo_id, repo_type="space", space_sdk="docker",
                      private=args.private, exist_ok=True, token=args.token)
    stage = _staging_dir()
    try:
        api.upload_folder(folder_path=str(stage), repo_id=repo_id, repo_type="space",
                          commit_message="deploy: инженерные калькуляторы (Flask, gunicorn, Docker)")
    finally:
        shutil.rmtree(stage, ignore_errors=True)

    host = f"{user}-{args.repo}".lower().replace("_", "-")
    print("Space:      " + str(url))
    print("Приложение: https://" + host + ".hf.space")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
