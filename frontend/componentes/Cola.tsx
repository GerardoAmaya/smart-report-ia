"use client";

/**
 * La cola de casos: la superficie de trabajo.
 *
 * El orden no es por fecha sino por lo que hay que atender antes —lo grave y lo
 * mas reportado—. Alguien la mira ocho horas, asi que la densidad importa mas
 * que el aire: caben mas casos sin hacer scroll.
 *
 * El movimiento es el que **muestra un cambio**: un caso que entra a la cola
 * aparece deslizandose, porque eso es informacion. Nada aparece con
 * desvanecido al hacer scroll.
 */
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";

import { ScrollArea } from "@/components/ui/scroll-area";
import { api, type Caso } from "@/lib/api";
import { cn } from "@/lib/utils";
import { categoria, hace } from "@/lib/textos";
import { CargandoCola, Fallo, Vacio } from "./Estados";
import { Cuantos, Dudoso, Severidad } from "./Marcas";

const FILTROS = [
  { valor: "", etiqueta: "Todo" },
  { valor: "open", etiqueta: "Sin atender" },
  { valor: "assigned", etiqueta: "Asignados" },
  { valor: "closed", etiqueta: "Cerrados" },
];

export function Cola({
  seleccionado,
  onElegir,
  filtro,
  onFiltrar,
}: {
  seleccionado: string | null;
  onElegir: (id: string) => void;
  filtro: string;
  onFiltrar: (f: string) => void;
}) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["casos", filtro],
    queryFn: () => api.casos(filtro ? { status: filtro } : undefined),
    // Los reportes entran solos: quien despacha no deberia recargar para verlos.
    refetchInterval: 10_000,
  });

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-1 border-b px-3 py-2.5">
        {FILTROS.map((f) => (
          <button
            key={f.valor}
            onClick={() => onFiltrar(f.valor)}
            aria-pressed={filtro === f.valor}
            className={cn(
              "relative rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
              filtro === f.valor
                ? "text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {/* El fondo se desliza entre pestañas en vez de parpadear: muestra
                de donde vino la seleccion. */}
            {filtro === f.valor && (
              <motion.span
                layoutId="filtro-activo"
                className="absolute inset-0 rounded-md bg-secondary"
                transition={{ type: "spring", stiffness: 500, damping: 40 }}
              />
            )}
            <span className="relative">{f.etiqueta}</span>
          </button>
        ))}
      </div>

      <ScrollArea className="flex-1">
        {isLoading && <CargandoCola />}
        {error && <Fallo mensaje={(error as Error).message} reintentar={() => refetch()} />}
        {data?.cases.length === 0 && (
          <Vacio
            titulo={filtro ? "Nada con ese filtro" : "Todavía no hay casos"}
            detalle={
              filtro
                ? "Probá con otro filtro o mirá todo."
                : "Cuando alguien reporte por el bot, aparece acá agrupado con los que sean el mismo problema."
            }
          />
        )}

        <AnimatePresence initial={false}>
          {data?.cases.map((caso) => (
            <Item
              key={caso.id}
              caso={caso}
              activo={caso.id === seleccionado}
              onElegir={() => onElegir(caso.id)}
            />
          ))}
        </AnimatePresence>
      </ScrollArea>
    </div>
  );
}

function Item({
  caso,
  activo,
  onElegir,
}: {
  caso: Caso;
  activo: boolean;
  onElegir: () => void;
}) {
  return (
    <motion.button
      layout
      // Un caso nuevo entra deslizandose: eso es un cambio y conviene verlo.
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.18, ease: "easeOut" }}
      onClick={onElegir}
      aria-current={activo ? "true" : undefined}
      className={cn(
        "relative block w-full overflow-hidden border-b px-4 py-3 text-left transition-colors",
        activo ? "bg-card" : "hover:bg-card/60",
      )}
    >
      {/* Barra de acento en el seleccionado: dice donde estas sin cambiar el
          color del texto, que empeoraria el contraste. */}
      {activo && (
        <motion.span
          layoutId="caso-activo"
          className="absolute inset-y-0 left-0 w-0.5 bg-primary"
          transition={{ type: "spring", stiffness: 500, damping: 40 }}
        />
      )}
      <div className="flex items-start justify-between gap-3">
        <span className="truncate text-sm font-medium leading-tight">
          {categoria(caso.category)}
        </span>
        <Cuantos n={caso.report_count} />
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1.5">
        <Severidad valor={caso.severity} />
        <Dudoso cuantos={caso.doubtful_count} />
        <span className="text-xs text-muted-foreground">{hace(caso.created_at)}</span>
      </div>
    </motion.button>
  );
}
