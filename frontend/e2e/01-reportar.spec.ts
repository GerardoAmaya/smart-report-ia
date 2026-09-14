/**
 * Recorrido 1: reportar.
 *
 * Alguien manda una foto y su ubicacion por el bot, y el reporte queda en el
 * sistema con su foto guardada. Es la fase 1 y la 2 juntas, por el camino de
 * verdad: el webhook con su secreto, el trabajador bajando la foto, el
 * almacenamiento.
 */
import { expect, test } from "@playwright/test";

import {
  API,
  entrarComoPrueba,
  entrarPorApi,
  esperarA,
  mandarFoto,
  mandarUbicacion,
  usuarioNuevo,
} from "./ayudas";

// El contexto de peticiones tiene sus propias cookies: sin esto, toda
// consulta a la API responde 401.
test.beforeEach(async ({ request }) => {
  await entrarPorApi(request);
});

test("una foto y una ubicacion se convierten en un reporte con su foto", async ({
  page,
  request,
}) => {
  const usuario = usuarioNuevo();
  const texto = `bache de prueba ${usuario}`;

  await mandarFoto(request, usuario, texto);
  await mandarUbicacion(request, usuario);

  await entrarComoPrueba(page);

  // El trabajador tiene que bajar la foto, subirla y clasificarla. Se espera a
  // que aparezca en la cola en vez de dormir un rato fijo.
  await page.getByRole("tab", { name: /caso/i }).click();

  const caso = await esperarA(async () => {
    const r = await request.get(`${API}/board/cases`);
    const { cases } = await r.json();
    return cases.length > 0 ? cases[0] : null;
  }, "que el reporte aparezca en la cola");

  expect(caso.report_count).toBeGreaterThanOrEqual(1);

  // Y la foto se guardo de verdad: el detalle trae un enlace que se puede abrir.
  const detalle = await esperarA(async () => {
    const r = await request.get(`${API}/board/cases/${caso.id}`);
    const d = await r.json();
    const foto = d.reports[0]?.photos?.[0];
    return foto?.thumbnail_url ? d : null;
  }, "que la foto quede guardada");

  const url = detalle.reports[0].photos[0].thumbnail_url;
  const foto = await request.get(url);
  expect(foto.ok()).toBeTruthy();
  expect(Number(foto.headers()["content-length"] ?? 0)).toBeGreaterThan(1000);
});

test("una ubicacion sin foto pide la foto primero", async ({ request }) => {
  const usuario = usuarioNuevo();

  const r = await request.post(`${API}/webhooks/telegram`, {
    data: {
      update_id: Date.now() % 1_000_000,
      message: {
        message_id: 1,
        date: Math.floor(Date.now() / 1000),
        chat: { id: Number(usuario), type: "private" },
        from: { id: Number(usuario), is_bot: false, first_name: "Vecina" },
        location: { latitude: 13.69, longitude: -89.22 },
      },
    },
    headers: { "X-Telegram-Bot-Api-Secret-Token": process.env.TELEGRAM_WEBHOOK_SECRET ?? "" },
  });

  const cuerpo = await r.json();
  expect(cuerpo.text).toContain("foto");
});

test("sin el secreto el webhook rechaza", async ({ request }) => {
  const r = await request.post(`${API}/webhooks/telegram`, {
    data: { update_id: 1 },
    headers: { "X-Telegram-Bot-Api-Secret-Token": "no-es-el-secreto" },
  });
  expect(r.status()).toBe(403);
});
