#!/bin/sh
# Registra el webhook de Telegram contra el dominio del despliegue.
#
# Aparte de `tunnel.sh` porque aquel levanta un tunel y lo borra al salir; este
# apunta a algo permanente y no se deshace solo. Se corre una vez al desplegar,
# y otra vez si cambia el dominio.
#
#   ./deploy/registrar-webhook.sh
set -e

ENV_FILE="${1:-.env.prod}"
if [ ! -f "$ENV_FILE" ]; then
  echo "No encuentro $ENV_FILE. Es donde viven el token y el dominio." >&2
  exit 1
fi

# shellcheck disable=SC1090
. "$ENV_FILE"

if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_WEBHOOK_SECRET" ] || [ -z "$DOMINIO" ]; then
  echo "Faltan TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET o DOMINIO en $ENV_FILE" >&2
  exit 1
fi

API="https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}"
WEBHOOK="https://${DOMINIO}/webhooks/telegram"

# Comprobar que el sitio contesta antes de decirle a Telegram que mande ahi.
# Sin esto, un dominio mal apuntado se descubre cuando alguien reporta y no
# pasa nada. Un 403 es la respuesta correcta a una peticion sin secreto: dice
# que la API esta viva y que el secreto se comprueba.
CODIGO="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$WEBHOOK" \
  -H 'content-type: application/json' -d '{}' || echo 000)"
if [ "$CODIGO" != "403" ]; then
  echo "El webhook contesto $CODIGO y se esperaba 403." >&2
  echo "Revisa que el dominio apunte al servidor y que Caddy tenga certificado." >&2
  exit 1
fi

# allowed_updates limita a lo que sabemos manejar: cada tipo que no se pide es
# superficie que no hay que defender. Sin callback_query no vuelven las
# confirmaciones de categoria y los botones giran para siempre.
RESPUESTA="$(curl -sS -X POST "${API}/setWebhook" \
  --data-urlencode "url=${WEBHOOK}" \
  --data-urlencode "secret_token=${TELEGRAM_WEBHOOK_SECRET}" \
  --data-urlencode 'allowed_updates=["message","callback_query"]' \
  --data-urlencode "max_connections=20")"

if ! echo "$RESPUESTA" | grep -q '"ok":true'; then
  # La respuesta de error no trae el token, pero la URL si, y esa no se imprime.
  echo "Telegram rechazo setWebhook: ${RESPUESTA}" >&2
  exit 1
fi

echo "Webhook registrado en ${WEBHOOK}"
