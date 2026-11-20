/**
 * Las llamadas del asistente: el chat del tablero y la comparación de dudosos.
 *
 * Aparte de `lib/api.ts` para no mezclar lo que despacha con lo que solo lee y
 * sugiere. Mismo contrato: la respuesta se valida con Zod, y un 401 es
 * `SinSesion` para que la interfaz mande a entrar.
 */
import { z } from "zod";

import { ApiError, SinSesion } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function enviar<T>(ruta: string, esquema: z.ZodType<T>, cuerpo?: unknown): Promise<T> {
  let respuesta: Response;
  try {
    respuesta = await fetch(`${API_URL}${ruta}`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, `Sin respuesta de ${API_URL}`);
  }
  if (respuesta.status === 401) throw new SinSesion(401, "hay que entrar");
  if (!respuesta.ok) {
    const detalle = await respuesta
      .json()
      .then((c) => (typeof c?.detail === "string" ? c.detail : null))
      .catch(() => null);
    throw new ApiError(respuesta.status, detalle ?? `Error ${respuesta.status}`);
  }
  return esquema.parse(await respuesta.json());
}

export const RespuestaAsistenteSchema = z.object({
  answer: z.string(),
  remaining_today: z.number(),
});
export type RespuestaAsistente = z.infer<typeof RespuestaAsistenteSchema>;

export const ComparacionSchema = z.object({
  parecidos: z.array(z.string()),
  diferencias: z.array(z.string()),
  lectura: z.string(),
  sugerencia: z.enum(["mismo_problema", "distintos", "no_se_puede_saber"]),
  candidate_report_id: z.string(),
  remaining_today: z.number(),
});
export type Comparacion = z.infer<typeof ComparacionSchema>;

export type MensajeChat = { role: "user" | "assistant"; content: string };

export const apiAsistente = {
  preguntar: (mensajes: MensajeChat[]) =>
    enviar("/board/asistente", RespuestaAsistenteSchema, { messages: mensajes }),
  comparar: (reporteId: string) =>
    enviar(`/board/reports/${reporteId}/compare`, ComparacionSchema),
};
