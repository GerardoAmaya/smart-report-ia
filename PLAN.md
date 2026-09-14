# PLAN.md — Smart Report IA

Sistema de reportes ciudadanos de hallazgos en la vía pública de El Salvador.
Alguien ve un hueco en la calle, le manda una foto a un bot de Telegram, y la
cuadrilla lo ve agrupado con los otros tres que reportaron lo mismo.

Este documento es la fuente de verdad del alcance y las fases. Si el código y
este archivo se contradicen, gana el que se haya medido.

---

## Qué es y para quién

Dos usuarios con necesidades opuestas:

**Quien reporta** está parado frente al problema, con el teléfono en la mano y
prisa. Tiene que poder reportar en menos de un minuto y sin instalar nada.

**Quien despacha** está en un escritorio, mira el sistema ocho horas, y su
problema no es recibir reportes sino **saber cuáles son el mismo**. Cuarenta y
siete reportes en un día son dieciocho problemas reales.

El sistema existe para la segunda persona. La primera es el sensor.

---

## El riesgo principal, y la respuesta

El riesgo es agrupar mal en silencio. Si el sistema junta dos huecos distintos
en un caso, la cuadrilla arregla uno y cierra los dos, y **el problema real
queda escondido detrás de un ticket resuelto**. Nadie se entera nunca.

La respuesta es la misma que resultó en Waypoint: **el modelo propone, el
código decide, y lo que no se puede sostener se informa.**

- El modelo clasifica la foto y sugiere categoría y severidad. No asigna
  cuadrillas ni cierra casos.
- La agrupación la decide código con umbrales medidos: distancia geográfica
  calculada con PostGIS más semejanza visual y textual.
- **Cada agrupación muestra su evidencia** —distancia y parecido, reporte por
  reporte— y se puede deshacer desde el tablero.
- Lo que queda en el límite no se agrupa ni se descarta: se marca como dudoso
  con el motivo, esperando una decisión humana.

Un número de confianza que cada quien interpreta distinto no sirve. Una lista
de reportes cercanos que el sistema decidió no agrupar, con la distancia
escrita, sí.

---

## Alcance cerrado

**Entra:** reportes con foto y ubicación por Telegram; clasificación asistida
por modelo con confirmación del usuario; agrupación por cercanía y semejanza;
tablero interno con cola, mapa y detalle; asignación a cuadrillas; cierre con
foto de evidencia; aviso de vuelta a todos los que reportaron.

**No entra, y conviene decir por qué:**

- **WhatsApp.** El canal se construye como adaptador desde el primer día, así
  que agregarlo después es escribir otra implementación del mismo contrato.
  Pero la API de Meta pide cuenta de empresa verificada y cobra por mensaje, y
  pelear con ese trámite en la fase 1 retrasa todo lo demás.
- **Aplicación móvil.** Telegram ya tiene cámara, ubicación y notificaciones.
  Construir una aplicación para reimplementar eso sería trabajo sin ganancia.
- **Integración con sistemas municipales.** No existe una API a la que
  conectarse. Si aparece, es un adaptador de salida.
- **Seguimiento de presupuesto o materiales.** Es otro sistema.

**Categorías del primer alcance:** vialidad, alumbrado, agua, desechos, riesgo
estructural, espacio público. Lo que tienen en común es la forma del problema:
se ve, se fotografía, y está en un punto del mapa.

---

## Stack

Versiones consultadas contra npm y PyPI el día de escribir esto. Cuando se
arranque, volver a consultarlas: este archivo envejece.

| Capa | Elección | Versión |
|---|---|---|
| Runtime frontend | Node LTS | 24 |
| Frontend | Next.js + React | 16.3 / 19.3 |
| Tipos | TypeScript | 7.0 (ver la nota) |
| Estilos | Tailwind | 4.3 |
| Estado de servidor | TanStack Query | 5.10 |
| Validación | Zod | 4.6 |
| Mapa | MapLibre GL | 6.9 |
| Backend | FastAPI | 0.141 |
| ORM y migraciones | SQLAlchemy + Alembic | 2.0 / 1.20 |
| Base | PostgreSQL + PostGIS | 17 / 3.5+ |
| Driver | psycopg | 3.3 |
| Modelo | Claude (SDK `anthropic`) | 1.5 |
| Bot | python-telegram-bot | 22.8 |
| Almacenamiento de objetos | MinIO local / Cloudflare R2 | S3 API |
| Unitarias | pytest + Vitest | 9.1 / 5.0 |
| Extremo a extremo | Playwright | 1.63 |
| Linters | ruff + ESLint | 0.16 / 9.39 (ver la nota) |

**TypeScript 7 es el compilador reescrito en Go.** Es un cambio de motor y
acaba de salir; `typescript-eslint` y los plugins de editor pueden ir detrás.
Se arranca en 7 **comprobando el primer día** que linter y editor funcionan,
con 5.9 como retirada. «Última estable» y «seguro» no son lo mismo.

**ESLint queda en 9 y no en 10.** `eslint-config-next` arrastra
`eslint-plugin-react`, que declara techo `eslint ^9.7`. Con ESLint 10 el
linter no marca errores: revienta con un `TypeError`, que es peor porque
parece otra cosa. Cuando suban el techo, migrar es cambiar el número.

**El almacenamiento se elige por egreso, no por espacio.** Diez gigas son
unas cuarenta mil fotos de Telegram; el espacio no es la restricción que
aprieta. El tablero sirve las mismas fotos ocho horas al día, y eso sí.
R2 no cobra egreso. El vendedor es una variable de entorno: lo que no es
reversible es hablar S3, y eso se decide desde la fase 1.

**MapLibre y no Leaflet.** El tablero tiene que dibujar cientos de casos con
agrupamiento y cambios en vivo. Leaflet es raster y se queda corto ahí;
MapLibre es vectorial y maneja eso sin pelear. Teselas de un proveedor sin
llave.

### Lo que NO se usa, y por qué

**Redis.** La cola vive en Postgres con `SELECT … FOR UPDATE SKIP LOCKED`. Es
una tabla, un índice y un bucle de trabajador. Meter un segundo almacén para
eso es infraestructura que hay que desplegar, vigilar y explicar. Si algún día
el volumen lo justifica, se cambia el adaptador de cola.

**Dos formas de entrar: Google y contraseña.** Google para el uso normal —no
hay que guardar ninguna credencial— y contraseña para un usuario de prueba
abierto al público, porque el panel es la mitad del proyecto y un tablero que
nadie puede ver no se puede mostrar.

**Ojo con la distinción:** Google dice **quién es**, no **si puede entrar**. La
autorización es una tabla de correos permitidos con su rol.

Sobre el usuario de prueba, dos reglas que son baratas ahora y caras después:

- **La contraseña va en una variable de entorno, nunca en el código.** Aunque
  esté publicada en el README. Una credencial escrita en el repositorio queda en
  el historial de git para siempre, y cuando haga falta cambiarla ya no se
  puede.
- **No puede borrar.** Va a entrar gente a tocar todo, que para eso está. Que
  asigne, agrupe, separe y cierre; que no vacíe la base. Es una condición en el
  rol y ahorra restaurar un respaldo.

Es un proyecto personal y de demostración: la decisión es consciente y no un
descuido. Si algún día lo usara una institución de verdad, el usuario de prueba
se apaga y queda solo Google.

---

## Fases

Ninguna se cierra sin correr su verificación. Una fase sin verificación es una
fase que alguien cree que terminó.

### Fase 0 — Esqueleto

Docker Compose con Postgres y PostGIS, FastAPI vivo, Alembic con la primera
migración, CI en GitHub Actions corriendo linters y pruebas. Frontend que
arranca y llama a `/health`.

El `/health` comprueba desde el principio las cosas sin las cuales el servicio
no puede trabajar: PostGIS, esquema al día, y conexión con el modelo. Un
chequeo que solo mira si hay conexión no comprueba nada útil.

*Verificación:* `make up` levanta todo desde cero en una máquina limpia, CI en
verde, y `/health` reporta el estado real y no un `ok` fijo.

### Fase 1 — El canal

Bot de Telegram recibiendo foto y ubicación, guardando el reporte crudo. **El
canal es un adaptador desde ahora**, no después: una interfaz `InboundChannel`
con Telegram como primera implementación.

El nombre va en inglés como todo identificador del proyecto; ver CLAUDE.md.

La ubicación se pide con el botón nativo de Telegram y no se saca de la foto:
Telegram comprime las imágenes y les quita los metadatos.

*Verificación:* un reporte real desde un teléfono queda en la base con su foto
y sus coordenadas, y el webhook responde en menos de un segundo.

### Fase 2 — Almacenamiento de imágenes

Subida a almacenamiento de objetos, miniaturas, y una política de retención
escrita. Las fotos son el dato más pesado y el más sensible.

*Verificación:* cien fotos subidas y servidas, con el costo por foto calculado
y anotado.

### Fase 3 — Clasificación

El modelo mira la foto y el texto y propone categoría y severidad. **El bot
confirma antes de aceptarla.** Clasificar en silencio y equivocarse manda una
cuadrilla de agua a arreglar una luminaria.

*Verificación:* un conjunto de doscientas fotos etiquetadas a mano, con
exactitud por categoría y la matriz de confusión. No un promedio: importa
cuáles se confunden entre sí.

### Fase 4 — Agrupación

La parte difícil. Distancia con PostGIS, semejanza visual y textual, y umbrales
calibrados contra datos.

**La métrica tiene una asimetría que hay que respetar.** Separar dos reportes
que eran el mismo caso genera trabajo duplicado, que es molesto. Juntar dos
problemas distintos esconde uno de ellos, que es grave. **El umbral se calibra
contra el segundo error, no contra el promedio de los dos.**

*Verificación:* doscientos reportes agrupados a mano, y las dos tasas por
separado. El comprobador no usa el mismo código que agrupa: medir con la misma
lógica que decide mide consistencia consigo misma, no acierto.

### Fase 5 — El tablero

Cola, mapa, detalle con la evidencia de la agrupación, y separar un reporte de
su grupo. Entrada con Google y con contraseña, y roles.

*Verificación:* un operador que no vio el sistema antes entiende por qué cuatro
reportes están juntos, sin que nadie se lo explique. Y el usuario de prueba
puede asignar, agrupar y cerrar, pero **no puede borrar** — comprobado con una
prueba, no a ojo.

### Fase 6 — Despacho y cierre

Asignación a cuadrillas, cambios de estado, cierre con foto de evidencia, y
aviso de vuelta **a todos los que reportaron, no solo al primero**.

Esa es la parte que casi nadie construye y sin la cual nadie reporta dos veces.
Y es lo que le da sentido al agrupamiento más allá de ahorrar trabajo: permite
responderle a cuatro personas con un solo arreglo.

*Verificación:* el ciclo completo con un reporte real, desde la foto hasta el
aviso de cerrado.

### Fase 7 — Tiempo real y pruebas extremo a extremo

El tablero se actualiza sin recargar. Playwright cubriendo los tres recorridos:
reportar, agrupar y despachar, cerrar.

*Verificación:* las pruebas corren en CI contra el sistema levantado, no contra
simulaciones.

### Fase 8 — Despliegue

Backend, frontend, base y almacenamiento. Límite por IP en el webhook desde el
primer día público: un bot expuesto es una superficie que alguien va a probar.

*Verificación:* el sistema desplegado atiende un reporte real de punta a punta,
y el costo por reporte está medido.

---

## Métricas

Las cuatro que definen si el proyecto sirve. Van al README con el número
medido, no con una promesa.

| Qué | Cómo se obtiene |
|---|---|
| Exactitud de clasificación | 200 fotos etiquetadas a mano, por categoría |
| Agrupaciones incorrectas | Tasa de falsos positivos, el error grave |
| Agrupaciones perdidas | Tasa de falsos negativos, el error molesto |
| Costo por reporte | Tokens más almacenamiento, medido sobre uso real |

Y dos operativas que solo existen con uso real: mediana hasta la primera
respuesta, y proporción de reportes que terminan agrupados. Esa última es la
medida directa de cuánto trabajo ahorra el sistema.

---

## Dirección de diseño

**La paleta sale del material del problema:** asfalto, pintura de
señalización, cono de obra. Nada de azul corporativo ni de generador de temas.

```
--fondo   #eeefec   superficie de trabajo
--tinta   #16181a   texto, nunca negro puro
--verde   #1f6f5c   señalización, acento y acciones
--ambar   #c77b23   cono de obra, atención y dudas
--rojo    #b4442e   urgente
--gris    #7a8288   resuelto
```

**Superficie clara.** Es una herramienta de escritorio que alguien mira ocho
horas con luz de oficina, no una demo para una captura.

**Sin kit de componentes.** Uno resuelve rápido y hace que el proyecto se vea
como los otros mil que usan el mismo kit.

**El color significa una cosa sola.** El ámbar es atención y nada más, así que
donde aparezca quiere decir «mirá esto». Un color que se usa de adorno deja de
poder usarse como señal.

**El tamaño del pin en el mapa es cuántos reportan lo mismo.** Un mapa de
puntos iguales tira a la basura la información de dónde se concentra el
reclamo.

**Movimiento solo donde muestra un cambio:** un reporte que entra a la cola, un
caso que cambia de estado. Nada que aparezca con desvanecido al hacer scroll.

**Piso de calidad, sin el cual la fase de interfaz no está terminada:** foco de
teclado visible, `prefers-reduced-motion`, contraste comprobado a plena luz, y
estados de vacío y de error redactados con dirección.

---

## Lo que todavía no se sabe

Anotado para no fingir que está resuelto:

**Cuánto cuesta clasificar una foto.** Define si el sistema es viable con
volumen real. Se sabrá en la fase 3.

**Si la semejanza visual sirve para distinguir dos huecos.** Dos baches se
parecen entre sí más que dos caras. Puede que la distancia pese mucho más que
la imagen, y en ese caso la fase 4 cambia de forma.

**Qué hace la gente que no debería.** Fotos que no son reportes, reportes
falsos, insultos. Un bot público recibe eso desde el primer día y no hay plan
todavía.

**Si Telegram alcanza.** En El Salvador la gente usa WhatsApp. El adaptador
existe para que la respuesta a esto sea trabajo y no un rediseño.
