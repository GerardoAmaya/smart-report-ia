"use client";

/**
 * Despacho y cierre.
 *
 * El flujo tiene un orden que la interfaz hace evidente en vez de explicar:
 * asignar, empezar, subir la foto del arreglo, cerrar. En cada estado solo se
 * ofrece lo que se puede hacer — un boton que va a devolver 409 es peor que no
 * tener boton.
 *
 * **Cerrar exige la foto del arreglo.** Sin evidencia, el cierre es una
 * afirmacion que nadie puede comprobar, y el tablero existe para que las
 * afirmaciones se puedan comprobar. Por eso el boton de cerrar no aparece hasta
 * que hay foto, y se dice por que.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import {
  Camera,
  CheckCircle2,
  MailCheck,
  Play,
  RotateCcw,
  TriangleAlert,
  Users,
} from "lucide-react";
import { useRef, useState } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api, type Detalle } from "@/lib/api";
import { hace } from "@/lib/textos";

export function Despacho({ caso }: { caso: Detalle }) {
  const cliente = useQueryClient();
  const [cuadrilla, setCuadrilla] = useState<string>("");
  const [nota, setNota] = useState("");
  const [error, setError] = useState<string | null>(null);
  const archivo = useRef<HTMLInputElement>(null);

  const { data: cuadrillas } = useQuery({
    queryKey: ["cuadrillas"],
    queryFn: api.cuadrillas,
    staleTime: 5 * 60_000,
  });

  const refrescar = () => {
    cliente.invalidateQueries({ queryKey: ["caso", caso.id] });
    cliente.invalidateQueries({ queryKey: ["casos"] });
    cliente.invalidateQueries({ queryKey: ["metricas"] });
  };

  function usar<T>(fn: () => Promise<T>) {
    setError(null);
    return fn().then(refrescar).catch((e: Error) => setError(e.message));
  }

  const asignar = useMutation({
    mutationFn: () => api.asignar(caso.id, cuadrilla),
    onSuccess: refrescar,
    onError: (e: Error) => setError(e.message),
  });
  const empezar = useMutation({
    mutationFn: () => api.empezar(caso.id),
    onSuccess: refrescar,
    onError: (e: Error) => setError(e.message),
  });
  const subir = useMutation({
    mutationFn: (f: File) => api.subirEvidencia(caso.id, f),
    onSuccess: refrescar,
    onError: (e: Error) => setError(e.message),
  });
  const cerrar = useMutation({
    mutationFn: () => api.cerrar(caso.id, nota.trim() || undefined),
    onSuccess: refrescar,
    onError: (e: Error) => setError(e.message),
  });
  const reabrir = useMutation({
    mutationFn: () => api.reabrir(caso.id),
    onSuccess: refrescar,
    onError: (e: Error) => setError(e.message),
  });

  const cerrado = caso.status === "closed";
  const tieneEvidencia = caso.evidence.length > 0;

  return (
    <Card className="mt-6">
      <CardContent className="space-y-5 pt-6">
        {/* --- Cuadrilla --- */}
        {!cerrado && (
          <div>
            <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
              <Users className="size-3.5" />
              Cuadrilla
            </p>
            {caso.crew ? (
              <p className="text-sm">
                <span className="font-medium">{caso.crew.name}</span>
                {caso.assigned_at && (
                  <span className="text-muted-foreground"> · asignada {hace(caso.assigned_at)}</span>
                )}
              </p>
            ) : (
              <div className="flex flex-wrap gap-2">
                <Select value={cuadrilla} onValueChange={setCuadrilla}>
                  <SelectTrigger size="sm" className="w-[240px]">
                    <SelectValue placeholder="Elegí una cuadrilla" />
                  </SelectTrigger>
                  <SelectContent>
                    {cuadrillas?.crews.map((c) => (
                      <SelectItem key={c.id} value={c.id}>
                        {c.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  size="sm"
                  disabled={!cuadrilla || asignar.isPending}
                  onClick={() => asignar.mutate()}
                >
                  {asignar.isPending ? "Asignando…" : "Asignar y avisar"}
                </Button>
              </div>
            )}
          </div>
        )}

        {/* --- Empezar --- */}
        {caso.status === "assigned" && (
          <Button size="sm" variant="outline" onClick={() => empezar.mutate()} disabled={empezar.isPending}>
            <Play className="size-3.5" />
            {empezar.isPending ? "Avisando…" : "Marcar que ya están trabajando"}
          </Button>
        )}

        {/* --- Evidencia --- */}
        {!cerrado && (
          <div>
            <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
              <Camera className="size-3.5" />
              Foto del arreglo
            </p>
            <input
              ref={archivo}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) subir.mutate(f);
                e.target.value = "";
              }}
            />
            <Button
              size="sm"
              variant="outline"
              onClick={() => archivo.current?.click()}
              disabled={subir.isPending}
            >
              <Camera className="size-3.5" />
              {subir.isPending ? "Subiendo…" : tieneEvidencia ? "Subir otra" : "Subir foto"}
            </Button>
            {!tieneEvidencia && (
              <p className="mt-2 text-xs text-muted-foreground">
                Hace falta para cerrar: un cierre sin foto no se puede comprobar.
              </p>
            )}
          </div>
        )}

        <Evidencias fotos={caso.evidence} />

        {/* --- Cerrar --- */}
        {!cerrado && tieneEvidencia && (
          <div className="space-y-2 border-t pt-5">
            <Textarea
              value={nota}
              onChange={(e) => setNota(e.target.value)}
              maxLength={500}
              rows={2}
              placeholder="Qué se hizo. Esto le llega tal cual a quienes reportaron."
              className="text-sm"
            />
            <CerrarConAviso
              cuantos={caso.report_count}
              pendiente={cerrar.isPending}
              onCerrar={() => cerrar.mutate()}
            />
          </div>
        )}

        {/* --- Cerrado --- */}
        {cerrado && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-3 border-t pt-5"
          >
            <p className="flex items-center gap-1.5 text-sm">
              <CheckCircle2 className="size-4 text-primary" />
              Cerrado {caso.closed_at && hace(caso.closed_at)}
            </p>
            {caso.closing_note && (
              <p className="border-l-2 pl-3 text-sm text-muted-foreground">{caso.closing_note}</p>
            )}
            <Avisos notificaciones={caso.notifications} />
            <Button size="sm" variant="outline" onClick={() => reabrir.mutate()} disabled={reabrir.isPending}>
              <RotateCcw className="size-3.5" />
              Reabrir
            </Button>
          </motion.div>
        )}

        {!cerrado && caso.notifications.sent > 0 && <Avisos notificaciones={caso.notifications} />}

        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * El aviso de vuelta, hecho visible.
 *
 * Es la parte que casi nadie construye, y si no se ve nadie sabe que existe.
 */
function Avisos({ notificaciones }: { notificaciones: Detalle["notifications"] }) {
  const { sent, pending, failed } = notificaciones;
  if (sent + pending + failed === 0) return null;

  return (
    <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
      <span className="flex items-center gap-1.5 text-muted-foreground">
        <MailCheck className="size-4" />
        {sent === 1 ? "Se avisó a 1 persona" : `Se avisó a ${sent} personas`}
      </span>
      {pending > 0 && <span className="text-xs text-muted-foreground">{pending} en camino</span>}
      {failed > 0 && (
        <span className="flex items-center gap-1 text-xs text-atencion">
          <TriangleAlert className="size-3" />
          {failed} sin entregar
        </span>
      )}
    </p>
  );
}

function Evidencias({ fotos }: { fotos: Detalle["evidence"] }) {
  if (fotos.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {fotos.map((f) => (
        <a
          key={f.id}
          href={f.original_url ?? undefined}
          target="_blank"
          rel="noreferrer"
          title={`Subida por ${f.uploaded_by}`}
          className="overflow-hidden rounded-lg border"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={f.thumbnail_url ?? ""}
            alt={`Foto del arreglo subida por ${f.uploaded_by}`}
            className="size-20 object-cover transition-transform duration-300 hover:scale-105"
            width={80}
            height={80}
          />
        </a>
      ))}
    </div>
  );
}

/** Cerrar avisa a gente de verdad, asi que se confirma antes. */
function CerrarConAviso({
  cuantos,
  pendiente,
  onCerrar,
}: {
  cuantos: number;
  pendiente: boolean;
  onCerrar: () => void;
}) {
  const [abierto, setAbierto] = useState(false);

  return (
    <AlertDialog open={abierto} onOpenChange={setAbierto}>
      <Button size="sm" onClick={() => setAbierto(true)} disabled={pendiente}>
        <CheckCircle2 className="size-3.5" />
        {pendiente ? "Cerrando…" : "Cerrar y avisar"}
      </Button>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>¿Cerrar el caso?</AlertDialogTitle>
          <AlertDialogDescription>
            Le va a llegar un mensaje a{" "}
            {cuantos === 1 ? "la persona que reportó" : `las ${cuantos} personas que reportaron`}{" "}
            esto. Un solo arreglo, {cuantos === 1 ? "una respuesta" : `${cuantos} respuestas`}.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Todavía no</AlertDialogCancel>
          <AlertDialogAction onClick={onCerrar}>Cerrar y avisar</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
