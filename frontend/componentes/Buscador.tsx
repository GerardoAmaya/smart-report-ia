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
  Map as MapIcon,
  MapPin,
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

  // La misma clave que la cola sin filtro: comparten cache y no se pide dos veces.
  const { data } = useQuery({
    queryKey: ["casos", ""],
    queryFn: () => api.casos(),
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
        className="h-8 gap-2 text-xs text-muted-foreground max-lg:w-8 max-lg:px-0"
        aria-label="Buscar un caso"
      >
        <Search className="size-3.5" />
        <span className="hidden lg:inline">Buscar caso</span>
        <kbd className="pointer-events-none hidden rounded border bg-muted px-1.5 font-mono text-[10px] lg:inline">
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
        <Command>
          <CommandInput placeholder="Buscar por categoría, colonia o estado…" />
          <CommandList>
            <CommandEmpty>Nada coincide con eso.</CommandEmpty>

            <CommandGroup heading="Ir a">
              <CommandItem
                value="resumen métricas"
                onSelect={() => ir(() => onVista("resumen"))}
              >
                <ChartNoAxesCombined />
                Resumen
              </CommandItem>
              <CommandItem
                value="mapa"
                onSelect={() => ir(() => onVista("mapa"))}
              >
                <MapIcon />
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
                      <MapPin />
                      <div className="min-w-0 flex-1">
                        <p className="truncate">{categoria(caso.category)}</p>
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
        </Command>
      </CommandDialog>
    </>
  );
}
