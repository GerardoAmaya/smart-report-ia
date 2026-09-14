#!/usr/bin/env bash
# Estado del webhook segun Telegram. Util cuando el bot "no contesta": aca se
# ve si Telegram esta recibiendo errores y cuantos updates tiene encolados.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

[[ -n "${TELEGRAM_BOT_TOKEN:-}" ]] || { echo "TELEGRAM_BOT_TOKEN sin definir" >&2; exit 1; }

curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" \
  | python3 -c "
import json, sys
d = json.load(sys.stdin).get('result', {})
# El secreto no se imprime; Telegram solo dice si hay uno puesto.
print('url                     ', d.get('url') or '(ninguna)')
print('secreto configurado     ', d.get('has_custom_certificate') is not None and bool(d.get('url')))
print('updates pendientes      ', d.get('pending_update_count'))
print('ultimo error            ', d.get('last_error_message') or 'ninguno')
print('conexiones maximas      ', d.get('max_connections'))
permitidos = d.get('allowed_updates') or []
print('tipos permitidos        ', permitidos or 'todos')

# Un tipo que el codigo maneja pero Telegram no manda es un fallo mudo: el
# boton gira para siempre y no hay error en ningun lado. Paso una vez.
ESPERADOS = {'message', 'callback_query'}
faltan = ESPERADOS - set(permitidos) if permitidos else set()
if faltan:
    print()
    print('  AVISO: Telegram no esta mandando', ', '.join(sorted(faltan)) + '.')
    print('  Los botones de confirmacion no van a volver. Arreglar con:')
    print('    make tunnel   (vuelve a registrar el webhook)')
"
