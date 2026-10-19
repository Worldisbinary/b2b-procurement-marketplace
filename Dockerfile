FROM python:3.12-slim AS builder
WORKDIR /build
ENV PIP_NO_CACHE_DIR=1
COPY pyproject.toml ./
RUN pip install --prefix=/install \
    "fastapi>=0.115" "sqlalchemy>=2.0" "uvicorn>=0.30" "prometheus-client>=0.20" "psycopg2-binary>=2.9"

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN useradd --create-home --uid 10001 app
COPY --from=builder /install /usr/local
WORKDIR /srv
COPY app ./app
COPY scripts ./scripts
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
