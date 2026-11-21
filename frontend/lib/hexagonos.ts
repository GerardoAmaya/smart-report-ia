/**
 * Los casos agrupados en hexagonos, para las columnas del mapa en 3D.
 *
 * **Hecho aqui y no con deck.gl ni H3.** Son decenas o cientos de puntos: el
 * calculo es una cuenta, no un motor. deck.gl son unos 300 KB comprimidos mas
 * un puente con MapLibre; H3 trae WebAssembly. Asi las columnas se dibujan con
 * `fill-extrusion` del mismo MapLibre que ya pinta el mapa, sin otra capa de
 * render que mantener.
 *
 * Hexagonos y no cuadros: todos los vecinos quedan a la misma distancia, asi
 * que dos reportes a 200 m no caen en celdas distintas segun hacia donde esten.
 */
import type { Punto } from "./api";

const R_TIERRA = 6_371_008.8;
const RAD = Math.PI / 180;

// Proyeccion local alrededor de San Salvador. Para el tamaño del pais la
// deformacion es despreciable, y evita traer una libreria de proyecciones.
const LAT0 = 13.6929 * RAD;
const LON0 = -89.2182 * RAD;

const aMetros = (lon: number, lat: number): [number, number] => [
  (lon * RAD - LON0) * Math.cos(LAT0) * R_TIERRA,
  (lat * RAD - LAT0) * R_TIERRA,
];

const aGrados = (x: number, y: number): [number, number] => [
  (x / (Math.cos(LAT0) * R_TIERRA) + LON0) / RAD,
  (y / R_TIERRA + LAT0) / RAD,
];

/** Hexagono que contiene el punto (coordenadas axiales, vertice arriba). */
function celda(x: number, y: number, radio: number): [number, number] {
  const q = ((Math.sqrt(3) / 3) * x - y / 3) / radio;
  const r = ((2 / 3) * y) / radio;
  // Redondeo en coordenadas cubicas: redondear q y r por separado cae a veces
  // en el hexagono vecino.
  let rq = Math.round(q);
  let rr = Math.round(r);
  const rs = Math.round(-q - r);
  const dq = Math.abs(rq - q);
  const dr = Math.abs(rr - r);
  const ds = Math.abs(rs - (-q - r));
  if (dq > dr && dq > ds) rq = -rr - rs;
  else if (dr > ds) rr = -rq - rs;
  return [rq, rr];
}

const ORDEN_SEVERIDAD: Record<string, number> = { alta: 3, media: 2, baja: 1 };

export type PropiedadesColumna = {
  /** Identidad estable de la celda (radio y posicion): con ella se anima cada
   *  columna por separado y se sabe cual es nueva cuando llegan datos. */
  clave: string;
  reportes: number;
  casos: number;
  /** El caso, si la columna tiene uno solo: el clic lo abre directo. */
  caso: string | null;
  severidad: string | null;
  lon: number;
  lat: number;
};

type Coleccion = {
  type: "FeatureCollection";
  features: {
    type: "Feature";
    properties: PropiedadesColumna;
    geometry: { type: "Polygon"; coordinates: [number, number][][] };
  }[];
};

/**
 * El radio del hexagono segun el zoom.
 *
 * Fijo no sirve: 180 m eran once pixeles a zoom 13 y una mancha que tapaba la
 * colonia a zoom 16. Por tramos y no continuo, porque cambiar el radio rehace
 * las celdas y los casos saltan de una a otra: con tramos eso pasa tres veces
 * y no en cada movimiento de la rueda.
 */
export function radioParaZoom(zoom: number): number {
  if (zoom < 13.5) return 320;
  if (zoom < 14.5) return 220;
  if (zoom < 15.5) return 150;
  if (zoom < 16.5) return 100;
  if (zoom < 17.5) return 60;
  return 40;
}

/**
 * Las columnas: una por hexagono con casos.
 *
 * Cuenta **reportes**, no casos: lo que se quiere ver es donde se concentra el
 * reclamo de la gente. La altura no se calcula aqui sino en el mapa, segun el
 * zoom (ver `ALTURA_COLUMNA` en Mapa.tsx).
 */
export function columnas(puntos: Punto[], radio = 180): Coleccion {
  const grupos = new Map<string, { q: number; r: number; ps: Punto[] }>();
  for (const p of puntos) {
    const [x, y] = aMetros(p.lon, p.lat);
    const [q, r] = celda(x, y, radio);
    const clave = `${q},${r}`;
    const g = grupos.get(clave) ?? { q, r, ps: [] };
    g.ps.push(p);
    grupos.set(clave, g);
  }

  // Un poco mas chico que la celda: el hueco entre columnas es lo que deja
  // leerlas como columnas y no como una sola masa.
  const lado = radio * 0.86;

  return {
    type: "FeatureCollection",
    features: [...grupos.values()].map(({ q, r, ps }) => {
      const cx = radio * Math.sqrt(3) * (q + r / 2);
      const cy = radio * 1.5 * r;
      const anillo: [number, number][] = [];
      for (let i = 0; i <= 6; i++) {
        const a = (60 * (i % 6) - 30) * RAD;
        anillo.push(aGrados(cx + lado * Math.cos(a), cy + lado * Math.sin(a)));
      }
      const reportes = ps.reduce((n, p) => n + p.report_count, 0);
      const severidad =
        ps
          .map((p) => p.severity)
          .sort((a, b) => (ORDEN_SEVERIDAD[b ?? ""] ?? 0) - (ORDEN_SEVERIDAD[a ?? ""] ?? 0))[0] ??
        null;
      const [lon, lat] = aGrados(cx, cy);
      return {
        type: "Feature" as const,
        properties: {
          clave: `${radio}:${q},${r}`,
          reportes,
          casos: ps.length,
          caso: ps.length === 1 ? ps[0].id : null,
          severidad,
          lon,
          lat,
        },
        geometry: { type: "Polygon" as const, coordinates: [anillo] },
      };
    }),
  };
}

export type Encuadre =
  | { tipo: "punto"; centro: [number, number] }
  | { tipo: "caja"; caja: [[number, number], [number, number]] };

// Celdas gruesas, del tamaño de un barrio grande, para buscar donde se
// concentra el reclamo. Y la distancia hasta la que un caso cuenta como "de
// esa zona" al encuadrar.
const CELDA_GRUESA = 1500;
const RADIO_ZONA = 2500;

/**
 * A donde mirar al entrar en 3D.
 *
 * **El grupo mas denso, no todos los casos.** Encuadrar todo, con casos a
 * kilometros unos de otros, aleja la camara hasta que cada columna es un punto y
 * no se ve ni un edificio: es el mapa 2D, inclinado y peor. Se busca la celda de
 * 1,5 km con mas reportes (en empate, con mas casos) y se encuadran los casos a
 * menos de 2,5 km de su centro, ponderado por reportes. El resto sigue en el
 * mapa; se llega con la rueda o volviendo a 2D.
 *
 * Si ese grupo es un solo caso, o todos estan en unas pocas cuadras, se centra
 * en el: una caja diminuta llevaria la camara mas cerca de lo util.
 */
export function encuadre(puntos: Punto[]): Encuadre | null {
  if (puntos.length === 0) return null;

  const celdas = new Map<string, Punto[]>();
  for (const p of puntos) {
    const [x, y] = aMetros(p.lon, p.lat);
    const clave = celda(x, y, CELDA_GRUESA).join(",");
    celdas.set(clave, [...(celdas.get(clave) ?? []), p]);
  }
  const peso = (ps: Punto[]) => ps.reduce((n, p) => n + p.report_count, 0);
  const densa = [...celdas.values()].sort(
    (a, b) => peso(b) - peso(a) || b.length - a.length,
  )[0];

  const total = peso(densa);
  const cx = densa.reduce((n, p) => n + aMetros(p.lon, p.lat)[0] * p.report_count, 0) / total;
  const cy = densa.reduce((n, p) => n + aMetros(p.lon, p.lat)[1] * p.report_count, 0) / total;

  const zona = puntos.filter((p) => {
    const [x, y] = aMetros(p.lon, p.lat);
    return Math.hypot(x - cx, y - cy) <= RADIO_ZONA;
  });
  const xs = zona.map((p) => aMetros(p.lon, p.lat)[0]);
  const ys = zona.map((p) => aMetros(p.lon, p.lat)[1]);
  const ancho = Math.max(...xs) - Math.min(...xs);
  const alto = Math.max(...ys) - Math.min(...ys);

  if (zona.length === 1 || Math.max(ancho, alto) < 400) {
    return { tipo: "punto", centro: aGrados(cx, cy) };
  }
  return {
    tipo: "caja",
    caja: [
      aGrados(Math.min(...xs), Math.min(...ys)),
      aGrados(Math.max(...xs), Math.max(...ys)),
    ],
  };
}
