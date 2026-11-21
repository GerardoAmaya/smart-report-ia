"use client";

/**
 * Un numero que cuenta hasta su valor.
 *
 * Al aparecer cuenta desde cero, y cuando cambia en vivo cuenta desde el valor
 * anterior: el movimiento dice "esto cambio", que es informacion. Corto —menos
 * de un segundo— porque quien mira el tablero ocho horas no espera a que un
 * numero termine de llegar.
 *
 * **El valor exacto va aparte, para lectores de pantalla.** Lo animado es
 * `aria-hidden`: un lector que leyera cada paso de la cuenta seria ruido, y
 * quien lea el numero a mitad de la animacion —una persona con lector, o una
 * prueba— tiene que ver el valor real, no uno intermedio.
 */
import { animate, useReducedMotion } from "motion/react";
import { useEffect, useRef } from "react";

export function Contador({
  valor,
  className,
  cifra,
}: {
  valor: number;
  className?: string;
  /** Marca para encontrar el valor exacto desde fuera (`data-cifra`). */
  cifra?: string;
}) {
  const visible = useRef<HTMLSpanElement>(null);
  const anterior = useRef(0);
  const quieto = useReducedMotion();

  useEffect(() => {
    const el = visible.current;
    if (!el) return;
    const desde = anterior.current;
    anterior.current = valor;
    if (quieto || desde === valor) {
      el.textContent = String(valor);
      return;
    }
    const control = animate(desde, valor, {
      duration: 0.8,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => {
        el.textContent = String(Math.round(v));
      },
    });
    return () => control.stop();
  }, [valor, quieto]);

  return (
    <span className={className}>
      <span className="sr-only" data-cifra={cifra}>
        {valor}
      </span>
      <span ref={visible} aria-hidden>
        {quieto ? valor : 0}
      </span>
    </span>
  );
}
