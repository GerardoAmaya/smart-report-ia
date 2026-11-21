"use client";

/**
 * La cola de casos: la superficie de trabajo.
 *
 * El orden no es por fecha sino por lo que hay que atender antes —lo grave y lo
 * mas reportado—. Alguien la mira ocho horas, asi que la densidad importa mas
 * que el aire: caben mas casos sin hacer scroll.
 *
 * El movimiento es el que **muestra un cambio**: un caso que entra a la cola
 * aparece deslizandose, porque eso es informacion. Nada aparece con
 * desvanecido al hacer scroll.
 */
import { useInfiniteQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { ImageOff, LoaderCircle, MapPin } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ScrollArea } from "@/components/ui/scroll-area";
import { type Caso } from "@/lib/api";
import { casosCargados, opcionesCola } from "@/lib/cola";
import { cn } from "@/lib/utils";
import { categoria, hace } from "@/lib/textos";
import { CargandoCola, Fallo, Vacio } from "./Estados";
import { Cuantos, Dudoso, Severidad } from "./Marcas";

const FILTROS = [
  { valor: "", etiqueta: "Todo" },
  { valor: "open", etiqueta: "Sin atender" },
  { valor: "assigned", etiqueta: "Asignados" },
  { valor: "closed", etiqueta: "Cerrados" },
];

export function Cola({
  seleccionado,
  onElegir,
  filtro,
  onFiltrar,
}: {
  seleccionado: string | null;
  onElegir: (id: string) => void;
  filtro: string;
  onFiltrar: (f: string) => void;
}) {
  // Por paginas: con mas de 50 casos, los ultimos —nuevos, leves y de un
  // reporte— no se veian nunca. Sin sondeo: el flujo en vivo invalida
  // ["casos"] y se vuelven a pedir las paginas ya cargadas, en su sitio.
  const { data: paginas, isLoading, error, refetch, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useInfiniteQuery(opcionesCola(filtro));
  const casos = paginas ? casosCargados(paginas.pages) : undefined;
  const total = paginas?.pages[0]?.total;

  // Otro filtro es otra lista: empieza arriba. Si no, se quedaba a la altura de
  // la anterior, a media lista o mas abajo del final de una mas corta.
  const centinelaFiltro = useRef<HTMLDivElement>(null);
  useEffect(() => {
    centinelaFiltro.current
      ?.closest<HTMLElement>("[data-radix-scroll-area-viewport]")
      ?.scrollTo({ top: 0 });
  }, [filtro]);

  // Pide la siguiente pagina cuando el final de la lista se acerca. Con margen
  // por debajo, para que al bajar ya este cargando y no se note la espera.
  const centinela = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = centinela.current;
    if (!el || !hasNextPage) return;
    const raiz = el.closest<HTMLElement>("[data-radix-scroll-area-viewport]");
    const observador = new IntersectionObserver(
      (entradas) => {
        if (entradas[0]?.isIntersecting && !isFetchingNextPage) fetchNextPage();
      },
      { root: raiz, rootMargin: "0px 0px 400px 0px" },
    );
    observador.observe(el);
    return () => observador.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  // Los casos que entraron mientras se miraba la cola, para iluminarlos. En la
  // primera carga no se marca nada: todo seria "nuevo" y el resplandor dejaria
  // de significar algo. Cambiar de filtro tampoco cuenta como llegada.
  const conocidos = useRef<{ filtro: string; ids: Set<string> } | null>(null);
  const [nuevos, setNuevos] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (!casos) return;
    const ids = casos.map((c) => c.id);
    const antes = conocidos.current;
    conocidos.current = { filtro, ids: new Set(ids) };
    if (!antes || antes.filtro !== filtro) return;
    const llegaron = ids.filter((id) => !antes.ids.has(id));
    if (llegaron.length === 0) return;
    setNuevos(new Set(llegaron));
    const t = setTimeout(() => setNuevos(new Set()), 2200);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- casos sale de paginas
  }, [paginas, filtro]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-1 border-b px-3 py-2.5">
        {FILTROS.map((f) => (
          <button
            key={f.valor}
            onClick={() => onFiltrar(f.valor)}
            aria-pressed={filtro === f.valor}
            className={cn(
              "relative rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
              filtro === f.valor
                ? "text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {/* El fondo se desliza entre pestañas en vez de parpadear: muestra
                de donde vino la seleccion. */}
            {filtro === f.valor && (
              <motion.span
                layoutId="filtro-activo"
                className="absolute inset-0 rounded-md bg-secondary"
                transition={{ type: "spring", stiffness: 500, damping: 40 }}
              />
            )}
            <span className="relative">{f.etiqueta}</span>
          </button>
        ))}
        {/* Cuantos hay con este filtro, no cuantos se cargaron: la lista llega
            por paginas y el numero de abajo engañaria. */}
        {total !== undefined && (
          <span
            className="ml-auto pr-1 font-mono text-xs tabular-nums text-muted-foreground"
            title={`${total} ${total === 1 ? "caso" : "casos"} con este filtro`}
          >
            {total}
          </span>
        )}
      </div>

      {/* Radix envuelve el contenido en un `display: table` que crece con el
          texto: la direccion larga se salia por el borde sin puntos
          suspensivos. Como bloque, el ancho lo pone la columna y `truncate`
          vuelve a funcionar. */}
      <ScrollArea className="min-h-0 flex-1 [&_[data-radix-scroll-area-viewport]>div]:!block">
        <div ref={centinelaFiltro} aria-hidden />
        {isLoading && <CargandoCola />}
        {error && <Fallo mensaje={(error as Error).message} reintentar={() => refetch()} />}
        {casos?.length === 0 && (
          <Vacio
            titulo={filtro ? "Nada con ese filtro" : "Todavía no hay casos"}
            detalle={
              filtro
                ? "Probá con otro filtro o mirá todo."
                : "Cuando alguien reporte por el bot, aparece acá agrupado con los que sean el mismo problema."
            }
          />
        )}

        <AnimatePresence initial={false}>
          {casos?.map((caso) => (
            <Item
              key={caso.id}
              caso={caso}
              nuevo={nuevos.has(caso.id)}
              activo={caso.id === seleccionado}
              onElegir={() => onElegir(caso.id)}
            />
          ))}
        </AnimatePresence>

        <div ref={centinela} aria-hidden className="h-px" />
        {isFetchingNextPage && (
          <p className="flex items-center justify-center gap-2 py-4 text-xs text-muted-foreground">
            <LoaderCircle className="size-3.5 animate-spin motion-reduce:animate-none" />
            Cargando más…
          </p>
        )}
        {casos && casos.length > 0 && !hasNextPage && (
          <p className="py-4 text-center text-xs text-muted-foreground">
            Son todos: {total ?? casos.length} {(total ?? casos.length) === 1 ? "caso" : "casos"}
          </p>
        )}
      </ScrollArea>
    </div>
  );
}

function Item({
  caso,
  nuevo,
  activo,
  onElegir,
}: {
  caso: Caso;
  nuevo: boolean;
  activo: boolean;
  onElegir: () => void;
}) {
  return (
    <motion.button
      layout
      // Un caso nuevo entra deslizandose: eso es un cambio y conviene verlo.
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.18, ease: "easeOut" }}
      onClick={onElegir}
      aria-current={activo ? "true" : undefined}
      className={cn(
        "group relative block w-full overflow-hidden border-b px-4 py-3 text-left transition-colors duration-200",
        activo ? "bg-card" : "hover:bg-card/70",
      )}
    >
      {/* Al pasar: una barra fina que asoma por la izquierda y la foto que se
          acerca un poco. Dice "esto se abre" sin cambiar nada de lo que se lee. */}
      {!activo && (
        <span
          aria-hidden
          className="pointer-events-none absolute inset-y-2 left-0 w-0.5 origin-center scale-y-0 rounded-full bg-primary/50 transition-transform duration-200 group-hover:scale-y-100"
        />
      )}
      {/* Resplandor de llegada: se enciende y se apaga solo, en unos dos
          segundos. Lo bastante para ver que entro, no tanto que estorbe. */}
      <AnimatePresence>
        {nuevo && (
          <motion.span
            aria-hidden
            className="pointer-events-none absolute inset-0 bg-primary/15 shadow-[inset_3px_0_0_var(--primary)]"
            initial={{ opacity: 1 }}
            animate={{ opacity: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 2, ease: "easeOut" }}
          />
        )}
      </AnimatePresence>
      {/* Barra de acento en el seleccionado: dice donde estas sin cambiar el
          color del texto, que empeoraria el contraste. */}
      {activo && (
        <motion.span
          layoutId="caso-activo"
          className="absolute inset-y-0 left-0 w-0.5 bg-primary"
          transition={{ type: "spring", stiffness: 500, damping: 40 }}
        />
      )}
      <div className="flex gap-3">
        <Miniatura url={caso.thumbnail_url ?? null} />
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <span className="truncate text-sm font-medium leading-tight">
              {categoria(caso.category)}
            </span>
            <Cuantos n={caso.report_count} />
          </div>
          {/* Donde. Es lo primero que pregunta quien despacha y hasta ahora habia
              que abrir el caso para saberlo. Se corta en una linea: son ocho horas
              mirando esta lista y una direccion larga rompe el ritmo de la cola. */}
          {caso.address && (
            <div className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
              <MapPin className="size-3 shrink-0" aria-hidden />
              {/* min-w-0: sin el, un hijo flexible no se encoge por debajo de su
                  texto, y la direccion se cortaba en el borde sin puntos. */}
              <span className="min-w-0 truncate">{caso.address}</span>
            </div>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1.5">
            <Severidad valor={caso.severity} />
            <Dudoso cuantos={caso.doubtful_count} />
            <span className="text-xs text-muted-foreground">{hace(caso.created_at)}</span>
          </div>
        </div>
      </div>
    </motion.button>
  );
}

/**
 * La foto del caso, chica.
 *
 * Un bache y una luminaria se reconocen de un vistazo, antes de leer la
 * categoria: es la forma mas rapida de recorrer la cola. Sin foto, el hueco
 * queda igual: si la columna cambiara de ancho, la lista bailaria al cargar.
 *
 * `<img>` y no next/image: el enlace es prefirmado y de vida corta, y pasarlo
 * por el optimizador lo cachearia mas alla de su caducidad.
 */
function Miniatura({ url }: { url: string | null }) {
  return (
    <div className="size-12 shrink-0 overflow-hidden rounded-md bg-muted ring-1 ring-border transition-shadow duration-200 group-hover:shadow-md">
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={url}
          alt=""
          loading="lazy"
          className="size-full object-cover transition-transform duration-300 ease-out group-hover:scale-110"
        />
      ) : (
        <div className="flex size-full items-center justify-center text-muted-foreground/60">
          <ImageOff className="size-4" aria-hidden />
        </div>
      )}
    </div>
  );
}
