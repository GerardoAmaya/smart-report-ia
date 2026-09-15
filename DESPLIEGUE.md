# Despliegue

Cómo poner este sistema en internet y cómo operarlo después. Todo el software
que hace falta es gratuito y permanente; el único costo real es la API del
modelo, unos **USD 0,0018 por foto**.

El sistema entero vive en una máquina. Es lo que permite que salga gratis, y
también lo que hay que tener presente: si la máquina cae, cae todo. Por eso el
respaldo diario a R2 no es opcional.

---

## Lo que hay que crear

Cinco cuentas. Ninguna cobra en este uso.

| Dónde | Para qué | Lo que hay que sacar |
|---|---|---|
| **Oracle Cloud** | la máquina | una VM Ampere A1 (ARM), Ubuntu |
| **Cloudflare R2** | fotos y respaldos | endpoint, bucket, clave y secreto |
| **DuckDNS** | el dominio | un subdominio y su token |
| **Google Cloud** | entrada al tablero | client id y secreto de OAuth |
| **Anthropic** | clasificación | una clave de API |

El bot de Telegram ya existe; solo hace falta su token.

### Oracle: la máquina

En «Always Free» tomar una **VM.Standard.A1.Flex** con 4 OCPU y 24 GB, imagen
**Ubuntu 22.04 o 24.04 (aarch64)**. Es gratis permanente, no una prueba.

Dos cosas que hacen perder una tarde si no se saben:

- **«Out of host capacity»** es normal en las regiones ARM más pedidas. Se
  resuelve probando otro dominio de disponibilidad o reintentando; no es un
  problema de la cuenta.
- **Abrir los puertos 80 y 443 en dos sitios.** En la *Security List* de la red
  virtual, y además dentro de la máquina: las imágenes de Ubuntu de Oracle
  traen reglas de `iptables` que bloquean todo lo que no sea SSH. Si solo se
  abre en la consola, el sitio no responde y parece que Caddy falla.

```sh
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

### DuckDNS: el dominio

Crear un subdominio y apuntarlo a la **IP pública** de la máquina. Sirve para
las tres cosas que necesitan nombre: el webhook de Telegram, el redirect de
Google y el certificado HTTPS.

### Google: la entrada al tablero

Crear credenciales OAuth de tipo «aplicación web» con el redirect
**exacto**: `https://TU-DOMINIO/auth/google/callback`. Google compara carácter
a carácter; una barra de más y falla con un error que no explica nada.

Quién puede entrar **no lo decide Google**: lo decide la tabla de usuarios. El
correo autorizado se siembra con los seeders.

### Cloudflare R2

Crear el bucket y unas credenciales de API con acceso solo a él. El endpoint
tiene la forma `https://<id de cuenta>.r2.cloudflarestorage.com`.

---

## Poner en marcha

En la máquina, con Docker ya instalado:

```sh
git clone <el repositorio> smart-report-ia
cd smart-report-ia

cp .env.prod.example .env.prod
# Rellenar. Los secretos se generan, no se inventan:
#   openssl rand -hex 32
nano .env.prod

docker compose -f deploy/compose.yml --env-file .env.prod up -d --build
```

Las migraciones corren solas al arrancar la API: van en `start.sh` y no en un
hook, porque un hook que no corre falla en silencio.

Sembrar el usuario que puede entrar y las cuadrillas:

```sh
docker compose -f deploy/compose.yml --env-file .env.prod exec api python -m seeders.runner
```

Registrar el webhook, ya con el dominio sirviendo por HTTPS:

```sh
./deploy/registrar-webhook.sh
```

El guión comprueba primero que el dominio conteste, antes de decirle a Telegram
que mande ahí. Un dominio mal apuntado, sin esa comprobación, se descubre
cuando alguien reporta y no pasa nada.

---

## Comprobar que quedó bien

```sh
curl -s https://TU-DOMINIO/health | python3 -m json.tool
```

Tiene que decir `"status": "ok"`. Devuelve 200 aunque esté degradado —el estado
va en el cuerpo— así que hay que leerlo, no mirar el código HTTP.

Después, **la verificación de verdad**: mandarle una foto y una ubicación al bot
desde un teléfono, confirmar la categoría cuando la proponga, y ver el caso
aparecer en el tablero. De la foto al aviso de vuelta.

---

## Operar

```sh
# Ver qué está pasando
docker compose -f deploy/compose.yml --env-file .env.prod logs -f api worker

# Actualizar a la última versión
git pull
docker compose -f deploy/compose.yml --env-file .env.prod up -d --build

# Qué dice Telegram del webhook ahora mismo
./scripts/webhook.sh
```

### Respaldos

El servicio `mantenimiento` aplica la retención y sube un volcado de la base a
R2 todos los días, y una vez al arrancar —así, si el respaldo está roto, se
sabe al desplegar y no veinticuatro horas después. Se guardan catorce días bajo
`respaldos/` en el bucket.

Va dentro del despliegue y no en un cron del servidor por el mismo motivo que
las migraciones: lo que hay que acordarse de configurar aparte es lo que un día
no está, y falla callado.

Para restaurar:

```sh
# Bajar el volcado del bucket, y entonces:
docker compose -f deploy/compose.yml --env-file .env.prod exec -T db \
  pg_restore --clean --if-exists -U smart_report -d smart_report < volcado.dump
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

**PostGIS no es la imagen oficial.** Esa no publica arm64 y la máquina gratuita
de Oracle es ARM. `imresamu/postgis` es el espejo multiarquitectura del mismo
proyecto.

**Las imágenes de producción son otras.** Las de desarrollo montan el código,
instalan las herramientas de prueba y recargan al guardar; la del tablero
arranca con `next dev`, que no puede salir a internet. Las de producción
compilan una vez, no traen `pytest` ni `ruff`, y corren sin root.

**`TRUSTED_PROXY_HOPS=1`.** Caddy es el único salto. Sin esto se usaría la IP
de Caddy para el límite por IP y todo el mundo compartiría el mismo cubo.
