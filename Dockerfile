FROM python:3.12-slim-bookworm

RUN useradd --uid 10001 --create-home --home-dir /app --shell /usr/sbin/nologin aah \
    && mkdir -p /data \
    && chown aah:aah /data

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY aah ./aah
COPY openapi.yaml .

USER aah

ENV AAH_DATABASE_URL=sqlite+aiosqlite:////data/aah.db \
    AAH_HOST=0.0.0.0 \
    AAH_PORT=8080

EXPOSE 8080

CMD ["python3", "-m", "aah"]
