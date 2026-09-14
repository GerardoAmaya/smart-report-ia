import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { TooltipProvider } from "@/components/ui/tooltip";
import { Proveedores } from "@/lib/sesion";
import { Tema } from "@/lib/tema";
import "./globals.css";

// Las variables van en <html> y no en <body>: shadcn genera estilos que las
// esperan en la raiz, y en <body> quedan fuera del alcance de los portales
// (dialogos, menus), que Radix monta fuera del arbol.
const sans = Geist({ subsets: ["latin"], variable: "--font-geist-sans", display: "swap" });
const mono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono", display: "swap" });

export const metadata: Metadata = {
  title: "Smart Report",
  description: "Reportes ciudadanos de hallazgos en la vía pública de El Salvador",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <body>
        <Tema>
          <Proveedores>
            <TooltipProvider delayDuration={200}>{children}</TooltipProvider>
          </Proveedores>
        </Tema>
      </body>
    </html>
  );
}
