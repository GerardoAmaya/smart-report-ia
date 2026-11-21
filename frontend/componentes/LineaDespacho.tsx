"use client";

/**
 * La linea de tiempo de un despacho: asignado, en curso, resuelto.
 *
 * La comparten el panel de quien despacha y la vista de solo lectura, para que
 * las dos cuenten lo mismo y no se separen con el tiempo. La via entre los
 * pasos se llena hasta el ultimo cumplido al abrir el caso: se lee de un
 * vistazo cuanto falta.
 */
import { CheckCircle2, CircleDashed, Play, Users } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";

import { type Detalle } from "@/lib/api";
import { hace } from "@/lib/textos";
import { cn } from "@/lib/utils";

type Paso = { etiqueta: string; cuando: string | null; hecho: boolean; icono: typeof Users };

function pasos(caso: Detalle): Paso[] {
  const enCurso = caso.status === "in_progress";
  const cerrado = caso.status === "closed";
  return [
    {
      etiqueta: caso.crew ? `Asignado a ${caso.crew.name}` : "Asignado a una cuadrilla",
      cuando: caso.assigned_at,
      hecho: Boolean(caso.assigned_at) || enCurso || cerrado,
      icono: Users,
    },
    // El caso no guarda cuando empezo; el paso se marca sin hora. Inventarla
    // a partir de otro dato seria una afirmacion que nadie hizo.
    { etiqueta: "Ya están trabajando", cuando: null, hecho: enCurso || cerrado, icono: Play },
    { etiqueta: "Resuelto", cuando: caso.closed_at, hecho: cerrado, icono: CheckCircle2 },
  ];
}

export function LineaDespacho({ caso }: { caso: Detalle }) {
  const quieto = useReducedMotion();
  const lista = pasos(caso);
  const hechos = lista.filter((p) => p.hecho).length;
  // Cuanto de la via se llena: hasta el ultimo paso cumplido. Con uno solo
  // cumplido no hay tramo que llenar todavia.
  const avance = hechos <= 1 ? 0 : (hechos - 1) / (lista.length - 1);

  return (
    <ol className="relative space-y-4" aria-label="Línea de tiempo del despacho">
      {/* La via que une los pasos, y el tramo ya recorrido llenandose de
          arriba abajo al abrir el caso: se lee de un vistazo cuanto falta. */}
      <span
        aria-hidden
        className="absolute top-3.5 bottom-3.5 left-[13px] w-0.5 rounded-full bg-border"
      />
      <motion.span
        aria-hidden
        className="absolute top-3.5 bottom-3.5 left-[13px] w-0.5 origin-top rounded-full bg-gradient-to-b from-primary to-primary/60"
        initial={{ scaleY: 0 }}
        animate={{ scaleY: avance }}
        transition={quieto ? { duration: 0 } : { duration: 0.9, ease: [0.22, 1, 0.36, 1], delay: 0.15 }}
      />
      {lista.map((paso, i) => {
        const Icono = paso.hecho ? paso.icono : CircleDashed;
        return (
          <motion.li
            key={paso.etiqueta}
            className="relative flex items-start gap-3 text-sm"
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={quieto ? { duration: 0 } : { duration: 0.3, delay: 0.1 + i * 0.12 }}
          >
            <span
              className={cn(
                "flex size-7 shrink-0 items-center justify-center rounded-full border bg-card",
                paso.hecho
                  ? "border-primary/40 text-primary shadow-[0_0_0_3px_color-mix(in_oklab,var(--primary)_12%,transparent)]"
                  : "border-dashed text-muted-foreground",
              )}
              aria-hidden
            >
              <Icono className="size-3.5" />
            </span>
            <span className="min-w-0 pt-1">
              <span className={cn(paso.hecho ? "font-medium" : "text-muted-foreground")}>
                {paso.etiqueta}
              </span>
              {paso.hecho && paso.cuando && (
                <span className="text-muted-foreground"> · {hace(paso.cuando)}</span>
              )}
              {!paso.hecho && <span className="sr-only"> (pendiente)</span>}
            </span>
          </motion.li>
        );
      })}
    </ol>
  );
}
