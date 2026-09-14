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
import { motion } from "motion/react";
import { AlertTriangle, Layers, TrendingDown } from "lucide-react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { categoria } from "@/lib/textos";
import { Fallo } from "./Estados";

const CONFIG_SERIE = {
  reportes: { label: "Reportes", color: "var(--serie-4)" },
} satisfies ChartConfig;

const CONFIG_CATEGORIAS = {
  casos: { label: "Casos", color: "var(--serie-4)" },
} satisfies ChartConfig;

export function Metricas() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["metricas"],
    queryFn: () => api.metricas(30),
  });

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
  if (error) return <Fallo mensaje={(error as Error).message} reintentar={() => refetch()} />;
  if (!data) return null;

  const proporcion = data.reportes > 0 ? data.ahorro / data.reportes : 0;

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-6">
      <div className="grid gap-4 md:grid-cols-3">
        <Hero
          reportes={data.reportes}
          casos={data.casos}
          ahorro={data.ahorro}
          proporcion={proporcion}
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
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle className="text-base">Reportes que entran</CardTitle>
            <CardDescription>Últimos {data.dias} días</CardDescription>
          </CardHeader>
          <CardContent>
            {/* Una sola serie: sin leyenda, el titulo la nombra. */}
            <ChartContainer config={CONFIG_SERIE} className="h-[200px] w-full">
              <AreaChart data={data.serie} margin={{ left: -20, right: 4, top: 4 }}>
                <defs>
                  <linearGradient id="relleno-reportes" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--serie-4)" stopOpacity={0.28} />
                    <stop offset="100%" stopColor="var(--serie-4)" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                {/* Rejilla recesiva: horizontal y nada mas. */}
                <CartesianGrid vertical={false} strokeOpacity={0.35} />
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
                <YAxis tickLine={false} axisLine={false} width={44} allowDecimals={false} />
                <ChartTooltip
                  cursor={{ strokeOpacity: 0.4 }}
                  content={
                    <ChartTooltipContent
                      labelFormatter={(v) =>
                        new Date(String(v) + "T00:00:00").toLocaleDateString("es-SV", {
                          weekday: "long",
                          day: "numeric",
                          month: "long",
                        })
                      }
                    />
                  }
                />
                <Area
                  dataKey="reportes"
                  type="monotone"
                  stroke="var(--serie-4)"
                  strokeWidth={2}
                  fill="url(#relleno-reportes)"
                />
              </AreaChart>
            </ChartContainer>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Casos por categoría</CardTitle>
            <CardDescription>Abiertos y en curso</CardDescription>
          </CardHeader>
          <CardContent>
            {data.categorias.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                Todavía no hay casos clasificados.
              </p>
            ) : (
              <ChartContainer config={CONFIG_CATEGORIAS} className="h-[200px] w-full">
                {/* Horizontal: los nombres de categoria en español no caben
                    bajo una barra vertical sin rotarlos, y el texto rotado no
                    se lee de un vistazo. */}
                <BarChart
                  data={data.categorias.map((c) => ({ ...c, nombre: categoria(c.categoria) }))}
                  layout="vertical"
                  margin={{ left: 4, right: 12 }}
                >
                  <CartesianGrid horizontal={false} strokeOpacity={0.35} />
                  <XAxis type="number" hide allowDecimals={false} />
                  <YAxis
                    dataKey="nombre"
                    type="category"
                    tickLine={false}
                    axisLine={false}
                    width={118}
                    tickMargin={4}
                  />
                  <ChartTooltip cursor={false} content={<ChartTooltipContent />} />
                  {/* Extremos redondeados de 4px anclados a la linea base. */}
                  <Bar dataKey="casos" fill="var(--serie-4)" radius={[0, 4, 4, 0]} barSize={18} />
                </BarChart>
              </ChartContainer>
            )}
          </CardContent>
        </Card>
      </div>

      <Severidades datos={data.severidades} costo={data.costo_usd} />
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
}: {
  reportes: number;
  casos: number;
  ahorro: number;
  proporcion: number;
}) {
  return (
    <Card className="md:col-span-2">
      <CardHeader className="pb-2">
        <CardDescription className="flex items-center gap-1.5">
          <Layers className="size-3.5" />
          Lo que el sistema junta
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <motion.span
            key={reportes}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="font-mono text-4xl font-semibold tabular-nums tracking-tight"
          >
            {reportes}
          </motion.span>
          <span className="text-sm text-muted-foreground">
            {reportes === 1 ? "reporte es" : "reportes son"}
          </span>
          <span className="font-mono text-4xl font-semibold tabular-nums tracking-tight text-primary">
            {casos}
          </span>
          <span className="text-sm text-muted-foreground">
            {casos === 1 ? "problema real" : "problemas reales"}
          </span>
        </div>

        {ahorro > 0 ? (
          <p className="mt-3 flex items-center gap-1.5 text-sm text-primary">
            <TrendingDown className="size-4" />
            {ahorro} {ahorro === 1 ? "reporte" : "reportes"} que no hay que atender aparte
            <span className="text-muted-foreground">
              ({Math.round(proporcion * 100)}% menos trabajo)
            </span>
          </p>
        ) : (
          <p className="mt-3 text-sm text-muted-foreground">
            Todavía no hay reportes repetidos que agrupar.
          </p>
        )}
      </CardContent>
    </Card>
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
    <Card className={alerta ? "border-atencion/35 bg-atencion/5" : undefined}>
      <CardHeader className="pb-2">
        <CardDescription className="flex items-center gap-1.5">
          <Icono className={alerta ? "size-3.5 text-atencion" : "size-3.5"} />
          {titulo}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <span
          className={
            alerta
              ? "font-mono text-4xl font-semibold tabular-nums tracking-tight text-atencion"
              : "font-mono text-4xl font-semibold tabular-nums tracking-tight"
          }
        >
          {valor}
        </span>
        <p className="mt-2 text-sm text-muted-foreground">{detalle}</p>
      </CardContent>
    </Card>
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
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Lo que está abierto</CardTitle>
        <CardDescription>
          {total === 0 ? "Nada pendiente." : `${total} ${total === 1 ? "caso" : "casos"} sin cerrar`}
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
                <span key={etiqueta} className="flex items-center gap-1.5 text-xs">
                  <span aria-hidden className={`size-2 rounded-full ${color}`} />
                  <span className="text-muted-foreground">{etiqueta}</span>
                  <span className="font-mono font-medium tabular-nums">{n}</span>
                </span>
              ))}
            </div>
          </>
        )}

        {costo > 0 && (
          <p className="mt-4 border-t pt-3 text-xs text-muted-foreground">
            Clasificar todo lo que entró costó{" "}
            <span className="font-mono tabular-nums">USD {costo.toFixed(4)}</span>
          </p>
        )}
      </CardContent>
    </Card>
  );
}
