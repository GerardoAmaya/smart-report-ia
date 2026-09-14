#!/usr/bin/env bash
# Tunel HTTPS publico hacia la API local y registro del webhook en Telegram.
#
# Telegram exige HTTPS con certificado valido, asi que en local hace falta un
# tunel. Se usa webhook tambien en desarrollo y no long polling a proposito: la
# verificacion de la fase mide el tiempo de respuesta del webhook, y con long
# polling no hay webhook que medir. El camino que se prueba tiene que ser el
# que corre desplegado.
#
# Dos proveedores. ngrok primero si esta configurado, porque publica el nombre
# de inmediato; cloudflared si no, que no pide cuenta pero cada tantas veces
# entrega un hostname que nunca aparece en DNS.
set -euo pipefail

cd "$(dirname "$0")/.."

PUERTO=8000
LOG="$(mktemp -t smartreport-tunnel)"
PID=""
URL=""

[[ -f .env ]] || { echo "Falta .env. Copiar de .env.example." >&2; exit 1; }
set -a; . ./.env; set +a

[[ -n "${TELEGRAM_BOT_TOKEN:-}" ]] || {
  echo "TELEGRAM_BOT_TOKEN sin definir en .env. Pedirlo a @BotFather." >&2; exit 1; }
[[ -n "${TELEGRAM_WEBHOOK_SECRET:-}" ]] || {
  echo "TELEGRAM_WEBHOOK_SECRET sin definir en .env. Generar: openssl rand -hex 32" >&2; exit 1; }

API="https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}"

limpiar() {
  echo
  echo "Bajando el tunel y borrando el webhook…"
  # Sin esto, Telegram sigue mandando updates a una URL muerta y los reintenta
  # durante horas. Borrarlo al salir deja el bot en un estado conocido.
  curl -sS -X POST "${API}/deleteWebhook" -d "drop_pending_updates=false" >/dev/null 2>&1 || true
  [[ -n "$PID" ]] && kill "$PID" 2>/dev/null || true
  rm -f "$LOG"
}
trap limpiar EXIT INT TERM

# --- Eleccion de proveedor ---

ngrok_configurado() {
  command -v ngrok >/dev/null || return 1
  # `ngrok config check` solo valida la sintaxis del archivo, no que el token
  # sirva. Que exista la linea es lo unico comprobable sin levantar un tunel.
  ngrok config check >/dev/null 2>&1 || return 1
  local cfg
  cfg="$(ngrok config check 2>/dev/null | grep -oE '/.*ngrok\.yml' || true)"
  # Indentado, no al principio de linea: en la version 3 del formato el
  # authtoken cuelga de `agent:`. Buscarlo anclado a columna cero hacia que la
  # deteccion fallara en silencio y se cayera a cloudflared.
  [[ -n "$cfg" && -f "$cfg" ]] && grep -qE '^[[:space:]]*authtoken:' "$cfg"
}

PROVEEDOR="${TUNNEL_PROVIDER:-auto}"
if [[ "$PROVEEDOR" == "auto" ]]; then
  if ngrok_configurado; then
    PROVEEDOR="ngrok"
  elif command -v cloudflared >/dev/null; then
    PROVEEDOR="cloudflared"
  else
    echo "No hay tunel disponible. Instalar uno:" >&2
    echo "  brew install ngrok       (cuenta gratuita, mas estable)" >&2
    echo "  brew install cloudflared (sin cuenta)" >&2
    exit 1
  fi
fi

# --- Proveedores ---

levantar_ngrok() {
  # --log=stdout evita la interfaz de terminal, que aca estorba.
  ngrok http "$PUERTO" --log=stdout --log-format=logfmt >"$LOG" 2>&1 &
  PID=$!

  for _ in $(seq 1 30); do
    # La API local de ngrok es la fuente fiable de la URL; el log cambia de
    # formato entre versiones.
    URL="$(curl -sS --max-time 3 http://127.0.0.1:4040/api/tunnels 2>/dev/null \
      | python3 -c "
import json, sys
try:
    for t in json.load(sys.stdin).get('tunnels', []):
        if t.get('public_url', '').startswith('https://'):
            print(t['public_url']); break
except Exception:
    pass
" 2>/dev/null || true)"
    [[ -n "$URL" ]] && return 0

    if grep -qiE 'ERR_NGROK_(105|107|108)|authentication failed|invalid.*authtoken' "$LOG"; then
      echo >&2
      echo "ngrok rechazo el authtoken." >&2
      echo "El authtoken de ngrok no es el token del bot: es una cadena larga" >&2
      echo "sin dos puntos, y sale de https://dashboard.ngrok.com/get-started/your-authtoken" >&2
      echo "  ngrok config add-authtoken <el de ngrok>" >&2
      return 1
    fi
    sleep 1
  done

  echo "ngrok no publico una URL. Log:" >&2
  tail -15 "$LOG" >&2
  return 1
}

levantar_cloudflared() {
  cloudflared tunnel --url "http://localhost:${PUERTO}" --no-autoupdate >"$LOG" 2>&1 &
  PID=$!

  for _ in $(seq 1 45); do
    URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | head -1 || true)"
    [[ -n "$URL" ]] && return 0
    sleep 1
  done

  echo "cloudflared no publico ninguna URL. Log:" >&2
  tail -15 "$LOG" >&2
  return 1
}

# --- Levantar ---

echo "Proveedor: ${PROVEEDOR}"
echo "Levantando tunel hacia http://localhost:${PUERTO} …"

case "$PROVEEDOR" in
  ngrok)       levantar_ngrok ;;
  cloudflared) levantar_cloudflared ;;
  *)           echo "Proveedor desconocido: ${PROVEEDOR}" >&2; exit 1 ;;
esac

echo "  URL: ${URL}"

# Esperar a que el host resuelva y conteste ANTES de avisarle a Telegram. Se
# comprueba contra /health, que ademas prueba que el tunel llega de verdad
# hasta la API y no solo que el nombre existe.
echo -n "  esperando a que responda"
LISTO=0
for _ in $(seq 1 30); do
  if curl -sS --max-time 5 -o /dev/null -w '%{http_code}' "${URL}/health" 2>/dev/null \
      | grep -q '^200$'; then
    LISTO=1
    break
  fi
  echo -n "."
  sleep 2
done
echo

if [[ "$LISTO" -ne 1 ]]; then
  echo >&2
  if [[ "$PROVEEDOR" == "cloudflared" ]]; then
    echo "El tunel se conecta pero el hostname no aparece en DNS." >&2
    echo >&2
    echo "Pasa cada tantas veces con los tuneles rapidos, que son sin cuenta y" >&2
    echo "sin garantia de servicio. Medido durante la fase 1: los intentos" >&2
    echo "aislados con unos minutos de por medio funcionan, y las rafagas de" >&2
    echo "tres fallan enteras, porque crear tuneles seguidos dispara el limite." >&2
    echo >&2
    echo "  Esperar unos minutos y repetir: make tunnel" >&2
    echo "  O usar ngrok, que publica el nombre de inmediato:" >&2
    echo "    ngrok config add-authtoken <token de dashboard.ngrok.com>" >&2
  else
    echo "El tunel no llega hasta la API en ${URL}/health." >&2
    echo "¿Esta levantada? make up" >&2
  fi
  exit 1
fi
echo "  el tunel llega hasta la API."

# --- Registrar el webhook ---

WEBHOOK="${URL}/webhooks/telegram"

# allowed_updates limita a lo que sabemos manejar. Cada tipo que no se pide es
# superficie que no hay que defender. callback_query entra en la fase 3: es
# por donde vuelve la confirmacion de la categoria.
RESPUESTA="$(curl -sS -X POST "${API}/setWebhook" \
  --data-urlencode "url=${WEBHOOK}" \
  --data-urlencode "secret_token=${TELEGRAM_WEBHOOK_SECRET}" \
  --data-urlencode 'allowed_updates=["message","callback_query"]' \
  --data-urlencode "max_connections=20" \
  --data-urlencode "drop_pending_updates=true")"

if ! grep -q '"ok":true' <<<"$RESPUESTA"; then
  # El token no se imprime nunca: la respuesta de error no lo trae, pero la URL
  # de la API si, y esa no se muestra.
  echo "Telegram rechazo setWebhook: ${RESPUESTA}" >&2
  exit 1
fi

echo
echo "Webhook registrado en ${WEBHOOK}"
echo
echo "Mandale una foto al bot desde el telefono. Ctrl-C para bajar todo."
wait "$PID"
