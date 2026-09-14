/**
 * Las marcas del tablero.
 *
 * **El color significa una cosa sola.** Es lo unico de la direccion de diseño
 * original que no se revirtio, porque no es estetica: es lo que permite barrer
 * la cola con la vista. El ambar aparece solo donde hay algo que decidir; si se
 * usara tambien para "severidad media", dejaria de poder usarse como señal.
 */
import { AlertTriangle, CircleDot } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { severidad } from "@/lib/textos";

export function Severidad({ valor, className }: { valor: string | null; className?: string }) {
  if (valor === "alta") {
    return (
      <Badge
        variant="outline"
        className={cn(
          "gap-1.5 border-urgente/30 bg-urgente/10 font-medium text-urgente",
          className,
        )}
      >
        <span aria-hidden className="size-1.5 rounded-full bg-urgente" />
        {severidad(valor)}
      </Badge>
    );
  }
  // Media y baja sin color: un tablero donde todo tiene color no tiene jerarquia.
  return (
    <span className={cn("text-xs text-muted-foreground", className)}>{severidad(valor)}</span>
  );
}

/** Ambar, y **solo aqui**: hay algo que una persona tiene que decidir. */
export function Dudoso({ cuantos }: { cuantos: number }) {
  if (cuantos < 1) return null;
  return (
    <Badge
      variant="outline"
      className="gap-1.5 border-atencion/35 bg-atencion/10 font-medium text-atencion"
    >
      <AlertTriangle aria-hidden className="size-3" />
      {cuantos === 1 ? "1 dudoso" : `${cuantos} dudosos`}
    </Badge>
  );
}

/**
 * Cuantos reportan lo mismo.
 *
 * Va con peso porque es la informacion que justifica el sistema entero:
 * cuarenta y siete reportes en un dia son dieciocho problemas.
 */
export function Cuantos({ n }: { n: number }) {
  return (
    <span
      className={cn(
        "inline-flex min-w-7 items-center justify-center rounded-md px-1.5 py-0.5 font-mono text-xs font-semibold tabular-nums",
        n > 1 ? "bg-primary/12 text-primary" : "text-muted-foreground",
      )}
      title={n === 1 ? "1 reporte" : `${n} reportes del mismo problema`}
    >
      {n}
    </span>
  );
}

const ESTADO_ESTILO: Record<string, string> = {
  open: "border-foreground/20 text-foreground/75",
  assigned: "border-primary/30 bg-primary/10 text-primary",
  in_progress: "border-primary/30 bg-primary/10 text-primary",
  closed: "border-resuelto/30 text-resuelto",
  discarded: "border-resuelto/30 text-resuelto line-through",
};

const ESTADO_TEXTO: Record<string, string> = {
  open: "Sin atender",
  assigned: "Asignado",
  in_progress: "En curso",
  closed: "Cerrado",
  discarded: "Descartado",
};

export function Estado({ valor }: { valor: string }) {
  return (
    <Badge variant="outline" className={cn("font-normal", ESTADO_ESTILO[valor])}>
      <CircleDot aria-hidden className="size-3" />
      {ESTADO_TEXTO[valor] ?? valor}
    </Badge>
  );
}
