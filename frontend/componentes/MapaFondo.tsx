"use client";

/**
 * San Salvador de fondo en la entrada, recorriendo colonias despacio.
 *
 * **Sin pines, a proposito.** Las ubicaciones de los reportes no se ven sin
 * entrar: el mapa dice de que va el sistema, no donde vive quien reporto.
 *
 * MapLibre se importa **dentro del efecto y solo en pantallas anchas**. En el
 * telefono el mapa no se muestra, y traerlo igual seria gastarle datos moviles
 * a alguien solo para entrar.
 *
 * Las dos trampas del mapa del tablero valen aqui (ver CLAUDE.md): el worker se
 * registra antes de crear el mapa, y el CSS ya va en el bundle principal.
 */
import type { Map as MapLibreMap } from "maplibre-gl";
import { useEffect, useRef } from "react";

const ESTILO_CLARO = "https://tiles.openfreemap.org/styles/positron";
const ESTILO_OSCURO = "https://tiles.openfreemap.org/styles/dark";

// Un recorrido corto por la ciudad: centro, Escalon, Mejicanos, Antiguo Cuscatlan.
const PARADAS: [number, number][] = [
  [-89.1914, 13.6989],
  [-89.24, 13.706],
  [-89.213, 13.7395],
  [-89.252, 13.6735],
];

export function MapaFondo({ oscuro }: { oscuro: boolean }) {
  const contenedor = useRef<HTMLDivElement>(null);
  const mapa = useRef<MapLibreMap | null>(null);
  const estilo = useRef(oscuro ? ESTILO_OSCURO : ESTILO_CLARO);

  useEffect(() => {
    if (!contenedor.current || !window.matchMedia("(min-width: 1024px)").matches) return;
    let cancelado = false;
    const quieto = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    import("maplibre-gl").then(({ Map, setWorkerUrl }) => {
      if (cancelado || !contenedor.current) return;
      setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");

      const m = new Map({
        container: contenedor.current,
        style: estilo.current,
        center: PARADAS[0],
        zoom: 13.4,
        interactive: false,
        // La atribucion es obligatoria: los datos son de OpenStreetMap (ODbL).
        attributionControl: { compact: true },
      });
      mapa.current = m;

      if (quieto) return;
      let parada = 0;
      const siguiente = () => {
        parada = (parada + 1) % PARADAS.length;
        m.easeTo({
          center: PARADAS[parada],
          bearing: parada % 2 === 0 ? 0 : -12,
          duration: 26_000,
          easing: (t) => t,
        });
      };
      m.on("load", siguiente);
      m.on("moveend", siguiente);
    });

    return () => {
      cancelado = true;
      mapa.current?.remove();
      mapa.current = null;
    };
  }, []);

  // El tema cambia el estilo sin rehacer el mapa, como en el tablero.
  useEffect(() => {
    const deseado = oscuro ? ESTILO_OSCURO : ESTILO_CLARO;
    if (estilo.current === deseado) return;
    estilo.current = deseado;
    mapa.current?.setStyle(deseado);
  }, [oscuro]);

  // Envuelto y no `absolute` directo en el contenedor: el CSS de MapLibre le
  // pone `position: relative` a su contenedor y, como no va en una capa de
  // Tailwind, gana. El mapa quedaba con alto cero y no se veia nada.
  return (
    <div aria-hidden className="absolute inset-0">
      <div ref={contenedor} className="h-full w-full" />
    </div>
  );
}
