"use client";

/**
 * Saltar a un caso escribiendo, con Ctrl+K o Cmd+K.
 *
 * Quien despacha suele saber **donde** esta lo que busca —«el de la colonia
 * Escalon»— y no en que lugar de la cola quedo. Recorrer la lista con la vista
 * es lento; escribir dos palabras, no.
 *
 * Busca sobre lo que la cola ya cargo: ninguna peticion nueva por tecla.
 */
import { useQuery } from "@tanstack/react-query";
import {
  ChartNoAxesCombined,
  CornerDownLeft,
  ImageOff,
  Map as MapIcon,
  Search,
} from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from "@/components/ui/command";
import { api } from "@/lib/api";
import { categoria, estado, hace } from "@/lib/textos";

export function Buscador({
  onElegir,
  onVista,
}: {
  onElegir: (id: string) => void;
  onVista: (vista: "resumen" | "mapa") => void;
}) {
  const [abierto, setAbierto] = useState(false);

  // Busca en los primeros 200 de la cola (el maximo de una pagina), no solo en
  // los que la cola ya cargo: buscar es justo para encontrar lo que no se ve.
  // Clave propia: la cola es paginada y guarda otra forma de dato. Empieza por
  // "casos", asi que el tablero en vivo la refresca igual.
  const { data } = useQuery({
    queryKey: ["casos", "buscador"],
    queryFn: () => api.casos(undefined, { limite: 200 }),
    enabled: abierto,
  });

  useEffect(() => {
    const alPulsar = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setAbierto((a) => !a);
      }
    };
    window.addEventListener("keydown", alPulsar);
    return () => window.removeEventListener("keydown", alPulsar);
  }, []);

  const ir = (accion: () => void) => {
    setAbierto(false);
    accion();
  };

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        onClick={() => setAbierto(true)}
        className="h-8 gap-2 rounded-full bg-card/70 text-xs text-muted-foreground shadow-xs backdrop-blur max-lg:w-8 max-lg:px-0 lg:pr-1.5 lg:pl-3"
        aria-label="Buscar un caso"
      >
        <Search className="size-3.5" />
        <span className="hidden lg:inline">Buscar caso</span>
        <kbd className="pointer-events-none hidden items-center gap-0.5 rounded-full border bg-muted px-2 py-0.5 font-mono text-[10px] lg:inline-flex">
          Ctrl K
        </kbd>
      </Button>

      <CommandDialog
        open={abierto}
        onOpenChange={setAbierto}
        title="Buscar un caso"
        description="Escribe la categoría, la colonia o el estado del caso."
      >
        {/* <Command> explicito: en esta version de shadcn el dialogo ya no lo
            pone, y sin el los items de cmdk no encuentran su estado y la pagina
            entera revienta al abrir el buscador. */}
        <Command className="[&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:tracking-[0.12em] [&_[cmdk-group-heading]]:uppercase">
          <CommandInput placeholder="Buscar por categoría, colonia o estado…" />
          <CommandList>
            <CommandEmpty>Nada coincide con eso.</CommandEmpty>

            <CommandGroup heading="Ir a">
              <CommandItem
                value="resumen métricas"
                onSelect={() => ir(() => onVista("resumen"))}
              >
                <IconoEnCaja>
                  <ChartNoAxesCombined />
                </IconoEnCaja>
                Resumen
              </CommandItem>
              <CommandItem
                value="mapa"
                onSelect={() => ir(() => onVista("mapa"))}
              >
                <IconoEnCaja>
                  <MapIcon />
                </IconoEnCaja>
                Mapa
              </CommandItem>
            </CommandGroup>

            {data && data.cases.length > 0 && (
              <>
                <CommandSeparator />
                <CommandGroup heading="Casos">
                  {data.cases.map((caso) => (
                    <CommandItem
                      key={caso.id}
                      // Lo que se escribe se busca aqui: categoria, direccion y
                      // estado en palabras, no los codigos internos.
                      value={`${categoria(caso.category)} ${caso.address ?? ""} ${estado(caso.status)} ${caso.id}`}
                      onSelect={() => ir(() => onElegir(caso.id))}
                    >
                      <MiniaturaBusqueda url={caso.thumbnail_url ?? null} />
                      <div className="min-w-0 flex-1">
                        <p className="flex items-center gap-1.5 truncate">
                          {caso.severity === "alta" && (
                            <span
                              aria-label="Urgente"
                              className="size-1.5 shrink-0 rounded-full bg-urgente"
                            />
                          )}
                          {categoria(caso.category)}
                        </p>
                        <p className="truncate text-xs text-muted-foreground">
                          {caso.address ?? "Sin dirección"}
                        </p>
                      </div>
                      <CommandShortcut className="tracking-normal">
                        {estado(caso.status)} · {hace(caso.created_at)}
                      </CommandShortcut>
                    </CommandItem>
                  ))}
                </CommandGroup>
              </>
            )}
          </CommandList>
          {/* Los atajos, dichos: quien abre esto con el teclado quiere seguir
              con el teclado, y no tiene por que adivinar como. */}
          <div className="flex items-center gap-4 border-t px-3 py-2 text-[11px] text-muted-foreground">
            <span className="flex items-center gap-1">
              <Tecla>↑</Tecla>
              <Tecla>↓</Tecla>
              moverse
            </span>
            <span className="flex items-center gap-1">
              <Tecla>
                <CornerDownLeft className="size-2.5" />
              </Tecla>
              abrir
            </span>
            <span className="flex items-center gap-1">
              <Tecla>Esc</Tecla>
              cerrar
            </span>
          </div>
        </Command>
      </CommandDialog>
    </>
  );
}

function Tecla({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex h-5 min-w-5 items-center justify-center rounded border bg-muted px-1 font-mono text-[10px]">
      {children}
    </kbd>
  );
}

function IconoEnCaja({ children }: { children: React.ReactNode }) {
  return (
    <span className="flex size-7 items-center justify-center rounded-md border bg-card text-primary [&_svg]:size-3.5">
      {children}
    </span>
  );
}

/** La foto del caso tambien aqui: un bache se reconoce antes que su direccion. */
function MiniaturaBusqueda({ url }: { url: string | null }) {
  return (
    <span className="flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-md bg-muted ring-1 ring-border">
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt="" className="size-full object-cover" />
      ) : (
        <ImageOff className="size-3.5 text-muted-foreground/60" aria-hidden />
      )}
    </span>
  );
}
