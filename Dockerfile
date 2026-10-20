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

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python3 -c "import urllib.request,sys; r=urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4); sys.exit(0 if r.status==200 else 1)"

CMD ["python3", "-m", "aah"]
