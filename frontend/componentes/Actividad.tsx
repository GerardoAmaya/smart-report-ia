"use client";

/**
 * Lo que acaba de pasar: el feed de actividad del tablero.
 *
 * Es lo que hace sentir que el sistema respira: alguien reporto en Mejicanos,
 * una cuadrilla empezo, a dos personas les llego el aviso. **Todo es real**: sale
 * de `/board/actividad`, que lo arma con los datos que hay, y se refresca con
 * el flujo en vivo como el resto del tablero, sin sondeo.
 *
 * Lo nuevo entra deslizandose y con un destello que se apaga solo. En la
 * primera carga no destella nada: si todo es nuevo, el destello no dice nada.
 */
import { useQuery } from "@tanstack/react-query";
import {
  CircleCheck,
  Hammer,
  Layers,
  type LucideIcon,
  MailCheck,
  MessageSquarePlus,
  Radio,
  TriangleAlert,
  Users,
} from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { obtenerActividad, type Evento } from "@/lib/api-actividad";
import { hace } from "@/lib/textos";
import { cn } from "@/lib/utils";

/** Icono y tono por tipo. Los tonos son los de la paleta, no colores nuevos. */
const ASPECTO: Record<string, { icono: LucideIcon; tono: string }> = {
  reporte: { icono: MessageSquarePlus, tono: "bg-primary/10 text-primary" },
  agrupado: { icono: Layers, tono: "bg-primary/10 text-primary" },
  dudoso: { icono: TriangleAlert, tono: "bg-atencion/15 text-atencion" },
  asignado: { icono: Users, tono: "bg-secondary text-foreground" },
  en_curso: { icono: Hammer, tono: "bg-atencion/15 text-atencion" },
  cerrado: { icono: CircleCheck, tono: "bg-primary/15 text-primary" },
  aviso: { icono: MailCheck, tono: "bg-secondary text-muted-foreground" },
};
const NEUTRO = { icono: Radio, tono: "bg-secondary text-muted-foreground" };

/** Cada cuanto se rehace «hace 2 min». No pide nada al servidor. */
const RELOJ_MS = 30_000;
const DESTELLO_MS = 1800;

export function Actividad({
  alElegirCaso,
  className,
}: {
  alElegirCaso: (id: string) => void;
  className?: string;
}) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["actividad"],
    queryFn: () => obtenerActividad(20),
    // Lo refresca el flujo en vivo (lib/tiempo-real.ts). Sin sondeo: dos
    // mecanismos para lo mismo se contradicen el dia que uno falla.
    staleTime: Infinity,
  });

  // El tiempo relativo envejece aunque no llegue nada nuevo.
  const [, setTic] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setTic((n) => n + 1), RELOJ_MS);
    return () => clearInterval(t);
  }, []);

  // Los eventos que llegaron mientras se miraba. La primera carga no cuenta.
  const conocidos = useRef<Set<string> | null>(null);
  const [nuevos, setNuevos] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (!data) return;
    const antes = conocidos.current;
    conocidos.current = new Set(data.map((e) => e.id));
    if (!antes) return;
    const llegaron = data.filter((e) => !antes.has(e.id)).map((e) => e.id);
    if (llegaron.length === 0) return;
    setNuevos(new Set(llegaron));
    const t = setTimeout(() => setNuevos(new Set()), DESTELLO_MS);
    return () => clearTimeout(t);
  }, [data]);

  return (
    <section className={cn("flex min-h-0 flex-col", className)} aria-label="Actividad reciente">
      <header className="flex items-center gap-2 px-4 py-3">
        {/* Quieto a proposito: el latido ya lo da «En vivo» en el encabezado, y
            un punto que parpadea sin parar junto a una lista cansa a las horas. */}
        <span className="size-2 rounded-full bg-primary" />
        <h2 className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
          Lo que acaba de pasar
        </h2>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {isLoading && <Cargando />}

        {error && (
          <p role="alert" className="px-2 py-4 text-sm text-muted-foreground">
            No se pudo cargar la actividad.{" "}
            <button
              type="button"
              onClick={() => refetch()}
              className="font-medium text-foreground underline underline-offset-2"
            >
              Probar de nuevo
            </button>
          </p>
        )}

        {data && data.length === 0 && (
          <p className="px-2 py-6 text-center text-sm text-muted-foreground">
            Todavía no ha pasado nada. Cuando alguien reporte por el bot, aparece aquí.
          </p>
        )}

        {data && data.length > 0 && (
          <ol className="space-y-0.5">
            <AnimatePresence initial={false}>
              {data.map((evento) => (
                <Fila
                  key={evento.id}
                  evento={evento}
                  nuevo={nuevos.has(evento.id)}
                  alElegir={() => alElegirCaso(evento.caso_id)}
                />
              ))}
            </AnimatePresence>
          </ol>
        )}
      </div>
    </section>
  );
}

function Fila({
  evento,
  nuevo,
  alElegir,
}: {
  evento: Evento;
  nuevo: boolean;
  alElegir: () => void;
}) {
  const reducido = useReducedMotion();
  const { icono: Icono, tono } = ASPECTO[evento.tipo] ?? NEUTRO;

  return (
    <motion.li
      layout={!reducido}
      initial={{ opacity: 0, x: -12, height: 0 }}
      animate={{ opacity: 1, x: 0, height: "auto" }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
    >
      <button
        type="button"
        onClick={alElegir}
        className="relative flex w-full items-start gap-3 overflow-hidden rounded-lg px-2 py-2 text-left transition-colors hover:bg-card"
      >
        {/* El destello: una franja que se apaga sola. Dice "esto acaba de llegar"
            sin quedarse parpadeando sobre algo que hay que leer. */}
        {nuevo && !reducido && (
          <motion.span
            aria-hidden
            className="pointer-events-none absolute inset-0 rounded-lg bg-primary/12"
            initial={{ opacity: 1 }}
            animate={{ opacity: 0 }}
            transition={{ duration: DESTELLO_MS / 1000, ease: "easeOut" }}
          />
        )}
        <span className={cn("mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full", tono)}>
          <Icono className="size-3.5" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm leading-snug">{evento.texto}</span>
          <span className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
            {evento.detalle && <span className="truncate">{evento.detalle}</span>}
            {evento.detalle && <span aria-hidden>·</span>}
            <time dateTime={evento.cuando} className="shrink-0">
              {hace(evento.cuando)}
            </time>
          </span>
        </span>
      </button>
    </motion.li>
  );
}

function Cargando() {
  return (
    <div className="space-y-3 px-2 py-1" role="status" aria-label="Cargando la actividad">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="flex items-start gap-3">
          <Skeleton className="size-7 rounded-full" />
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-3.5 w-4/5" />
            <Skeleton className="h-3 w-1/3" />
          </div>
        </div>
      ))}
    </div>
  );
}
