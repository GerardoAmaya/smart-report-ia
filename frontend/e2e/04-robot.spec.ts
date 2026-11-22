/**
 * Recorrido 4: el robot del asistente se queda donde lo dejaron.
 *
 * En el celular, al desplazarse, la barra del navegador aparece y se oculta y
 * la ventana cambia de alto varias veces por segundo. Con el drag de Motion,
 * cada cambio volvia a medir y reubicaba al robot arrastrado (saltaba al medio
 * o hasta arriba), y el reacomodo propio lo devolvia a la posicion que tenia al
 * cargar la pagina. Aqui se arrastra y se cambia el alto de la ventana igual.
 */
import { expect, test, type Page } from "@playwright/test";

import { entrarComoPrueba } from "./ayudas";

/** Donde esta el robot: su borde izquierdo y su distancia al borde inferior. */
async function dondeEsta(page: Page) {
  return page.getByRole("button", { name: "Asistente" }).evaluate((b) => {
    const r = b.getBoundingClientRect();
    return {
      izquierda: Math.round(r.left),
      alBorde: Math.round(window.innerHeight - r.bottom),
    };
  });
}

/** Espera a que el muelle termine: dos lecturas seguidas iguales. */
async function quieto(page: Page) {
  let antes = await dondeEsta(page);
  for (let i = 0; i < 30; i++) {
    await page.waitForTimeout(100);
    const ahora = await dondeEsta(page);
    if (ahora.izquierda === antes.izquierda && ahora.alBorde === antes.alBorde) {
      return ahora;
    }
    antes = ahora;
  }
  throw new Error("El robot no se quedo quieto");
}

test("el robot arrastrado se queda donde lo dejaron aunque cambie la ventana", async ({
  page,
}) => {
  await entrarComoPrueba(page);
  const robot = page.getByRole("button", { name: "Asistente" });
  await expect(robot).toBeVisible();
  const caja = (await robot.boundingBox())!;
  const { width, height } = page.viewportSize()!;

  // Arrastrarlo hacia la izquierda y hacia arriba.
  await page.mouse.move(caja.x + caja.width / 2, caja.y + caja.height / 2);
  await page.mouse.down();
  await page.mouse.move(width * 0.3, caja.y - 220, { steps: 12 });
  await page.mouse.up();

  // Arrastrar no es hacer clic: el panel no se abre.
  await expect(page.getByRole("dialog", { name: /Pregúntale al tablero/ })).toBeHidden();
  // Al soltarlo se pega al borde mas cercano, el izquierdo.
  const dejado = await quieto(page);
  expect(dejado.izquierda).toBeLessThan(width / 2);
  expect(dejado.alBorde).toBeGreaterThan(150);

  // La ventana cambia de alto varias veces seguidas, como con la barra del
  // navegador del celular al desplazarse.
  for (const alto of [height - 64, height, height - 64, height, height - 64, height]) {
    await page.setViewportSize({ width, height: alto });
    await page.waitForTimeout(40);
  }

  expect(await quieto(page)).toEqual(dejado);
});

test("el robot subido hasta el tope aparece en el mismo sitio al recargar", async ({ page }) => {
  // Soltado por encima del tope, se guardaba la y sin acotar, y al recargar el
  // reacomodo lo bajaba de mas: tantos pixeles como se hubiera pasado.
  await entrarComoPrueba(page);
  const robot = page.getByRole("button", { name: "Asistente" });
  await expect(robot).toBeVisible();
  const caja = (await robot.boundingBox())!;

  await page.mouse.move(caja.x + caja.width / 2, caja.y + caja.height / 2);
  await page.mouse.down();
  await page.mouse.move(200, 0, { steps: 15 });
  await page.mouse.up();
  const dejado = await quieto(page);

  await page.reload();
  await expect(robot).toBeVisible();
  expect(await quieto(page)).toEqual(dejado);
});
