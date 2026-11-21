/**
 * Color para el mapa base, con la paleta del proyecto.
 *
 * Positron y dark de OpenFreeMap son grises a proposito, y el mapa se veia
 * muerto. Aqui se retiñen sobre el estilo ya cargado: agua azul suave, verde de
 * la familia de --verde en parques y bosques, arena calida en edificios, calles
 * claras. En oscuro, la misma idea en tonos nocturnos.
 *
 * **Nada rojo, naranja ni ambar en el fondo.** Esos colores dicen "urgente" y
 * "atender" en los pines y en las columnas 3D; si el mapa los usara, un pin rojo
 * sobre una carretera naranja dejaria de saltar a la vista, que es su unico
 * trabajo. La arena de los edificios es neutra y apagada por la misma razon.
 *
 * Los ids salen de los estilos reales (positron y dark difieren: el parque es
 * `park` en uno y `landuse_park` en el otro). Cada capa se comprueba antes de
 * tocarla: si OpenFreeMap cambia el estilo, se pierde el color, no el mapa.
 */
import type { Map as MapLibreMap } from "maplibre-gl";

type Propiedad = Parameters<MapLibreMap["setPaintProperty"]>[1];

type Tinte = Record<string, Record<string, string | number | undefined>>;

const CLARO: Tinte = {
  background: { "background-color": "#f2f0ea" },
  landuse_residential: { "fill-color": "#ece8df" },
  park: { "fill-color": "#d6e7d9" },
  landuse_park: { "fill-color": "#d6e7d9" },
  landcover_wood: { "fill-color": "#cde1d0" },
  water: { "fill-color": "#bcd6e4" },
  waterway: { "line-color": "#a8cadb" },
  building: { "fill-color": "#e8dfcf", "fill-outline-color": "#d9ccb5" },
  "aeroway-area": { "fill-color": "#f6f4ef" },
  highway_path: { "line-color": "#f7f5f0" },
  highway_minor: { "line-color": "#ffffff" },
  highway_major_casing: { "line-color": "#ddd6c8" },
  highway_major_inner: { "line-color": "#ffffff" },
  highway_motorway_casing: { "line-color": "#d4ccbc" },
  highway_motorway_inner: { "line-color": "#ffffff" },
  highway_motorway_bridge_casing: { "line-color": "#d4ccbc" },
  highway_motorway_bridge_inner: { "line-color": "#ffffff" },
  water_name_point_label: { "text-color": "#3d6f8c" },
  water_name_line_label: { "text-color": "#3d6f8c" },
};

const OSCURO: Tinte = {
  background: { "background-color": "#12161a" },
  landuse_residential: { "fill-color": "#161b20" },
  park: { "fill-color": "#1b3629" },
  landuse_park: { "fill-color": "#1b3629" },
  // El estilo oscuro pinta el bosque con una textura (`fill-pattern`), que tapa
  // cualquier color, y lo baja a 0,4 a zoom de ciudad: sin quitar las dos, el
  // verde no aparecia. `undefined` devuelve la propiedad a su valor por defecto.
  landcover_wood: { "fill-pattern": undefined, "fill-color": "#1a3428", "fill-opacity": 0.85 },
  water: { "fill-color": "#12304a" },
  waterway: { "line-color": "#1a4260" },
  building: { "fill-color": "#1f2329", "fill-outline-color": "#2a3037" },
  highway_path: { "line-color": "#20262d" },
  highway_minor: { "line-color": "#252c34" },
  highway_major_casing: { "line-color": "#1b2026" },
  highway_major_inner: { "line-color": "#2e363f" },
  highway_major_subtle: { "line-color": "#2a3139" },
  highway_motorway_casing: { "line-color": "#1b2026" },
  highway_motorway_inner: { "line-color": "#36404a" },
  highway_motorway_subtle: { "line-color": "#262d35" },
  water_name: { "text-color": "#6f9ab5", "text-halo-color": "#0d1b24" },
  highway_name_other: { "text-color": "#7c8791", "text-halo-color": "#12161a" },
  highway_name_motorway: { "text-color": "#8a959f" },
  place_other: { "text-color": "#8b96a0" },
  place_suburb: { "text-color": "#8b96a0" },
  place_village: { "text-color": "#97a2ab" },
  place_town: { "text-color": "#a3adb5" },
  place_city: { "text-color": "#b3bcc3" },
  place_city_large: { "text-color": "#b3bcc3" },
};

/** Retiñe el estilo cargado. Se llama en cada `style.load`: el tema lo reemplaza. */
export function teñirMapa(m: MapLibreMap, oscuro: boolean): void {
  for (const [capa, pintura] of Object.entries(oscuro ? OSCURO : CLARO)) {
    if (!m.getLayer(capa)) continue;
    for (const [propiedad, valor] of Object.entries(pintura)) {
      try {
        m.setPaintProperty(capa, propiedad as Propiedad, valor);
      } catch {
        // Una propiedad que la capa no admite no puede tumbar el mapa.
      }
    }
  }
}

/**
 * Los edificios en relieve del 3D: la misma arena, un punto mas clara que la de
 * los edificios planos, porque las caras laterales ya salen en sombra.
 */
export function colorEdificio3D(oscuro: boolean): string {
  return oscuro ? "#2a2e35" : "#ece2d1";
}
