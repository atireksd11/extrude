FROM python:3.13-slim AS build
WORKDIR /src
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY extrude ./extrude
COPY eval ./eval
RUN pip install --no-cache-dir --prefix=/install .

FROM kicad/kicad:10.0.4@sha256:770e2fa006695077b5ba218742d5c3137896af91257b2ca971243fa56b01bb86
USER root
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EXTRUDE_DATA_DIR=/app/data

COPY --from=build /usr/local /usr/local
COPY --from=build /install /usr/local
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && ldconfig && kicad-cli version \
    && rm -rf /var/lib/apt/lists/* && mkdir -p /app/data

EXPOSE 8000
CMD ["uvicorn", "extrude.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
