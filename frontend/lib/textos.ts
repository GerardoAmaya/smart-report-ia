/**
 * Las palabras del tablero, en un sitio.
 *
 * Los estados de vacio y de error estan **redactados**, no puestos por salir
 * del paso: son parte del piso de calidad que PLAN.md exige para dar la fase
 * por terminada. "Sin resultados" no dice si el sistema esta roto, si los
 * filtros esconden todo, o si de verdad no hay nada.
 */

export const CATEGORIAS: Record<string, string> = {
  vialidad: "Calle o acera",
  alumbrado: "Alumbrado",
  agua: "Agua o drenaje",
  desechos: "Basura",
  riesgo_estructural: "Riesgo de derrumbe",
  espacio_publico: "Espacio público",
  no_es_reporte: "No es un reporte",
};

export const ESTADOS: Record<string, string> = {
  open: "Sin atender",
  assigned: "Asignado",
  in_progress: "En curso",
  closed: "Cerrado",
  discarded: "Descartado",
};

export const SEVERIDADES: Record<string, string> = {
  alta: "Urgente",
  media: "Atender",
  baja: "Sin urgencia",
};

export function categoria(valor: string | null): string {
  return valor ? (CATEGORIAS[valor] ?? valor) : "Sin clasificar";
}

export function estado(valor: string): string {
  return ESTADOS[valor] ?? valor;
}

export function severidad(valor: string | null): string {
  return valor ? (SEVERIDADES[valor] ?? valor) : "—";
}

/** Distancia legible. Un operador lee "12 m", no "12.437281". */
export function metros(valor: number | null): string {
  if (valor === null) return "—";
  return valor < 1000 ? `${Math.round(valor)} m` : `${(valor / 1000).toFixed(1)} km`;
}

/** Cuanto hace. Relativo porque lo que importa es si es de hoy o de la semana pasada. */
export function hace(iso: string): string {
  const minutos = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutos < 1) return "recién";
  if (minutos < 60) return `hace ${minutos} min`;
  const horas = Math.floor(minutos / 60);
  if (horas < 24) return `hace ${horas} h`;
  const dias = Math.floor(horas / 24);
  return dias === 1 ? "ayer" : `hace ${dias} días`;
}
