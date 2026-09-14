# Smart Report IA

Sistema de reportes ciudadanos de hallazgos en la vía pública de El Salvador.
Alguien ve un hueco en la calle, le manda una foto a un bot de Telegram, y la
cuadrilla lo ve agrupado con los otros tres que reportaron lo mismo.

El alcance, las fases y las decisiones ya tomadas están en [`PLAN.md`](PLAN.md).

**Estado: fase 0 — esqueleto.** No recibe reportes todavía.

---

## Arrancar

```bash
cp .env.example .env      # poner ANTHROPIC_API_KEY
make up
```

| | |
|---|---|
| API | http://localhost:8000/health |
| Docs | http://localhost:8000/docs |
| Web | http://localhost:3100 |

`make up` levanta Postgres con PostGIS, corre las migraciones y sirve API y
frontend. La primera vez tarda: construye las dos imágenes.

## Comandos

| | |
|---|---|
| `make test` | pytest contra la base levantada |
| `make lint` | ruff, ESLint y `tsc --noEmit` |
| `make migrate` | `alembic upgrade head` |
| `make revision m="…"` | nueva migración autogenerada |
| `make health` | `/health` formateado |
| `make nuke` | baja todo y borra los datos |

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
