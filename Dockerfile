# syntax=docker/dockerfile:1
FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 AS build
WORKDIR /src
COPY pyproject.toml ./
COPY extrude ./extrude
COPY eval ./eval
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir --prefix=/install .

FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EXTRUDE_DATA_DIR=/app/data \
    EXTRUDE_HOSTED=1

COPY --from=build /install /usr/local
WORKDIR /app
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* && mkdir -p /app/data && chown 10001:10001 /app/data

# Build tooling and its vendored libraries are unnecessary at runtime.
RUN python -m pip uninstall -y pip

USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "extrude.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
