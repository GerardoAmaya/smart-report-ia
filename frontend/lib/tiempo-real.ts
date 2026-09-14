"use client";

/**
 * El tablero se actualiza sin recargar.
 *
 * Escucha los cambios por SSE y le dice a React Query que lo que tiene esta
 * viejo. **No trae los datos por el flujo**: el servidor solo dice "algo cambio
 * aqui" y el cliente pide lo que necesite. Mandar la fila por el flujo
 * obligaria a mantener dos formas de leer lo mismo, y la segunda se queda
 * vieja.
 *
 * Se agrupan los avisos en una ventana corta: cerrar un caso dispara cambios en
 * `cases`, `notifications` y `case_photos` casi a la vez, y recargar tres veces
 * seguidas es pedirle al servidor lo mismo dos veces de mas.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Que recargar segun donde ocurrio el cambio. Explicito y no "recargalo todo":
// una foto nueva no tiene por que rehacer la consulta del mapa.
const AFECTA: Record<string, string[]> = {
  cases: ["casos", "caso", "mapa", "metricas"],
  reports: ["casos", "caso", "mapa", "metricas"],
  classifications: ["caso", "metricas"],
  notifications: ["caso"],
  case_photos: ["caso"],
};

const AGRUPAR_MS = 250;

export type EstadoFlujo = "conectando" | "en-vivo" | "sin-conexion";

export function useTiempoReal(): EstadoFlujo {
  const cliente = useQueryClient();
  const [estado, setEstado] = useState<EstadoFlujo>("conectando");
  const pendientes = useRef<Set<string>>(new Set());
  const temporizador = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    // withCredentials para que viaje la cookie de sesion: EventSource no deja
    // poner cabeceras, asi que la sesion en cookie es lo unico que funciona.
    const fuente = new EventSource(`${API_URL}/board/stream`, { withCredentials: true });

    const vaciar = () => {
      for (const clave of pendientes.current) {
        cliente.invalidateQueries({ queryKey: [clave] });
      }
      pendientes.current.clear();
      temporizador.current = null;
    };

    fuente.addEventListener("abierto", () => setEstado("en-vivo"));

    fuente.addEventListener("cambio", (e) => {
      setEstado("en-vivo");
      try {
        const { tabla } = JSON.parse((e as MessageEvent).data);
        for (const clave of AFECTA[tabla] ?? []) pendientes.current.add(clave);
      } catch {
        return;
      }
      if (temporizador.current === null) {
        temporizador.current = setTimeout(vaciar, AGRUPAR_MS);
      }
    });

    // EventSource reconecta solo; lo unico que hace falta es decirlo en la
    // interfaz para que nadie confie en un tablero que dejo de actualizarse.
    fuente.onerror = () => setEstado("sin-conexion");

    return () => {
      if (temporizador.current) clearTimeout(temporizador.current);
      fuente.close();
    };
  }, [cliente]);

  return estado;
}
