# CLAUDE.md

Contexto del proyecto para Claude Code. `PLAN.md` es la fuente de verdad del
alcance y las fases; este archivo dice cómo se trabaja y qué ya está decidido.

Si `PLAN.md` y este archivo se contradicen, gana `PLAN.md`.

---

## Qué es

Sistema de reportes ciudadanos de hallazgos en la vía pública de El Salvador.
Alguien ve un hueco en la calle, le manda una foto a un bot de Telegram, y la
cuadrilla lo ve agrupado con los otros tres que reportaron lo mismo.

Hay dos usuarios con necesidades opuestas. **Quien reporta** está parado frente
al problema, con prisa, y tiene que poder reportar en menos de un minuto sin
instalar nada. **Quien despacha** mira el sistema ocho horas y su problema no
es recibir reportes sino saber cuáles son el mismo. El sistema existe para la
segunda persona; la primera es el sensor.

## El riesgo principal, y la respuesta

Agrupar mal en silencio. Si el sistema junta dos huecos distintos en un caso,
la cuadrilla arregla uno y cierra los dos, y el problema real queda escondido
detrás de un ticket resuelto.

**El modelo propone, el código decide, y lo que no se puede sostener se
informa.** El modelo clasifica y sugiere; no asigna cuadrillas ni cierra casos.
La agrupación la decide código con umbrales medidos. Cada agrupación muestra su
evidencia y se puede deshacer. Lo que queda en el límite se marca como dudoso
con el motivo, esperando decisión humana.

Este principio no se negocia: es lo que hace el sistema verificable.

---

## Estado

**Fase 0 cerrada y verificada.** Lo que existe:

- Docker Compose con Postgres 17 y PostGIS 3.5
- FastAPI con `/health` que comprueba PostGIS, revisión de esquema y conexión
  con el modelo
- Alembic con la migración `0001` (extensión PostGIS)
- CI en GitHub Actions: ruff, migraciones en ambas direcciones, pytest, y
  lint/typecheck/build del frontend
- Frontend Next.js que lee `/health` y distingue «degradado» de «sin respuesta»

**Siguiente: fase 1 — el canal.** Bot de Telegram que recibe foto y ubicación y
guarda el reporte crudo.

---

## Decisiones tomadas

No hace falta volver a discutirlas. Si alguna hay que revertir, que sea con un
motivo nuevo y quede escrito.

**`/health` devuelve 200 aunque esté degradado.** El estado va en el cuerpo,
con `checks` e `issues`. Un 503 hace que el orquestador reinicie el contenedor
en bucle por un problema de datos que reiniciar no arregla.

**Las migraciones corren en `start.sh`**, no en un hook del proveedor. Un hook
que no corre falla en silencio; esto falla fuerte y no arranca.

**La cola vive en Postgres** con `SELECT … FOR UPDATE SKIP LOCKED`. No hay
Redis. Es una tabla, un índice y un bucle de trabajador; un segundo almacén es
infraestructura que hay que desplegar, vigilar y explicar. Si el volumen lo
justifica, se cambia el adaptador de cola.

**El canal es un adaptador desde la fase 1**, no después. Telegram es la
primera implementación de la interfaz. WhatsApp queda fuera del alcance por el
trámite de cuenta verificada de Meta, no por diseño.

**La ubicación se pide con el botón nativo de Telegram**, nunca de los EXIF de
la foto: Telegram comprime las imágenes y les quita los metadatos.

**TypeScript está en 6.0.3 y no en 7.** `typescript-eslint` declara
`typescript >=4.8.4 <6.1.0` y entra transitivamente vía `eslint-config-next`.
Cuando suban el techo, migrar es cambiar el número.

**El sondeo al modelo en `/health` se cachea 60 segundos** y usa
`models.list(limit=1)`, que no genera tokens. El panel consulta cada diez
segundos; sin caché eso es cuota y latencia regaladas.

**El chequeo de esquema falla en cualquier dirección.** Una base adelantada
respecto al código desplegado rompe igual que una atrasada.

**Dos formas de entrar (fase 5):** Google para uso normal y contraseña para un
usuario de prueba público. Google dice quién es, no si puede entrar: la
autorización es una tabla de correos permitidos con su rol. La contraseña del
usuario de prueba va en variable de entorno, nunca en el código, y ese usuario
no puede borrar.

---

## Convenciones

**Idioma.** Identificadores, cadenas y mensajes de commit en **inglés**.
Comentarios y docstrings en **español**, y cortos. `PLAN.md` nombra algunas
cosas en español (`CanalEntrada`); en código van en inglés (`InboundChannel`).

**Commits.** Conventional Commits. Un commit por cambio con sentido propio.

**Comentarios.** Explican por qué, no qué. Si el comentario repite el código,
sobra. Los que valen son los que dicen qué pasa si alguien cambia esa línea.

**Cada bug encontrado se lleva su prueba.** No un test genérico del módulo: uno
que falle con el código viejo y pase con el nuevo.

**El comprobador no usa el código que comprueba.** El verificador de agrupación
no llama a la misma lógica que agrupa; medir con la lógica que decide mide
consistencia consigo misma, no acierto.

---

## Entorno local

Estas tres son particularidades de la máquina de desarrollo (Apple Silicon),
no del proyecto:

- **`platform: linux/amd64` en el servicio `db`.** La imagen oficial de PostGIS
  no publica arm64; Docker Desktop la corre emulada. Esto vuelve a aparecer en
  el despliegue: la arquitectura del proveedor decide.
- **El frontend entra por `localhost:3100`**, no 3000, porque el 3000 está
  ocupado por otro proyecto en esta máquina.
- **`CORS_ORIGINS` apunta a 3100** por lo mismo.

## Comandos

| | |
|---|---|
| `make up` | levanta base, API y frontend |
| `make health` | `/health` formateado |
| `make test` | pytest contra la base levantada |
| `make lint` | ruff, ESLint y `tsc --noEmit` |
| `make migrate` | `alembic upgrade head` |
| `make revision m="…"` | nueva migración autogenerada |
| `make nuke` | baja todo y borra los datos |

El código está montado en el contenedor: para cambios en Python basta
`docker compose restart api`, sin rebuild.

---

## Métricas

Van al README con el número medido, nunca con una promesa.

| Qué | Valor | Fase |
|---|---|---|
| Exactitud de clasificación | — | 3 |
| Agrupaciones incorrectas (falsos positivos) | — | 4 |
| Agrupaciones perdidas (falsos negativos) | — | 4 |
| Costo por reporte | — | 8 |

**La métrica de agrupación tiene una asimetría que hay que respetar.** Separar
dos reportes que eran el mismo caso genera trabajo duplicado, que es molesto.
Juntar dos problemas distintos esconde uno, que es grave. El umbral se calibra
contra el segundo error, no contra el promedio de los dos.

---

## Deuda conocida

- **Falta la prueba de `head_revision` con `monkeypatch.chdir`.** Fue el primer
  bug del proyecto: `script_location` se resolvía contra el directorio de
  trabajo, que bajo uvicorn no es el mismo que al correr alembic a mano.
  Arreglado, sin cobertura.
- **El puerto 3100 y el `CORS_ORIGINS` están fijos en el compose.** Quien clone
  el repo con el 3000 libre va a entrar por un puerto que el README no explica.
- **`EXTRACTION_MODEL` en `.env.example`** no lo lee nadie todavía.

## Lo que todavía no se sabe

Anotado para no fingir que está resuelto.

**Cuánto cuesta clasificar una foto.** Define si el sistema es viable con
volumen real. Se sabrá en la fase 3.

**Si la semejanza visual sirve para distinguir dos huecos.** Dos baches se
parecen entre sí más que dos caras. Puede que la distancia pese mucho más que
la imagen, y en ese caso la fase 4 cambia de forma.

**Qué hace la gente que no debería.** Fotos que no son reportes, reportes
falsos, insultos. Un bot público recibe eso desde el primer día y no hay plan.

**Si Telegram alcanza.** En El Salvador la gente usa WhatsApp. El adaptador
existe para que la respuesta a esto sea trabajo y no un rediseño.

---

## Cómo trabajar

Paso a paso, confirmando antes de pasar al siguiente. Ninguna fase se cierra
sin correr su verificación: una fase sin verificación es una fase que alguien
cree que terminó.

Antes de elegir versiones de paquetes, consultarlas contra npm y PyPI. `PLAN.md`
avisa de que ese archivo envejece.
