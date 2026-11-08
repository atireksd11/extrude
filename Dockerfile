FROM python:3.12-slim-trixie
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EXTRUDE_DATA_DIR=/app/data
WORKDIR /app
COPY pyproject.toml ./
COPY extrude ./extrude
COPY eval ./eval
# Optional CA mount supports builds behind a trusted corporate/session proxy.
RUN --mount=type=secret,id=proxy_ca \
    apt-get update \
    && apt-get install -y --no-install-recommends \
       git ca-certificates kicad kicad-symbols kicad-footprints libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi \
    && pip install --no-cache-dir . \
    && useradd --create-home --uid 1000 extrude \
    && mkdir -p /app/data && chown extrude:extrude /app/data
USER extrude
EXPOSE 8000
CMD ["uvicorn", "extrude.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
