FROM python:3.13-slim AS build
WORKDIR /src
COPY pyproject.toml ./
COPY extrude ./extrude
COPY eval ./eval
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EXTRUDE_DATA_DIR=/app/data

COPY --from=build /install /usr/local
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* && mkdir -p /app/data

EXPOSE 8000
CMD ["uvicorn", "extrude.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
