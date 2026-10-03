FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml .
COPY app ./app
COPY plugins ./plugins
COPY alembic ./alembic
COPY alembic.ini .
RUN pip install --no-cache-dir ".[postgres,gdal]"

EXPOSE 8000
# 用工厂入口而不是 app.main:app：入口在启动前会校验 schema 版本，漂移就拒绝启动。
CMD ["uvicorn", "app.main:build", "--factory", "--host", "0.0.0.0", "--port", "8000"]
