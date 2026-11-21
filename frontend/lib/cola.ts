/**
 * La cola paginada, en un solo sitio.
 *
 * La usan la cola y el robot del asistente (que cuenta urgentes de lo que ya
 * esta en cache). Con las mismas opciones comparten la entrada de cache; con
 * una `useQuery` normal y la misma clave, TanStack mezclaria dos formas de dato
 * y la que llegara segunda romperia a la otra.
 *
 * La clave empieza por "casos": lo que invalida el tablero en vivo y el despacho
 * (`["casos"]`) refresca tambien estas paginas, todas las que ya se cargaron.
 */
import { infiniteQueryOptions } from "@tanstack/react-query";

import { api, type Caso, type PaginaCasos } from "@/lib/api";

export function opcionesCola(filtro: string) {
  return infiniteQueryOptions({
    queryKey: ["casos", "cola", filtro],
    queryFn: ({ pageParam }) =>
      api.casos(filtro ? { status: filtro } : undefined, { cursor: pageParam }),
    initialPageParam: null as string | null,
    getNextPageParam: (ultima: PaginaCasos) => ultima.next_cursor ?? undefined,
  });
}

/** Los casos de todas las paginas cargadas, en orden. */
export function casosCargados(paginas: PaginaCasos[] | undefined): Caso[] {
  return paginas?.flatMap((p) => p.cases) ?? [];
}
