"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/**
 * Cambiar entre claro y oscuro.
 *
 * Los dos iconos estan siempre en el DOM y **CSS decide cual se ve**. La forma
 * habitual —un estado `montado` que se activa en un efecto— existe porque el
 * servidor no sabe que tema eligio el navegador; pero escribir estado dentro de
 * un efecto provoca un render en cascada, y aqui no hace falta: la clase `dark`
 * ya esta en el html cuando el CSS se aplica, asi que no hay desajuste que
 * arreglar.
 */
export function CambiarTema() {
  const { resolvedTheme, setTheme } = useTheme();

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
          aria-label="Cambiar entre tema claro y oscuro"
        >
          <Moon className="size-4 dark:hidden" />
          <Sun className="hidden size-4 dark:block" />
        </Button>
      </TooltipTrigger>
      <TooltipContent>Cambiar tema</TooltipContent>
    </Tooltip>
  );
}
