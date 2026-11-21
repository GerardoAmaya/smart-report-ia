"use client";

/**
 * El mapa de casos.
 *
 * **El tamaño del pin es cuantos reportan lo mismo.** Un mapa de puntos iguales
 * tira a la basura la informacion de donde se concentra el reclamo, que es
 * justo lo que un mapa deberia mostrar.
 *
 * **En 3D, la misma idea con altura.** La camara se inclina, los edificios
 * salen en relieve para orientarse, y los casos se juntan en columnas por zona:
 * la altura es cuantos reportan ahi y el color la urgencia mas alta. El 3D va
 * aqui y no en las graficas: en un mapa la altura informa; en una barra, la
 * perspectiva deforma las cantidades.
 *
 * MapLibre y no Leaflet: el tablero tiene que dibujar cientos de casos con
 * cambios en vivo, y Leaflet es raster y se queda corto ahi.
 *
 * Teselas de un proveedor sin llave: una demo que pide registrarse para ver el
 * mapa deja de ser una demo.
 */
import { useQuery } from "@tanstack/react-query";
// MapLibre 6 quito el export por defecto: ahora son exports nombrados.
import {
  type GeoJSONSource,
  Map as MapLibreMap,
  type MapLayerMouseEvent,
  Marker,
  NavigationControl,
  Popup,
  setWorkerUrl,
} from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

import {
  anillosDeUrgencia,
  CAPAS_PULSO,
  crearCrecimiento,
  crearOrbita,
  crearPulso,
  FUENTE_COLUMNAS,
  FUENTE_PULSO,
  sinMovimiento,
} from "@/componentes/MapaAnimaciones";
import { api, type Punto } from "@/lib/api";
import { colorEdificio3D, teñirMapa } from "@/lib/colorMapa";
import {
  columnas,
  encuadre,
  type PropiedadesColumna,
  radioParaZoom,
} from "@/lib/hexagonos";
import { categoria } from "@/lib/textos";
import { cn } from "@/lib/utils";

// San Salvador. Si no hay casos, el mapa tiene que abrir en algun sitio con
// sentido y no en el Atlantico.
const CENTRO: [number, number] = [-89.2182, 13.6929];

/**
 * El worker de MapLibre, servido desde `public/`.
 *
 * **Turbopack no lo emite**, asi que el mapa se monta y no pide una sola
 * tesela: los pines se ven —son HTML— y el fondo no. No hay error en consola
 * ni peticion fallida, que es lo que lo vuelve dificil de encontrar.
 *
 * Los copia `scripts/copiar-worker-maplibre.mjs` antes de cada `dev` y `build`.
 * Se registra **antes de construir ningun mapa**: despues no tiene efecto.
 */
setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");

const ESTILO_CLARO = "https://tiles.openfreemap.org/styles/positron";
const ESTILO_OSCURO = "https://tiles.openfreemap.org/styles/dark";

// Inclinada lo justo para que la altura se lea como altura sin esconder las
// calles de atras; el giro leve evita la vista de maqueta perfectamente
// frontal, donde las columnas se tapan entre si.
const CAMARA_3D = { pitch: 55, bearing: -18 };

// Al entrar en 3D: lo bastante cerca para que salgan los edificios (la capa
// trae relieve desde zoom 13 y se nota desde 14) y no tanto que una zona de
// varios casos no quepa. Con un solo caso, 15,5: se ve la cuadra alrededor.
const ZOOM_3D_MIN = 14;
const ZOOM_3D_MAX = 16;
const ZOOM_3D_UN_CASO = 15.5;

/**
 * La altura de las columnas, segun el zoom.
 *
 * Fija no sirve: a zoom 13 una columna de 110 m es un punto, y a zoom 16 la
 * misma es una torre que tapa la colonia. Con la altura que baja al acercarse,
 * una columna de **un** reporte queda siempre varias veces por encima del
 * edificio tipico (10 a 20 m) y una de muchos destaca sin salirse del cuadro.
 * Lineal en reportes y no raiz: aqui se comparan alturas de un vistazo y una
 * escala deformada mentiria. Con tope.
 *
 * Cada parada va multiplicada por el estado `h` de la columna, que es lo que
 * la hace crecer desde el suelo (ver `crearCrecimiento`). Va dentro de cada
 * parada y no envolviendo la interpolacion: MapLibre solo acepta el zoom como
 * entrada de la interpolacion de arriba del todo. Sin estado, `h` vale 1.
 */
const CRECE = ["coalesce", ["feature-state", "h"], 1];
const ALTURA_COLUMNA = [
  "interpolate",
  ["linear"],
  ["zoom"],
  12,
  ["*", CRECE, ["min", 2600, ["+", 260, ["*", ["get", "reportes"], 160]]]],
  14,
  ["*", CRECE, ["min", 1600, ["+", 150, ["*", ["get", "reportes"], 90]]]],
  16,
  ["*", CRECE, ["min", 900, ["+", 80, ["*", ["get", "reportes"], 45]]]],
  18,
  ["*", CRECE, ["min", 300, ["+", 35, ["*", ["get", "reportes"], 14]]]],
];

type Modo = "2d" | "3d";

/**
 * El radio con el que estan hechas las celdas que hay en el mapa.
 *
 * No se lee del zoom en cada uso: al entrar en 3D la camara vuela de zoom 12 a
 * 15, y con el zoom de ese momento las primeras columnas salian de celdas de
 * 320 m —un hexagono gigante que se encogia al aterrizar—. Se fija con el zoom
 * de **destino** del encuadre y solo cambia al cruzar un tramo con el mapa
 * quieto.
 */
const RADIOS = new WeakMap<MapLibreMap, number>();
const radioActual = (m: MapLibreMap) => RADIOS.get(m) ?? radioParaZoom(m.getZoom());
const CLAVE_MODO = "smart-report:mapa-modo";

/** Los colores del dominio, leidos del tema para no repetirlos aqui. */
function colorDe(severidad: string | null, oscuro: boolean): string {
  if (severidad === "alta") return oscuro ? "#d4614a" : "#b4442e";
  if (severidad === "media") return oscuro ? "#e09a45" : "#c77b23";
  return oscuro ? "#9aa1a6" : "#7a8288";
}

/** Radio segun cuantos reportan. Raiz y no lineal: con veinte reportes un pin
 *  lineal taparia media pantalla, y lo que interesa es comparar, no escalar. */
function radioDe(cuantos: number): number {
  return Math.min(34, 9 + Math.sqrt(cuantos) * 7);
}

function leerModo(): Modo {
  try {
    return localStorage.getItem(CLAVE_MODO) === "3d" ? "3d" : "2d";
  } catch {
    return "2d";
  }
}

export function Mapa({
  seleccionado,
  onElegir,
  oscuro,
}: {
  seleccionado: string | null;
  onElegir: (id: string) => void;
  oscuro: boolean;
}) {
  const contenedor = useRef<HTMLDivElement>(null);
  const mapa = useRef<MapLibreMap | null>(null);
  const marcadores = useRef<globalThis.Map<string, Marker>>(new globalThis.Map());
  // El estilo con el que se creo, para no pisarlo al montar.
  const estiloInicial = useRef(oscuro ? ESTILO_OSCURO : ESTILO_CLARO);
  // 2D por defecto; se recuerda la eleccion de cada quien en su navegador. Se
  // lee al iniciar: este componente solo existe en el navegador (ssr: false).
  const [modo, setModo] = useState<Modo>(leerModo);

  // Los manejadores del mapa se registran una vez y leen de aqui: con el valor
  // capturado al crearlos verian siempre el primer tema y los primeros datos.
  const actual = useRef({ modo, oscuro, puntos: [] as Punto[], onElegir });
  // Lo que se mueve, creado con el mapa y destruido con el.
  const animaciones = useRef<{
    crecimiento: ReturnType<typeof crearCrecimiento>;
    pulso: ReturnType<typeof crearPulso>;
  } | null>(null);
  // Cuantos reportes tenia cada columna la ultima vez: para saber cual es nueva
  // o cambio cuando llegan datos en vivo, y hacer crecer solo esa.
  const previas = useRef(new globalThis.Map<string, number>());

  const { data } = useQuery({
    queryKey: ["mapa"],
    queryFn: api.mapa,
  });

  useEffect(() => {
    actual.current = { modo, oscuro, puntos: data?.points ?? [], onElegir };
  });

  // El mapa se crea **una sola vez**. Con `oscuro` en las dependencias, este
  // efecto y el de abajo corrian los dos al montar: uno creaba el mapa con un
  // estilo y el otro llamaba a setStyle encima, mientras el primero todavia
  // cargaba. El estilo quedaba a medias y las fuentes sin inicializar.
  useEffect(() => {
    if (!contenedor.current || mapa.current) return;

    const m = new MapLibreMap({
      container: contenedor.current,
      style: estiloInicial.current,
      center: CENTRO,
      zoom: 12.5,
      attributionControl: { compact: true },
      ...(leerModo() === "3d" ? CAMARA_3D : {}),
    });
    // La brujula vuelve al norte y a la vista cenital: en 3D hace falta.
    m.addControl(new NavigationControl({ visualizePitch: true }), "top-right");
    mapa.current = m;
    const crecimiento = crearCrecimiento(m);
    const pulso = crearPulso(m, () => radioActual(m));
    animaciones.current = { crecimiento, pulso };

    // Cambiar el estilo (al pasar de tema) borra las capas propias: se
    // vuelven a poner al terminar de cargar el nuevo.
    m.on("style.load", () => {
      // El color va en los dos modos y en cada estilo: setStyle lo reemplaza.
      teñirMapa(m, actual.current.oscuro);
      if (actual.current.modo !== "3d") return;
      ponerCapas3D(m, actual.current.puntos, actual.current.oscuro);
      // Un tema nuevo no es un dato nuevo: las columnas vuelven enteras.
      previas.current = reportesPorColumna(m, actual.current.puntos);
      pulso.hayUrgentes(ponerPulso(m, actual.current.puntos));
    });

    // El radio de los hexagonos va por tramos de zoom: al cruzar un tramo se
    // rehacen las celdas. Al terminar el movimiento y no durante, para no
    // recalcular en cada paso de la rueda.
    m.on("zoomend", () => {
      const nuevo = radioParaZoom(m.getZoom());
      if (nuevo === radioActual(m)) return;
      RADIOS.set(m, nuevo);
      const fuente = m.getSource(FUENTE_COLUMNAS) as GeoJSONSource | undefined;
      if (fuente && actual.current.modo === "3d") {
        // Rehacer las celdas tampoco es un dato nuevo: sin crecer.
        crecimiento.detener();
        fuente.setData(colorear(columnas(actual.current.puntos, nuevo), actual.current.oscuro));
        previas.current = reportesPorColumna(m, actual.current.puntos);
        pulso.hayUrgentes(ponerPulso(m, actual.current.puntos));
      }
    });

    const aviso = new Popup({ closeButton: false, closeOnClick: false, offset: 12 });
    m.on("mousemove", "columnas-3d", (e: MapLayerMouseEvent) => {
      const p = e.features?.[0]?.properties as PropiedadesColumna | undefined;
      if (!p) return;
      m.getCanvas().style.cursor = "pointer";
      aviso
        .setLngLat(e.lngLat)
        .setHTML(
          `<strong>${p.reportes} ${p.reportes === 1 ? "reporte" : "reportes"}</strong>` +
            ` · ${p.casos} ${p.casos === 1 ? "caso" : "casos"}<br>` +
            `<span style="opacity:.7">${p.caso ? "Clic para abrir el caso" : "Clic para acercar"}</span>`,
        )
        .addTo(m);
    });
    m.on("mouseleave", "columnas-3d", () => {
      m.getCanvas().style.cursor = "";
      aviso.remove();
    });
    m.on("click", "columnas-3d", (e: MapLayerMouseEvent) => {
      const p = e.features?.[0]?.properties as PropiedadesColumna | undefined;
      if (!p) return;
      aviso.remove();
      // Una columna de un solo caso abre ese caso; una de varios acerca la
      // camara para que se separen, en vez de elegir uno al azar.
      if (p.caso) actual.current.onElegir(p.caso);
      else
        m.easeTo({
          center: [p.lon, p.lat],
          zoom: Math.min(m.getZoom() + 1.6, 17),
          duration: sinMovimiento() ? 0 : 900,
        });
    });

    return () => {
      crecimiento.detener();
      pulso.destruir();
      animaciones.current = null;
      aviso.remove();
      m.remove();
      mapa.current = null;
    };
  }, []);

  // El estilo cambia con el tema sin rehacer el mapa: recrearlo perderia la
  // posicion y el zoom, que es lo que el operador acababa de ajustar.
  useEffect(() => {
    const deseado = oscuro ? ESTILO_OSCURO : ESTILO_CLARO;
    // No en el primer render: ahi ya se creo con el estilo correcto, y pisarlo
    // es justo la carrera que rompia el mapa.
    if (estiloInicial.current === deseado) return;
    estiloInicial.current = deseado;
    mapa.current?.setStyle(deseado);
  }, [oscuro]);

  // Si ya se encuadro esta entrada a 3D: los datos en vivo no deben mover la
  // camara que el operador acaba de ajustar. Se reinicia al volver a 2D.
  const encuadrado = useRef(false);

  // Pasar de 2D a 3D y de vuelta: capas, camara y pines.
  useEffect(() => {
    const m = mapa.current;
    if (!m) return;
    const duracion = sinMovimiento() ? 0 : 1100;
    const aplicar = () => {
      const anim = animaciones.current;
      if (modo === "3d") {
        // Primero el encuadre: fija el radio de las celdas con el zoom al que va
        // la camara, y las capas se hacen ya con el.
        encuadrado.current = encuadrar3D(m, actual.current.puntos, duracion);
        ponerCapas3D(m, actual.current.puntos, actual.current.oscuro);
        // Al entrar, todas crecen desde el suelo, un poco despues de que la
        // camara empiece a inclinarse: asi se ve que salen del mapa.
        previas.current = reportesPorColumna(m, actual.current.puntos);
        anim?.crecimiento.animar(desdeCero(previas.current), { retraso: 250 });
        anim?.pulso.hayUrgentes(ponerPulso(m, actual.current.puntos));
      } else {
        encuadrado.current = false;
        anim?.crecimiento.detener();
        anim?.pulso.hayUrgentes(false);
        previas.current = new globalThis.Map();
        quitarCapas3D(m);
        m.easeTo({ pitch: 0, bearing: 0, duration: duracion });
      }
    };
    // Si el estilo todavia carga teselas, se espera a `idle` y no a `load`:
    // `load` ya ocurrio al crear el mapa y no vuelve, y pulsar 3D mientras
    // cargaba dejaba el mapa plano y sin columnas, sin ningun error.
    if (m.isStyleLoaded()) aplicar();
    else m.once("idle", aplicar);
    try {
      localStorage.setItem(CLAVE_MODO, modo);
    } catch {
      // Sin almacenamiento (ventana privada): se pierde la preferencia, nada mas.
    }
    // Si se cambia de modo antes de que llegue `idle`, la orden vieja se
    // cancela. Sin esto, el 2D que quedo pendiente al abrir el mapa llegaba
    // despues de pasar a 3D y lo volvia a aplanar.
    return () => {
      m.off("idle", aplicar);
    };
  }, [modo]);

  // Las columnas siguen a los datos en vivo, sin rehacer las capas. Y si se
  // entro a 3D antes de que llegaran los datos, se encuadra ahora.
  useEffect(() => {
    const m = mapa.current;
    const fuente = m?.getSource(FUENTE_COLUMNAS) as GeoJSONSource | undefined;
    if (!m || modo !== "3d" || !fuente || !data) return;
    if (!encuadrado.current) {
      encuadrado.current = encuadrar3D(m, data.points, sinMovimiento() ? 0 : 1100);
    }
    fuente.setData(colorear(columnas(data.points, radioActual(m)), oscuro));
    const ahora = reportesPorColumna(m, data.points);
    animaciones.current?.crecimiento.animar(cambiadas(previas.current, ahora));
    previas.current = ahora;
    animaciones.current?.pulso.hayUrgentes(ponerPulso(m, data.points));
  }, [data, modo, oscuro]);

  // La orbita vive mientras se esta en 3D. Al desmontar —cambiar de pestaña del
  // tablero— o volver a 2D se destruye con sus escuchas.
  useEffect(() => {
    const m = mapa.current;
    if (!m || modo !== "3d") return;
    const orbita = crearOrbita(m);
    return () => orbita.destruir();
  }, [modo]);

  useEffect(() => {
    if (!mapa.current || !data) return;
    const m = mapa.current;

    const vistos = new Set<string>();
    for (const punto of data.points) {
      vistos.add(punto.id);
      marcadores.current.get(punto.id)?.remove();

      // En 3D no se pintan: un pin HTML no se inclina con la camara y flota
      // sobre la columna que ya cuenta lo mismo.
      if (modo === "3d") {
        marcadores.current.delete(punto.id);
        continue;
      }

      const el = crearPin(punto, punto.id === seleccionado, oscuro);
      if (esUrgente(punto)) anillosDeUrgencia(el, colorDe(punto.severity, oscuro));
      el.addEventListener("click", () => onElegir(punto.id));

      marcadores.current.set(
        punto.id,
        new Marker({ element: el }).setLngLat([punto.lon, punto.lat]).addTo(m),
      );
    }

    // Lo que ya no esta se quita: un caso descartado no puede seguir pintado.
    for (const [id, marcador] of marcadores.current) {
      if (!vistos.has(id)) {
        marcador.remove();
        marcadores.current.delete(id);
      }
    }
  }, [data, seleccionado, oscuro, onElegir, modo]);

  return (
    <div className="relative h-full">
      <div ref={contenedor} className="h-full w-full" />

      {/* 2D por defecto: es donde se lee cada caso. 3D es para ver donde se
          concentra el reclamo. */}
      <div
        role="group"
        aria-label="Vista del mapa"
        className="absolute top-3 left-3 flex rounded-lg border bg-popover/90 p-0.5 text-xs font-medium shadow-sm backdrop-blur"
      >
        {(["2d", "3d"] as const).map((m) => (
          <button
            key={m}
            type="button"
            aria-pressed={modo === m}
            onClick={() => setModo(m)}
            className={cn(
              "rounded-md px-2.5 py-1 uppercase transition-colors",
              modo === m ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {m}
          </button>
        ))}
      </div>

      {modo === "3d" && data && data.points.length === 0 && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center p-6">
          <div className="max-w-sm rounded-lg border bg-popover/95 px-4 py-3 text-center text-sm shadow-sm backdrop-blur">
            <p className="font-medium">No hay nada que graficar todavía</p>
            <p className="mt-1 text-muted-foreground">
              Las columnas salen de los casos con ubicación. Cuando alguien reporte por el bot,
              aparecen aquí.
            </p>
          </div>
        </div>
      )}

      {data && data.points.length > 0 && (
        <div className="pointer-events-none absolute bottom-6 left-3 rounded-lg border bg-popover/90 px-3 py-2 text-xs shadow-sm backdrop-blur">
          <p className="font-medium">
            {data.points.length} {data.points.length === 1 ? "caso" : "casos"}
          </p>
          <p className="mt-0.5 text-muted-foreground">
            {modo === "3d"
              ? "La altura es cuántos reportan en la zona; el color, la urgencia más alta"
              : "El tamaño dice cuántos reportan lo mismo"}
          </p>
        </div>
      )}
    </div>
  );
}

/** Urgente y abierto: lo unico que late. Un cerrado urgente ya no pide nada. */
function esUrgente(p: Punto): boolean {
  return p.severity === "alta" && p.status !== "closed";
}

/** Reportes de cada columna, por su clave, al zoom actual. */
function reportesPorColumna(m: MapLibreMap, puntos: Punto[]) {
  return new globalThis.Map(
    columnas(puntos, radioActual(m)).features.map((f) => [
      f.properties.clave,
      f.properties.reportes,
    ]),
  );
}

function desdeCero(columnasActuales: globalThis.Map<string, number>) {
  return new globalThis.Map([...columnasActuales.keys()].map((k) => [k, 0]));
}

/**
 * Que columnas crecen cuando llegan datos: las nuevas desde el suelo, y las que
 * cambiaron desde la altura que tenian. Las demas, quietas: si todo se moviera
 * en cada evento, el movimiento dejaria de decir que algo cambio.
 */
function cambiadas(
  antes: globalThis.Map<string, number>,
  ahora: globalThis.Map<string, number>,
) {
  const crecen = new globalThis.Map<string, number>();
  // La proporcion con la formula de zoom 14: alcanza para que la columna salga
  // de donde estaba y no de cero.
  const alto = (n: number) => 150 + 90 * n;
  for (const [clave, n] of ahora) {
    const previo = antes.get(clave);
    if (previo === undefined) crecen.set(clave, 0);
    else if (previo !== n) crecen.set(clave, alto(previo) / alto(n));
  }
  return crecen;
}

/**
 * Pone los centros de las columnas con algo urgente en la fuente del pulso.
 * Devuelve si hay alguno, para arrancar o parar el bucle.
 */
function ponerPulso(m: MapLibreMap, puntos: Punto[]): boolean {
  const fuente = m.getSource(FUENTE_PULSO) as GeoJSONSource | undefined;
  if (!fuente) return false;
  // Las celdas de lo urgente, en la misma rejilla que las columnas: el centro
  // cae justo bajo la columna que lo contiene.
  const urgentes = columnas(puntos.filter(esUrgente), radioActual(m)).features;
  fuente.setData({
    type: "FeatureCollection",
    features: urgentes.map((f) => ({
      type: "Feature" as const,
      properties: {},
      geometry: { type: "Point" as const, coordinates: [f.properties.lon, f.properties.lat] },
    })),
  });
  return urgentes.length > 0;
}

/** El color va en cada columna: la expresion de MapLibre no conoce el tema. */
function colorear(coleccion: ReturnType<typeof columnas>, oscuro: boolean) {
  return {
    ...coleccion,
    features: coleccion.features.map((f) => ({
      ...f,
      properties: { ...f.properties, color: colorDe(f.properties.severidad, oscuro) },
    })),
  };
}

function ponerCapas3D(m: MapLibreMap, puntos: Punto[], oscuro: boolean) {
  // El relieve va encima de todo lo que no es texto, y las etiquetas encima del
  // relieve: los nombres de las calles orientan y un edificio no puede
  // taparlos. Se busca la ultima capa que no es texto y no la primera de texto:
  // el estilo oscuro pone etiquetas antes que las calles, y con la primera las
  // calles se pintaban encima de las columnas.
  const capas = m.getStyle().layers;
  const ultima = capas.findLastIndex((l) => l.type !== "symbol");
  const antesDe = capas[ultima + 1]?.id;

  // El pulso, primero: queda por debajo de edificios y columnas, que lo tapan
  // donde corresponde y la onda se ve salir de la base.
  if (!m.getSource(FUENTE_PULSO)) {
    m.addSource(FUENTE_PULSO, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  }
  for (const id of CAPAS_PULSO) {
    if (m.getLayer(id)) continue;
    m.addLayer(
      {
        id,
        type: "circle",
        source: FUENTE_PULSO,
        paint: {
          // Tendido sobre el suelo, no de frente a la camara.
          "circle-pitch-alignment": "map",
          "circle-pitch-scale": "map",
          "circle-radius": 0,
          "circle-color": "rgba(0,0,0,0)",
          "circle-stroke-width": 3,
          "circle-stroke-color": colorDe("alta", oscuro),
          "circle-stroke-opacity": 0,
        },
      },
      antesDe,
    );
  }

  if (!m.getLayer("edificios-3d")) {
    m.addLayer(
      {
        id: "edificios-3d",
        type: "fill-extrusion",
        // Esquema OpenMapTiles de OpenFreeMap: fuente `openmaptiles`, capa
        // `building`, con alturas en `render_height`.
        source: "openmaptiles",
        "source-layer": "building",
        minzoom: 13,
        paint: {
          "fill-extrusion-color": colorEdificio3D(oscuro),
          "fill-extrusion-height": ["coalesce", ["get", "render_height"], 0],
          "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0],
          // Recesivos: estan para orientarse, no para competir con los casos.
          "fill-extrusion-opacity": 0.55,
        },
      },
      antesDe,
    );
  }

  const datos = colorear(columnas(puntos, radioActual(m)), oscuro);
  const fuente = m.getSource(FUENTE_COLUMNAS) as GeoJSONSource | undefined;
  if (fuente) fuente.setData(datos);
  // promoteId: el estado de cada columna (cuanto ha crecido) va por su clave,
  // que es estable entre actualizaciones; un id por posicion en la lista no.
  else m.addSource(FUENTE_COLUMNAS, { type: "geojson", data: datos, promoteId: "clave" });

  if (!m.getLayer("columnas-3d")) {
    m.addLayer(
      {
        id: "columnas-3d",
        type: "fill-extrusion",
        source: FUENTE_COLUMNAS,
        paint: {
          "fill-extrusion-color": ["get", "color"],
          // Expresion de MapLibre: el tipo de la constante es mas estrecho que
          // el que declara la libreria, de ahi el cast.
          "fill-extrusion-height": ALTURA_COLUMNA as unknown as number,
          "fill-extrusion-base": 0,
          // Solida: con transparencia, la tapa de la columna dejaba ver los
          // edificios de abajo y se leia como un vidrio, no como una cantidad.
          "fill-extrusion-opacity": 1,
          "fill-extrusion-vertical-gradient": true,
        },
      },
      antesDe,
    );
  }
}

/**
 * Lleva la camara al grupo mas denso de casos, inclinada. Devuelve si encuadro:
 * sin casos no hay nada que encuadrar y se deja la camara donde esta.
 */
function encuadrar3D(m: MapLibreMap, puntos: Punto[], duracion: number): boolean {
  const destino = encuadre(puntos);
  if (!destino) {
    RADIOS.set(m, radioParaZoom(m.getZoom()));
    m.easeTo({ ...CAMARA_3D, duration: duracion });
    return false;
  }
  if (destino.tipo === "punto") {
    RADIOS.set(m, radioParaZoom(ZOOM_3D_UN_CASO));
    m.easeTo({ ...CAMARA_3D, center: destino.centro, zoom: ZOOM_3D_UN_CASO, duration: duracion });
    return true;
  }
  // La camara que encuadra la caja ya inclinada, con el zoom acotado: ni tan
  // lejos que no salgan los edificios ni tan cerca que no quepa la zona.
  const camara = m.cameraForBounds(destino.caja, { padding: 80, ...CAMARA_3D });
  const zoom = Math.min(ZOOM_3D_MAX, Math.max(ZOOM_3D_MIN, camara?.zoom ?? ZOOM_3D_MIN));
  RADIOS.set(m, radioParaZoom(zoom));
  m.easeTo({ ...CAMARA_3D, center: camara?.center ?? destino.caja[0], zoom, duration: duracion });
  return true;
}

function quitarCapas3D(m: MapLibreMap) {
  for (const id of ["columnas-3d", "edificios-3d", ...CAPAS_PULSO]) {
    if (m.getLayer(id)) m.removeLayer(id);
  }
  for (const id of [FUENTE_COLUMNAS, FUENTE_PULSO]) if (m.getSource(id)) m.removeSource(id);
  RADIOS.delete(m);
}

function crearPin(punto: Punto, activo: boolean, oscuro: boolean): HTMLElement {
  const radio = radioDe(punto.report_count);
  const color = colorDe(punto.severity, oscuro);

  const el = document.createElement("button");
  el.type = "button";
  el.setAttribute(
    "aria-label",
    `${categoria(punto.category)}, ${punto.report_count} ${
      punto.report_count === 1 ? "reporte" : "reportes"
    }`,
  );
  el.style.cssText = `
    width:${radio * 2}px; height:${radio * 2}px;
    display:flex; align-items:center; justify-content:center;
    border-radius:9999px; cursor:pointer;
    background:${color}2e; border:2px solid ${color};
    color:${color}; font-weight:600; font-size:${Math.max(11, radio * 0.55)}px;
    font-variant-numeric:tabular-nums;
    transition:transform .18s ease, box-shadow .18s ease;
    ${activo ? `box-shadow:0 0 0 4px ${color}33; transform:scale(1.12);` : ""}
  `;
  // Solo se escribe el numero si hay mas de uno: un "1" en cada pin es ruido.
  el.textContent = punto.report_count > 1 ? String(punto.report_count) : "";
  return el;
}
