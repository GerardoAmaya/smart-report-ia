/**
 * Recorrido 2: agrupar y despachar.
 *
 * Dos personas reportan el mismo hueco. El sistema los junta, el tablero
 * explica por que, y se asigna a una cuadrilla.
 *
 * **Lo que se comprueba no es que se agrupe, sino que se pueda entender.** La
 * fase 5 exige que un operador que no vio el sistema entienda por que varios
 * reportes estan juntos sin que nadie se lo explique, asi que la prueba busca
 * la distancia escrita y el motivo en español.
 */
import { expect, test } from "@playwright/test";

import {
  API,
  buscarMiCaso,
  entrarComoPrueba,
  entrarPorApi,
  esperarA,
  reportarCompleto,
} from "./ayudas";

// El contexto de peticiones tiene sus propias cookies: sin esto, toda
// consulta a la API responde 401.
test.beforeEach(async ({ request }) => {
  await entrarPorApi(request);
});

test("dos reportes del mismo hueco quedan juntos y el tablero explica por que", async ({
  page,
  request,
}) => {
  const marca = `hueco-${Date.now()}`;

  await reportarCompleto(request, { texto: `${marca} uno`, metros: 0 });
  await reportarCompleto(request, { texto: `${marca} dos`, metros: 12 });

  const juntos = await esperarA(async () => {
    const { casoId } = await buscarMiCaso(request, `${marca} dos`);
    const d = await (await request.get(`${API}/board/cases/${casoId}`)).json();
    return d.report_count >= 2 ? d : null;
  }, "que los dos reportes queden en el mismo caso");

  // Los dos mios estan, y estan juntos. No se afirma el total: el sistema
  // agrupa por cercania, asi que otro reporte cerca entraria con razon.
  const mios = juntos.reports.filter((r: { caption?: string }) =>
    r.caption?.startsWith(marca),
  );
  expect(mios).toHaveLength(2);

  await entrarComoPrueba(page);
  // Por enlace directo y no pulsando el primero de la cola: el primero cambia
  // segun lo que haya en la base, y la prueba acabaria mirando un caso ajeno.
  await page.goto(`/?caso=${juntos.id}`);
  await page.getByRole("tab", { name: "Caso" }).click();

  await expect(page.getByText("Por qué están juntos")).toBeVisible();
  // La distancia en metros y el motivo en español: "a 12 m" se puede discutir,
  // un 0,87 no.
  await expect(page.getByText(/A \d+ m del caso, misma categoría/)).toBeVisible();
});

test("asignar a una cuadrilla avisa a quien reporto", async ({ request }) => {
  const texto = `poste-${Date.now()}`;
  const { casoId } = await reportarCompleto(request, { texto, metros: 900 });

  const { crews } = await (await request.get(`${API}/board/crews`)).json();
  expect(crews.length).toBeGreaterThan(0);

  const r = await request.post(`${API}/board/cases/${casoId}/assign?crew_id=${crews[0].id}`);
  expect(r.ok(), await r.text()).toBeTruthy();

  const cuerpo = await r.json();
  expect(cuerpo.status).toBe("assigned");
  // Lo que define la fase 6: el aviso de vuelta salio.
  expect(cuerpo.avisados).toBeGreaterThanOrEqual(1);
});

test("un reporte en la banda de duda no se junta solo", async ({ request }) => {
  /**
   * La asimetria del proyecto: juntar dos problemas distintos esconde uno, que
   * es grave. A 55 m el sistema **no** junta y lo deja marcado como dudoso.
   */
  const marca = `duda-${Date.now()}`;
  await reportarCompleto(request, { texto: `${marca} cerca`, metros: 2000 });
  await reportarCompleto(request, { texto: `${marca} lejos`, metros: 2055 });

  const { casoId } = await buscarMiCaso(request, `${marca} lejos`);
  const d = await (await request.get(`${API}/board/cases/${casoId}`)).json();

  expect(d.report_count).toBe(1);
  expect(d.reports[0].grouping_status).toBe("doubtful");
  const motivo = d.reports[0].evidence.find((e: { decision: string }) => e.decision === "doubtful");
  expect(motivo?.reason).toContain("revisión");
});
