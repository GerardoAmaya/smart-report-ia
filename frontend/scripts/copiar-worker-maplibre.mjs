/**
 * Copia el worker de MapLibre a `public/`.
 *
 * Existe por un fallo conocido de Turbopack: no emite el worker que decodifica
 * las teselas, asi que **el mapa se monta y no pide una sola tesela**. No hay
 * error en consola ni peticion fallida — los pines se ven, el fondo no, y
 * parece un problema del proveedor de teselas.
 *
 * Se copian los dos archivos: el worker importa `./maplibre-gl-shared.mjs`
 * **relativo a si mismo**, asi que tienen que quedar en la misma carpeta.
 *
 * Se corre en cada `dev` y `build` en vez de dejar los archivos en el
 * repositorio: asi no se quedan viejos cuando se suba la version de MapLibre,
 * que es como esto vuelve a romperse sin que nadie lo relacione.
 */
import { copyFile, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";

const require = createRequire(import.meta.url);
const dist = dirname(require.resolve("maplibre-gl/dist/maplibre-gl.mjs"));
const destino = join(process.cwd(), "public", "maplibre");

const ARCHIVOS = ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"];

await mkdir(destino, { recursive: true });
for (const archivo of ARCHIVOS) {
  await copyFile(join(dist, archivo), join(destino, archivo));
}
console.log(`maplibre: ${ARCHIVOS.length} archivos copiados a public/maplibre/`);
