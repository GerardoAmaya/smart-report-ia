"use client";

/**
 * Si el tablero esta al dia o no.
 *
 * Se enseña porque un tablero que dejo de actualizarse y no lo dice es peor que
 * uno que hay que recargar a mano: quien lo mira sigue creyendo lo que ve.
 */
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { EVENTO_CAMBIO, type EstadoFlujo } from "@/lib/tiempo-real";

const TEXTO: Record<EstadoFlujo, string> = {
  conectando: "Conectando…",
  "en-vivo": "Al día. Los cambios aparecen solos.",
  "sin-conexion": "Se perdió la conexión. Reintentando…",
};

export function EnVivo({ estado }: { estado: EstadoFlujo }) {
  // Un latido por cada cambio que llega, y nada mas. Antes latia en bucle
  // mientras hubiera conexion: un movimiento que no para deja de decir nada, y
  // en una pantalla que se mira ocho horas, distrae. Asi el latido significa
  // "acaba de entrar algo".
  const [latido, setLatido] = useState(0);
  const quieto = useReducedMotion();
  useEffect(() => {
    const latir = () => setLatido((n) => n + 1);
    window.addEventListener(EVENTO_CAMBIO, latir);
    return () => window.removeEventListener(EVENTO_CAMBIO, latir);
  }, []);

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className="relative flex size-2">
            <AnimatePresence>
              {estado === "en-vivo" && latido > 0 && !quieto && (
                <motion.span
                  key={latido}
                  className="absolute inline-flex size-full rounded-full bg-primary"
                  initial={{ scale: 1, opacity: 0.7 }}
                  animate={{ scale: 3.2, opacity: 0 }}
                  transition={{ duration: 0.9, ease: "easeOut" }}
                />
              )}
            </AnimatePresence>
            <span
              className={cn(
                "relative inline-flex size-2 rounded-full",
                estado === "en-vivo" && "bg-primary",
                estado === "conectando" && "bg-muted-foreground",
                estado === "sin-conexion" && "bg-atencion",
              )}
            />
          </span>
          <span className="hidden sm:inline">
            {estado === "en-vivo" ? "En vivo" : estado === "conectando" ? "Conectando" : "Sin conexión"}
          </span>
        </span>
      </TooltipTrigger>
      <TooltipContent>{TEXTO[estado]}</TooltipContent>
    </Tooltip>
  );
}
