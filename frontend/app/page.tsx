"use client";

/**
 * El tablero.
 *
 * Cola a la izquierda, detalle a la derecha, y el mapa como otra vista del
 * mismo panel. No en paginas separadas: quien despacha vive en la cola, y
 * mandarlo a otra pagina por cada caso le hace perder el sitio cada vez.
 */
import { useTheme } from "next-themes";
import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import { ChartNoAxesCombined, List, LogOut, Map as MapIcon } from "lucide-react";
import { Suspense, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { useSesion } from "@/lib/sesion";
import { CambiarTema } from "@/componentes/CambiarTema";
import { Cola } from "@/componentes/Cola";
import { Detalle } from "@/componentes/Detalle";
import { Fallo } from "@/componentes/Estados";
import { EnVivo } from "@/componentes/EnVivo";
import { useQueryClient } from "@tanstack/react-query";

import { useTiempoReal } from "@/lib/tiempo-real";
import { Metricas } from "@/componentes/Metricas";

// El mapa solo en el navegador: MapLibre toca `window` al cargarse y romperia
// el render del servidor.
const Mapa = dynamic(() => import("@/componentes/Mapa").then((m) => m.Mapa), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full rounded-none" />,
});

type Vista = "resumen" | "detalle" | "mapa";

/**
 * `useSearchParams` obliga a un limite de Suspense para poder prerenderizar.
 *
 * Es de esos requisitos que parecen burocracia y no lo son: sin el, Next tendria
 * que renderizar la pagina sabiendo la URL, y una pagina estatica no la sabe.
 */
export default function Pagina() {
  return (
    <Suspense fallback={<Cargando />}>
      <Tablero />
    </Suspense>
  );
}

function Cargando() {
  return (
    <div className="flex h-screen flex-col">
      <div className="border-b px-5 py-3">
        <Skeleton className="h-5 w-40" />
      </div>
      <div className="flex flex-1">
        <div className="w-[360px] border-r p-4">
          <Skeleton className="h-full w-full" />
        </div>
        <div className="flex-1 p-6">
          <Skeleton className="h-full w-full" />
        </div>
      </div>
    </div>
  );
}

function Tablero() {
  const router = useRouter();
  const { resolvedTheme } = useTheme();
  const { perfil, cargando, sinSesion, error } = useSesion();
  const parametros = useSearchParams();
  // El caso abierto va en la URL.
  //
  // Asi un operador puede mandarle a otro el enlace de un caso concreto, que es
  // lo primero que alguien intenta hacer cuando encuentra algo raro. Y de paso
  // recargar no pierde donde estabas.
  const [seleccionado, setSeleccionado] = useState<string | null>(parametros.get("caso"));
  const [filtro, setFiltro] = useState("");
  const [vista, setVista] = useState<Vista>("resumen");
  const enVivo = useTiempoReal();

  const elegir = (id: string) => {
    setSeleccionado(id);
    setVista("detalle");
    // replaceState y no router.push: cambiar de caso no tiene por que llenar el
    // historial del navegador de pasos atras que nadie quiere deshacer.
    window.history.replaceState(null, "", `?caso=${id}`);
  };
  const cliente = useQueryClient();

  useEffect(() => {
    if (sinSesion) router.replace("/entrar");
  }, [sinSesion, router]);

  if (cargando) {
    return <Cargando />;
  }

  if (error) {
    return (
      <main className="flex h-screen items-center justify-center">
        <Fallo mensaje={error} />
      </main>
    );
  }
  if (!perfil) return null;

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <header className="flex shrink-0 items-center justify-between gap-4 border-b px-4 py-2.5">
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold tracking-tight">Smart Report</span>
          <Separator orientation="vertical" className="h-4" />
          <EnVivo estado={enVivo} />
        </div>

        <Tabs value={vista} onValueChange={(v) => setVista(v as Vista)}>
          <TabsList className="h-8">
            <TabsTrigger value="resumen" className="gap-1.5 text-xs">
              <ChartNoAxesCombined className="size-3.5" />
              Resumen
            </TabsTrigger>
            <TabsTrigger value="detalle" className="gap-1.5 text-xs">
              <List className="size-3.5" />
              Caso
            </TabsTrigger>
            <TabsTrigger value="mapa" className="gap-1.5 text-xs">
              <MapIcon className="size-3.5" />
              Mapa
            </TabsTrigger>
          </TabsList>
        </Tabs>

        <div className="flex items-center gap-1">
          <span className="hidden text-xs text-muted-foreground md:inline">
            {perfil.display_name ?? perfil.email}
            {perfil.role === "demo" && " · prueba"}
          </span>
          <CambiarTema />
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Salir"
                onClick={async () => {
                  await api.salir();
                  // Se limpia la cache: sin esto el perfil viejo sobrevive y
                  // la pantalla de entrada rebota al tablero.
                  cliente.clear();
                  router.push("/entrar");
                }}
              >
                <LogOut className="size-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Salir</TooltipContent>
          </Tooltip>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="w-[360px] shrink-0 border-r">
          <Cola
            seleccionado={seleccionado}
            onElegir={elegir}
            filtro={filtro}
            onFiltrar={setFiltro}
          />
        </aside>

        <main className="min-w-0 flex-1 overflow-hidden">
          {vista === "mapa" && (
            <Mapa
              seleccionado={seleccionado}
              onElegir={elegir}
              oscuro={resolvedTheme === "dark"}
            />
          )}
          {vista === "resumen" && (
            <div className="h-full overflow-y-auto">
              <Metricas />
            </div>
          )}
          {vista === "detalle" && (
            <div className="h-full overflow-y-auto">
              <Detalle casoId={seleccionado} />
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
