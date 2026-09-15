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
 * Sale lo que haya en la base de desarrollo. No inventa datos: una captura con
 * casos falsos es una promesa, y este proyecto mide en vez de prometer.
 */
import { mkdir } from "node:fs/promises";
import { chromium } from "@playwright/test";

const BASE = process.env.BASE_URL ?? "http://localhost:3100";
const PASSWORD = process.env.DEMO_PASSWORD;
const DESTINO = process.env.DESTINO ?? "../docs/capturas";

if (!PASSWORD) {
  console.error("Falta DEMO_PASSWORD: es la contraseña del usuario de prueba.");
  process.exit(1);
}

const PESTANAS = [
  ["Resumen", "tablero-resumen.png"],
  ["Caso", "tablero-caso.png"],
  ["Mapa", "tablero-mapa.jpg"],
];

const navegador = await chromium.launch();
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
  await pagina.fill("#password", PASSWORD);
  await pagina.click('button[type="submit"]');
  // Se espera al tablero y no a la URL: la navegacion es del lado del cliente
  // y no dispara un evento de carga que esperar.
  await pagina.getByRole("tab", { name: "Resumen", exact: true }).waitFor({ timeout: 20000 });
  // El primer caso de la cola, para que la pestaña del caso no salga vacía.
  // Sin `catch` a propósito: si esto falla, la captura saldría mal y es mejor
  // enterarse aquí que descubrirlo en el README.
  await pagina.locator("button", { hasText: "Alameda" }).first().click();
  await pagina.waitForTimeout(1200);

  for (const [pestana, nombre] of PESTANAS) {
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
} finally {
  await navegador.close();
}
