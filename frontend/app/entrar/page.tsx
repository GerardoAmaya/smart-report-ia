"use client";

/**
 * Entrar al tablero.
 *
 * Dos mitades. La izquierda dice de que va esto —la marca y para que sirve—
 * sobre San Salvador de fondo; la derecha es para entrar. Sin cifras: hubo
 * cuatro, y se quitaron. Quien despacha cruza esta puerta todos los dias, y
 * numeros que va a ver dentro del tablero solo cargaban la entrada. Es la unica pantalla donde lo vistoso se permite: el tablero
 * lo mira alguien ocho horas y ahi manda la calma.
 *
 * Dos formas de entrar, y la diferencia se dice en voz alta: Google para quien
 * trabaja aqui, contraseña para quien viene a mirar. Esconder que el usuario de
 * prueba es limitado haria que alguien se topara con un 403 sin saber por que.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import { useTheme } from "next-themes";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Eye } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { api } from "@/lib/api";
import { CambiarTema } from "@/componentes/CambiarTema";
import { MarcaGoogle, MarcaTelegram } from "@/componentes/Marcas-svg";

// Solo en el navegador: MapLibre toca `window` al cargarse.
const MapaFondo = dynamic(() => import("@/componentes/MapaFondo").then((m) => m.MapaFondo), {
  ssr: false,
});

const SOLO_MIRA =
  "Solo mira: la cola, los casos, el mapa y las métricas. Despachar es para operadores, porque los casos son reales.";
const DESPACHA = "Puede asignar, agrupar, separar y cerrar. No puede borrar.";

export default function Entrar() {
  const router = useRouter();
  const cliente = useQueryClient();
  const { resolvedTheme } = useTheme();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  // Si no llega, la entrada funciona igual y el invitado se describe como lo
  // que es en produccion: alguien que solo mira.
  const { data: config } = useQuery({
    queryKey: ["config-publica"],
    queryFn: api.configPublica,
    retry: false,
    staleTime: 60_000,
  });

  async function entrarDePrueba(e: React.FormEvent) {
    e.preventDefault();
    setEnviando(true);
    setError(null);
    try {
      const perfil = await api.entrarDePrueba(password);
      // Se siembra el perfil en la cache antes de navegar.
      //
      // Sin esto el tablero rebota de vuelta aqui: la consulta "yo" quedo en
      // estado de error del intento anterior —y no se reintenta a proposito,
      // porque sin sesion no va a mejorar sola—, asi que al llegar al tablero
      // seguia creyendo que no hay sesion. Con una recarga a mano funcionaba;
      // navegando, no. Lo encontro una prueba extremo a extremo.
      cliente.setQueryData(["yo"], perfil);
      router.push("/");
    } catch {
      setError("Esa contraseña no es. Revisala y probá de nuevo.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="grid min-h-screen lg:grid-cols-[1.15fr_1fr]">
      {/* --- La marca --- */}
      <section className="relative flex flex-col justify-between gap-10 overflow-hidden border-b px-6 py-8 lg:border-r lg:border-b-0 lg:px-14 lg:py-12">
        <div className="hidden lg:block">
          <MapaFondo oscuro={resolvedTheme === "dark"} />
          {/* Velo con la superficie: el mapa se intuye, el texto se lee. Casi
              opaco a la izquierda, donde esta todo lo que hay que leer, y abierto
              hacia la derecha: con un velo parejo los nombres de las colonias se
              mezclaban con el texto. */}
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-background from-35% via-background/90 via-60% to-background/35" />
        </div>

        <div className="relative flex items-center gap-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/marca/avatar-bot.png" alt="" className="size-10 rounded-full shadow-sm" />
          <div className="leading-tight">
            <p className="font-semibold tracking-tight">Smart Report</p>
            <p className="text-xs text-muted-foreground">Vía pública · El Salvador</p>
          </div>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, ease: "easeOut" }}
          className="relative max-w-xl"
        >
          <h1 className="text-3xl leading-[1.05] font-semibold tracking-tight text-balance lg:text-5xl">
            Lo que ves en la calle, <span className="text-primary">atendido.</span>
          </h1>
          <LineaPintada className="mt-6" />
          <p className="mt-6 max-w-md text-pretty text-muted-foreground lg:text-lg">
            Una foto por Telegram. Quienes reportan lo mismo quedan en un solo caso, y cuando se
            arregla, a todos les llega la foto del arreglo.
          </p>
        </motion.div>

        <div className="relative space-y-6">
          <a
            href="https://t.me/smartreport_sv_bot"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <MarcaTelegram className="size-4" />
            Reportar un problema: <span className="font-medium">@smartreport_sv_bot</span>
          </a>
        </div>
      </section>

      {/* --- Entrar --- */}
      <section className="relative flex items-center justify-center px-6 py-12 lg:px-12">
        {/* Fijo arriba en el telefono: apilado, el borde de esta seccion cae a
            media pagina y el boton quedaba flotando en medio de la nada. */}
        <div className="fixed top-3 right-3 z-10 lg:absolute lg:top-4 lg:right-4">
          <CambiarTema />
        </div>

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: "easeOut", delay: 0.05 }}
          className="w-full max-w-sm space-y-8 rounded-xl border bg-card p-7 shadow-sm sm:p-8"
        >
          <div className="space-y-2">
            <h2 className="text-2xl font-semibold tracking-tight">Entrar al tablero</h2>
            <p className="text-sm text-muted-foreground">
              Para quien despacha: la cola de casos, el mapa y el cierre con evidencia.
            </p>
          </div>

          <div className="space-y-2">
            <Button asChild variant="outline" className="h-11 w-full text-sm">
              <a href={api.urlEntrarConGoogle()}>
                <MarcaGoogle className="size-4" />
                Entrar con Google
              </a>
            </Button>
            <p className="text-xs text-muted-foreground">
              Solo cuentas autorizadas. Tener cuenta de Google no da acceso.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <Separator className="flex-1" />
            <span className="text-xs tracking-wider text-muted-foreground uppercase">
              o mirar como invitado
            </span>
            <Separator className="flex-1" />
          </div>

          <form onSubmit={entrarDePrueba} className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="password">Usuario de prueba</Label>
              <p className="text-xs text-muted-foreground">
                {config?.demo_can_dispatch ? DESPACHA : SOLO_MIRA}
              </p>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                placeholder="Contraseña"
                className="h-10"
              />
            </div>
            <Button type="submit" disabled={enviando || !password} className="h-10 w-full">
              <Eye className="size-4" />
              {enviando ? "Entrando…" : "Entrar a mirar"}
            </Button>
          </form>

          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
        </motion.div>
      </section>
    </main>
  );
}

/** La linea discontinua de una via: el material del problema, como en la paleta. */
function LineaPintada({ className }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={`h-1.5 w-24 rounded-full bg-[repeating-linear-gradient(90deg,var(--atencion)_0_16px,transparent_16px_26px)] ${className ?? ""}`}
    />
  );
}


