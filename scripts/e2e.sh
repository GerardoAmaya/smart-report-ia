#!/usr/bin/env bash
# Pruebas extremo a extremo **contra el sistema levantado**, no contra
# simulaciones. Es lo que PLAN.md exige para dar la fase 7 por terminada.
#
# Lo unico que se sustituye es a que servidor le habla el bot: un Telegram falso
# que sirve una foto y guarda los mensajes. El codigo que corre es el mismo de
# produccion, incluido el cliente de Telegram; lo que cambia es una variable de
# entorno.
#
# Existe como script porque hacerlo a mano es una danza de variables que se
# olvida: basta reiniciar `worker` sin ellas para que vuelva a hablarle a
# Telegram de verdad, y entonces las pruebas fallan por un motivo que no tiene
# nada que ver con lo que prueban. Paso.
set -euo pipefail

cd "$(dirname "$0")/.."

[[ -f .env ]] || { echo "Falta .env. Copiar de .env.example." >&2; exit 1; }
set -a; . ./.env; set +a

[[ -n "${DEMO_PASSWORD:-}" ]] || {
  echo "DEMO_PASSWORD hace falta: las pruebas entran al tablero con el." >&2; exit 1; }
[[ -n "${TELEGRAM_WEBHOOK_SECRET:-}" ]] || {
  echo "TELEGRAM_WEBHOOK_SECRET hace falta: el webhook falla cerrado." >&2; exit 1; }

export TELEGRAM_API_BASE_URL="http://telegram-falso:8099/bot"
export TELEGRAM_API_FILE_URL="http://telegram-falso:8099/file/bot"

echo "Levantando el stack con el Telegram falso…"
docker compose --profile e2e up -d

echo -n "Esperando a que la API responda"
for _ in $(seq 1 40); do
  if curl -sf --max-time 3 http://localhost:8000/health >/dev/null 2>&1; then break; fi
  echo -n "."; sleep 2
done
echo

# Que el bot apunte al falso se comprueba, no se supone: si `worker` quedo con
# la configuracion vieja, las pruebas fallarian por una descarga a Telegram de
# verdad y el motivo no apuntaria aqui.
destino=$(docker compose exec -T worker python -c \
  "from app.config import settings; print(settings.telegram_api_base_url)" 2>/dev/null | tr -d '\r')
if [[ "$destino" != "http://telegram-falso:8099/bot" ]]; then
  echo "El trabajador apunta a ${destino}, no al Telegram falso." >&2
  echo "Levantarlo con: docker compose --profile e2e up -d --force-recreate worker" >&2
  exit 1
fi
echo "El bot apunta al Telegram falso."

curl -sf -X POST --max-time 5 http://localhost:8099/bot1/_limpiar >/dev/null || true

# Con --solo-levantar se para aqui: CI levanta el sistema, instala lo suyo con
# cache, y despues corre las pruebas.
if [[ "${1:-}" == "--solo-levantar" ]]; then
  echo "Sistema listo."
  exit 0
fi

cd frontend
DEMO_PASSWORD="$DEMO_PASSWORD" \
TELEGRAM_WEBHOOK_SECRET="$TELEGRAM_WEBHOOK_SECRET" \
  npx playwright test "$@"
