"use client";

/**
 * Piezas visuales del resumen: la aurora de fondo, la tarjeta de vidrio y el
 * icono que reacciona al dato.
 *
 * Lo continuo va en CSS (globals.css: `.aurora`, `.borde-brillo`, `.foco`) y
 * no en JS: una aurora que deriva treinta segundos en bucle no puede costar un
 * render por cuadro en una pantalla que esta abierta ocho horas. Lo que si usa
 * motion es lo puntual —el icono que salta cuando cambia el dato—, que dura
 * menos de un segundo y dice "esto cambio".
 *
 * Con menos movimiento pedido, el CSS deja la aurora y los brillos quietos y
 * el icono aparece sin saltar.
 */
import { motion, useReducedMotion } from "motion/react";
import type { ComponentProps, ComponentType, PointerEvent } from "react";

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/** Manchas de verde y ambar muy difuminadas que derivan despacio, detras de todo. */
export function Aurora() {
  return (
    <div aria-hidden className="aurora">
      <span className="aurora-mancha aurora-verde" />
      <span className="aurora-mancha aurora-ambar" />
      <span className="aurora-mancha aurora-verde-2" />
    </div>
  );
}

/**
 * Una tarjeta de vidrio sobre la aurora.
 *
 * `brillo` pone un borde que recorre la tarjeta: verde-ambar para la cifra
 * principal, solo ambar para lo que pide atencion. Va en dos tarjetas como
 * mucho; un brillo en todas ya no señala nada.
 *
 * El foco bajo el cursor se mueve escribiendo dos variables CSS en el propio
 * elemento, sin estado de React: seguir el raton con `setState` volveria a
 * pintar la grafica en cada pixel.
 */
export function TarjetaVidrio({
  brillo,
  className,
  ...props
}: ComponentProps<typeof Card> & { brillo?: "marca" | "atencion" }) {
  const seguir = (e: PointerEvent<HTMLDivElement>) => {
    const caja = e.currentTarget.getBoundingClientRect();
    e.currentTarget.style.setProperty("--foco-x", `${e.clientX - caja.left}px`);
    e.currentTarget.style.setProperty("--foco-y", `${e.clientY - caja.top}px`);
  };
  return (
    <Card
      onPointerMove={seguir}
      className={cn(
        "foco relative bg-card/70 backdrop-blur-xl backdrop-saturate-150",
        "shadow-[0_1px_2px_rgb(0_0_0/0.04),0_8px_24px_-12px_rgb(0_0_0/0.12)]",
        "transition-shadow duration-300 hover:shadow-[0_1px_2px_rgb(0_0_0/0.05),0_16px_40px_-16px_rgb(0_0_0/0.22)]",
        "dark:bg-card/55 dark:shadow-[0_1px_2px_rgb(0_0_0/0.3),0_12px_32px_-16px_rgb(0_0_0/0.6)]",
        // El contenido por encima del foco: si no, el tinte de luz cae sobre
        // los numeros y les baja el contraste.
        "[&>*]:relative [&>*]:z-[1]",
        brillo === "marca" && "borde-brillo",
        brillo === "atencion" && "borde-brillo borde-brillo-atencion",
        className,
      )}
      {...props}
    />
  );
}

/**
 * El icono de un encabezado, que entra girando y vuelve a saltar cada vez que
 * su dato cambia (`clave`). Un movimiento por cambio, nunca en bucle.
 */
export function IconoVivo({
  icono: Icono,
  clave,
  className,
}: {
  icono: ComponentType<{ className?: string }>;
  clave?: string | number;
  className?: string;
}) {
  const quieto = useReducedMotion();
  return (
    <motion.span
      key={clave}
      aria-hidden
      className="inline-flex"
      initial={quieto ? false : { rotate: -25, scale: 0.6, opacity: 0 }}
      animate={{ rotate: 0, scale: 1, opacity: 1 }}
      transition={{ type: "spring", stiffness: 420, damping: 16 }}
    >
      <Icono className={className} />
    </motion.span>
  );
}
