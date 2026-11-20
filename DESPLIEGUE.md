# Despliegue

Cómo poner este sistema en internet y cómo operarlo después. Todo lo que hace
falta está en un nivel gratuito **permanente**, no en una prueba que vence al
mes; el único costo real es la API del modelo, unos **USD 0,0018 por foto**.

El sistema entero vive en una máquina. Es lo que permite que salga gratis, y
también lo que hay que tener presente: si la máquina cae, cae todo. Por eso el
respaldo diario a R2 no es opcional.

Escrito después de hacerlo de verdad, el 20 de noviembre de 2026. Lo que dice
«hace perder una tarde» es porque la hizo perder.

---

## Lo que hay que crear

Seis cosas. Ninguna cobra en este uso, aunque Oracle y Cloudflare piden tarjeta
para verificar la cuenta.

| Dónde | Para qué | Lo que hay que sacar |
|---|---|---|
| **Oracle Cloud** | la máquina | una VM ARM con Ubuntu y su IP pública |
| **DuckDNS** | el dominio | un subdominio apuntado a esa IP |
| **Cloudflare R2** | fotos y respaldos | endpoint, clave y secreto |
| **Google Cloud** | entrada al tablero | client id y secreto de OAuth |
| **Telegram** | el canal | el token de un bot **solo para producción** |
| **Anthropic** | clasificación | una clave de API |

### Oracle: la máquina

Crear la cuenta en <https://www.oracle.com/cloud/free/>.

- **La región principal no se cambia nunca.** Para El Salvador, *Mexico Central
  (Querétaro)* o *US West (Phoenix)*. Lo que importa no es la cercanía —el
  webhook llega desde los servidores de Telegram, en Europa— sino que haya
  máquinas ARM libres.

**Primero la red, después la máquina.** Si se deja que el formulario de la
instancia cree la red, el interruptor de *IPv4 pública* sale gris con «You must
select a public subnet» aunque la subred sea pública, y la máquina queda sin
forma de entrar. En su lugar:

1. *Networking → Virtual cloud networks → Actions → Start VCN Wizard →
   Create VCN with Internet Connectivity*. Nombre `smart-report-vcn`, el resto
   como viene. Crea la red, la subred pública y su salida a internet.
2. *Compute → Instances → Create instance*:

| Campo | Valor |
|---|---|
| Image | Canonical Ubuntu 24.04 (la normal, no *Minimal*) |
| Shape | Ampere **VM.Standard.A1.Flex**, **2 OCPU y 12 GB** |
| Capacity type | On-demand. **Nunca *Preemptible***: esa la apaga Oracle cuando quiere |
| Network | *Select existing* → `smart-report-vcn` → **public subnet** |
| Public IPv4 | *Automatically assign*, encendido |
| SSH | pegar la clave pública de una llave **solo para este servidor** |
| Boot volume | como viene, unos 47 GB |

**2 OCPU y 12 GB, no más.** Es el tope gratuito actual. Guías viejas —y una
versión anterior de este documento— dicen 4 y 24: con eso la cuenta funciona
durante el mes de prueba y al terminar Oracle **desactiva las instancias ARM y
las borra a los 30 días**. Justo lo que este despliegue existe para evitar.

Si sale **«Out of host capacity»**, es normal en ARM: reintentar en unos
minutos. No es un problema de la cuenta.

3. **Abrir 80 y 443** en *Networking → smart-report-vcn → Security → Default
   Security List → Add Ingress Rules*: origen `0.0.0.0/0`, TCP, destino `80`; y
   otra igual con `443`. No borrar la del 22.

#### La máquina ociosa

Oracle puede **recuperar** una instancia gratuita si durante 7 días la CPU (p95),
la red y —en ARM— la memoria quedan las tres por debajo del 20 %. Este sistema
con poco tráfico usa unos 2 o 3 GB de 12, así que entra en el criterio.

La salida habitual es pasar la cuenta a **Pay As You Go**: lo que está dentro del
nivel gratuito sigue sin cobrarse. La comunidad reporta que eso evita la
recuperación; la documentación de Oracle no lo dice, así que es probable y no
garantizado. Si se hace, poner una **alerta de presupuesto de USD 1** en
*Billing → Budgets*.

Si aun así la recupera: crear otra máquina con estos pasos, correr los dos
guiones de abajo y restaurar el último respaldo de R2. Para eso existen.

### DuckDNS: el dominio

Entrar en <https://www.duckdns.org> con GitHub o Google, crear el subdominio, y
en *current ip* poner la **IP pública de la máquina** (no la que trae, que es la
de tu casa). La IP no cambia mientras la máquina exista, así que no hace falta
nada que la actualice: el token de DuckDNS no se usa.

**Los filtros corporativos lo bloquean.** FortiGuard y otros bloquean la
categoría *Dynamic DNS* entera: desde una red así el tablero no abre, y parece
que el servidor falla. No afecta al bot —el webhook lo llama Telegram— ni a
quien está con datos móviles. Si quien despacha trabaja detrás de un filtro
así, hace falta un dominio propio (unos USD 10 al año) o que lo desbloqueen.

### Cloudflare R2

En <https://dash.cloudflare.com>: *Storage & databases → R2 object storage* →
activar el plan (pide tarjeta; dice USD 0,00 y cobra solo pasando 10 GB).

- **Bucket** `smart-report-photos`, clase **Standard** —la otra no entra en lo
  gratuito— y acceso público **desactivado**: las fotos llevan caras y placas, y
  el tablero las muestra con enlaces firmados que caducan en 15 minutos.
- **Token**: *Manage API Tokens → Create Account API token*, permiso **Object
  Read & Write**, solo sobre ese bucket. Con eso, si se filtra, no puede ni
  crear ni borrar buckets. De la pantalla final salen el endpoint, el *Access Key
  ID* y el *Secret Access Key*, una sola vez.
- **Alerta de presupuesto** de USD 1, en la misma página.

No hace falta CORS: el tablero muestra las fotos con `<img>` y sube la
evidencia a través de la API, nunca directo a R2.

### Google: la entrada al tablero

En <https://console.cloud.google.com>, **con la cuenta personal**, no con la del
trabajo: un proyecto `smart-report` sin organización.

1. *Google Auth Platform → Comenzar*: público **Externo**.
2. *Clientes → Crear cliente → Aplicación web*. En **URIs de redireccionamiento
   autorizados**, exactamente `https://TU-DOMINIO/auth/google/callback`. Los
   *Orígenes de JavaScript* van **vacíos**: ahí una ruta es inválida, y el
   intercambio lo hace la API, no el navegador.
3. *Público → Publicar aplicación.* En modo de prueba solo entran los correos
   agregados a mano.

Quién puede entrar **no lo decide Google**: lo decide la tabla de usuarios. El
correo autorizado va en `ADMIN_EMAIL` y lo siembran los seeders.

### Telegram: un bot solo para producción

Crear uno con `/newbot` en [@BotFather](https://t.me/BotFather). **No reutilizar
el de desarrollo**: un bot admite un solo webhook, y `make tunnel` lo apunta a
la máquina de desarrollo y lo borra al salir. Producción se quedaría sorda sin
ningún error.

---

## Poner en marcha

### 1. Preparar la máquina

Una vez, y se puede repetir sin romper nada:

```sh
ssh -i ~/.ssh/LLAVE ubuntu@IP 'sh -s' < deploy/preparar-servidor.sh
```

Abre 80 y 443 en el firewall de la propia máquina —las imágenes de Oracle traen
`iptables` que rechaza todo salvo SSH, y abrir solo en la consola deja el sitio
mudo—, instala Docker desde su repositorio oficial con tope de tamaño para los
registros, activa los parches de seguridad automáticos y crea 2 GB de swap.

### 2. Copiar el código y los secretos

```sh
git clone https://github.com/GerardoAmaya/smart-report-ia.git
cd smart-report-ia
cp .env.prod.example .env.prod   # y rellenar
chmod 600 .env.prod
```

Los secretos se generan, no se inventan: `openssl rand -hex 32` para el del
webhook y el de sesión. El del webhook, solo hexadecimal: Telegram rechaza
cualquier cosa fuera de letras, dígitos, `_` y `-`.

### 3. Levantar

```sh
docker compose -f deploy/compose.yml --env-file .env.prod up -d --build
docker compose -f deploy/compose.yml --env-file .env.prod exec api python -m seeders.runner
./deploy/registrar-webhook.sh
```

La primera vez tarda unos cuatro minutos en la máquina ARM, casi todo en
compilar el tablero. Las migraciones corren solas al arrancar la API. El guion
del webhook comprueba antes que el dominio conteste por HTTPS; **córrelo en el
servidor** si tu red filtra el dominio.

---

## Comprobar que quedó bien

```sh
curl -s https://TU-DOMINIO/health | python3 -m json.tool
```

Tiene que decir `"status": "ok"` con los cuatro *checks* en verde. Devuelve 200
aunque esté degradado —el estado va en el cuerpo—, así que hay que leerlo, no
mirar el código HTTP.

Y en los registros:

- `api`: las migraciones hasta la última y `Uvicorn running`.
- `caddy`: `certificate obtained successfully`.
- `mantenimiento`: `retencion aplicada` y `respaldo respaldos/AAAA-MM-DD.dump`.

Después, **la verificación de verdad**: mandarle una foto y una ubicación al bot
desde un teléfono, confirmar la categoría, ver el caso aparecer en el tablero
sin recargar, despacharlo, cerrarlo con foto, y recibir el aviso de vuelta.

---

## Operar

```sh
C="docker compose -f deploy/compose.yml --env-file .env.prod"

$C ps                          # qué está arriba
$C logs -f api worker          # qué está pasando
git pull && $C up -d --build   # actualizar
```

Conviene un monitor externo gratuito —UptimeRobot o Healthchecks.io— que pida
`/health` cada cinco minutos y avise por correo. Si Oracle recupera la máquina
de madrugada, es la diferencia entre enterarse por el correo o por la gente.

### Respaldos

El servicio `mantenimiento` aplica la retención y sube un volcado de la base a
R2 todos los días, y una vez al arrancar: si el respaldo está roto, se sabe al
desplegar y no veinticuatro horas después. Se guardan catorce días bajo
`respaldos/` en el bucket.

Para restaurar:

```sh
# Bajar el volcado del bucket, y entonces:
$C exec -T db pg_restore --clean --if-exists -U smart_report -d smart_report < volcado.dump
```

Conviene probar la restauración una vez, en una base de prueba. Un respaldo que
nunca se restauró es una suposición.

---

## Por qué está armado así

**Un solo origen.** Caddy manda `/health`, `/auth`, `/board` y `/webhooks` a la
API y todo lo demás al tablero. Con dos orígenes habría que configurar CORS y
la cookie de sesión viajaría entre sitios: dos fuentes de fallos que solo
aparecen en producción.

**La base no se asoma a internet.** No tiene `ports`. Un Postgres con el 5432
abierto lo encuentran solo.

**El trabajador y el mantenimiento esperan a la API, no a la base.** La API
migra antes de responder, así que «sana» quiere decir «esquema al día». En el
primer despliegue solo esperaban a la base: la retención corrió contra tablas
que no existían y el respaldo salió con el esquema a medias.

**PostGIS no es la imagen oficial.** Esa no publica arm64 y la máquina gratuita
de Oracle es ARM. `imresamu/postgis` es el espejo multiarquitectura del mismo
proyecto.

**Las imágenes de producción son otras.** Las de desarrollo montan el código,
instalan las herramientas de prueba y recargan al guardar; la del tablero
arranca con `next dev`, que no puede salir a internet. Las de producción
compilan una vez, no traen `pytest` ni `ruff`, y corren sin root.

**`TRUSTED_PROXY_HOPS=1`.** Caddy es el único salto. Sin esto se usaría la IP
de Caddy para el límite por IP y todo el mundo compartiría el mismo cubo.

**El usuario de prueba solo mira.** Su contraseña está en el README. Con
permiso de despacho, cualquiera podría cerrar un caso real y el bot le avisaría
al ciudadano que se arregló. `DEMO_CAN_DISPATCH` lo enciende en local y en las
pruebas, que recorren el ciclo con él; en producción va apagado.
