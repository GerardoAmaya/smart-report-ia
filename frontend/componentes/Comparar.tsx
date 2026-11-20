"use client";

/**
 * Comparar las fotos de una agrupación dudosa.
 *
 * El modelo mira la foto de este reporte y la del que casi se le junta, y dice
 * en qué se parecen y en qué no. **Sugiere, no decide**: la etiqueta lo dice y
 * no hay ningún botón aquí que junte o separe. Lo que importa es la lista de
 * diferencias concretas, que se pueden comprobar mirando las dos fotos.
 */
import { useMutation } from "@tanstack/react-query";
import { LoaderCircle, ScanSearch } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { apiAsistente, type Comparacion } from "@/lib/api-asistente";
import { cn } from "@/lib/utils";

const SUGERENCIA: Record<Comparacion["sugerencia"], { texto: string; clase: string }> = {
  mismo_problema: { texto: "Parecen el mismo problema", clase: "text-primary" },
  distintos: { texto: "Parecen problemas distintos", clase: "text-atencion" },
  no_se_puede_saber: { texto: "Con las fotos no se puede saber", clase: "text-muted-foreground" },
};

export function Comparar({ reporteId }: { reporteId: string }) {
  const comparar = useMutation({ mutationFn: () => apiAsistente.comparar(reporteId) });
  const r = comparar.data;

  return (
    <div className="mt-3 space-y-3">
      {!r && (
        <Button
          variant="outline"
          size="sm"
          onClick={() => comparar.mutate()}
          disabled={comparar.isPending}
        >
          {comparar.isPending ? (
            <LoaderCircle className="size-3.5 animate-spin" />
          ) : (
            <ScanSearch className="size-3.5" />
          )}
          {comparar.isPending ? "Comparando las fotos…" : "Comparar las fotos"}
        </Button>
      )}

      {comparar.isError && (
        <p
          role="alert"
          className={cn(
            "text-sm",
            comparar.error instanceof ApiError && comparar.error.status === 429
              ? "text-atencion"
              : "text-destructive",
          )}
        >
          {comparar.error instanceof ApiError
            ? comparar.error.message
            : "No se pudo comparar ahora. Prueba de nuevo."}
        </p>
      )}

      {r && (
        <div className="space-y-3 rounded-lg border bg-card/60 p-3.5 text-sm">
          <p>
            <span className="text-xs uppercase tracking-[0.12em] text-muted-foreground">
              Sugerencia del modelo ·{" "}
            </span>
            <span className={cn("font-medium", SUGERENCIA[r.sugerencia].clase)}>
              {SUGERENCIA[r.sugerencia].texto}
            </span>
          </p>
          <p className="text-muted-foreground">{r.lectura}</p>
          {r.diferencias.length > 0 && (
            <Lista titulo="En qué se diferencian" items={r.diferencias} />
          )}
          {r.parecidos.length > 0 && <Lista titulo="En qué se parecen" items={r.parecidos} />}
          <p className="border-t pt-2.5 text-xs text-muted-foreground">
            Decides tú. El modelo solo miró las dos fotos: la distancia y la categoría ya están
            arriba, y mover o separar reportes se hace desde el caso.
          </p>
        </div>
      )}
    </div>
  );
}

function Lista({ titulo, items }: { titulo: string; items: string[] }) {
  return (
    <div>
      <p className="mb-1 text-xs font-medium">{titulo}</p>
      <ul className="ml-4 list-disc space-y-0.5 text-muted-foreground">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  );
}
