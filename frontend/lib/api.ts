/**
 * Cliente de la API.
 *
 * Las respuestas se validan con Zod en vez de confiar en el tipo declarado.
 * Un `as Case[]` es una promesa, no una comprobacion: si la API cambia de
 * forma, la pantalla renderiza `undefined` y el fallo aparece lejos de la
 * causa. Con esquema falla aqui y dice que campo falta.
 */
import { z } from "zod";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Sin sesion. La interfaz manda a entrar en vez de mostrar un error crudo. */
export class SinSesion extends ApiError {}

async function pedir<T>(ruta: string, esquema: z.ZodType<T>, init?: RequestInit): Promise<T> {
  let respuesta: Response;
  try {
    respuesta = await fetch(`${API_URL}${ruta}`, {
      ...init,
      // La sesion va en cookie: sin esto el navegador no la manda a otro origen
      // y todo responde 401 sin explicacion.
      credentials: "include",
      headers: { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, `Sin respuesta de ${API_URL}`);
  }

  if (respuesta.status === 401) throw new SinSesion(401, "hay que entrar");
  if (!respuesta.ok) {
    const detalle = await respuesta
      .json()
      .then((c) => c?.detail)
      .catch(() => null);
    throw new ApiError(respuesta.status, detalle ?? `Error ${respuesta.status}`);
  }

  return esquema.parse(await respuesta.json());
}

// --- Esquemas ---

export const PerfilSchema = z.object({
  email: z.string(),
  role: z.enum(["admin", "operator", "demo"]),
  display_name: z.string().nullable(),
  permissions: z.array(z.string()),
});
export type Perfil = z.infer<typeof PerfilSchema>;

export const CasoSchema = z.object({
  id: z.string(),
  status: z.string(),
  category: z.string().nullable(),
  severity: z.string().nullable(),
  report_count: z.number(),
  doubtful_count: z.number(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type Caso = z.infer<typeof CasoSchema>;

export const EvidenciaSchema = z.object({
  decision: z.enum(["grouped", "rejected", "doubtful", "alone"]),
  distance_m: z.number().nullable(),
  hours_apart: z.number().nullable(),
  text_similarity: z.number().nullable(),
  visual_distance: z.number().nullable(),
  reason: z.string(),
  thresholds: z.record(z.string(), z.number()).nullable(),
});
export type Evidencia = z.infer<typeof EvidenciaSchema>;

export const FotoSchema = z.object({
  id: z.string(),
  thumbnail_url: z.string().nullable(),
  original_url: z.string().nullable(),
  status: z.string(),
});

export const ReporteSchema = z.object({
  id: z.string(),
  caption: z.string().nullable(),
  grouping_status: z.enum(["pending", "grouped", "alone", "doubtful"]),
  created_at: z.string(),
  lat: z.number().nullable(),
  lon: z.number().nullable(),
  photos: z.array(FotoSchema),
  classification: z
    .object({
      proposed_category: z.string().nullable(),
      final_category: z.string().nullable(),
      severity: z.string().nullable(),
      reason: z.string().nullable(),
      confirmed: z.boolean(),
      corrected: z.boolean(),
    })
    .nullable(),
  evidence: z.array(EvidenciaSchema),
});
export type Reporte = z.infer<typeof ReporteSchema>;

export const DetalleSchema = z.object({
  id: z.string(),
  status: z.string(),
  category: z.string().nullable(),
  severity: z.string().nullable(),
  report_count: z.number(),
  created_at: z.string(),
  reports: z.array(ReporteSchema),
});
export type Detalle = z.infer<typeof DetalleSchema>;

export const PuntoSchema = z.object({
  id: z.string(),
  category: z.string().nullable(),
  severity: z.string().nullable(),
  status: z.string(),
  report_count: z.number(),
  lat: z.number(),
  lon: z.number(),
});
export type Punto = z.infer<typeof PuntoSchema>;

export const MetricasSchema = z.object({
  dias: z.number(),
  reportes: z.number(),
  casos: z.number(),
  ahorro: z.number(),
  serie: z.array(z.object({ dia: z.string(), reportes: z.number() })),
  categorias: z.array(
    z.object({ categoria: z.string(), casos: z.number(), reportes: z.number() }),
  ),
  severidades: z.object({ alta: z.number(), media: z.number(), baja: z.number() }),
  dudosos: z.number(),
  costo_usd: z.number(),
});
export type Metricas = z.infer<typeof MetricasSchema>;

// --- Llamadas ---

export const api = {
  yo: () => pedir("/auth/yo", PerfilSchema),

  entrarDePrueba: (password: string) =>
    pedir("/auth/demo", PerfilSchema, {
      method: "POST",
      body: JSON.stringify({ password }),
    }),

  salir: () => pedir("/auth/salir", z.object({ ok: z.boolean() }), { method: "POST" }),

  casos: (filtros?: { status?: string; category?: string }) => {
    const q = new URLSearchParams();
    if (filtros?.status) q.set("status", filtros.status);
    if (filtros?.category) q.set("category", filtros.category);
    const cola = q.toString() ? `?${q}` : "";
    return pedir(`/board/cases${cola}`, z.object({ cases: z.array(CasoSchema) }));
  },

  caso: (id: string) => pedir(`/board/cases/${id}`, DetalleSchema),

  metricas: (dias = 30) => pedir(`/board/metrics?dias=${dias}`, MetricasSchema),

  mapa: () => pedir("/board/cases/map", z.object({ points: z.array(PuntoSchema) })),

  separar: (reportId: string) =>
    pedir(`/board/reports/${reportId}/ungroup`, z.object({ ok: z.boolean() }), {
      method: "POST",
    }),

  cambiarEstado: (casoId: string, nuevo: string) =>
    pedir(`/board/cases/${casoId}/status?nuevo=${nuevo}`, z.object({ ok: z.boolean(), status: z.string() }), {
      method: "POST",
    }),

  urlEntrarConGoogle: () => `${API_URL}/auth/google/start`,
};
