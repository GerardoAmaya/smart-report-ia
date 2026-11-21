"use client";

/**
 * El robot del asistente: la puerta de entrada a «Pregúntale al tablero».
 *
 * Un personaje propio, con la paleta del proyecto: cabeza con visor, casco de
 * obra color cono —es un asistente de la vía pública, no un robot genérico— y
 * una antena con luz ámbar. La vida está en los ojos: siguen el cursor por toda
 * la página, parpadean, se ponen felices cuando alguien se acerca, celebran el
 * clic, giran mientras el asistente piensa y se adormecen si nadie hace nada.
 *
 * **Se mueve con mesura.** El tablero se mira ocho horas: la flotación es
 * lenta, el globo sale como mucho una vez cada 45 s y se cierra solo, y con
 * «movimiento reducido» el robot se queda quieto, mira al frente y no habla.
 *
 * No pide nada nuevo al servidor: el número de urgentes del globo sale de la
 * cola que el tablero ya tiene en caché.
 */
import { useQuery } from "@tanstack/react-query";
import {
  AnimatePresence,
  animate,
  motion,
  useMotionValue,
  useReducedMotion,
  useSpring,
  type MotionValue,
} from "motion/react";
import { useCallback, useEffect, useId, useRef, useState } from "react";

import { BorderBeam } from "@/components/ui/border-beam";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const FRASES = [
  "¿Te ayudo con algo?",
  "Puedo resumirte el turno.",
  "Pregúntame por los casos urgentes.",
];

// El primer globo espera a que la persona se ubique; despues, uno cada 45-75 s.
const PRIMER_GLOBO_MS = 14_000;
const ENTRE_GLOBOS_MS = 45_000;
const GLOBO_VISIBLE_MS = 6_500;

// Sin mover el raton este rato, la mirada vuelve al frente; con mucho mas,
// el robot se adormece.
const MIRADA_QUIETA_MS = 3_000;
const SUENO_MS = 60_000;

// Cuanto se pueden mover las pupilas dentro del visor, en unidades del dibujo.
const RECORRIDO_X = 4.2;
const RECORRIDO_Y = 2.8;

// La reaccion al clic dura esto; el panel se abre antes de que termine, para
// que la celebracion no se sienta como espera.
const REACCION_MS = 420;
const ABRIR_TRAS_MS = 220;

/** Lo que dicen los ojos. */
type Gesto =
  "normal" | "feliz" | "estrellas" | "pensando" | "dormido" | "sorpresa";

/**
 * Donde lo dejo la persona. `null` es su sitio de siempre, abajo a la
 * derecha: solo ahi el robot se aparta solo de la atribucion del mapa y de los
 * avisos; si alguien lo movio, se respeta su eleccion.
 */
type Posicion = { lado: "izq" | "der"; y: number } | null;

const CLAVE_POSICION = "smart-report:robot";
// Mas de esto con el boton apretado es arrastre, no clic.
const UMBRAL_ARRASTRE_PX = 5;
// Por debajo del encabezado: arrastrado mas arriba taparia buscar y perfil.
const TOPE_SUPERIOR_PX = 64;

function leerPosicion(): Posicion {
  try {
    const crudo = window.localStorage.getItem(CLAVE_POSICION);
    if (!crudo) return null;
    const p = JSON.parse(crudo);
    if ((p.lado === "izq" || p.lado === "der") && typeof p.y === "number")
      return p;
  } catch {
    // Sin almacenamiento (ventana privada, bloqueado): a su sitio de siempre.
  }
  return null;
}

function guardarPosicion(p: Posicion) {
  try {
    if (p) window.localStorage.setItem(CLAVE_POSICION, JSON.stringify(p));
    else window.localStorage.removeItem(CLAVE_POSICION);
  } catch {
    // Que no se recuerde no rompe nada: la proxima visita vuelve a la esquina.
  }
}

/** Margen al borde de la ventana, el mismo que dan las clases right-4/lg:right-6. */
const margen = () => (window.innerWidth >= 1024 ? 24 : 16);

export function Robot({
  onAbrir,
  pensando,
  abierto,
  enMapa,
}: {
  onAbrir: () => void;
  pensando: boolean;
  abierto: boolean;
  /** En el mapa sube un poco: abajo a la derecha esta la atribucion de OSM. */
  enMapa: boolean;
}) {
  const reducido = !!useReducedMotion();
  const [hover, setHover] = useState(false);
  const [parpadeo, setParpadeo] = useState(false);
  const [dormido, setDormido] = useState(false);
  const [reaccion, setReaccion] = useState(false);
  const [globo, setGlobo] = useState<string | null>(null);
  const [elevacion, setElevacion] = useState(0);
  const [arrastrando, setArrastrando] = useState(false);
  // El componente solo se pinta en el cliente (el tablero espera la sesion),
  // asi que leer el almacenamiento al iniciar no descuadra la hidratacion.
  const [posicion, setPosicion] = useState<Posicion>(() =>
    typeof window === "undefined" ? null : leerPosicion(),
  );
  const boton = useRef<HTMLButtonElement>(null);
  const limites = useRef<HTMLDivElement>(null);
  const arrastro = useRef(false);

  // El desplazamiento respecto de su sitio de siempre. En x solo hay dos
  // valores en reposo, pegado a un lado o al otro; en y, lo que eligio.
  const dx = useMotionValue(0);
  const dy = useMotionValue(posicion?.y ?? 0);

  // La mirada: un objetivo que pone el cursor y un resorte que lo persigue, asi
  // los ojos llegan con un poco de inercia en vez de saltar.
  const objetivoX = useMotionValue(0);
  const objetivoY = useMotionValue(0);
  const ojoX = useSpring(objetivoX, { stiffness: 180, damping: 18, mass: 0.6 });
  const ojoY = useSpring(objetivoY, { stiffness: 180, damping: 18, mass: 0.6 });

  // La cola de "Todo" que ya esta en cache. `enabled: false`: solo se lee lo
  // que el tablero ya pidio; si no esta, el globo no menciona urgentes.
  const { data: cola } = useQuery({
    queryKey: ["casos", ""],
    queryFn: () => api.casos(),
    enabled: false,
  });
  const urgentes =
    cola?.cases.filter((c) => c.severity === "alta" && c.status !== "closed")
      .length ?? 0;

  const gesto: Gesto = arrastrando
    ? "sorpresa"
    : pensando
      ? "pensando"
      : reaccion
        ? "estrellas"
        : hover
          ? "feliz"
          : dormido
            ? "dormido"
            : "normal";

  // Seguir el cursor por toda la pagina, volver al frente cuando se queda
  // quieto o sale de la ventana, y dormirse tras un minuto sin nadie.
  useEffect(() => {
    if (reducido) return;
    let cuadro = 0;
    let quieto: ReturnType<typeof setTimeout>;
    let sueno: ReturnType<typeof setTimeout>;
    const alFrente = () => {
      objetivoX.set(0);
      objetivoY.set(0);
    };
    const despertar = () => {
      setDormido(false);
      clearTimeout(sueno);
      sueno = setTimeout(() => {
        alFrente();
        setDormido(true);
      }, SUENO_MS);
    };
    const mover = (e: PointerEvent) => {
      despertar();
      clearTimeout(quieto);
      quieto = setTimeout(alFrente, MIRADA_QUIETA_MS);
      cancelAnimationFrame(cuadro);
      cuadro = requestAnimationFrame(() => {
        const r = boton.current?.getBoundingClientRect();
        if (!r) return;
        const dx = e.clientX - (r.left + r.width / 2);
        const dy = e.clientY - (r.top + r.height * 0.38);
        // Normalizado a la pantalla: asi un cursor en la otra punta lleva los
        // ojos al borde del visor, y uno cerca los mueve poco.
        const nx = Math.max(-1, Math.min(1, dx / (window.innerWidth * 0.45)));
        const ny = Math.max(-1, Math.min(1, dy / (window.innerHeight * 0.45)));
        objetivoX.set(nx * RECORRIDO_X);
        objetivoY.set(ny * RECORRIDO_Y);
      });
    };
    const salir = (e: MouseEvent) => {
      if (!e.relatedTarget) alFrente();
    };
    window.addEventListener("pointermove", mover, { passive: true });
    window.addEventListener("pointerdown", despertar, { passive: true });
    window.addEventListener("keydown", despertar);
    window.addEventListener("blur", alFrente);
    document.addEventListener("mouseout", salir);
    sueno = setTimeout(() => {
      alFrente();
      setDormido(true);
    }, SUENO_MS);
    return () => {
      window.removeEventListener("pointermove", mover);
      window.removeEventListener("pointerdown", despertar);
      window.removeEventListener("keydown", despertar);
      window.removeEventListener("blur", alFrente);
      document.removeEventListener("mouseout", salir);
      cancelAnimationFrame(cuadro);
      clearTimeout(quieto);
      clearTimeout(sueno);
    };
  }, [reducido, objetivoX, objetivoY]);

  // Parpadeo: cada 2,5-5 s al azar, y una de cada cuatro veces, doble. A ritmo
  // fijo se nota la maquina.
  useEffect(() => {
    if (reducido) return;
    const timers: ReturnType<typeof setTimeout>[] = [];
    const cerrar = (en: number) => {
      timers.push(setTimeout(() => setParpadeo(true), en));
      timers.push(setTimeout(() => setParpadeo(false), en + 120));
    };
    let siguiente: ReturnType<typeof setTimeout>;
    const programar = () => {
      siguiente = setTimeout(
        () => {
          cerrar(0);
          if (Math.random() < 0.25) cerrar(260);
          programar();
        },
        2500 + Math.random() * 2500,
      );
    };
    programar();
    return () => {
      clearTimeout(siguiente);
      timers.forEach(clearTimeout);
    };
  }, [reducido]);

  // El globo: de vez en cuando, nunca con el panel abierto, dormido ni con
  // movimiento reducido. Si hay urgentes en la cola, lo dice con el numero real.
  const urgentesRef = useRef(urgentes);
  useEffect(() => {
    urgentesRef.current = urgentes;
  }, [urgentes]);
  useEffect(() => {
    if (reducido || abierto) return;
    let indice = 0;
    let mostrar: ReturnType<typeof setTimeout>;
    let ocultar: ReturnType<typeof setTimeout>;
    const programar = (espera: number) => {
      mostrar = setTimeout(() => {
        if (document.visibilityState !== "visible")
          return programar(ENTRE_GLOBOS_MS);
        const n = urgentesRef.current;
        const texto =
          n > 0 && indice % 2 === 0
            ? n === 1
              ? "Hay 1 caso urgente abierto. ¿Te cuento?"
              : `Hay ${n} casos urgentes abiertos. ¿Te cuento?`
            : FRASES[indice % FRASES.length];
        indice += 1;
        setGlobo(texto);
        ocultar = setTimeout(() => setGlobo(null), GLOBO_VISIBLE_MS);
        programar(ENTRE_GLOBOS_MS + Math.random() * 30_000);
      }, espera);
    };
    programar(PRIMER_GLOBO_MS);
    return () => {
      clearTimeout(mostrar);
      clearTimeout(ocultar);
      // Al abrir el panel, el globo que estuviera se va y no vuelve al cerrar.
      setGlobo(null);
    };
  }, [reducido, abierto]);

  // Los avisos de Sonner salen abajo a la derecha, justo donde vive el robot:
  // cuando hay alguno, el robot sube por encima en vez de taparlo.
  useEffect(() => {
    const medir = () => {
      const avisos = document.querySelectorAll<HTMLElement>(
        "[data-sonner-toast]",
      );
      let alto = 0;
      avisos.forEach((a) => {
        const r = a.getBoundingClientRect();
        if (r.height > 0) alto = Math.max(alto, window.innerHeight - r.top);
      });
      setElevacion(alto > 0 ? alto - 8 : 0);
    };
    const observador = new MutationObserver(() => requestAnimationFrame(medir));
    observador.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
    });
    return () => observador.disconnect();
  }, []);

  // Coloca el robot donde dice `p`, dentro de la ventana. Se usa al soltarlo,
  // al cargar la pagina y cuando la ventana cambia de tamaño.
  const colocar = useCallback(
    (p: Posicion, suave: boolean) => {
      const b = boton.current;
      if (!b) return;
      const x =
        p?.lado === "izq"
          ? -(window.innerWidth - b.offsetWidth - 2 * margen())
          : 0;
      // y acotada: nunca por debajo de su sitio (que ya esta sobre la barra
      // inferior del celular) ni por encima del encabezado.
      const rect = b.getBoundingClientRect();
      const arriba = rect.top - (dy.get() - (p?.y ?? 0));
      let y = Math.min(0, p?.y ?? 0);
      if (arriba < TOPE_SUPERIOR_PX) y += TOPE_SUPERIOR_PX - arriba;
      if (suave && !reducido) {
        animate(dx, x, { type: "spring", stiffness: 380, damping: 30 });
        animate(dy, y, { type: "spring", stiffness: 380, damping: 30 });
      } else {
        dx.set(x);
        dy.set(y);
      }
    },
    [dx, dy, reducido],
  );

  useEffect(() => {
    colocar(posicion, false);
    const alCambiar = () => colocar(posicion, false);
    window.addEventListener("resize", alCambiar);
    return () => window.removeEventListener("resize", alCambiar);
    // Solo al cargar y al cambiar el tamaño: al soltarlo ya se coloca con muelle.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [colocar]);

  // Al soltarlo: se pega al borde mas cercano con un muelle y se recuerda. Si
  // cae cerca de su esquina de siempre, vuelve a ser "su sitio", con lo que
  // recupera el apartarse solo del mapa y de los avisos.
  const soltar = () => {
    setArrastrando(false);
    const b = boton.current;
    if (!b) return;
    const r = b.getBoundingClientRect();
    const lado = r.left + r.width / 2 < window.innerWidth / 2 ? "izq" : "der";
    const y = Math.min(0, dy.get());
    const nueva: Posicion = lado === "der" && y > -24 ? null : { lado, y };
    setPosicion(nueva);
    guardarPosicion(nueva);
    colocar(nueva, true);
  };

  // El clic: estrellas en los ojos y un "boing", y el panel se abre a los
  // 220 ms, antes de que acabe la celebracion. Sin movimiento, abre al instante.
  // Un arrastre que termina sobre el boton tambien dispara "click": ese no abre.
  const alHacerClic = () => {
    if (arrastro.current) {
      arrastro.current = false;
      return;
    }
    if (reducido) return onAbrir();
    setReaccion(true);
    setTimeout(onAbrir, ABRIR_TRAS_MS);
    setTimeout(() => setReaccion(false), REACCION_MS);
  };

  const flotar = !reducido && !hover && !dormido && !arrastrando;
  const enSuSitio = posicion === null;
  // El globo sale hacia donde haya sitio: a la derecha si el robot esta a la
  // izquierda, y debajo si lo subieron cerca del encabezado.
  const globoALaDerecha = posicion?.lado === "izq";
  const globoAbajo =
    posicion !== null &&
    typeof window !== "undefined" &&
    window.innerHeight + posicion.y < 360;

  return (
    <>
      {/* El area donde se puede soltar: la ventana, menos el encabezado y, en
          el celular, la barra inferior. */}
      <div
        ref={limites}
        aria-hidden
        className="pointer-events-none fixed inset-x-2 top-14 bottom-[calc(4rem+env(safe-area-inset-bottom))] lg:bottom-2"
      />
      <motion.div
        className={cn(
          "fixed right-4 z-40 lg:right-6",
          // En el celular, por encima de la barra inferior y del borde de gestos.
          "bottom-[calc(4.5rem+env(safe-area-inset-bottom))] lg:bottom-6",
          enSuSitio &&
            enMapa &&
            "max-lg:bottom-[calc(6rem+env(safe-area-inset-bottom))] lg:bottom-12",
        )}
        animate={{
          y: enSuSitio ? -elevacion : 0,
          scale: abierto ? 0.6 : 1,
          opacity: abierto ? 0 : 1,
        }}
        transition={{ type: "spring", stiffness: 260, damping: 26 }}
        style={{ pointerEvents: abierto ? "none" : undefined }}
      >
        <motion.div
          className="relative"
          style={{ x: dx, y: dy }}
          drag
          dragConstraints={limites}
          dragElastic={0.06}
          dragMomentum={false}
          onPointerDown={() => {
            arrastro.current = false;
          }}
          onDragStart={() => setArrastrando(true)}
          onDrag={(_, info) => {
            if (Math.hypot(info.offset.x, info.offset.y) > UMBRAL_ARRASTRE_PX)
              arrastro.current = true;
          }}
          onDragEnd={soltar}
        >
          <AnimatePresence>
            {globo && !abierto && !dormido && !arrastrando && (
              <motion.button
                type="button"
                key={globo}
                onClick={alHacerClic}
                initial={{ opacity: 0, y: globoAbajo ? -8 : 8, scale: 0.9 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: globoAbajo ? -4 : 4, scale: 0.95 }}
                transition={{ duration: 0.22, ease: "easeOut" }}
                // El globo no es otro boton "Asistente": su nombre es lo que dice.
                // Va suelto sobre el robot para que su ancho no lo empuje al salir.
                className={cn(
                  "absolute w-max max-w-60 overflow-hidden rounded-2xl border bg-card/95 px-3.5 py-2.5 text-left text-sm shadow-lg backdrop-blur",
                  globoAbajo ? "top-full mt-2" : "bottom-full mb-2",
                  globoALaDerecha ? "left-2" : "right-2",
                  globoAbajo
                    ? globoALaDerecha
                      ? "rounded-tl-sm"
                      : "rounded-tr-sm"
                    : globoALaDerecha
                      ? "rounded-bl-sm"
                      : "rounded-br-sm",
                )}
              >
                {globo}
                {/* El borde con brillo de Magic UI, en la paleta: verde a ambar. Solo
                mientras el globo esta a la vista, que es poco. */}
                {!reducido && (
                  <BorderBeam
                    size={60}
                    duration={3.2}
                    colorFrom="var(--verde)"
                    colorTo="var(--ambar)"
                    borderWidth={1.5}
                  />
                )}
              </motion.button>
            )}
          </AnimatePresence>

          <motion.button
            ref={boton}
            type="button"
            aria-label="Asistente"
            title="Pregúntale al tablero"
            onClick={alHacerClic}
            onPointerEnter={() => setHover(true)}
            onPointerLeave={() => setHover(false)}
            onFocus={() => setHover(true)}
            onBlur={() => setHover(false)}
            className={cn(
              "group relative block size-18 touch-none rounded-full outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background lg:size-23",
              arrastrando ? "cursor-grabbing" : "cursor-grab",
            )}
            // El "boing" del clic.
            animate={reaccion ? { scale: [1, 0.86, 1.12, 1] } : { scale: 1 }}
            transition={{ duration: 0.4, ease: "easeOut" }}
          >
            {/* Halo suave detras: separa al robot de lo que tenga abajo, y crece
            cuando alguien se acerca. */}
            <span
              className={cn(
                "absolute inset-2 rounded-full bg-primary/15 blur-xl transition-all duration-300 dark:bg-primary/25",
                hover &&
                  !reducido &&
                  "inset-0 bg-primary/25 dark:bg-primary/35",
              )}
            />
            <motion.div
              className="relative size-full"
              animate={
                flotar
                  ? { y: [0, -6, 0], rotate: 0 }
                  : arrastrando && !reducido
                    ? // Agarrado: colgando ladeado del dedo.
                      { y: -4, rotate: 12 }
                    : // Al acercarse alguien, un saltito de saludo.
                      { y: hover && !reducido ? -9 : 0, rotate: 0 }
              }
              transition={
                flotar
                  ? { duration: 3.6, repeat: Infinity, ease: "easeInOut" }
                  : { type: "spring", stiffness: 420, damping: 14 }
              }
            >
              <DibujoRobot
                gesto={gesto}
                parpadeo={parpadeo && (gesto === "normal" || gesto === "feliz")}
                saluda={hover && !reducido}
                ojoX={ojoX}
                ojoY={ojoY}
                reducido={reducido}
              />
              {/* Las "z" del sueño, saliendo de la cabeza. */}
              <AnimatePresence>
                {gesto === "dormido" && !reducido && <Zetas />}
              </AnimatePresence>
            </motion.div>
            {/* La sombra en el suelo se achica cuando el robot sube. */}
            <motion.span
              className="absolute -bottom-1 left-1/2 h-1.5 w-10 -translate-x-1/2 rounded-full bg-foreground/15 blur-[2px]"
              animate={
                flotar
                  ? { scaleX: [1, 0.8, 1], opacity: [0.6, 0.35, 0.6] }
                  : // Levantado del suelo, la sombra se agranda y se aclara.
                    arrastrando
                    ? { scaleX: 1.5, opacity: 0.3 }
                    : { scaleX: 1, opacity: 0.6 }
              }
              transition={
                flotar
                  ? { duration: 3.6, repeat: Infinity, ease: "easeInOut" }
                  : { duration: 0.2 }
              }
            />
          </motion.button>
        </motion.div>
      </motion.div>
    </>
  );
}

function Zetas() {
  return (
    <motion.span
      aria-hidden
      className="pointer-events-none absolute -top-1 right-1 font-semibold text-primary"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="absolute"
          style={{ fontSize: 10 + i * 3, right: i * 7 }}
          animate={{ y: [0, -22], x: [0, 6], opacity: [0, 1, 0] }}
          transition={{
            duration: 2.4,
            repeat: Infinity,
            delay: i * 0.8,
            ease: "easeOut",
          }}
        >
          z
        </motion.span>
      ))}
    </motion.span>
  );
}

/**
 * El mismo robot, chico y sin seguir el cursor, para el encabezado del panel.
 * Con el panel abierto el flotante se esconde, y es justo cuando el asistente
 * piensa: aqui es donde se ve que piensa.
 */
export function RobotMini({
  pensando,
  className,
}: {
  pensando: boolean;
  className?: string;
}) {
  const reducido = !!useReducedMotion();
  const quieto = useMotionValue(0);
  return (
    <span className={cn("inline-block size-8 shrink-0", className)}>
      <DibujoRobot
        gesto={pensando ? "pensando" : "normal"}
        parpadeo={false}
        saluda={false}
        ojoX={quieto}
        ojoY={quieto}
        reducido={reducido}
      />
    </span>
  );
}

const OJO = "#7fd8b9";
const ESTRELLA = "#ffd08a";
const CENTROS = [31, 49];
const CY = 40;

/**
 * El dibujo. Coordenadas en una caja de 80 x 88; los colores salen de las
 * variables del tema para que el modo oscuro venga solo.
 */
function DibujoRobot({
  gesto,
  parpadeo,
  saluda,
  ojoX,
  ojoY,
  reducido,
}: {
  gesto: Gesto;
  parpadeo: boolean;
  saluda: boolean;
  ojoX: MotionValue<number>;
  ojoY: MotionValue<number>;
  reducido: boolean;
}) {
  // Ids propios por dibujo: hay dos robots en la pagina (el flotante y el del
  // panel) y con ids repetidos los degradados apuntarian al del otro.
  const u = useId().replace(/[^a-zA-Z0-9]/g, "");
  const id = (n: string) => `robot-${n}-${u}`;
  const feliz = gesto === "feliz" || gesto === "estrellas";

  return (
    <svg viewBox="0 0 80 88" className="size-full drop-shadow-md" aria-hidden>
      <defs>
        <linearGradient id={id("cuerpo")} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="var(--card)" />
          <stop
            offset="1"
            stopColor="color-mix(in oklab, var(--card) 82%, var(--tinta))"
          />
        </linearGradient>
        <linearGradient id={id("casco")} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#dd9446" />
          <stop offset="1" stopColor="var(--ambar)" />
        </linearGradient>
        <radialGradient id={id("luz")}>
          <stop offset="0" stopColor="#ffe2b0" />
          <stop offset="1" stopColor="var(--ambar)" />
        </radialGradient>
        <radialGradient id={id("pupila")} cx="0.4" cy="0.35" r="0.75">
          <stop offset="0" stopColor="#c9f5e5" />
          <stop offset="0.55" stopColor={OJO} />
          <stop offset="1" stopColor="#3fae8b" />
        </radialGradient>
        <radialGradient id={id("visor")} cx="0.5" cy="0.3" r="0.9">
          <stop offset="0" stopColor="#1e2428" />
          <stop offset="1" stopColor="#0d1013" />
        </radialGradient>
        <clipPath id={id("recorte")}>
          <rect x="18" y="29" width="44" height="22" rx="11" />
        </clipPath>
      </defs>

      {/* Brazo izquierdo, quieto. */}
      <rect
        x="11"
        y="58"
        width="8"
        height="16"
        rx="4"
        fill={`url(#${id("cuerpo")})`}
        stroke="var(--border)"
      />
      {/* Brazo derecho: saluda. Gira desde el hombro. */}
      <motion.g
        style={{ originX: "66px", originY: "60px" }}
        animate={
          saluda ? { rotate: [0, -150, -120, -150, -130] } : { rotate: 0 }
        }
        transition={
          saluda ? { duration: 1.1, ease: "easeInOut" } : { duration: 0.3 }
        }
      >
        <rect
          x="61"
          y="58"
          width="8"
          height="16"
          rx="4"
          fill={`url(#${id("cuerpo")})`}
          stroke="var(--border)"
        />
      </motion.g>

      {/* Cuerpo con la etiqueta IA. */}
      <rect
        x="18"
        y="54"
        width="44"
        height="28"
        rx="12"
        fill={`url(#${id("cuerpo")})`}
        stroke="var(--border)"
      />
      <rect x="29" y="61" width="22" height="13" rx="6.5" fill="var(--verde)" />
      <text
        x="40"
        y="70.6"
        textAnchor="middle"
        fontSize="9"
        fontWeight="700"
        fill="#f4f6f4"
        fontFamily="ui-sans-serif, system-ui, sans-serif"
        letterSpacing="0.5"
      >
        IA
      </text>

      {/* La cabeza: ladea al saludar y cabecea cuando duerme. */}
      <motion.g
        style={{ originX: "40px", originY: "52px" }}
        animate={{
          rotate: saluda ? -8 : gesto === "dormido" && !reducido ? 6 : 0,
        }}
        transition={{ type: "spring", stiffness: 220, damping: 14 }}
      >
        {/* Antena con su luz ámbar: destella, y más cuando alguien se acerca. */}
        <line
          x1="40"
          y1="12"
          x2="40"
          y2="6"
          stroke="var(--tinta)"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
        <motion.circle
          cx="40"
          cy="5"
          r="3.2"
          fill={`url(#${id("luz")})`}
          // Se agranda con el radio y no con scale: dentro de un SVG el origen
          // del scale se calcula aparte y la luz se despegaba de la antena.
          animate={
            reducido
              ? {}
              : feliz
                ? { r: [3.2, 4.8, 3.9], opacity: 1 }
                : gesto === "dormido"
                  ? { opacity: 0.35, r: 3.2 }
                  : { opacity: [1, 0.45, 1], r: 3.2 }
          }
          transition={
            reducido
              ? {}
              : feliz
                ? { duration: 0.35 }
                : { duration: 1.8, repeat: Infinity, ease: "easeInOut" }
          }
        />
        {!reducido && gesto !== "dormido" && (
          <motion.circle
            cx="40"
            cy="5"
            r="3.2"
            fill="none"
            stroke="var(--ambar)"
            strokeWidth="1"
            animate={{ r: [3.2, feliz ? 10 : 7.5], opacity: [0.8, 0] }}
            transition={{
              duration: feliz ? 0.9 : 1.8,
              repeat: Infinity,
              ease: "easeOut",
            }}
          />
        )}

        {/* Cabeza. */}
        <rect
          x="14"
          y="17"
          width="52"
          height="38"
          rx="19"
          fill={`url(#${id("cuerpo")})`}
          stroke="var(--border)"
        />

        {/* Casco de obra color cono, con su franja reflectante. */}
        <path
          d="M17 26 C 19 11, 61 11, 63 26 Z"
          fill={`url(#${id("casco")})`}
        />
        <rect
          x="12"
          y="24"
          width="56"
          height="4.5"
          rx="2.25"
          fill="var(--ambar)"
        />
        <path
          d="M24 21 L 56 21"
          stroke="#fff3df"
          strokeOpacity="0.85"
          strokeWidth="2"
          strokeLinecap="round"
        />

        {/* Visor oscuro con los ojos. */}
        <rect
          x="18"
          y="29"
          width="44"
          height="22"
          rx="11"
          fill={`url(#${id("visor")})`}
        />
        <g clipPath={`url(#${id("recorte")})`}>
          <Ojos
            gesto={gesto}
            parpadeo={parpadeo}
            ojoX={ojoX}
            ojoY={ojoY}
            reducido={reducido}
            id={id}
          />
        </g>
        {/* Brillo del visor, encima de todo. */}
        <path
          d="M23 33 Q 26 31 31 31"
          stroke="#ffffff"
          strokeOpacity="0.22"
          strokeWidth="1.5"
          fill="none"
          strokeLinecap="round"
        />
        {/* Mejillas que se encienden cuando esta feliz. */}
        <AnimatePresence>
          {feliz && (
            <motion.g
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <ellipse
                cx="22"
                cy="49"
                rx="3"
                ry="1.6"
                fill="var(--ambar)"
                opacity="0.45"
              />
              <ellipse
                cx="58"
                cy="49"
                rx="3"
                ry="1.6"
                fill="var(--ambar)"
                opacity="0.45"
              />
            </motion.g>
          )}
        </AnimatePresence>
      </motion.g>
    </svg>
  );
}

/** Los ojos, según el gesto. Todo dentro del visor (recortado a su forma). */
function Ojos({
  gesto,
  parpadeo,
  ojoX,
  ojoY,
  reducido,
  id,
}: {
  gesto: Gesto;
  parpadeo: boolean;
  ojoX: MotionValue<number>;
  ojoY: MotionValue<number>;
  reducido: boolean;
  id: (n: string) => string;
}) {
  if (gesto === "pensando") {
    // Pensando: cada ojo es un anillo que gira.
    return (
      <>
        {CENTROS.map((cx) => (
          <motion.circle
            key={cx}
            cx={cx}
            cy={CY}
            r="4.4"
            fill="none"
            stroke={OJO}
            strokeWidth="2.4"
            strokeLinecap="round"
            strokeDasharray="16 12"
            style={{ originX: `${cx}px`, originY: `${CY}px` }}
            animate={reducido ? {} : { rotate: 360 }}
            transition={
              reducido
                ? {}
                : { duration: 0.9, repeat: Infinity, ease: "linear" }
            }
          />
        ))}
      </>
    );
  }

  if (gesto === "estrellas") {
    // El clic: estrellas que aparecen de golpe y giran un poco.
    return (
      <>
        {CENTROS.map((cx) => (
          <motion.path
            key={cx}
            d={estrella(cx, CY, 6.2, 2.6)}
            fill={ESTRELLA}
            style={{ originX: `${cx}px`, originY: `${CY}px` }}
            initial={{ scale: 0.2, rotate: -40 }}
            animate={{ scale: [0.2, 1.25, 1], rotate: 0 }}
            transition={{ duration: 0.3, ease: "easeOut" }}
          />
        ))}
      </>
    );
  }

  if (gesto === "feliz") {
    // Feliz: ojos en arco, como ^ ^.
    return (
      <>
        {CENTROS.map((cx) => (
          <motion.path
            key={cx}
            d={`M${cx - 5} ${CY + 2.2} Q ${cx} ${CY - 5.5} ${cx + 5} ${CY + 2.2}`}
            fill="none"
            stroke={OJO}
            strokeWidth="2.8"
            strokeLinecap="round"
            initial={{ pathLength: 0 }}
            animate={{ pathLength: 1 }}
            transition={{ duration: 0.18 }}
          />
        ))}
      </>
    );
  }

  if (gesto === "sorpresa") {
    // Agarrado: ojos muy abiertos, pupila chica en el centro.
    return (
      <>
        {CENTROS.map((cx) => (
          <motion.g
            key={cx}
            style={{ originX: `${cx}px`, originY: `${CY}px` }}
            initial={{ scale: 0.7 }}
            animate={{ scale: 1 }}
            transition={{ type: "spring", stiffness: 500, damping: 12 }}
          >
            <circle
              cx={cx}
              cy={CY}
              r="6.6"
              fill="none"
              stroke={OJO}
              strokeWidth="2.2"
            />
            <circle cx={cx} cy={CY} r="2.4" fill={OJO} />
            <circle cx={cx - 1.6} cy={CY - 1.8} r="1.2" fill="#ffffff" />
          </motion.g>
        ))}
      </>
    );
  }

  if (gesto === "dormido") {
    // Dormido: párpados caídos, una línea curva hacia abajo.
    return (
      <>
        {CENTROS.map((cx) => (
          <path
            key={cx}
            d={`M${cx - 5} ${CY} Q ${cx} ${CY + 3.2} ${cx + 5} ${CY}`}
            fill="none"
            stroke={OJO}
            strokeOpacity="0.75"
            strokeWidth="2.2"
            strokeLinecap="round"
          />
        ))}
      </>
    );
  }

  // Normal: pupilas grandes con su reflejo, que siguen al cursor y parpadean.
  return (
    <motion.g style={{ x: ojoX, y: ojoY }}>
      {CENTROS.map((cx) => (
        <motion.g
          key={cx}
          style={{ originX: `${cx}px`, originY: `${CY}px` }}
          animate={{ scaleY: parpadeo ? 0.08 : 1 }}
          transition={{ duration: 0.06, ease: "easeInOut" }}
        >
          {/* Resplandor alrededor de la pupila. */}
          <circle cx={cx} cy={CY} r="7.5" fill={OJO} opacity="0.16" />
          <circle cx={cx} cy={CY} r="5.4" fill={`url(#${id("pupila")})`} />
          {/* El reflejo: lo que hace que un ojo parezca vivo. */}
          <circle cx={cx - 1.9} cy={CY - 2} r="1.7" fill="#ffffff" />
          <circle
            cx={cx + 1.8}
            cy={CY + 1.9}
            r="0.7"
            fill="#ffffff"
            opacity="0.7"
          />
        </motion.g>
      ))}
    </motion.g>
  );
}

/** Una estrella de cinco puntas centrada en (cx, cy). */
function estrella(
  cx: number,
  cy: number,
  fuera: number,
  dentro: number,
): string {
  const puntos: string[] = [];
  for (let i = 0; i < 10; i++) {
    const r = i % 2 === 0 ? fuera : dentro;
    const a = (Math.PI / 5) * i - Math.PI / 2;
    puntos.push(
      `${(cx + r * Math.cos(a)).toFixed(2)} ${(cy + r * Math.sin(a)).toFixed(2)}`,
    );
  }
  return `M${puntos.join(" L")} Z`;
}
