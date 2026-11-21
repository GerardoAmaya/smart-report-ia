"use client";

/**
 * Entrar al tablero.
 *
 * Dos mitades. La izquierda dice de que va esto —la marca y para que sirve—
 * sobre San Salvador de fondo; la derecha es para entrar. Sin cifras: hubo
 * cuatro, y se quitaron. Quien despacha cruza esta puerta todos los dias, y
 * numeros que va a ver dentro del tablero solo cargaban la entrada.
 *
 * Es la unica pantalla donde lo vistoso se permite: el tablero lo mira alguien
 * ocho horas y ahi manda la calma. Las animaciones viven en EntradaAnimada.tsx,
 * con sus reglas: nada bloquea el formulario y con movimiento reducido nada se
 * mueve.
 *
 * Dos formas de entrar, y la diferencia se dice en voz alta: Google para quien
 * trabaja aqui, contraseña para quien viene a mirar. Esconder que el usuario de
 * prueba es limitado haria que alguien se topara con un 403 sin saber por que.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
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
import { api, ApiError } from "@/lib/api";
import { CambiarTema } from "@/componentes/CambiarTema";
import {
  EntraEnCascada,
  LineaPintada,
  LogoQueCae,
  PasosDeEntrada,
  PildoraDeMarca,
  PinQueLlega,
  TarjetaConBrillo,
} from "@/componentes/EntradaAnimada";
import { MarcaGoogle, MarcaTelegram } from "@/componentes/Marcas-svg";

// Solo en el navegador: MapLibre toca `window` al cargarse.
const MapaFondo = dynamic(
  () => import("@/componentes/MapaFondo").then((m) => m.MapaFondo),
  {
    ssr: false,
  },
);

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
    } catch (err) {
      // El 429 se dice tal cual: con el mensaje de contraseña mala, quien se
      // paso del limite seguiria probando y alargando el bloqueo.
      if (err instanceof ApiError && err.status === 429) {
        setError("Demasiados intentos. Espera un minuto.");
      } else if (err instanceof ApiError && err.status !== 401) {
        setError("No se pudo entrar ahora. Probá de nuevo en un momento.");
      } else {
        setError("Esa contraseña no es. Revisala y probá de nuevo.");
      }
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
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-background from-55% via-background/85 via-72% to-background/30" />
          {/* Sobre la parte del mapa que el velo deja ver, lejos del texto. */}
          <PinQueLlega className="top-[44%] left-[78%]" />
        </div>

        <div className="relative flex items-center gap-3">
          <LogoQueCae className="size-10 rounded-full shadow-sm" />
          <div className="leading-tight">
            <p className="font-semibold tracking-tight">Smart Report</p>
            <p className="text-xs text-muted-foreground">
              Vía pública · El Salvador
            </p>
          </div>
        </div>

        <div className="relative max-w-xl">
          <EntraEnCascada retraso={0.05}>
            <PildoraDeMarca>Reportes ciudadanos con IA</PildoraDeMarca>
          </EntraEnCascada>
          <EntraEnCascada retraso={0.15}>
            <h1 className="mt-5 text-3xl leading-[1.05] font-semibold tracking-tight text-balance lg:text-[3.4rem]">
              Los problemas de la calle,{" "}
              <span className="texto-degradado">reportados con una foto.</span>
            </h1>
          </EntraEnCascada>
          <LineaPintada retraso={0.45} className="mt-6" />
          <EntraEnCascada retraso={0.65}>
            <p className="mt-6 max-w-md text-pretty text-muted-foreground lg:text-lg">
              Los vecinos mandan una foto por Telegram. El sistema junta los reportes
              del mismo problema y la cuadrilla lo atiende.
            </p>
          </EntraEnCascada>
          <PasosDeEntrada retraso={0.85} className="mt-7" />
        </div>

        <EntraEnCascada retraso={1.2} className="relative space-y-6">
          <a
            href="https://t.me/smartreport_sv_bot"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <MarcaTelegram className="size-4" />
            Reportar un problema:{" "}
            <span className="font-medium">@smartreport_sv_bot</span>
          </a>
        </EntraEnCascada>
      </section>

      {/* --- Entrar --- */}
      <section className="relative flex items-center justify-center overflow-hidden px-6 py-12 lg:px-12">
        {/* Trama de puntos que se apaga hacia los bordes, y un halo verde detras
            de la tarjeta: le dan profundidad a la mitad que antes era un plano
            gris, sin competir con el formulario. */}
        <div
          aria-hidden
          className="trama-puntos pointer-events-none absolute inset-0 [mask-image:radial-gradient(ellipse_at_center,#000_15%,transparent_70%)]"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute top-1/2 left-1/2 size-[28rem] -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/10 blur-3xl dark:bg-primary/15"
        />
        {/* Fijo arriba en el telefono: apilado, el borde de esta seccion cae a
            media pagina y el boton quedaba flotando en medio de la nada. */}
        <div className="fixed top-3 right-3 z-10 lg:absolute lg:top-4 lg:right-4">
          <CambiarTema />
        </div>

        <TarjetaConBrillo retraso={0.2} className="max-w-sm">
          <div className="space-y-8 p-7 sm:p-8">
            <div className="space-y-2">
              <h2 className="text-2xl font-semibold tracking-tight">
                Entrar al tablero
              </h2>
              <p className="text-sm text-muted-foreground">
                Para quien despacha: la cola de casos, el mapa y el cierre con
                evidencia.
              </p>
            </div>

            <div className="space-y-2">
              <Button asChild variant="outline" className="boton-brillo h-11 w-full text-sm transition-shadow hover:shadow-md">
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
              <Button
                type="submit"
                disabled={enviando || !password}
                className="boton-brillo h-10 w-full transition-shadow hover:shadow-md hover:shadow-primary/25"
              >
                <Eye className="size-4" />
                {enviando ? "Entrando…" : "Entrar a mirar"}
              </Button>
            </form>

            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </div>
        </TarjetaConBrillo>
      </section>
    </main>
  );
}
