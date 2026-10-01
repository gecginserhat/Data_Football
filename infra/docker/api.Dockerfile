# Kurgu API ve worker imajı (aynı paket, ADR-0001).
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1
WORKDIR /app

# Bağımlılıklar önce, kaynak kod sonra (katman önbelleği).
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY analytics/pyproject.toml analytics/pyproject.toml
RUN uv sync --frozen --no-dev --all-packages --no-install-workspace

COPY apps/api apps/api
COPY analytics analytics

FROM base AS dev
# Geliştirmede kaynaklar volume ile bağlanır; paketler düzenlenebilir kurulur.
RUN uv sync --frozen --no-dev --all-packages
EXPOSE 8000

FROM base AS prod
RUN uv sync --frozen --no-dev --all-packages --no-editable \
 && useradd --system --uid 10001 kurgu
USER kurgu
EXPOSE 8000
CMD ["uvicorn", "kurgu_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
