# Smart Report IA

Sistema de reportes ciudadanos de hallazgos en la vía pública de El Salvador.
Alguien ve un hueco en la calle, le manda una foto a un bot de Telegram, y la
cuadrilla lo ve agrupado con los otros tres que reportaron lo mismo.

El alcance, las fases y las decisiones ya tomadas están en [`PLAN.md`](PLAN.md).

**Estado: fase 1 — el canal.** El bot recibe foto y ubicación y guarda el
reporte. Las fotos todavía no se copian a almacenamiento propio: eso es la
fase 2.

---

## Arrancar

```bash
cp .env.example .env      # poner ANTHROPIC_API_KEY
make up
make seed
```

| | |
|---|---|
| API | http://localhost:8000/health |
| Docs | http://localhost:8000/docs |
| Web | http://localhost:3100 |
| MinIO | http://localhost:9001 |

`make up` levanta Postgres con PostGIS, MinIO, corre las migraciones y sirve
API y frontend. La primera vez tarda: construye las imágenes. `make seed`
deja sembrados los canales conocidos y se puede correr las veces que sea.

## Comandos

| | |
|---|---|
| `make test` | pytest contra la base levantada |
| `make lint` | ruff, ESLint y `tsc --noEmit` |
| `make migrate` | `alembic upgrade head` |
| `make revision m="…"` | nueva migración autogenerada |
| `make seed` | datos de siembra, idempotentes |
| `make tunnel` | túnel HTTPS y registro del webhook |
| `make webhook` | qué dice Telegram del webhook |
| `make reports` | últimos reportes con coordenadas y fotos |
| `make health` | `/health` formateado |
| `make nuke` | baja todo y borra los datos |

## El bot

Telegram necesita un HTTPS público, así que en local hace falta un túnel. Se usa
webhook también en desarrollo y no long polling: la verificación de la fase mide
el tiempo de respuesta del webhook, y con long polling no hay webhook que medir.
El camino que se prueba es el que corre desplegado.

**Una vez:**

1. Hablar con [@BotFather](https://t.me/BotFather), `/newbot`, y pegar el token
   en `TELEGRAM_BOT_TOKEN` del `.env`.
2. Generar el secreto del webhook: `openssl rand -hex 32` en
   `TELEGRAM_WEBHOOK_SECRET`. **No lo da Telegram**, es propio, y es lo único
   que distingue un update real de un POST de cualquiera.
3. `brew install cloudflared` si no está.

**Cada vez:**

```bash
make up
make tunnel     # deja esto corriendo; Ctrl-C baja el túnel y borra el webhook
```

Mandarle una foto al bot desde el teléfono, y después la ubicación con el botón
que aparece. `make reports` muestra lo que quedó guardado.

Si el bot no contesta, `make webhook` dice qué está viendo Telegram: si hay
updates encolados y cuál fue el último error.

### Si el túnel no levanta

Los túneles rápidos de Cloudflare son sin cuenta y **sin garantía de
servicio**: a veces entregan un hostname que nunca se publica en DNS. No
avisa —cloudflared dice que la conexión quedó registrada y el nombre
responde `NXDOMAIN` para siempre—, así que `make tunnel` lo detecta
comprobando `/health` a través del túnel y pide otro. Crear varios seguidos
empeora la probabilidad.

**No reintentar en el acto.** Medido durante la fase 1: los intentos aislados
con unos minutos de por medio funcionan, y las ráfagas de tres fallan enteras,
porque crear túneles seguidos es lo que dispara el límite. Por eso `make tunnel`
hace **un** intento y te dice que esperes, en vez de insistir y empeorarlo.

Si pasa seguido, ngrok es más estable y solo pide cuenta gratuita — **no hace
falta dominio propio**, a diferencia de los túneles con nombre de Cloudflare,
que exigen una zona en tu cuenta:

```bash
brew install ngrok
ngrok config add-authtoken <token>
ngrok http 8000
```

y registrar esa URL a mano con el mismo secreto.

### Cómo conversa

La foto llega en un mensaje y la ubicación en otro, así que hay un reporte
abierto entre los dos. La ubicación **se pide con el botón nativo de Telegram**
y nunca se saca de los EXIF: Telegram comprime las imágenes y les quita los
metadatos.

| Llega | Pasa |
|---|---|
| Foto | Abre un reporte `incomplete` y pide la ubicación |
| Otra foto dentro de la hora | Se suma al mismo reporte (los álbumes llegan así) |
| Ubicación | Completa el reporte: `received` con sus coordenadas |
| Ubicación sin foto previa | Pide la foto primero |
| Cualquier otra cosa | Se guarda cruda y se contesta que no se entiende |

## Seguridad del webhook

El endpoint es público desde el momento en que hay túnel. Lo que lo protege:

| Qué | Cómo |
|---|---|
| Autenticidad | `X-Telegram-Bot-Api-Secret-Token` con `hmac.compare_digest` |
| Sin secreto configurado | **Rechaza todo.** El fallo cierra, no abre |
| Cuerpo enorme | Tope por `Content-Length` y además contando lo que llega |
| Abuso por origen | Límite por IP, contador en Postgres |
| Abuso por persona | Límite por usuario de Telegram, que es lo que protege el almacenamiento |
| IP falseada | `X-Forwarded-For` se ignora salvo que haya proxy declarado |
| Datos personales | Las IP se guardan como HMAC, nunca en claro |
| Updates repetidos | Único en `(channel, external_update_id)` |
| Inyección SQL | Parámetros ligados en todo, PostGIS incluido |
| Fugas en errores | En producción el detalle es el tipo de excepción y nada más |

**El reporte crudo se guarda siempre**, antes de interpretarlo y en su propia
transacción. Si el parser tiene un bug, eso es lo único que permite reprocesar.

## Tiempo de respuesta

El webhook tiene un segundo: si tarda, Telegram reenvía el update. Medido en
local sobre 30 peticiones:

| | |
|---|---|
| Mediana | 3,9 ms |
| p95 | 9,7 ms |
| Máximo | 96,2 ms |

Sale de que **el webhook no hace ni una llamada de red saliente**: la respuesta
a quien reporta viaja en el cuerpo de la propia respuesta HTTP. Bajar la foto es
trabajo de la fase 2 y va por la cola.

## `/health`

No devuelve un `ok` fijo. Comprueba las tres cosas sin las cuales el servicio
no puede trabajar y dice cuál falló:

```json
{
  "status": "degraded",
  "environment": "dev",
  "schema_revision": "0001",
  "checks": {
    "postgis": { "ok": true, "version": "3.5.0", "detail": null },
    "schema":  { "ok": true, "applied_revision": "0001", "expected_revision": "0001" },
    "model":   { "ok": false, "detail": "ANTHROPIC_API_KEY sin definir", "cached": false }
  },
  "issues": ["model: ANTHROPIC_API_KEY sin definir"]
}
```

Dos decisiones que conviene no revertir sin pensarlo:

- **Devuelve 200 aunque esté degradado.** Un 503 hace que el orquestador
  reinicie el contenedor en bucle por un problema que reiniciar no arregla.
  El estado va en el cuerpo, no en el código HTTP.
- **El sondeo al modelo se cachea 60 segundos.** `/health` puede consultarse
  cada pocos segundos; sin caché eso es cuota y latencia regaladas.

## Métricas

Las cuatro que definen si el proyecto sirve. Se llenan con el número medido,
nunca con una promesa.

| Qué | Valor | Fase |
|---|---|---|
| Exactitud de clasificación | — | 3 |
| Agrupaciones incorrectas (falsos positivos) | — | 4 |
| Agrupaciones perdidas (falsos negativos) | — | 4 |
| Costo por reporte | — | 8 |

## Convenciones

Identificadores, cadenas y mensajes de commit en inglés. Comentarios y
docstrings en español. Commits en formato Conventional Commits.
