# Образ для хостингов с Docker (Render, Hugging Face Spaces, Koyeb и др.).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MPLCONFIGDIR=/tmp/mpl \
    OUT_DIR=/tmp/out \
    PORT=7860

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 7860

CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT} --timeout 180 --workers 1 --threads 4"]
