"use client";

/**
 * «Pregúntale al tablero»: un panel lateral donde quien despacha pregunta en
 * lenguaje normal y el modelo contesta con datos reales y enlaces a los casos.
 *
 * **Solo mira.** No hay nada aquí que asigne, cierre o junte: si alguien se lo
 * pide, el asistente explica que eso se hace en el panel del caso. Es el mismo
 * principio de todo el sistema —el modelo propone y lee, las personas deciden—.
 *
 * La conversación vive en el navegador y se manda entera en cada pregunta: no
 * se guarda en ningún lado, y cerrar el panel no la pierde, recargar sí.
 */
import { useMutation } from "@tanstack/react-query";
import {
  ClipboardList,
  LoaderCircle,
  RotateCcw,
  SendHorizontal,
  Sparkles,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, SinSesion } from "@/lib/api";
import { apiAsistente, type MensajeChat } from "@/lib/api-asistente";
import { cn } from "@/lib/utils";

const SUGERENCIAS = [
  "¿Qué quedó pendiente hoy?",
  "Resumen de la semana",
  "¿Qué cuadrilla tiene más casos?",
  "¿Hay casos urgentes sin cuadrilla?",
];

const RESUMEN_DEL_TURNO =
  "Hazme el resumen del turno de hoy: lo que entró, lo urgente que sigue abierto, " +
  "lo que se cerró y los dudosos que esperan decisión.";

// El servidor acepta 30 mensajes; se mandan los últimos 20 empezando por una
// pregunta, para que una charla larga no se vuelva cara ni se rechace.
const HISTORIAL = 20;

function recortar(mensajes: MensajeChat[]): MensajeChat[] {
  const ultimos = mensajes.slice(-HISTORIAL);
  const inicio = ultimos.findIndex((m) => m.role === "user");
  return inicio <= 0 ? ultimos : ultimos.slice(inicio);
}

function mensajeDeError(error: unknown): string {
  if (error instanceof SinSesion) return "Tu sesión terminó. Vuelve a entrar.";
  if (error instanceof ApiError) return error.message;
  return "Algo falló al preguntar. Prueba de nuevo.";
}

export function BotonAsistente({
  alElegirCaso,
  className,
}: {
  /** Abre un caso sin recargar. Sin él, el enlace navega a `/?caso=…`. */
  alElegirCaso?: (id: string) => void;
  className?: string;
}) {
  const [abierto, setAbierto] = useState(false);
  const [mensajes, setMensajes] = useState<MensajeChat[]>([]);
  const [borrador, setBorrador] = useState("");
  const [restantes, setRestantes] = useState<number | null>(null);
  const final = useRef<HTMLDivElement>(null);
  const router = useRouter();

  const preguntar = useMutation({
    mutationFn: (historial: MensajeChat[]) => apiAsistente.preguntar(recortar(historial)),
    onSuccess: (r) => {
      setMensajes((m) => [...m, { role: "assistant", content: r.answer }]);
      setRestantes(r.remaining_today);
    },
    onError: (_error, historial) => {
      // La pregunta que fallo se saca del historial: si quedara, la siguiente
      // tendria dos preguntas seguidas y el servidor la rechazaria.
      setMensajes(historial.slice(0, -1));
    },
  });

  useEffect(() => {
    final.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [mensajes, preguntar.isPending]);

  const enviar = (texto: string) => {
    const limpio = texto.trim();
    if (!limpio || preguntar.isPending) return;
    const historial: MensajeChat[] = [...mensajes, { role: "user", content: limpio }];
    setMensajes(historial);
    setBorrador("");
    preguntar.mutate(historial);
  };

  const elegirCaso = (id: string) => {
    if (alElegirCaso) {
      alElegirCaso(id);
      setAbierto(false);
    } else {
      setAbierto(false);
      router.push(`/?caso=${id}`);
    }
  };

  return (
    <Sheet open={abierto} onOpenChange={setAbierto}>
      <SheetTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          aria-label="Asistente"
          className={cn("gap-1.5 max-lg:size-8 max-lg:px-0", className)}
        >
          <Sparkles className="size-3.5 max-lg:size-4" />
          {/* En el celular, solo el icono: el texto no cabe junto al resto. */}
          <span className="hidden lg:inline">Asistente</span>
        </Button>
      </SheetTrigger>
      <SheetContent
        side="right"
        // Con el prefijo data-[side=right]: el Sheet trae w-3/4 y sm:max-w-sm con
        // ese prefijo, que le ganan a un w-full sin el, y en el celular el panel
        // ocupaba tres cuartos de pantalla.
        className="gap-0 p-0 data-[side=right]:w-full data-[side=right]:sm:max-w-md"
      >
        <SheetHeader className="border-b px-5 py-4">
          <SheetTitle className="flex items-center gap-2">
            <Sparkles className="size-4 text-primary" />
            Pregúntale al tablero
          </SheetTitle>
          <SheetDescription>
            Contesta con los datos del sistema y enlaza los casos. Solo mira: asignar y cerrar
            se hace en el panel de cada caso.
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {mensajes.length === 0 && (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">Prueba con algo como:</p>
              <div className="flex flex-wrap gap-2">
                {SUGERENCIAS.map((s) => (
                  <Button
                    key={s}
                    variant="outline"
                    size="sm"
                    className="h-auto py-1.5 text-left whitespace-normal"
                    onClick={() => enviar(s)}
                  >
                    {s}
                  </Button>
                ))}
              </div>
            </div>
          )}

          {mensajes.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="flex justify-end">
                <p className="max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-3.5 py-2 text-sm text-primary-foreground">
                  {m.content}
                </p>
              </div>
            ) : (
              <div key={i} className="max-w-[95%] text-sm leading-relaxed">
                <Formato texto={m.content} alElegirCaso={elegirCaso} />
              </div>
            ),
          )}

          {preguntar.isPending && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <LoaderCircle className="size-3.5 animate-spin" />
              Consultando el tablero…
            </p>
          )}

          {preguntar.isError && (
            <p
              role="alert"
              className={cn(
                "rounded-lg border px-3 py-2 text-sm",
                preguntar.error instanceof ApiError && preguntar.error.status === 429
                  ? "border-atencion/40 bg-atencion/5 text-atencion"
                  : "border-destructive/30 bg-destructive/5 text-destructive",
              )}
            >
              {mensajeDeError(preguntar.error)}
            </p>
          )}
          <div ref={final} />
        </div>

        <div className="space-y-2 border-t px-5 py-4">
          <div className="flex items-center justify-between gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => enviar(RESUMEN_DEL_TURNO)}
              disabled={preguntar.isPending}
            >
              <ClipboardList className="size-3.5" />
              Resumen del turno
            </Button>
            <div className="flex items-center gap-2">
              {restantes !== null && (
                <span className="text-xs text-muted-foreground">
                  {restantes === 1 ? "Queda 1 consulta hoy" : `Quedan ${restantes} consultas hoy`}
                </span>
              )}
              {mensajes.length > 0 && (
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Empezar de nuevo"
                  title="Empezar de nuevo"
                  onClick={() => {
                    setMensajes([]);
                    preguntar.reset();
                  }}
                  disabled={preguntar.isPending}
                >
                  <RotateCcw className="size-3.5" />
                </Button>
              )}
            </div>
          </div>
          <form
            className="flex items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              enviar(borrador);
            }}
          >
            <Textarea
              value={borrador}
              onChange={(e) => setBorrador(e.target.value)}
              onKeyDown={(e) => {
                // Enter manda, Mayúsculas+Enter baja de línea: lo que se espera
                // de cualquier chat.
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  enviar(borrador);
                }
              }}
              placeholder="Pregunta sobre los casos…"
              rows={2}
              maxLength={2000}
              className="min-h-0 resize-none"
              aria-label="Pregunta para el asistente"
            />
            <Button
              type="submit"
              size="icon"
              aria-label="Preguntar"
              disabled={preguntar.isPending || !borrador.trim()}
            >
              <SendHorizontal className="size-4" />
            </Button>
          </form>
        </div>
      </SheetContent>
    </Sheet>
  );
}

// --- Formato de la respuesta ---
//
// Un Markdown mínimo y a propósito: párrafos, listas, negritas y enlaces. Y de
// enlaces, **solo los que abren un caso**. Lo que escribe el modelo puede venir
// influido por textos de quien reporta; un enlace a cualquier sitio sería una
// puerta para mandar al operador fuera del tablero.

const ENLACE_A_CASO = /^\/\?caso=([0-9a-f-]{36})$/i;
const EN_LINEA = /(\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*)/g;

function EnLinea({
  texto,
  alElegirCaso,
}: {
  texto: string;
  alElegirCaso: (id: string) => void;
}) {
  const partes = texto.split(EN_LINEA).filter(Boolean);
  return (
    <>
      {partes.map((parte, i) => {
        const enlace = parte.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
        if (enlace) {
          const caso = enlace[2].trim().match(ENLACE_A_CASO);
          if (!caso) return <Fragment key={i}>{enlace[1]}</Fragment>;
          return (
            // Un <a> y no un <button>: Chrome trata un boton como bloque aunque
            // lleve `inline`, y una direccion larga partia la linea y dejaba la
            // viñeta de la lista en el segundo renglon. Con href, ademas, el clic
            // del medio abre el caso en otra pestaña.
            <a
              key={i}
              href={`/?caso=${caso[1]}`}
              onClick={(e) => {
                if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
                e.preventDefault();
                alElegirCaso(caso[1]);
              }}
              className="font-medium text-primary underline underline-offset-2 hover:no-underline"
            >
              {enlace[1]}
            </a>
          );
        }
        const negrita = parte.match(/^\*\*([^*]+)\*\*$/);
        if (negrita) return <strong key={i}>{negrita[1]}</strong>;
        return <Fragment key={i}>{parte}</Fragment>;
      })}
    </>
  );
}

function Formato({ texto, alElegirCaso }: { texto: string; alElegirCaso: (id: string) => void }) {
  const bloques: ReactNode[] = [];
  let lista: string[] = [];
  const cerrarLista = () => {
    if (lista.length) {
      bloques.push(
        <ul key={`l${bloques.length}`} className="ml-4 list-disc space-y-1">
          {lista.map((item, i) => (
            <li key={i}>
              <EnLinea texto={item} alElegirCaso={alElegirCaso} />
            </li>
          ))}
        </ul>,
      );
      lista = [];
    }
  };
  for (const linea of texto.split("\n")) {
    const item = linea.match(/^\s*(?:[-*•]|\d+\.)\s+(.*)$/);
    if (item) {
      lista.push(item[1]);
      continue;
    }
    cerrarLista();
    const limpia = linea.replace(/^#+\s*/, "").trim();
    if (limpia) {
      bloques.push(
        <p key={`p${bloques.length}`}>
          <EnLinea texto={limpia} alElegirCaso={alElegirCaso} />
        </p>,
      );
    }
  }
  cerrarLista();
  return <div className="space-y-2">{bloques}</div>;
}
