FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml alembic.ini ./
COPY backend ./backend
COPY configs ./configs
RUN pip install --no-cache-dir .

ENV CONFIG_DIR=/app/configs
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
