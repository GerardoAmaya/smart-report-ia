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
import { Users } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { type Detalle } from "@/lib/api";
import { Avisos, Evidencias } from "./Despacho";
import { LineaDespacho } from "./LineaDespacho";

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
          <LineaDespacho caso={caso} />
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
