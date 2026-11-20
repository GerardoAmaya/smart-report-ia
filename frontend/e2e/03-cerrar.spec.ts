/**
 * Recorrido 3: cerrar.
 *
 * La parte que casi nadie construye: se sube la foto del arreglo, se cierra, y
 * **se le avisa de vuelta a todos los que reportaron**. Sin eso nadie reporta
 * dos veces.
 */
import { expect, test } from "@playwright/test";

import {
  API,
  buscarMiCaso,
  entrarComoPrueba,
  entrarPorApi,
  esperarA,
  mensajesDelBot,
  reportarCompleto,
} from "./ayudas";

/** Un JPEG minimo pero valido: la evidencia se valida abriendola. */
function jpegDePrueba(): Buffer {
  // 1x1 en JPEG, suficiente para que Pillow lo abra.
  return Buffer.from(
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a" +
      "HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAA" +
      "AAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q==",
    "base64",
  );
}

// El contexto de peticiones tiene sus propias cookies: sin esto, toda
// consulta a la API responde 401.
test.beforeEach(async ({ request }) => {
  await entrarPorApi(request);
});

test("no se cierra sin foto del arreglo", async ({ request }) => {
  const texto = `sin-foto-${Date.now()}`;
  const { casoId } = await reportarCompleto(request, { texto, metros: 3000 });

  const { crews } = await (await request.get(`${API}/board/crews`)).json();
  await request.post(`${API}/board/cases/${casoId}/assign?crew_id=${crews[0].id}`);

  // Recien asignado, la foto del arreglo todavia no cabe: nadie esta trabajando.
  const antes = await request.post(`${API}/board/cases/${casoId}/evidence`, {
    multipart: {
      archivo: { name: "arreglo.jpg", mimeType: "image/jpeg", buffer: jpegDePrueba() },
    },
  });
  expect(antes.status()).toBe(409);
  expect((await antes.json()).detail).toContain("trabajando");

  // Ya en curso, lo que falta para cerrar es la foto.
  expect((await request.post(`${API}/board/cases/${casoId}/start`)).ok()).toBeTruthy();
  const r = await request.post(`${API}/board/cases/${casoId}/close`);

  expect(r.status()).toBe(409);
  expect((await r.json()).detail).toContain("foto");
});

test("el ciclo completo: reportar, asignar, empezar, subir evidencia, cerrar y avisar", async ({
  page,
  request,
}) => {
  const texto = `ciclo-${Date.now()}`;
  const { usuario, casoId } = await reportarCompleto(request, { texto, metros: 4000 });

  const { crews } = await (await request.get(`${API}/board/crews`)).json();
  const asignado = await request.post(
    `${API}/board/cases/${casoId}/assign?crew_id=${crews[0].id}`,
  );
  expect(asignado.ok()).toBeTruthy();

  // La foto del arreglo solo cabe con el caso en curso.
  const empezado = await request.post(`${API}/board/cases/${casoId}/start`);
  expect(empezado.ok(), await empezado.text()).toBeTruthy();

  const subida = await request.post(`${API}/board/cases/${casoId}/evidence`, {
    multipart: {
      archivo: { name: "arreglo.jpg", mimeType: "image/jpeg", buffer: jpegDePrueba() },
    },
  });
  expect(subida.ok(), await subida.text()).toBeTruthy();

  const cerrado = await request.post(
    `${API}/board/cases/${casoId}/close?nota=${encodeURIComponent("Se reparó el tramo")}`,
  );
  expect(cerrado.ok(), await cerrado.text()).toBeTruthy();

  const cuerpo = await cerrado.json();
  expect(cuerpo.status).toBe("closed");
  expect(cuerpo.avisados).toBeGreaterThanOrEqual(1);

  // El trabajador tiene que mandarlo de verdad, no solo encolarlo, y con la
  // foto del arreglo: quien reporto es quien mejor sabe si se arreglo.
  const cierre = await esperarA(async () => {
    const enviados = await mensajesDelBot(request, usuario);
    return enviados.find((m) => (m.foto ?? 0) > 0) ?? null;
  }, "que el aviso de cierre salga con la foto del arreglo");
  expect(cierre.texto).toContain("resuelto");

  // Y se ve en el tablero.
  await entrarComoPrueba(page);
  await page.getByRole("tab", { name: "Caso" }).click();
  await page.goto(`/?caso=${casoId}`);
});

test("el tablero se actualiza sin recargar", async ({ page, request }) => {
  /**
   * Lo que define esta fase. Se abre el tablero, entra un reporte por el bot, y
   * el tablero lo cuenta **sin que nadie recargue**.
   *
   * Se mira el contador del resumen y no la cola: la cola ordena por gravedad y
   * por antigüedad, muestra un tope, y un caso nuevo y leve cae al final. Con la
   * base de desarrollo llena de corridas anteriores, el caso entraba y no se
   * veia, y la prueba fallaba por un motivo que no era el que mide.
   */
  await entrarComoPrueba(page);

  // El indicador dice que el flujo esta vivo.
  await expect(page.getByText("En vivo")).toBeVisible({ timeout: 15_000 });

  const contador = page.locator('[data-cifra="reportes"]');
  await expect(contador).toBeVisible({ timeout: 15_000 });
  const antes = Number(await contador.innerText());

  await reportarCompleto(request, { texto: `en-vivo-${Date.now()}`, metros: 5000 });

  // Sin page.reload(): si hiciera falta recargar, esto fallaria.
  await expect(async () => {
    expect(Number(await contador.innerText())).toBeGreaterThan(antes);
  }).toPass({ timeout: 30_000 });
});
