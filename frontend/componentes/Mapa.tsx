"use client";

/**
 * El mapa de casos.
 *
 * **El tamaño del pin es cuantos reportan lo mismo.** Un mapa de puntos iguales
 * tira a la basura la informacion de donde se concentra el reclamo, que es
 * justo lo que un mapa deberia mostrar.
 *
 * MapLibre y no Leaflet: el tablero tiene que dibujar cientos de casos con
 * cambios en vivo, y Leaflet es raster y se queda corto ahi.
 *
 * Teselas de un proveedor sin llave: una demo que pide registrarse para ver el
 * mapa deja de ser una demo.
 */
import { useQuery } from "@tanstack/react-query";
// MapLibre 6 quito el export por defecto: ahora son exports nombrados.
import { Map as MapLibreMap, Marker, NavigationControl, setWorkerUrl } from "maplibre-gl";
import { useEffect, useRef } from "react";

import { api, type Punto } from "@/lib/api";
import { categoria } from "@/lib/textos";

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

  const { data } = useQuery({
    queryKey: ["mapa"],
    queryFn: api.mapa,
  });

  // El mapa se crea **una sola vez**. Con `oscuro` en las dependencias, este
  // efecto y el de abajo corrian los dos al montar: uno creaba el mapa con un
  // estilo y el otro llamaba a setStyle encima, mientras el primero todavia
  // cargaba. El estilo quedaba a medias y las fuentes sin inicializar.
  useEffect(() => {
    if (!contenedor.current || mapa.current) return;

    mapa.current = new MapLibreMap({
      container: contenedor.current,
      style: estiloInicial.current,
      center: CENTRO,
      zoom: 12.5,
      attributionControl: { compact: true },
    });
    mapa.current.addControl(new NavigationControl({ showCompass: false }), "top-right");

    return () => {
      mapa.current?.remove();
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

  useEffect(() => {
    if (!mapa.current || !data) return;
    const m = mapa.current;

    const vistos = new Set<string>();
    for (const punto of data.points) {
      vistos.add(punto.id);
      marcadores.current.get(punto.id)?.remove();

      const el = crearPin(punto, punto.id === seleccionado, oscuro);
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
  }, [data, seleccionado, oscuro, onElegir]);

  return (
    <div className="relative h-full">
      <div ref={contenedor} className="h-full w-full" />
      {data && (
        <div className="pointer-events-none absolute bottom-6 left-3 rounded-lg border bg-popover/90 px-3 py-2 text-xs shadow-sm backdrop-blur">
          <p className="font-medium">
            {data.points.length} {data.points.length === 1 ? "caso" : "casos"}
          </p>
          <p className="mt-0.5 text-muted-foreground">
            El tamaño dice cuántos reportan lo mismo
          </p>
        </div>
      )}
    </div>
  );
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
