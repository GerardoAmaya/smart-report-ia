/**
 * Capturas del tablero para el README.
 *
 * Es un guión y no un puñado de capturas a mano para que se puedan **rehacer**:
 * unas imágenes que no se pueden regenerar envejecen con el primer cambio de
 * diseño, y un README con capturas viejas miente sobre lo que el proyecto es.
 *
 * Corre en el **host** y no en el contenedor, igual que las pruebas E2E: el
 * navegador tiene que alcanzar la API en localhost:8000, y desde dentro del
 * contenedor ese localhost es otro.
 *
 *   cd frontend && DEMO_PASSWORD=... node scripts/capturas.mjs
 *
 * `SOLO=entrada,asistente` rehace solo esas. Sirve cuando la base tiene datos
 * de las pruebas E2E y no se quiere pisar las del tablero con ellos.
 *
 * La del asistente hace **una pregunta real al modelo** (unos USD 0,006): una
 * respuesta inventada para la foto seria justo lo que este guion evita.
 *
 * Contra produccion, con el invitado de solo lectura, por un tunel cuando la red
 * filtra el dominio:
 *
 *   ssh -f -N -L 8443:127.0.0.1:443 ubuntu@SERVIDOR
 *   BASE_URL=https://DOMINIO:8443 RESOLVER="MAP DOMINIO 127.0.0.1" \
 *     DEMO_PASSWORD=... node scripts/capturas.mjs
 *
 * Sale lo que haya en la base de desarrollo. No inventa datos: una captura con
 * casos falsos es una promesa, y este proyecto mide en vez de prometer.
 */
import { mkdir } from "node:fs/promises";
import { chromium } from "@playwright/test";

const BASE = process.env.BASE_URL ?? "http://localhost:3100";
const PASSWORD = process.env.DEMO_PASSWORD;
const DESTINO = process.env.DESTINO ?? "../docs/capturas";
const SOLO = process.env.SOLO ? new Set(process.env.SOLO.split(",")) : null;
const toca = (nombre) => !SOLO || SOLO.has(nombre);
// El nombre del dominio se resuelve al tunel: asi el certificado sigue valiendo.
const RESOLVER = process.env.RESOLVER;

if (!PASSWORD) {
  console.error("Falta DEMO_PASSWORD: es la contraseña del usuario de prueba.");
  process.exit(1);
}

const PESTANAS = [
  ["Resumen", "tablero-resumen.png"],
  ["Caso", "tablero-caso.png"],
  ["Mapa", "tablero-mapa.jpg"],
];

const navegador = await chromium.launch({
  args: RESOLVER ? [`--host-resolver-rules=${RESOLVER}`] : [],
});
try {
  await mkdir(DESTINO, { recursive: true });

  // El doble de densidad: en una pantalla normal las capturas a 1x se ven
  // borrosas dentro del README.
  const contexto = await navegador.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
  });
  const pagina = await contexto.newPage();

  await pagina.goto(`${BASE}/entrar`);
  if (toca("entrada")) {
    // El mapa de fondo carga teselas y recorre colonias despacio.
    await pagina.waitForTimeout(6000);
    await pagina.screenshot({ path: `${DESTINO}/entrada.jpg`, quality: 82 });
    console.log(`  ${DESTINO}/entrada.jpg`);
  }
  await pagina.fill("#password", PASSWORD);
  await pagina.click('button[type="submit"]');
  // Se espera al tablero y no a la URL: la navegacion es del lado del cliente
  // y no dispara un evento de carga que esperar.
  await pagina.getByRole("tab", { name: "Resumen", exact: true }).waitFor({ timeout: 20000 });
  // El primer caso de la cola —el mas grave y mas reportado—, abierto por la
  // URL. Antes se buscaba un caso por su direccion escrita aqui, y en otra base
  // no existia. Sin `catch` a proposito: si no hay casos, la captura del caso
  // saldria vacia y es mejor enterarse aqui que en el README.
  // Desde el navegador y no con `pagina.request`: esa la hace Node, que no ve
  // la regla de resolucion del tunel y se va al servidor real por otro puerto.
  const cola = await pagina.evaluate(
    async (base) => (await fetch(`${base}/board/cases`, { credentials: "include" })).json(),
    BASE,
  );
  const primero = cola.cases[0];
  if (!primero) throw new Error("No hay casos: la captura del caso saldria vacia.");
  await pagina.goto(`${BASE}/?caso=${primero.id}`);
  await pagina.getByRole("tab", { name: "Resumen", exact: true }).waitFor({ timeout: 20000 });
  await pagina.waitForTimeout(1200);

  for (const [pestana, nombre] of PESTANAS) {
    if (!toca(nombre.split(".")[0])) continue;
    await pagina.getByRole("tab", { name: pestana, exact: true }).click();
    // El mapa carga teselas y las gráficas animan al entrar: sin esta espera
    // la captura las agarra a medio dibujar.
    await pagina.waitForTimeout(pestana === "Mapa" ? 5000 : 1500);
    await pagina.screenshot({
      path: `${DESTINO}/${nombre}`,
      // El mapa va en JPEG: en PNG pesa dos megas y en un README se nota. Las
      // de interfaz se quedan en PNG, donde el texto sale nítido.
      ...(nombre.endsWith(".jpg") ? { quality: 82 } : {}),
    });
    console.log(`  ${DESTINO}/${nombre}`);
  }

  if (toca("tablero-mapa-3d")) {
    await pagina.getByRole("tab", { name: "Mapa", exact: true }).click();
    await pagina.getByRole("button", { name: /^3d$/i }).click();
    // Encuadre, columnas que crecen y edificios: unos segundos.
    await pagina.waitForTimeout(6000);
    await pagina.screenshot({ path: `${DESTINO}/tablero-mapa-3d.jpg`, quality: 82 });
    console.log(`  ${DESTINO}/tablero-mapa-3d.jpg`);
    await pagina.getByRole("button", { name: /^2d$/i }).click();
  }

  if (toca("robot")) {
    // De cerca y con el raton encima: en una captura de pagina entera el robot
    // es un punto en la esquina, y lo que lo hace simpatico es la cara.
    await pagina.getByRole("tab", { name: "Resumen", exact: true }).click();
    const robot = pagina.getByRole("button", { name: "Asistente" });
    await robot.hover();
    await pagina.waitForTimeout(900);
    const caja = await robot.boundingBox();
    if (caja) {
      const lado = 260;
      await pagina.screenshot({
        path: `${DESTINO}/robot.png`,
        clip: {
          x: Math.max(0, caja.x + caja.width / 2 - lado / 2),
          y: Math.max(0, caja.y + caja.height / 2 - lado / 2 - 20),
          width: lado,
          height: lado,
        },
      });
      console.log(`  ${DESTINO}/robot.png`);
    }
    await pagina.mouse.move(10, 10);
  }

  if (toca("asistente")) {
    await pagina.getByRole("tab", { name: "Resumen", exact: true }).click();
    await pagina.getByRole("button", { name: "Asistente" }).click();
    await pagina
      .getByLabel("Pregunta para el asistente")
      .fill("¿Qué quedó pendiente? Dame los urgentes primero.");
    await pagina.getByRole("button", { name: "Preguntar" }).click();
    // Se espera a que deje de consultar, no un tiempo fijo: el modelo tarda lo
    // que tarda, y una captura a medias mostraria el indicador de carga.
    await pagina.getByText("Consultando el tablero").waitFor({ state: "visible", timeout: 10000 });
    await pagina.getByText("Consultando el tablero").waitFor({ state: "detached", timeout: 90000 });
    await pagina.waitForTimeout(800);
    await pagina.screenshot({ path: `${DESTINO}/asistente.png` });
    console.log(`  ${DESTINO}/asistente.png`);
  }
  if (toca("movil")) {
    // El tablero en un telefono, con su barra de abajo. Contexto propio: el
    // ancho decide el diseño desde la primera pintura.
    const movil = await navegador.newContext({
      viewport: { width: 390, height: 844 },
      deviceScaleFactor: 2,
      isMobile: true,
      hasTouch: true,
    });
    await movil.addCookies(await contexto.cookies());
    const tel = await movil.newPage();
    await tel.goto(`${BASE}/`);
    await tel.waitForTimeout(4000);
    await tel.screenshot({ path: `${DESTINO}/movil.png` });
    console.log(`  ${DESTINO}/movil.png`);
    await movil.close();
  }
} finally {
  await navegador.close();
}
