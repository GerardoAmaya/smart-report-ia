"use client";

/**
 * La cara de alguien, o sus iniciales.
 *
 * Con respaldo de verdad: si la foto no carga —un enlace firmado que caducó, la
 * de Google que ya no existe— se vuelve a las iniciales en vez de dejar el
 * icono de imagen rota, que es lo que hace parecer roto un tablero entero.
 */
import { useState } from "react";

import { cn } from "@/lib/utils";

export function iniciales(nombre: string | null | undefined, email: string): string {
  const base = nombre || email;
  const partes = base.replace(/@.*/, "").split(/[\s._-]+/).filter(Boolean);
  return (partes[0]?.[0] ?? "?").concat(partes[1]?.[0] ?? "").toUpperCase();
}

export function Avatar({
  url,
  nombre,
  email,
  className,
}: {
  url?: string | null;
  nombre?: string | null;
  email: string;
  className?: string;
}) {
  // Se recuerda que URL fallo y no un booleano: si llega otra URL (una foto
  // nueva) se vuelve a intentar sin un efecto que reinicie el estado.
  const [fallida, setFallida] = useState<string | null>(null);
  const foto = url && url !== fallida ? url : null;

  return (
    <span
      aria-hidden
      className={cn(
        "relative inline-flex size-6 shrink-0 items-center justify-center overflow-hidden rounded-full bg-primary text-[10px] font-semibold text-primary-foreground",
        className,
      )}
    >
      {foto ? (
        // eslint-disable-next-line @next/next/no-img-element -- firmada y de vida corta, como las demás fotos del tablero
        <img
          src={foto}
          alt=""
          referrerPolicy="no-referrer"
          className="size-full object-cover"
          onError={() => setFallida(foto)}
        />
      ) : (
        iniciales(nombre, email)
      )}
    </span>
  );
}
