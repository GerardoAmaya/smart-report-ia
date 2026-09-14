FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# Capa de dependencias separada del codigo: un cambio en app/ no reinstala todo.
COPY pyproject.toml ./
RUN mkdir -p app && touch app/__init__.py \
    && pip install --no-cache-dir -e ".[dev]"

COPY . .
EXPOSE 8000
CMD ["./start.sh"]
