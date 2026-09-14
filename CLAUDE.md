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

**Fases 0, 1, 2 y 7 cerradas y verificadas. Fases 3 a 6 escritas.** Lo que
existe:

- `InboundChannel` como contrato, con Telegram como primera implementación
- Webhook con secreto, límites, tope de cuerpo y **cero llamadas de red salientes**
- Trabajador aparte con dos colas en Postgres: fotos y clasificación
- Miniaturas, huella perceptual y retención que borra de verdad, huérfanos incluidos
- Clasificación con salida por esquema y confirmación por botones en el bot
- Agrupación por código con distancia PostGIS, evidencia escrita y deshacer
- Tablero con cola, detalle, mapa y panel de métricas; entrada con Google y con
  contraseña, y permisos comprobados en la API
- Despacho: asignar cuadrilla, cerrar con foto de evidencia, y **aviso de
  vuelta a todos los que reportaron**, encolado y con reintentos
- Tablero en vivo por SSE sobre `LISTEN/NOTIFY`, sin sondeo
- Nueve pruebas extremo a extremo con Playwright contra el sistema levantado
- Diecinueve migraciones, una por tabla, y seeders versionados aparte
- 198 pruebas y 9 recorridos en verde, CI en verde

**Las fases 3, 4 y 5 no están cerradas**, y cada una espera una verificación que
no se puede fabricar:

| Fase | Le falta |
|---|---|
| 3 — clasificación | 200 fotos etiquetadas: exactitud por categoría y matriz de confusión |
| 4 — agrupación | 200 reportes agrupados a mano: las dos tasas por separado |
| 5 — el tablero | Alguien que no vio el sistema mira un caso agrupado y lo entiende solo |
| 6 — despacho | El ciclo completo con un reporte real: de la foto al aviso de cerrado |

(La fase 7 sí está cerrada: sus pruebas corren en CI contra el sistema
levantado, que es exactamente lo que pedía su verificación.)

El código que mide las tres existe y **avisa cuando la muestra no alcanza** en
vez de dar un número. Las etiquetas de la fase 3 se juntan solas: cada
confirmación en el bot es una.

**Siguiente: fase 8 — despliegue.**

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

**El costo se mide con fotos reales, nunca sintéticas.** Se intentó al revés
en la fase 2 y salió un 28,5 % bajo: las sintéticas se calibraron por el tamaño
del original, pero su miniatura pesaba 2,6 veces menos que la de una foto de
verdad, porque el detalle real no comprime a 320px como una textura generada.
El rendimiento sí se mide con sintéticas; ahí el contenido no cambia nada.

**La cola de fotos es la propia tabla de fotos.** El trabajo *es* la fila, y una
tabla genérica de trabajos sería infraestructura para un segundo tipo de trabajo
que todavía no existe. Cuando llegue la clasificación, se decide con dos casos a
la vista en vez de uno imaginado.

**Se marca `processing` y se confirma antes de descargar.** Mantener la
transacción abierta durante la descarga tendría la fila bloqueada varios
segundos, y una transacción larga estorba a toda la base. El precio es
`locked_at` y un reclamo de filas huérfanas, que es más barato que lo otro.

**Se distingue el fallo transitorio del permanente.** La red vuelve a la cola
con espera creciente; un archivo que no es imagen queda en `failed` a la
primera. Reintentar lo permanente llega a la misma conclusión pagando cinco
veces el ancho de banda.

**La imagen se valida abriéndola, no olfateando sus bytes.** Un archivo con
cabecera JPEG y basura detrás pasa cualquier número mágico y revienta después.
Además ahorra `libmagic` como dependencia del sistema.

**El original se guarda sin reencodear.** Es evidencia; reencodearla la altera.
La miniatura va aparte y siempre en JPEG.

**Los duplicados se detectan pero no se comparten bytes.** El `content_sha256`
dice que dos reportes traen la misma foto —señal que la fase 4 quiere— pero cada
uno guarda su copia. Compartir bytes obliga a contar referencias, y contarlas
mal es cómo la retención borra una foto que otro caso todavía usaba.

**Las pruebas corren contra `smart_report_test`, nunca contra desarrollo.** Esto
no es pulcritud: la suite vacía tablas entre casos, y apuntando a la base de
desarrollo borra reportes reales. Pasó — un reporte mandado desde un teléfono
desapareció en un `make test`. Hay un guardia que se niega a correr si la URL no
termina en `_test`, antes del primer TRUNCATE y no después.

**Ningún registro puede llevar credenciales.** `python-telegram-bot` habla por
httpx, httpx registra la URL completa en INFO, y la URL de Telegram lleva el
token **dentro de la ruta**: el trabajador lo escupía en cada llamada. Se tapa
con un filtro en la raíz y además httpx queda en WARNING. Dos defensas porque
esta es la vía que ya falló una vez.

**El costo se mide con fotos reales, nunca sintéticas.** Se intentó al revés
en la fase 2 y salió un 28,5 % bajo: las sintéticas se calibraron por el tamaño
del original, pero su miniatura pesaba 2,6 veces menos que la de una foto real.
El rendimiento sí se mide con sintéticas; ahí el contenido no cambia nada.

**La imagen es dos tercios del costo de clasificar.** De 2 627 tokens, 858 son
el prompt y 1 769 la imagen. Encogerla a miniatura ahorra más que cambiar de
modelo, y el ahorro sirve con cualquiera de los tres.

**El clasificador usa `haiku-4.5` con miniatura**, elegido con el saldo a la
vista: USD 0,0018 por foto. Cuál conviene de verdad se decide con la matriz de
confusión, no de memoria. Subir de modelo es cambiar `CLASSIFY_MODEL`.

**El texto de quien reporta es pista, no instrucción.** El prompt lo dice
explícitamente y el modelo lo respeta: con una foto de un patio y el texto
«Bache en Av Manuel» devolvió `no_es_reporte`. Es la defensa contra inyección
por pie de foto.

**La agrupación tiene tres salidas, no dos.** `grouped`, `doubtful` y `alone`.
La banda de duda existe porque la asimetría manda: lo que queda en el límite
abre su propio caso con el candidato anotado, equivocándose hacia el error
molesto y nunca hacia el grave.

**Se agrupa por la categoría confirmada, nunca por la propuesta.** Agrupar con
lo que sugirió el modelo sin confirmar sería dejarlo decidir agrupaciones por la
puerta de atrás, que es justo lo que PLAN.md reserva para el código.

**La huella perceptual no fuerza uniones.** Una imagen idéntica a 60 m puede ser
un reenvío con ubicación propia, o sea una agrupación falsa de las graves. Se
anota como evidencia y deja el reporte dudoso; nunca lo junta sola.

**El comprobador de agrupación no importa el agrupador**, y hay una prueba que
falla si alguien lo agrega. Medir con la lógica que decide mide consistencia
consigo misma.

**Las pruebas vacían la base entera, derivada del esquema.** La lista escrita a
mano se quedó vieja al llegar la fase 4 y los casos se filtraban entre pruebas:
fallos que solo aparecían en la suite completa y desaparecían al correr la
prueba sola. Ahora sale de `Base.metadata`.

**El reloj del limitador es una función propia.** La ventana es fija y arranca
en el reloj de pared; una prueba que cruza el borde ve el contador reiniciarse.
Una prueba de seguridad que falla de vez en cuando enseña a ignorar el rojo.

**Ningún código puede vaciar la base de desarrollo.** Un listener en el motor
bloquea `TRUNCATE`, `DROP` y `DELETE`/`UPDATE` sin `WHERE` salvo que la base
termine en `_test`. Va enganchado al motor y no en cada sitio que borra: un
guardia que hay que acordarse de llamar protege solo al que ya iba con cuidado.
Pasó dos veces —la suite apuntando a desarrollo, y después un script de
depuración a mano— y las dos se perdió un reporte real. La escotilla es
`ALLOW_DESTRUCTIVE_SQL=1`, variable de entorno para que se vea.

**El bucket de pruebas también va aparte.** Aislar la base sin aislar el
almacenamiento deja el mismo agujero con otra forma: una prueba del barrido de
huérfanos borró objetos reales, porque «huérfano» significa «ningún registro lo
apunta» y los registros de desarrollo no están en la base de pruebas.

**La retención barre huérfanos**, con 24 horas de gracia. El trabajador sube los
bytes y después confirma la fila; sin margen, barrer durante esa ventana
borraría una foto que estaba entrando. Sin este barrido, un objeto que perdió su
fila queda fuera del alcance de la política para siempre.

**El aviso de vuelta se encola, nunca se manda en la peticion.** El cierre es
un hecho; avisarlo es un intento. Si mandar cuatro mensajes viviera dentro de la
peticion que cierra el caso, un fallo en el cuarto dejaria el caso sin cerrar.

**Un aviso por persona y por tipo, no por reporte.** Unico en (caso, canal,
usuario, tipo). Quien reporto tres veces recibe uno, y reabrir y volver a cerrar
no reenvia nada: un sistema que avisa dos veces de lo mismo se aprende a
ignorar.

**El mensaje habla del reporte, no del caso.** Quien reporto un hueco no sabe
que existe un caso ni por que su foto esta junto a otras tres.

**Y dice cual de sus reportes es: cuando lo mando y donde.** La categoria sola
no lo distingue —quien reporto dos fugas en la misma semana recibe dos veces
«tu reporte sobre el agua o drenaje»—, asi que el texto se arma por persona con
las señas de **su** reporte, no del caso. La hora va en la de El Salvador y los
nombres de dia y mes estan escritos en el codigo: el contenedor no trae la
configuracion regional en español y `strftime("%A")` devolveria «Sunday» sin
avisar.

**El sitio se enseña como punto, no como direccion.** De la ubicacion solo
llegan coordenadas; traducirlas a nombre de calle pide un servicio de
geocodificacion que no existe en el sistema, y una calle inventada es peor que
ninguna. El enlace abre el punto exacto que recibio la cuadrilla. Si algun dia
se quiere la direccion escrita, es geocodificacion inversa con su columna
cacheada, no una llamada por aviso.

**El enlace va al final y sin punto detras.** Telegram se traga el punto dentro
del enlace y el mapa abre en un sitio que no existe. Hay una prueba que lo fija.

**La evidencia va en `case_photos`, no en `report_photos.kind='evidence'`.**
La fase 2 anticipo lo segundo y la anticipacion estaba mal: una foto de arreglo
la sube un operador, no se clasifica, no se le saca huella, y no puede entrar en
la agrupacion. Compartiendo tabla, olvidar un `WHERE kind='report'` una vez
mete la foto del arreglo como si fuera otro reporte del problema.

**No se cierra sin foto.** Un cierre sin evidencia es una afirmacion que nadie
puede comprobar.

**La retencion de la evidencia cuelga de `closed_at`, no de `updated_at`.** Un
caso reabierto deja `closed_at` en nulo, asi que su foto vuelve a estar fuera de
alcance mientras siga abierto.

**El worker de MapLibre se sirve desde `public/`, no desde el bundle.**
Turbopack no lo emite, así que el mapa se monta y **no pide una sola tesela**:
los pines se ven —son HTML— y el fondo no. Sin error en consola ni petición
fallida. Lo copia `scripts/copiar-worker-maplibre.mjs` antes de cada `dev` y
`build`, y se registra con `setWorkerUrl` **antes** de construir ningún mapa.
No se guardan los archivos en el repositorio a propósito: ahí se quedarían
viejos al subir la versión de MapLibre, y esto volvería a romperse sin que nadie
lo relacione.

**El CSS de una librería va al bundle principal, no dentro del componente.**
Con `dynamic()` el import acaba en el chunk que se carga aparte, y el lienzo de
MapLibre se quedaba sin posicionar: **los pines se veían** —MapLibre les pone
estilos en línea— **y el mapa no**. Un fallo mudo, sin error en consola ni en
red, que parece un problema de teselas y no lo es.

**El tablero se actualiza por SSE sobre `LISTEN/NOTIFY`, sin sondeo.** El
aviso sale de Postgres, que es donde ya vive la cola: cuando el trabajador
guarda una foto en su proceso y la API la tiene que enseñar en otro, Postgres ya
está en medio. SSE y no WebSocket porque el tablero escucha y no habla.

**El aviso de cambio sale de un disparador, no de llamadas en el código.** La
tentación es avisar a mano en cada sitio que cambia algo, y es así como el
tablero se queda viejo: basta olvidar uno. Un disparador no se puede olvidar, y
vive en una migración versionada.

**Por el flujo solo va «algo cambió aquí», nunca la fila.** Mandar el dato
obligaría a mantener dos formas de leer lo mismo, y la segunda se queda vieja.

**Las pruebas extremo a extremo corren contra el sistema levantado.** Sin
endpoints de prueba ni escrituras directas: los reportes entran por el webhook
real. Lo único sustituido es a qué servidor le habla el bot —`TELEGRAM_API_BASE_URL`
apunta a un Telegram falso— para no necesitar cuenta ni fotos reales en cada
corrida.

**Las pruebas corrigen la categoría en vez de confirmarla.** La foto que sirve
el Telegram falso es un patrón generado y el modelo responde `no_es_reporte`,
**acertando**. Una persona ante eso corrige, así que la prueba corrige: de paso
cubre el camino de corrección y la categoría deja de depender de lo que el
modelo opine de una imagen sintética.

**Cada corrida de las pruebas trabaja en su propio sitio del mapa.** Sin eso los
reportes de una corrida se agrupan con los de la anterior —que es el
comportamiento correcto— y afirmar cuántos hay en un caso se vuelve imposible.

**Los textos que lee un operador van en español correcto, con tildes.** Los
comentarios del código pueden ir sin ellas; la evidencia que se muestra en el
tablero no. Hay una prueba que lo fija.

**Una eleccion se contesta con las dos cosas: el aviso en el cuerpo y la
reescritura detras.** El cuerpo del webhook admite una sola llamada, y ninguna
de las dos sola alcanza. Solo `answerCallbackQuery`: el boton se apaga pero el
mensaje no cambia, y confirmar —el camino normal— parece no hacer nada
(«le di dos veces y no paso de ahi»; habia pasado las dos veces). Solo
`editMessageText`: el mensaje cambia pero nadie apaga el reloj del boton, que
se queda girando («se me quedo cargando»). Las dos se reportaron desde un
telefono real, una tras otra. Va en el cuerpo lo que Telegram cronometra
—apagar el reloj— y la reescritura por `BackgroundTasks`, ya fuera del handler.
El texto nuevo repite la categoria porque **reemplaza** a la propuesta: si solo
dijera «gracias», el chat perderia lo unico que se confirmo.

**Un aviso no reescribe el mensaje.** «No encuentro ese reporte» y «ya estaba
confirmado» salen como aviso emergente. Reescribir con ellos borraria del chat
la propuesta que todavia espera respuesta, cambiando un tropiezo por una
perdida.

**Con la categoria confirmada, el texto suelto ya no se pega al reporte.** Se
pegaba: un «Hola» acababa dentro de la evidencia que lee la cuadrilla, y el bot
contestaba «Anotado, gracias» a un saludo —que es justo lo que hace pensar que
no entiende nada—. Antes de confirmar el texto sigue siendo descripcion y se
guarda; despues, la conversacion de ese reporte se acabo y un texto nuevo
empieza otro.

**La propuesta llega despues de pedir la ubicacion, no antes.** Se considero
mostrarla en cuanto llega la foto, que se lee mejor. Medido: diez segundos
desde la foto hasta la propuesta —cuatro de descarga y miniatura, seis del
modelo—. Mostrarla primero deja al bot mudo esos diez segundos antes de que la
persona haya hecho nada; pidiendo la ubicacion se llenan con algo util, y la
agrupacion necesita la ubicacion de todos modos. La clasificacion ya arranca
con la foto y no espera a la ubicacion, asi que el orden no cuesta tiempo. Lo
que si cambio es el texto: ya no dice «quedo registrado» —que suena a final y
hace que la pregunta siguiente parezca de otra conversacion— sino que anuncia
que la revision viene en camino.

**El bot no manda Markdown.** El motivo de la propuesta lo escribe el modelo, y
un guion bajo suelto hace que Telegram rechace el mensaje entero con 400. Los
asteriscos se quitaron; la negrita no vale el mensaje perdido.

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
- **Postgres entra por `localhost:5433`**, no 5432, por lo mismo. Dentro de
  compose los servicios siguen hablándole a `db:5432`; esto solo afecta a un
  `psql` desde el host.
- **`S3_PUBLIC_ENDPOINT_URL` apunta a `localhost:9000`.** Las URLs firmadas
  las abre el navegador, que corre en el host y no resuelve `minio`. No se
  arregla cambiando el texto tras firmar: la firma v4 lleva el host dentro.
  Al desplegar contra R2 los dos valores coinciden.
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
| `make photos` | estado de la cola de fotos |
| `make bench` | costo por foto, medido sobre las reales |
| `make retention` | aplica la política de retención |
| `make accuracy` | exactitud de clasificación, con las confirmaciones |
| `make grouping` | casos y evidencia de cada unión |
| `make grouping-eval f=…` | las dos tasas, por separado |
| `make e2e` | los tres recorridos contra el sistema levantado |
| `make e2e-up` | solo levanta el sistema con el Telegram falso |
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
- **Los umbrales de agrupación son razonados, no medidos.** 30 y 80 metros,
  elegidos por la precisión típica del GPS de un teléfono. PLAN.md pide
  calibrarlos contra doscientos reportes agrupados a mano.
- **Un reporte dudoso no se revisa desde ningún lado todavía.** Queda
  marcado con su motivo esperando el tablero de la fase 5.
- **El costo por foto tiene una sola muestra real.** `make bench` lo recalcula
  con lo que haya en la base; conviene repetirlo cuando entren reportes.
- **La retención se corre a mano.** No hay tarea programada todavía; en la
  fase 8 tiene que entrar al despliegue o la política queda escrita y sin
  aplicar, que es peor que no tenerla.
- **Un `asyncio.run` por foto en el trabajador.** Monta un bucle de eventos
  por descarga. Es invisible al lado de la red, pero si algún día se procesan
  miles por minuto, ahí está.
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
