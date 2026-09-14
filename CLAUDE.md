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

**Fase 1 escrita, pendiente la verificación con teléfono.** Lo que existe:

- `InboundChannel` como contrato, con Telegram como primera implementación
- Webhook en `POST /webhooks/telegram`, con secreto, límite por IP y por
  usuario, tope de cuerpo y cabeceras de seguridad
- Cinco tablas nuevas, una migración cada una, y seeders versionados aparte
- MinIO en compose como destino de las fotos (nada lo escribe hasta la fase 2)
- 32 pruebas en verde; webhook con mediana de 3,9 ms y p95 de 9,7 ms en local

Falta el último paso de la verificación: un reporte real desde un teléfono.

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

**Webhook también en desarrollo, con túnel.** No long polling. La verificación
de la fase 1 mide el tiempo de respuesta del webhook, y con long polling no hay
webhook que medir. Además, lo que el sondeo se salta no es cosmético: el
secreto en la cabecera, la presión del segundo, y los reintentos de Telegram.
`make tunnel` levanta cloudflared y registra el webhook; al salir lo borra.

**El webhook no hace ni una llamada de red saliente.** La respuesta a quien
reporta viaja en el cuerpo de la propia respuesta HTTP (`method: sendMessage`).
Es lo que mantiene la mediana en milisegundos. Si algún día hace falta más de
un mensaje, va por `BackgroundTasks`, nunca dentro del handler.

**El `file_id` de Telegram es un comprobante, no almacenamiento.** El
`file_path` que se pide con él caduca en una hora, y las fotos vivirían en una
cuenta de bot que no controlamos: si el token se rota, se pierde la evidencia
de todos los casos a la vez. Los bytes se copian a almacenamiento propio en la
fase 2; `report_photos` ya tiene la fila y las columnas esperando.

**Almacenamiento S3-compatible: MinIO en local, R2 al desplegar.** Se elige por
egreso y no por espacio: 10 GB son unas cuarenta mil fotos de Telegram, pero el
tablero sirve las mismas fotos ocho horas al día. R2 no cobra egreso. Supabase
queda descartado porque pausa el proyecto tras una semana sin tráfico, lo que
mataría al usuario de prueba de la fase 5. El vendedor es una variable de
entorno; lo que no es reversible es el protocolo, y ese es S3.

**El secreto del webhook falla cerrado.** Sin `TELEGRAM_WEBHOOK_SECRET` se
rechaza todo. Abrir sería el peor error posible: el bot aceptaría reportes de
cualquiera y nadie se enteraría hasta ver datos falsos en el tablero. Se compara
con `hmac.compare_digest`, no con `==`.

**`X-Forwarded-For` no se lee salvo que haya proxy declarado.** Esa cabecera la
escribe cualquiera: leerla sin más permite saltarse el límite por IP mandando
una distinta cada vez. `TRUSTED_PROXY_HOPS` dice cuántos saltos contar desde la
derecha; con cero se usa la IP del socket.

**Las IP no se guardan en claro.** La tabla de límites solo necesita saber si
dos peticiones vienen del mismo lado, no de dónde. Se guarda un HMAC.

**Dos límites y no uno.** Por IP protege el servicio; por usuario protege el
almacenamiento y la cuota del modelo. Una oficina entera sale por una sola IP y
una persona puede cambiar de red: son problemas distintos.

**El crudo se confirma en su propia transacción.** Si interpretar el update
falla, se revierte lo aplicado pero el payload original queda, que es lo único
que permite reprocesar. Y se responde 200: un error haría que Telegram reintente
para siempre algo que nunca va a poder parsearse.

**ESLint queda en 9.39.5 y no en 10.** `eslint-config-next` arrastra
`eslint-plugin-react`, que declara techo `eslint ^9.7`. Con ESLint 10 el linter
no falla: revienta con un `TypeError`, que es peor porque parece otra cosa. Es
la misma forma que la nota de TypeScript.

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
| `make seed` | datos de siembra, idempotentes |
| `make tunnel` | túnel HTTPS y registro del webhook en Telegram |
| `make webhook` | qué dice Telegram del webhook ahora mismo |
| `make reports` | últimos reportes con coordenadas y fotos |
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

- **El barrido de `rate_limit_buckets` es probabilístico**, una de cada cien
  peticiones. Si el tráfico cae a cero justo después de un pico, las filas de
  ese pico se quedan hasta la siguiente petición. Son bytes, pero está escrito
  para que nadie lo descubra como sorpresa.
- **La ventana de límite es fija, no deslizante.** En el borde de la ventana se
  pueden meter hasta dos veces el límite. Se eligió así porque es un solo
  UPSERT y cabe en el presupuesto del webhook; si hiciera falta afinarlo, el
  cambio es local a `rate_limit.py`.
- **`report_photos.kind` ya admite `evidence`** pero nadie lo escribe hasta la
  fase 6.
- **Nada lee MinIO todavía.** El bucket se crea y queda privado; el trabajador
  que sube los bytes es de la fase 2.
- **El puerto 3100 y el `CORS_ORIGINS` están fijos en el compose.** Quien clone
  el repo con el 3000 libre va a entrar por un puerto que el README no explica.
- **`EXTRACTION_MODEL` se quitó de `.env.example`** al reescribirlo en la
  fase 1. No lo leía nadie. Cuando la fase 3 elija modelo, vuelve con su
  lector, no antes.

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
