"use client";

/**
 * El despacho de un caso, para quien solo puede mirar.
 *
 * El invitado no despacha, pero lo que el despacho deja es lo mas convincente
 * del sistema: a quien se le asigno, cuando, la foto del arreglo y a cuantas
 * personas se les aviso. Antes el panel entero se escondia con los botones, y
 * un caso cerrado con su prueba se veia igual que uno que nadie habia tocado.
 *
 * Sin botones ni formularios: es la misma informacion que ve un operador, sin
 * nada que la cambie. Reutiliza la galeria y el contador de avisos del panel de
 * despacho para que las dos vistas no se separen con el tiempo.
 */
import { CheckCircle2, CircleDashed, Play, Users } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { type Detalle } from "@/lib/api";
import { hace } from "@/lib/textos";
import { cn } from "@/lib/utils";
import { Avisos, Evidencias } from "./Despacho";

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

export function DespachoLectura({ caso }: { caso: Detalle }) {
  const sinDespacho = !caso.assigned_at && caso.status === "open";

  return (
    <Card className="mt-6">
      <CardContent className="space-y-5 pt-6">
        <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
          <Users className="size-3.5" />
          Despacho
        </p>

        {sinDespacho ? (
          <p className="text-sm text-muted-foreground">
            Todavía no se ha asignado a ninguna cuadrilla.
          </p>
        ) : (
          <ol className="space-y-3" aria-label="Línea de tiempo del despacho">
            {pasos(caso).map((paso) => {
              const Icono = paso.hecho ? paso.icono : CircleDashed;
              return (
                <li key={paso.etiqueta} className="flex items-start gap-3 text-sm">
                  <span
                    className={cn(
                      "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border",
                      paso.hecho
                        ? "border-primary/30 bg-primary/10 text-primary"
                        : "border-dashed text-muted-foreground",
                    )}
                    aria-hidden
                  >
                    <Icono className="size-3.5" />
                  </span>
                  <span className="min-w-0">
                    <span className={cn(paso.hecho ? "font-medium" : "text-muted-foreground")}>
                      {paso.etiqueta}
                    </span>
                    {paso.hecho && paso.cuando && (
                      <span className="text-muted-foreground"> · {hace(paso.cuando)}</span>
                    )}
                    {!paso.hecho && <span className="sr-only"> (pendiente)</span>}
                  </span>
                </li>
              );
            })}
          </ol>
        )}

        {caso.evidence.length > 0 && (
          <div className="space-y-2 border-t pt-5">
            <p className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
              Foto del arreglo
            </p>
            <Evidencias fotos={caso.evidence} />
          </div>
        )}

        {caso.closing_note && (
          <p className="border-l-2 pl-3 text-sm text-muted-foreground">{caso.closing_note}</p>
        )}

        <Avisos notificaciones={caso.notifications} />
      </CardContent>
    </Card>
  );
}
