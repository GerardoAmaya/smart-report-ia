"use client";

/**
 * Si el tablero esta al dia o no.
 *
 * Se enseña porque un tablero que dejo de actualizarse y no lo dice es peor que
 * uno que hay que recargar a mano: quien lo mira sigue creyendo lo que ve.
 */
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { EstadoFlujo } from "@/lib/tiempo-real";

const TEXTO: Record<EstadoFlujo, string> = {
  conectando: "Conectando…",
  "en-vivo": "Al día. Los cambios aparecen solos.",
  "sin-conexion": "Se perdió la conexión. Reintentando…",
};

export function EnVivo({ estado }: { estado: EstadoFlujo }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className="relative flex size-2">
            {estado === "en-vivo" && (
              // Solo late cuando de verdad esta escuchando: una animacion que
              // sigue cuando la conexion se corto es una mentira en pantalla.
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary opacity-60" />
            )}
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
