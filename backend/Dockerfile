FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends adduser libreoffice-writer fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system --gid 10001 converter \
    && adduser --system --uid 10001 --ingroup converter --home /home/converter converter \
    && mkdir -p /data \
    && chown 10001:10001 /data

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

ENV HOME=/home/converter
USER 10001:10001

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
