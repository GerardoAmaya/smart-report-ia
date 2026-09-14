"use client";

/**
 * El detalle de un caso.
 *
 * **Aqui se juega la verificacion de la fase:** un operador que no vio el
 * sistema antes tiene que entender por que cuatro reportes estan juntos sin que
 * nadie se lo explique.
 *
 * Por eso cada reporte trae su distancia al caso y el motivo en español, y no
 * un puntaje. "A 13 m, misma categoria" se puede discutir; un 0,87 no.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import { ImageOff, Images, Link2Off, MapPin, Text } from "lucide-react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { api, type Reporte } from "@/lib/api";
import { cn } from "@/lib/utils";
import { categoria, hace, metros } from "@/lib/textos";
import { puede, useSesion } from "@/lib/sesion";
import { Despacho } from "./Despacho";
import { CargandoDetalle, Fallo, Vacio } from "./Estados";
import { Estado, Severidad } from "./Marcas";

export function Detalle({ casoId }: { casoId: string | null }) {
  const { perfil } = useSesion();
  const cliente = useQueryClient();

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["caso", casoId],
    queryFn: () => api.caso(casoId!),
    enabled: Boolean(casoId),
  });

  const refrescar = () => {
    cliente.invalidateQueries({ queryKey: ["caso", casoId] });
    cliente.invalidateQueries({ queryKey: ["casos"] });
  };

  const separar = useMutation({
    mutationFn: (reportId: string) => api.separar(reportId),
    onSuccess: refrescar,
  });


  if (!casoId) {
    return (
      <Vacio
        icono={MapPin}
        titulo="Elegí un caso de la cola"
        detalle="Vas a ver sus reportes y por qué el sistema los juntó."
      />
    );
  }
  if (isLoading) return <CargandoDetalle />;
  if (error) return <Fallo mensaje={(error as Error).message} reintentar={() => refetch()} />;
  if (!data) return null;

  const puedeDespachar = puede(perfil, "despachar");
  const agrupado = data.report_count > 1;

  return (
    <motion.article
      key={data.id}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
      className="mx-auto max-w-3xl px-6 py-6"
    >
      <header>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="text-xl font-semibold tracking-tight">
              {categoria(data.category)}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {agrupado
                ? `${data.report_count} reportes del mismo problema`
                : "Un reporte"}
              {" · abierto "}
              {hace(data.created_at)}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Severidad valor={data.severity} />
            <Estado valor={data.status} />
          </div>
        </div>

      </header>

      {puedeDespachar && <Despacho caso={data} />}

      <Separator className="my-6" />

      {agrupado && (
        <h3 className="mb-4 text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
          Por qué están juntos
        </h3>
      )}

      <ol className="space-y-px">
        {data.reports.map((reporte, i) => (
          <Fila
            key={reporte.id}
            reporte={reporte}
            indice={i}
            primero={i === 0}
            puedeSeparar={puedeDespachar && agrupado}
            separando={separar.isPending && separar.variables === reporte.id}
            onSeparar={() => separar.mutate(reporte.id)}
          />
        ))}
      </ol>

      {separar.isError && (
        <p role="alert" className="mt-4 text-sm text-destructive">
          No se pudo separar: {(separar.error as Error).message}
        </p>
      )}
    </motion.article>
  );
}

function Fila({
  reporte,
  indice,
  primero,
  puedeSeparar,
  separando,
  onSeparar,
}: {
  reporte: Reporte;
  indice: number;
  primero: boolean;
  puedeSeparar: boolean;
  separando: boolean;
  onSeparar: () => void;
}) {
  // La evidencia que explica por que este reporte esta donde esta. Se prefiere
  // la decision que lo coloco; los descartes son contexto, no la razon.
  const decisiva =
    reporte.evidence.find((e) => e.decision === "grouped") ??
    reporte.evidence.find((e) => e.decision === "doubtful") ??
    reporte.evidence.find((e) => e.decision === "alone");

  const dudoso = reporte.grouping_status === "doubtful";
  const foto = reporte.photos[0];

  return (
    <motion.li
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      // Escalonado corto: se lee de arriba abajo sin que nadie espere.
      transition={{ duration: 0.2, delay: Math.min(indice * 0.04, 0.24), ease: "easeOut" }}
      className={cn(
        "flex gap-4 rounded-lg border p-4 transition-colors",
        dudoso ? "border-atencion/30 bg-atencion/5" : "border-transparent hover:bg-card/60",
      )}
    >
      {foto?.thumbnail_url ? (
        <a
          href={foto.original_url ?? undefined}
          target="_blank"
          rel="noreferrer"
          className="group relative shrink-0 overflow-hidden rounded-lg"
        >
          {/* <img> y no next/image: el enlace es prefirmado y de vida corta, y
              el optimizador lo cachearia con una firma que caduca. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={foto.thumbnail_url}
            alt={`Foto del reporte de ${hace(reporte.created_at)}`}
            className="size-28 object-cover transition-transform duration-300 group-hover:scale-[1.04]"
            width={112}
            height={112}
          />
        </a>
      ) : (
        <div className="flex size-28 shrink-0 flex-col items-center justify-center gap-1 rounded-lg border border-dashed text-muted-foreground">
          <ImageOff className="size-4" />
          <span className="text-xs">sin foto</span>
        </div>
      )}

      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-3">
          <span className="text-sm font-medium">
            {primero ? "Abrió el caso" : `A ${metros(decisiva?.distance_m ?? null)}`}
          </span>
          <span className="shrink-0 text-xs text-muted-foreground">
            {hace(reporte.created_at)}
          </span>
        </div>

        {decisiva && !primero && (
          <p
            className={cn(
              "mt-1 text-sm",
              dudoso ? "text-atencion" : "text-muted-foreground",
            )}
          >
            {decisiva.reason}
          </p>
        )}

        {reporte.caption && (
          <p className="mt-2.5 border-l-2 pl-3 text-sm italic">{reporte.caption}</p>
        )}

        {reporte.classification?.corrected && (
          <p className="mt-2 text-xs text-muted-foreground">
            La persona corrigió la categoría que propuso el modelo.
          </p>
        )}

        <Senales decisiva={decisiva} />

        {puedeSeparar && (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="outline" size="sm" disabled={separando} className="mt-3">
                <Link2Off className="size-3.5" />
                {separando ? "Separando…" : "No es el mismo problema"}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>¿Separar este reporte del caso?</AlertDialogTitle>
                <AlertDialogDescription>
                  Va a quedar en un caso propio. Se puede volver a agrupar después, y queda
                  constancia de quién lo separó.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Mejor no</AlertDialogCancel>
                <AlertDialogAction onClick={onSeparar}>Separar</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
      </div>
    </motion.li>
  );
}

/**
 * Las señales que **el titulo no dice ya**.
 *
 * La distancia no entra aqui: la lleva el titulo de la fila ("A 11 m"), y
 * repetirla debajo le hace pensar a quien lee que son dos datos distintos. Una
 * interfaz que dice lo mismo dos veces enseña a dejar de leerla.
 *
 * Lo que queda va por separado y en su unidad, no combinado en un puntaje: con
 * "texto 60% parecido" y "misma imagen" delante, un operador puede estar de
 * acuerdo o no, que es lo que hace el sistema verificable.
 */
function Senales({ decisiva }: { decisiva: Reporte["evidence"][number] | undefined }) {
  if (!decisiva) return null;

  const partes: { icono: React.ComponentType<{ className?: string }>; texto: string }[] = [];
  if (decisiva.text_similarity !== null && decisiva.text_similarity >= 0.3) {
    partes.push({
      icono: Text,
      texto: `texto ${Math.round(decisiva.text_similarity * 100)}% parecido`,
    });
  }
  if (decisiva.visual_distance !== null && decisiva.visual_distance <= 6) {
    partes.push({ icono: Images, texto: "misma imagen" });
  }
  if (partes.length === 0) return null;

  return (
    <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5">
      {partes.map(({ icono: Icono, texto }) => (
        <span
          key={texto}
          className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"
        >
          <Icono className="size-3" />
          {texto}
        </span>
      ))}
    </div>
  );
}
