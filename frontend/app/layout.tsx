import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Smart Report",
  description: "Reportes ciudadanos de hallazgos en la via publica",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
