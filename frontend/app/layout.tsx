import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { Toaster } from "@/components/ui/sonner";
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

// `viewport-fit=cover` para que `env(safe-area-inset-*)` tenga valor: sin
// esto vale 0 y la barra inferior del celular queda bajo la raya de gestos.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <body>
        <Tema>
          <Proveedores>
            <TooltipProvider delayDuration={200}>{children}</TooltipProvider>
            {/* Confirma lo que hizo una accion de despacho. Abajo a la derecha:
                lejos de la cola, que es donde estan los ojos. */}
            <Toaster position="bottom-right" closeButton />
          </Proveedores>
        </Tema>
      </body>
    </html>
  );
}
