import nextConfig from "eslint-config-next/core-web-vitals";

// El paquete puede exportar un array o un objeto segun la version; normalizamos.
const base = Array.isArray(nextConfig) ? nextConfig : [nextConfig];

const config = [...base, { ignores: [".next/**", "node_modules/**"] }];

export default config;
