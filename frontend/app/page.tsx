"use client";

/**
 * El tablero.
 *
 * Cola a la izquierda, detalle a la derecha, y el mapa como otra vista del
 * mismo panel. No en paginas separadas: quien despacha vive en la cola, y
 * mandarlo a otra pagina por cada caso le hace perder el sitio cada vez.
 *
 * En el celular no caben las dos columnas: la cola de 360 px ocupaba la
 * pantalla entera y el resto ni se veia. Ahi la cola pasa a ser un destino mas
 * de una barra inferior —al alcance del pulgar— junto a Resumen, Caso y Mapa.
 * El escritorio no cambia: todo lo de movil va detras de `lg:`.
 */
import { AnimatePresence, motion } from "motion/react";
import { useTheme } from "next-themes";
import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import { ChartNoAxesCombined, Inbox, List, Map as MapIcon, type LucideIcon } from "lucide-react";
import { Suspense, useEffect, useState } from "react";

import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useSesion } from "@/lib/sesion";
import { BotonAsistente } from "@/componentes/Asistente";
import { Buscador } from "@/componentes/Buscador";
import { CambiarTema } from "@/componentes/CambiarTema";
import { Cola } from "@/componentes/Cola";
import { Detalle } from "@/componentes/Detalle";
import { Fallo } from "@/componentes/Estados";
import { MenuUsuario } from "@/componentes/MenuUsuario";
import { EnVivo } from "@/componentes/EnVivo";

import { useTiempoReal } from "@/lib/tiempo-real";
import { cn } from "@/lib/utils";
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
    <div className="flex h-dvh flex-col">
      <div className="border-b px-5 py-3">
        <Skeleton className="h-5 w-40" />
      </div>
      <div className="flex flex-1">
        <div className="hidden w-[360px] border-r p-4 lg:block">
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
  // Con un caso en la URL se abre en el caso: un enlace compartido que llevaba
  // al resumen obligaba a buscar el caso otra vez, que es lo que evitaba.
  const [vista, setVista] = useState<Vista>(parametros.get("caso") ? "detalle" : "resumen");
  // Solo en el celular: si se ve la cola en vez del contenido. En escritorio se
  // ven las dos siempre y esto no se lee.
  const [colaMovil, setColaMovil] = useState(false);
  const enVivo = useTiempoReal();

  const elegir = (id: string) => {
    setSeleccionado(id);
    setVista("detalle");
    setColaMovil(false);
    // replaceState y no router.push: cambiar de caso no tiene por que llenar el
    // historial del navegador de pasos atras que nadie quiere deshacer.
    window.history.replaceState(null, "", `?caso=${id}`);
  };

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
    // `h-dvh` y no `h-screen`: en el celular `100vh` cuenta la barra del
    // navegador, y la barra inferior quedaba escondida debajo.
    <div className="flex h-dvh flex-col overflow-hidden">
      <header className="flex shrink-0 items-center justify-between gap-2 border-b px-3 py-2 lg:gap-4 lg:px-4">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex items-center gap-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/marca/avatar-bot.png" alt="" className="size-6 rounded-full" />
            <span className="text-sm font-semibold tracking-tight">Smart Report</span>
          </span>
          <Separator orientation="vertical" className="h-4" />
          <EnVivo estado={enVivo} />
        </div>

        <Tabs value={vista} onValueChange={(v) => setVista(v as Vista)} className="hidden lg:flex">
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

        <div className="flex shrink-0 items-center gap-1 lg:gap-2">
          <Buscador
            onElegir={elegir}
            onVista={(v) => {
              setVista(v);
              setColaMovil(false);
            }}
          />
          {/* Suelto en la barra y no en el menu: se cambia al pasar de la
              oficina a la calle, y escondido no lo encontraba nadie. */}
          <CambiarTema />
          <MenuUsuario perfil={perfil} />
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside
          className={cn(
            "w-full shrink-0 lg:block lg:w-[360px] lg:border-r",
            colaMovil ? "block" : "hidden",
          )}
        >
          <Cola
            seleccionado={seleccionado}
            onElegir={elegir}
            filtro={filtro}
            onFiltrar={setFiltro}
          />
        </aside>

        <main
          className={cn("min-w-0 flex-1 overflow-hidden lg:block", colaMovil ? "hidden" : "block")}
        >
          {/* Un fundido corto al cambiar de vista: dice que cambio el contenido
              sin hacer esperar. `wait` para que nunca convivan dos vistas, que
              con el mapa seria dos lienzos WebGL a la vez. */}
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={vista}
              className="h-full"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.16, ease: "easeOut" }}
            >
              {vista === "mapa" && (
                <Mapa
                  seleccionado={seleccionado}
                  onElegir={elegir}
                  oscuro={resolvedTheme === "dark"}
                />
              )}
              {vista === "resumen" && (
                <div className="h-full overflow-y-auto">
                  <Metricas alElegirCaso={elegir} />
                </div>
              )}
              {vista === "detalle" && (
                <div className="h-full overflow-y-auto">
                  <Detalle casoId={seleccionado} />
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>

      {/* El robot flota abajo a la derecha y abre el asistente: fuera del
          encabezado, donde un boton mas no lo encontraba nadie. */}
      <BotonAsistente alElegirCaso={elegir} enMapa={vista === "mapa" && !colaMovil} />

      <BarraMovil
        actual={colaMovil ? "cola" : vista}
        onIr={(destino) => {
          if (destino === "cola") {
            setColaMovil(true);
          } else {
            setVista(destino);
            setColaMovil(false);
          }
        }}
      />
    </div>
  );
}

type Destino = Vista | "cola";

const DESTINOS: { id: Destino; etiqueta: string; icono: LucideIcon }[] = [
  { id: "cola", etiqueta: "Cola", icono: Inbox },
  { id: "resumen", etiqueta: "Resumen", icono: ChartNoAxesCombined },
  { id: "detalle", etiqueta: "Caso", icono: List },
  { id: "mapa", etiqueta: "Mapa", icono: MapIcon },
];

/**
 * La navegacion del celular, abajo: es donde llega el pulgar con una mano.
 *
 * Con el relleno del borde inferior del telefono (`safe-area-inset-bottom`):
 * sin el, en los que no tienen boton fisico la barra queda bajo la raya de
 * gestos y el primer toque cierra la app en vez de cambiar de vista.
 */
function BarraMovil({ actual, onIr }: { actual: Destino; onIr: (d: Destino) => void }) {
  return (
    <nav
      aria-label="Secciones"
      className="grid shrink-0 grid-cols-4 border-t bg-background pb-[env(safe-area-inset-bottom)] lg:hidden"
    >
      {DESTINOS.map(({ id, etiqueta, icono: Icono }) => {
        const activo = actual === id;
        return (
          <button
            key={id}
            type="button"
            onClick={() => onIr(id)}
            aria-current={activo ? "page" : undefined}
            className={cn(
              "flex min-h-14 flex-col items-center justify-center gap-1 text-[11px] font-medium transition-colors",
              activo ? "text-primary" : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Icono className="size-5" aria-hidden />
            {etiqueta}
          </button>
        );
      })}
    </nav>
  );
}
