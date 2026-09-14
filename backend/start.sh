#!/bin/sh
# Migraciones antes de servir. Van aca y no en un hook del proveedor: un hook
# que no corre falla en silencio, este falla fuerte y no arranca.
set -e
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 ${RELOAD:+--reload}
