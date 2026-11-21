"use client";

/**
 * Lo que el sistema **logra**, no lo que contiene.
 *
 * La cifra de arriba es la proporcion de reportes que terminan agrupados, que
 * PLAN.md llama la medida directa de cuanto trabajo ahorra el sistema:
 * cuarenta y siete reportes en un dia son dieciocho problemas. Un tablero que
 * solo lista casos no enseña eso, y es lo unico que justifica todo lo demas.
 *
 * Decisiones de color, tomadas con el validador y no a ojo:
 *
 * - **Las categorias no llevan color de identidad.** Ese grafico mide magnitud
 *   —cuantos casos— y el nombre va en el eje, asi que le corresponde una rampa
 *   de un solo tono. Ademas libera el ambar y el rojo para lo unico que
 *   significan; gastarlos en "alumbrado" y "agua" los volveria decoracion.
 * - **La rampa oscura esta escalonada aparte**, no es la clara invertida.
 * - **La severidad usa los colores de estado**, que van siempre con etiqueta y
 *   nunca solos: el color no puede ser la unica forma de leerla.
 */
import { useQuery } from "@tanstack/react-query";
import { motion, useReducedMotion, type Variants } from "motion/react";
import {
  AlertTriangle,
  ChartColumnIncreasing,
  Gauge,
  Layers,
  Shapes,
  TrendingDown,
} from "lucide-react";
import { useId } from "react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import {
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { categoria } from "@/lib/textos";
import { Contador } from "./Contador";
import { Fallo } from "./Estados";
import { Actividad } from "./Actividad";
import { Aurora, IconoVivo, TarjetaVidrio } from "./ResumenVivo";

// Las tarjetas entran una tras otra, en menos de medio segundo entre todas: se
// lee de arriba a abajo en el orden en que conviene leer. Una sola vez, al
// abrir el resumen; los cambios en vivo los cuentan los numeros, no la entrada.
const ESCALONADO: Variants = {
  visible: { transition: { staggerChildren: 0.06 } },
};
const TARJETA: Variants = {
  oculta: { opacity: 0, y: 10 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.32, ease: "easeOut" },
  },
};

// El tooltip de las graficas, de vidrio como las tarjetas.
const TOOLTIP_VIDRIO = "bg-popover/75 backdrop-blur-md border-border/60";

// Un id de React sirve para un `<linearGradient>` sin los dos puntos, que en
// `url(#...)` romperian la referencia.
const useIdSvg = () => useId().replace(/:/g, "");

const CONFIG_SERIE = {
  reportes: { label: "Reportes", color: "var(--serie-4)" },
} satisfies ChartConfig;

const CONFIG_CATEGORIAS = {
  casos: { label: "Casos", color: "var(--serie-4)" },
} satisfies ChartConfig;

export function Metricas({ alElegirCaso }: { alElegirCaso: (id: string) => void }) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["metricas"],
    queryFn: () => api.metricas(30),
  });
  const quieto = useReducedMotion();
  const idSerie = useIdSvg();
  const idCategorias = useIdSvg();

  if (isLoading) {
    return (
      <div className="grid gap-4 p-6 md:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-32" />
        ))}
        <Skeleton className="h-64 md:col-span-2" />
        <Skeleton className="h-64" />
      </div>
    );
  }
  if (error)
    return (
      <Fallo mensaje={(error as Error).message} reintentar={() => refetch()} />
    );
  if (!data) return null;

  const proporcion = data.reportes > 0 ? data.ahorro / data.reportes : 0;

  return (
    // `isolate` deja la aurora en su propia capa: las tarjetas de vidrio la
    // difuminan detras sin que se escape por encima del encabezado.
    <div className="relative isolate min-h-full">
      <Aurora />
      <motion.div
        variants={ESCALONADO}
        initial="oculta"
        animate="visible"
        className="relative z-[1] mx-auto max-w-5xl space-y-4 p-6"
      >
        <div className="grid gap-4 md:grid-cols-3">
          <Hero
            reportes={data.reportes}
            casos={data.casos}
            ahorro={data.ahorro}
            proporcion={proporcion}
            serie={data.serie.slice(-14)}
          />
          <Tarjeta
            icono={AlertTriangle}
            titulo="Esperando decisión"
            valor={data.dudosos}
            detalle={
              data.dudosos === 0
                ? "Ninguna agrupación quedó en el límite."
                : "Agrupaciones que quedaron en el límite y nadie ha revisado."
            }
            alerta={data.dudosos > 0}
          />
        </div>

        <div className="grid gap-4 lg:grid-cols-5">
          <motion.div variants={TARJETA} className="lg:col-span-3">
            <TarjetaVidrio className="h-full">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <IconoVivo
                    icono={ChartColumnIncreasing}
                    clave={data.reportes}
                    className="size-4 text-primary"
                  />
                  Reportes que entran
                </CardTitle>
                <CardDescription>Últimos {data.dias} días</CardDescription>
              </CardHeader>
              <CardContent>
                {/* Una sola serie: sin leyenda, el titulo la nombra.
                Barras por dia y no una curva: la curva suavizada dibujaba una
                subida desde antes del primer reporte, en dias en que no entro
                nada. Una barra por dia no inventa lo que no paso. */}
                <ChartContainer
                  config={CONFIG_SERIE}
                  className="h-[200px] w-full"
                >
                  <BarChart
                    data={data.serie}
                    // Margen izquierdo casi cero: con -20 el eje se salia del cuadro y
                    // un "120" se leia "20" en cuanto un dia pasaba de 99 reportes.
                    margin={{ left: -6, right: 4, top: 4 }}
                  >
                    <defs>
                      {/* Degradado del mismo verde, mas denso arriba: da volumen
                      sin cambiar de tono, asi que la altura sigue siendo lo
                      unico que codifica la cantidad. */}
                      <linearGradient id={idSerie} x1="0" y1="0" x2="0" y2="1">
                        <stop
                          offset="0%"
                          stopColor="var(--primary)"
                          stopOpacity={1}
                        />
                        <stop
                          offset="100%"
                          stopColor="var(--primary)"
                          stopOpacity={0.35}
                        />
                      </linearGradient>
                    </defs>
                    {/* Rejilla recesiva: horizontal y nada mas. */}
                    <CartesianGrid vertical={false} strokeOpacity={0.2} />
                    <XAxis
                      dataKey="dia"
                      tickLine={false}
                      axisLine={false}
                      tickMargin={8}
                      minTickGap={28}
                      tickFormatter={(v: string) =>
                        new Date(v + "T00:00:00").toLocaleDateString("es-SV", {
                          day: "numeric",
                          month: "short",
                        })
                      }
                    />
                    <YAxis
                      tickLine={false}
                      axisLine={false}
                      width={44}
                      allowDecimals={false}
                    />
                    <ChartTooltip
                      cursor={{ fill: "var(--muted)", opacity: 0.6 }}
                      content={
                        <ChartTooltipContent
                          className={TOOLTIP_VIDRIO}
                          labelFormatter={(v) =>
                            new Date(
                              String(v) + "T00:00:00",
                            ).toLocaleDateString("es-SV", {
                              weekday: "long",
                              day: "numeric",
                              month: "long",
                            })
                          }
                        />
                      }
                    />
                    <Bar
                      dataKey="reportes"
                      fill={`url(#${idSerie})`}
                      radius={[3, 3, 0, 0]}
                      maxBarSize={18}
                      isAnimationActive={!quieto}
                      animationDuration={700}
                    />
                  </BarChart>
                </ChartContainer>
              </CardContent>
            </TarjetaVidrio>
          </motion.div>

          <motion.div variants={TARJETA} className="lg:col-span-2">
            <TarjetaVidrio className="h-full">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <IconoVivo
                    icono={Shapes}
                    clave={data.categorias.length}
                    className="size-4 text-primary"
                  />
                  Casos por categoría
                </CardTitle>
                <CardDescription>Abiertos y en curso</CardDescription>
              </CardHeader>
              <CardContent>
                {data.categorias.length === 0 ? (
                  <p className="py-8 text-center text-sm text-muted-foreground">
                    Todavía no hay casos clasificados.
                  </p>
                ) : (
                  <ChartContainer
                    config={CONFIG_CATEGORIAS}
                    className="h-[200px] w-full"
                  >
                    {/* Horizontal: los nombres de categoria en español no caben
                    bajo una barra vertical sin rotarlos, y el texto rotado no
                    se lee de un vistazo. */}
                    <BarChart
                      data={data.categorias.map((c) => ({
                        ...c,
                        nombre: categoria(c.categoria),
                      }))}
                      layout="vertical"
                      margin={{ left: 4, right: 12 }}
                    >
                      <defs>
                        <linearGradient
                          id={idCategorias}
                          x1="0"
                          y1="0"
                          x2="1"
                          y2="0"
                        >
                          <stop
                            offset="0%"
                            stopColor="var(--primary)"
                            stopOpacity={0.45}
                          />
                          <stop
                            offset="100%"
                            stopColor="var(--primary)"
                            stopOpacity={1}
                          />
                        </linearGradient>
                      </defs>
                      <CartesianGrid horizontal={false} strokeOpacity={0.2} />
                      <XAxis type="number" hide allowDecimals={false} />
                      <YAxis
                        dataKey="nombre"
                        type="category"
                        tickLine={false}
                        axisLine={false}
                        width={118}
                        tickMargin={4}
                      />
                      <ChartTooltip
                        cursor={false}
                        content={
                          <ChartTooltipContent className={TOOLTIP_VIDRIO} />
                        }
                      />
                      {/* Extremos redondeados de 4px anclados a la linea base. */}
                      <Bar
                        dataKey="casos"
                        fill={`url(#${idCategorias})`}
                        radius={[0, 4, 4, 0]}
                        barSize={18}
                        isAnimationActive={!quieto}
                        animationDuration={700}
                      />
                    </BarChart>
                  </ChartContainer>
                )}
              </CardContent>
            </TarjetaVidrio>
          </motion.div>
        </div>

        <div className="grid gap-4 lg:grid-cols-5">
          <motion.div variants={TARJETA} className="lg:col-span-3">
            <Severidades datos={data.severidades} costo={data.costo_usd} />
          </motion.div>
          {/* Lo que va pasando, con datos reales: es lo que hace sentir que el
              sistema respira aunque nadie este mirando la cola. */}
          <motion.div variants={TARJETA} className="lg:col-span-2">
            <TarjetaVidrio className="h-full">
              <Actividad alElegirCaso={alElegirCaso} className="h-full" />
            </TarjetaVidrio>
          </motion.div>
        </div>
      </motion.div>
    </div>
  );
}

/**
 * La cifra que justifica el sistema.
 *
 * Un numero grande y no un grafico: es un dato solo, y dibujarlo seria adorno.
 */
function Hero({
  reportes,
  casos,
  ahorro,
  proporcion,
  serie,
}: {
  reportes: number;
  casos: number;
  ahorro: number;
  proporcion: number;
  serie: { dia: string; reportes: number }[];
}) {
  return (
    <motion.div variants={TARJETA} className="md:col-span-2">
      <TarjetaVidrio brillo="marca" className="h-full">
        <CardHeader className="pb-2">
          <CardDescription className="flex items-center gap-1.5">
            <IconoVivo
              icono={Layers}
              clave={reportes}
              className="size-3.5 text-primary"
            />
            Lo que el sistema junta
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <Contador
              valor={reportes}
              cifra="reportes"
              className="font-mono text-4xl font-semibold tabular-nums tracking-tight"
            />
            <span className="text-sm text-muted-foreground">
              {reportes === 1 ? "reporte es" : "reportes son"}
            </span>
            <Contador
              valor={casos}
              className="font-mono text-4xl font-semibold tabular-nums tracking-tight text-primary"
            />
            <span className="text-sm text-muted-foreground">
              {casos === 1 ? "problema real" : "problemas reales"}
            </span>
          </div>

          {ahorro > 0 ? (
            <p className="mt-3 flex items-center gap-1.5 text-sm text-primary">
              <TrendingDown className="size-4" />
              {ahorro} {ahorro === 1 ? "reporte" : "reportes"} que no hay que
              atender aparte
              <span className="text-muted-foreground">
                ({Math.round(proporcion * 100)}% menos trabajo)
              </span>
            </p>
          ) : (
            <p className="mt-3 text-sm text-muted-foreground">
              Todavía no hay reportes repetidos que agrupar.
            </p>
          )}

          <Pulso serie={serie} />
        </CardContent>
      </TarjetaVidrio>
    </motion.div>
  );
}

/**
 * Los ultimos catorce dias, en chico, junto a la cifra.
 *
 * Barras y no una linea, por lo mismo que la grafica grande: una linea
 * suavizada dibuja subidas en dias en que no entro nada. Sin ejes: es el ritmo,
 * no el dato; el dato esta en la grafica de abajo.
 */
function Pulso({ serie }: { serie: { dia: string; reportes: number }[] }) {
  const quieto = useReducedMotion();
  const maximo = Math.max(1, ...serie.map((d) => d.reportes));
  if (serie.every((d) => d.reportes === 0)) return null;
  return (
    <div className="mt-4 border-t pt-3">
      <div className="flex h-8 items-end gap-[3px]" aria-hidden>
        {serie.map((d, i) => (
          <motion.span
            key={d.dia}
            className={
              d.reportes > 0
                ? "flex-1 rounded-[2px] bg-gradient-to-t from-primary/35 to-primary"
                : "flex-1 rounded-[2px] bg-muted"
            }
            initial={quieto ? false : { height: 0 }}
            animate={{ height: `${Math.max(8, (d.reportes / maximo) * 100)}%` }}
            transition={{
              duration: 0.4,
              delay: quieto ? 0 : 0.25 + i * 0.025,
              ease: "easeOut",
            }}
          />
        ))}
      </div>
      <p className="mt-1.5 text-xs text-muted-foreground">
        Reportes por día, últimas dos semanas
      </p>
    </div>
  );
}

function Tarjeta({
  icono: Icono,
  titulo,
  valor,
  detalle,
  alerta,
}: {
  icono: React.ComponentType<{ className?: string }>;
  titulo: string;
  valor: number;
  detalle: string;
  alerta?: boolean;
}) {
  return (
    <motion.div variants={TARJETA}>
      <TarjetaVidrio
        brillo={alerta ? "atencion" : undefined}
        className={
          alerta
            ? "h-full bg-atencion/[0.07] dark:bg-atencion/[0.08]"
            : "h-full"
        }
      >
        <CardHeader className="pb-2">
          <CardDescription className="flex items-center gap-1.5">
            <IconoVivo
              icono={Icono}
              clave={valor}
              className={alerta ? "size-3.5 text-atencion" : "size-3.5"}
            />
            {titulo}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Contador
            valor={valor}
            className={
              alerta
                ? "font-mono text-4xl font-semibold tabular-nums tracking-tight text-atencion"
                : "font-mono text-4xl font-semibold tabular-nums tracking-tight"
            }
          />
          <p className="mt-2 text-sm text-muted-foreground">{detalle}</p>
        </CardContent>
      </TarjetaVidrio>
    </motion.div>
  );
}

/**
 * Severidad de lo que esta abierto.
 *
 * Barra apilada y no un donut: comparar angulos es mas dificil que comparar
 * longitudes, y aqui lo que importa es cuanto de lo abierto es urgente.
 * **Cada tramo lleva etiqueta**: el color no puede ser la unica forma de leerlo.
 */
function Severidades({
  datos,
  costo,
}: {
  datos: { alta: number; media: number; baja: number };
  costo: number;
}) {
  const total = datos.alta + datos.media + datos.baja;

  return (
    <TarjetaVidrio className="h-full">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <IconoVivo
            icono={Gauge}
            clave={total}
            className="size-4 text-primary"
          />
          Lo que está abierto
        </CardTitle>
        <CardDescription>
          {total === 0
            ? "Nada pendiente."
            : `${total} ${total === 1 ? "caso" : "casos"} sin cerrar`}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {total > 0 && (
          <>
            {/* Separacion de 2px entre tramos: sin ella dos colores contiguos
                se leen como uno solo. */}
            <div className="flex h-2.5 gap-0.5 overflow-hidden rounded-full">
              {(
                [
                  ["alta", datos.alta, "bg-urgente"],
                  ["media", datos.media, "bg-atencion"],
                  ["baja", datos.baja, "bg-resuelto"],
                ] as const
              ).map(([clave, n, color]) =>
                n > 0 ? (
                  <motion.div
                    key={clave}
                    initial={{ width: 0 }}
                    animate={{ width: `${(n / total) * 100}%` }}
                    transition={{ duration: 0.4, ease: "easeOut" }}
                    className={color}
                  />
                ) : null,
              )}
            </div>
            <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5">
              {(
                [
                  ["Urgentes", datos.alta, "bg-urgente"],
                  ["Atender", datos.media, "bg-atencion"],
                  ["Sin urgencia", datos.baja, "bg-resuelto"],
                ] as const
              ).map(([etiqueta, n, color]) => (
                <span
                  key={etiqueta}
                  className="flex items-center gap-1.5 text-xs"
                >
                  <span
                    aria-hidden
                    className={`size-2 rounded-full ${color}`}
                  />
                  <span className="text-muted-foreground">{etiqueta}</span>
                  <span className="font-mono font-medium tabular-nums">
                    {n}
                  </span>
                </span>
              ))}
            </div>
          </>
        )}

        {costo > 0 && (
          <p className="mt-4 border-t pt-3 text-xs text-muted-foreground">
            Clasificar todo lo que entró costó{" "}
            <span className="font-mono tabular-nums">
              USD {costo.toFixed(4)}
            </span>
          </p>
        )}
      </CardContent>
    </TarjetaVidrio>
  );
}
