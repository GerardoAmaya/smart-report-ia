"use client";

/**
 * Claro y oscuro.
 *
 * El claro manda: es una herramienta de escritorio que alguien mira ocho horas
 * con luz de oficina. El oscuro esta porque sale casi gratis con tokens.
 *
 * `disableTransitionOnChange` evita que todo el tablero haga una transicion de
 * color al cambiar de tema: se ve mal y tarda.
 */
import { ThemeProvider } from "next-themes";

export function Tema({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="light"
      enableSystem
      disableTransitionOnChange
    >
      {children}
    </ThemeProvider>
  );
}
