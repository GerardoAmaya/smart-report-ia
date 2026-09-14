/**
 * Estados de vacio, carga y error, **redactados**.
 *
 * Parte del piso de calidad que PLAN.md exige para dar la fase por terminada.
 * "Sin resultados" no dice si el sistema esta roto, si los filtros esconden
 * todo, o si de verdad no hay nada — y quien lo lee tiene que ir a los logs
 * para saberlo, que es justo lo que este tablero deberia ahorrar.
 */
import { Inbox, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

/** Esqueleto con la forma del contenido, no un spinner: la pagina no salta. */
export function CargandoCola() {
  return (
    <div className="space-y-px" role="status" aria-label="Cargando la cola">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="space-y-2 px-4 py-3.5">
          <div className="flex items-center justify-between gap-3">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-5 w-7 rounded-md" />
          </div>
          <Skeleton className="h-3 w-24" />
        </div>
      ))}
    </div>
  );
}

export function CargandoDetalle() {
  return (
    <div className="space-y-6 p-6" role="status" aria-label="Cargando el caso">
      <div className="space-y-2">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-4 w-64" />
      </div>
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="flex gap-4">
          <Skeleton className="h-28 w-24 rounded-lg" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-3 w-full max-w-md" />
            <Skeleton className="h-3 w-40" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function Vacio({
  titulo,
  detalle,
  icono: Icono = Inbox,
}: {
  titulo: string;
  detalle: string;
  icono?: React.ComponentType<{ className?: string }>;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-8 py-16 text-center">
      <div className="mb-4 rounded-full bg-muted p-3">
        <Icono className="size-5 text-muted-foreground" />
      </div>
      <p className="text-sm font-medium">{titulo}</p>
      <p className="mt-1.5 max-w-xs text-sm text-muted-foreground">{detalle}</p>
    </div>
  );
}

export function Fallo({ mensaje, reintentar }: { mensaje: string; reintentar?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center px-8 py-16 text-center" role="alert">
      <div className="mb-4 rounded-full bg-destructive/10 p-3">
        <TriangleAlert className="size-5 text-destructive" />
      </div>
      <p className="text-sm font-medium">No se pudo cargar</p>
      {/* El detalle entero: un estado rojo sin motivo obliga a ir a los logs. */}
      <p className="mt-1.5 max-w-sm text-sm text-muted-foreground">{mensaje}</p>
      {reintentar && (
        <Button variant="outline" size="sm" onClick={reintentar} className="mt-5">
          Probar de nuevo
        </Button>
      )}
    </div>
  );
}
