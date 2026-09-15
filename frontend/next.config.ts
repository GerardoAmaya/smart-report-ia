import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  // Salida autocontenida para la imagen de produccion: trae solo lo que el
  // servidor necesita en vez de node_modules entero, que son cientos de MB.
  output: "standalone",
};

export default config;
