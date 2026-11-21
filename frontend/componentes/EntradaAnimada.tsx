"use client";

/**
 * Las animaciones de la entrada.
 *
 * Es la unica pantalla donde lo vistoso se permite (ver app/entrar): se cruza
 * una vez al dia y dura segundos. Aun asi, tres reglas:
 *
 * - **Nada bloquea el formulario.** Todo entra en menos de un segundo y el
 *   campo de contraseña se puede escribir desde el primer cuadro: una
 *   animacion que hace esperar a quien va a trabajar es un estorbo con adorno.
 * - **Con movimiento reducido, nada se mueve.** Las transiciones duran cero, y
 *   el pin del mapa y el brillo del borde los esconde el CSS
 *   (`motion-reduce:hidden`) en vez de un `if`: el servidor no sabe la
 *   preferencia, y montar distinto en el navegador rompia la hidratacion. Se usa duracion cero y no `initial={false}`:
 *   el HTML del servidor ya viene en el estado inicial, y cambiar `initial` en
 *   el cliente desacompasa la hidratacion.
 * - **El pin del mapa es adorno y se nota.** Uno solo, siempre en el mismo
 *   sitio, sin direccion ni numero: un pin que cayera en sitios distintos
 *   pareceria un reporte de verdad, y aqui no se publican datos inventados.
 */
import { motion, useReducedMotion, type Transition } from "motion/react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** Duracion cero cuando el sistema pide movimiento reducido. */
function useTransicionSuave(t: Transition): Transition {
  return useReducedMotion() ? { duration: 0 } : t;
}

/** Entra subiendo un poco, con retraso: para la cascada del titular. */
export function EntraEnCascada({
  retraso,
  className,
  children,
}: {
  retraso: number;
  className?: string;
  children: ReactNode;
}) {
  const transicion = useTransicionSuave({
    duration: 0.5,
    ease: [0.22, 1, 0.36, 1],
    delay: retraso,
  });
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={transicion}
      className={className}
    >
      {children}
    </motion.div>
  );
}

/** El logo cae y rebota una vez, como el pin que es. */
export function LogoQueCae({ className }: { className?: string }) {
  const transicion = useTransicionSuave({
    type: "spring",
    stiffness: 420,
    damping: 13,
    mass: 0.8,
  });
  return (
    <motion.img
      src="/marca/avatar-bot.png"
      alt=""
      initial={{ y: -22, opacity: 0, scale: 0.9 }}
      animate={{ y: 0, opacity: 1, scale: 1 }}
      transition={transicion}
      className={className}
    />
  );
}

/**
 * La linea discontinua de una via, pintada tramo a tramo.
 *
 * Despues queda quieta. Se probo dejarla avanzar como vista desde un carro y
 * cansaba: junto al titular, algo que no para de moverse le roba la vista.
 */
export function LineaPintada({
  retraso = 0,
  className,
}: {
  retraso?: number;
  className?: string;
}) {
  const quieto = useReducedMotion();
  return (
    <div aria-hidden className={cn("flex h-1.5 gap-2.5", className)}>
      {[0, 1, 2, 3].map((i) => (
        <motion.span
          key={i}
          initial={{ scaleX: 0 }}
          animate={{ scaleX: 1 }}
          transition={
            quieto
              ? { duration: 0 }
              : { duration: 0.22, ease: "easeOut", delay: retraso + i * 0.12 }
          }
          className="h-full w-4 origin-left rounded-full bg-atencion"
        />
      ))}
    </div>
  );
}

/**
 * Un borde que se ilumina dando la vuelta a la tarjeta, despacio.
 *
 * Un gradiente conico gira detras de la tarjeta y solo asoma por el pixel de
 * borde. Muy tenue a proposito: marca donde se entra sin pedir atencion.
 */
export function TarjetaConBrillo({
  retraso,
  className,
  children,
}: {
  retraso: number;
  className?: string;
  children: ReactNode;
}) {
  const transicion = useTransicionSuave({
    duration: 0.5,
    ease: [0.22, 1, 0.36, 1],
    delay: retraso,
  });
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={transicion}
      className={cn(
        "relative w-full overflow-hidden rounded-xl bg-border p-px shadow-sm",
        className,
      )}
    >
      <motion.div
        aria-hidden
        animate={{ rotate: 360 }}
          transition={{ duration: 9, ease: "linear", repeat: Infinity }}
          className="absolute top-1/2 left-1/2 aspect-square w-[160%] -translate-x-1/2 -translate-y-1/2 bg-[conic-gradient(from_0deg,transparent_0deg,transparent_250deg,var(--primary)_310deg,var(--atencion)_340deg,transparent_360deg)] opacity-70 motion-reduce:hidden"
        />
      <div className="relative rounded-[calc(var(--radius-xl)-1px)] bg-card">
        {children}
      </div>
    </motion.div>
  );
}

const CICLO = 7;

/**
 * Un pin de la marca que cae sobre el mapa y deja ondas, en bucle lento.
 *
 * Evoca "llega un reporte" sin decir donde: va en un punto fijo de la pantalla,
 * no del mapa, y el mapa se mueve por debajo. Con movimiento reducido se
 * esconde: un pin quieto sobre el mapa si pareceria un dato.
 */
export function PinQueLlega({ className }: { className?: string }) {
  return (
    <div aria-hidden className={cn("pointer-events-none absolute motion-reduce:hidden", className)}>
      {/* Ondas: salen del punto donde se clava el pin. */}
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          initial={{ scale: 0.2, opacity: 0 }}
          animate={{ scale: [0.2, 3.2], opacity: [0.5, 0] }}
          transition={{
            duration: 1.8,
            ease: "easeOut",
            delay: 0.75 + i * 0.4,
            repeat: Infinity,
            repeatDelay: CICLO - 1.8,
          }}
          className="absolute top-0 left-0 size-10 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-atencion"
        />
      ))}

      {/* Sombra en el suelo: se ve cuando el pin ya cayo. */}
      <motion.span
        initial={{ opacity: 0, scaleX: 0.3 }}
        animate={{ opacity: [0, 0.35, 0.35, 0], scaleX: [0.3, 1, 1, 0.3] }}
        transition={{
          duration: CICLO,
          times: [0, 0.1, 0.78, 0.88],
          repeat: Infinity,
        }}
        className="absolute top-0 left-0 h-1.5 w-5 -translate-x-1/2 -translate-y-1/2 rounded-[50%] bg-black blur-[1px]"
      />

      {/* El pin: cae, rebota, se queda un rato y se va. */}
      <motion.svg
        viewBox="0 0 24 32"
        initial={{ y: -48, opacity: 0 }}
        animate={{ y: [-48, 0, -6, 0, 0, -10], opacity: [0, 1, 1, 1, 1, 0] }}
        transition={{
          duration: CICLO,
          times: [0, 0.08, 0.11, 0.14, 0.78, 0.88],
          ease: "easeOut",
          repeat: Infinity,
        }}
        className="absolute bottom-0 left-0 h-11 w-8 -translate-x-1/2 drop-shadow-md"
      >
        <path
          d="M12 0C5.4 0 0 5.3 0 11.9 0 20.8 12 32 12 32s12-11.2 12-20.1C24 5.3 18.6 0 12 0Z"
          className="fill-atencion"
        />
        <circle cx="12" cy="11.5" r="5.2" className="fill-[#eeefec]" />
        <circle cx="12" cy="11.5" r="2" className="fill-[#16181a]" />
      </motion.svg>
    </div>
  );
}
