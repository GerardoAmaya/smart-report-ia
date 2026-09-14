"use client";

/**
 * Quien esta usando el tablero.
 *
 * Los permisos que llegan de aqui sirven para **no ofrecer** botones que van a
 * fallar. No para proteger nada: la comprobacion de verdad esta en la API, y
 * esconder un boton no impide llamarla.
 */
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { createContext, useContext, useState } from "react";

import { api, type Perfil, SinSesion } from "./api";

const SesionCtx = createContext<{
  perfil: Perfil | null;
  cargando: boolean;
  sinSesion: boolean;
  error: string | null;
}>({ perfil: null, cargando: true, sinSesion: false, error: null });

export function useSesion() {
  return useContext(SesionCtx);
}

export function puede(perfil: Perfil | null, permiso: string): boolean {
  return perfil?.permissions.includes(permiso) ?? false;
}

function Proveedor({ children }: { children: React.ReactNode }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["yo"],
    queryFn: api.yo,
    // Sin sesion no se reintenta: no va a mejorar solo y cada intento retrasa
    // la pantalla de entrada.
    retry: (intentos, e) => !(e instanceof SinSesion) && intentos < 2,
  });

  return (
    <SesionCtx.Provider
      value={{
        perfil: data ?? null,
        cargando: isLoading,
        sinSesion: error instanceof SinSesion,
        error: error && !(error instanceof SinSesion) ? error.message : null,
      }}
    >
      {children}
    </SesionCtx.Provider>
  );
}

export function Proveedores({ children }: { children: React.ReactNode }) {
  const [cliente] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Diez segundos: el tablero se mira ocho horas y los reportes
            // entran solos. Mas fresco seria pedir sin que nada haya cambiado.
            staleTime: 10_000,
            refetchOnWindowFocus: true,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={cliente}>
      <Proveedor>{children}</Proveedor>
    </QueryClientProvider>
  );
}
