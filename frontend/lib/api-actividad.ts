/**
 * El feed de actividad: lo que acaba de pasar en el sistema.
 *
 * Aparte de `lib/api.ts`, como el asistente: es una lectura nueva y no hace
 * falta tocar el cliente que despacha. Mismo contrato: la respuesta se valida
 * con Zod, y un 401 es `SinSesion` para que la interfaz mande a entrar.
 */
import { z } from "zod";

import { ApiError, SinSesion } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const TipoEventoSchema = z.enum([
  "reporte",
  "agrupado",
  "dudoso",
  "asignado",
  "en_curso",
  "cerrado",
  "aviso",
]);
export type TipoEvento = z.infer<typeof TipoEventoSchema>;

export const EventoSchema = z.object({
  id: z.string(),
  // Un tipo que este cliente no conoce no tumba el feed: se muestra con un
  // icono neutro. Un servidor mas nuevo que el tablero no deberia romperlo.
  tipo: z.string(),
  cuando: z.string(),
  caso_id: z.string(),
  texto: z.string(),
  detalle: z.string().nullable(),
});
export type Evento = z.infer<typeof EventoSchema>;

const ActividadSchema = z.object({ eventos: z.array(EventoSchema) });

export async function obtenerActividad(limite = 20): Promise<Evento[]> {
  let respuesta: Response;
  try {
    respuesta = await fetch(`${API_URL}/board/actividad?limite=${limite}`, {
      credentials: "include",
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, `Sin respuesta de ${API_URL}`);
  }
  if (respuesta.status === 401) throw new SinSesion(401, "hay que entrar");
  if (!respuesta.ok) throw new ApiError(respuesta.status, `Error ${respuesta.status}`);
  return ActividadSchema.parse(await respuesta.json()).eventos;
}
