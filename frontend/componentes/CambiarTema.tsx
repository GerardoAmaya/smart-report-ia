"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import type { MouseEvent } from "react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/**
 * Cambiar entre claro y oscuro, con una transicion.
 *
 * El tema nuevo se abre como un circulo que crece desde el boton y cubre la
 * pantalla, en vez de un parpadeo de todo a la vez. Usa la View Transitions API
 * del navegador: congela la pantalla vieja, aplica el tema, y anima el recorte
 * de la nueva. Donde no existe (Firefox viejo) o con «reducir movimiento», el
 * tema cambia directo, como antes.
 *
 * Los dos iconos estan siempre en el DOM y **CSS decide cual se ve**, sin un
 * estado `montado`: la clase `dark` ya esta en el html cuando el CSS se aplica.
 * El que aparece entra girando, en vez de aparecer de golpe.
 */
export function CambiarTema() {
  const { resolvedTheme, setTheme } = useTheme();

  const cambiar = (e: MouseEvent<HTMLButtonElement>) => {
    const nuevo = resolvedTheme === "dark" ? "light" : "dark";
    const reducido = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!document.startViewTransition || reducido) {
      setTheme(nuevo);
      return;
    }

    // Centro del boton; el radio es la distancia a la esquina mas lejana, para
    // que el circulo termine cubriendo la pantalla entera.
    const caja = e.currentTarget.getBoundingClientRect();
    const x = caja.left + caja.width / 2;
    const y = caja.top + caja.height / 2;
    const radio = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));

    const transicion = document.startViewTransition(() => {
      // La clase se pone aqui, a mano y en el acto: next-themes la aplica en un
      // efecto, despues de esta captura, y la animacion recortaria el tema
      // viejo. setTheme vuelve a poner la misma y guarda la eleccion.
      const html = document.documentElement;
      html.classList.toggle("dark", nuevo === "dark");
      html.style.colorScheme = nuevo;
      setTheme(nuevo);
    });

    transicion.ready
      .then(() => {
        document.documentElement.animate(
          { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radio}px at ${x}px ${y}px)`] },
          {
            duration: 550,
            easing: "cubic-bezier(0.4, 0, 0.2, 1)",
            pseudoElement: "::view-transition-new(root)",
          },
        );
      })
      // Si el navegador cancela la transicion, el tema ya quedo puesto.
      .catch(() => {});
  };

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button variant="ghost" size="icon" onClick={cambiar} aria-label="Cambiar tema">
          <span className="relative size-4">
            {/* Con keyframes y no con transition: next-themes apaga todas las
                transiciones justo al cambiar de tema, y el giro quedaba cortado. */}
            <Moon className="icono-tema absolute inset-0 size-4 dark:hidden" />
            <Sun className="icono-tema absolute inset-0 hidden size-4 dark:block" />
          </span>
        </Button>
      </TooltipTrigger>
      <TooltipContent>Cambiar tema</TooltipContent>
    </Tooltip>
  );
}
