import { defineConfig, devices } from "@playwright/test";

/**
 * Pruebas extremo a extremo **contra el sistema levantado**, no contra
 * simulaciones. Es lo que PLAN.md exige para dar la fase por terminada: una
 * prueba que simula la API comprueba que el frontend se entiende consigo mismo,
 * no que el sistema funciona.
 *
 * Por eso no hay `webServer`: el stack se levanta con `make up` —base, API,
 * trabajador, almacenamiento y frontend— y estas pruebas lo usan tal cual.
 */
export default defineConfig({
  // Montado desde la raiz del repo en `./e2e` dentro del contenedor: las
  // pruebas viven fuera de frontend/ porque prueban el sistema entero, pero
  // Node necesita verlas bajo el arbol que tiene node_modules.
  // Viven bajo frontend/ por una razon practica, no conceptual: **prueban el
  // sistema entero** —webhook, trabajador, almacenamiento, tablero— pero Node
  // resuelve los modulos subiendo desde el archivo, y desde la raiz del repo
  // no verian `frontend/node_modules`, que es donde vive Playwright.
  testDir: "./e2e",
  // Uno solo: las pruebas comparten la misma base y el mismo bot. En paralelo
  // se pisarian los datos, y un fallo intermitente enseña a ignorar el rojo.
  workers: 1,
  fullyParallel: false,
  // Sin reintentos: un recorrido que solo pasa a veces es un recorrido roto, y
  // reintentar lo esconde.
  retries: 0,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3100",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    locale: "es-SV",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
