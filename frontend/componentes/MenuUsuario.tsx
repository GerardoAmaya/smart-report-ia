"use client";

/**
 * Quién está dentro, y lo que se hace con la cuenta: perfil, usuarios y salir.
 *
 * El tema ya no vive aquí: va suelto en la barra, porque se cambia más de lo
 * que se pensaba —al pasar de la oficina a la calle— y escondido en un menú
 * nadie lo encontraba.
 *
 * Dice el rol en palabras y en color. Un invitado que no sabe que solo mira se
 * topa con botones que no están y cree que el tablero está roto.
 */
import { useQueryClient } from "@tanstack/react-query";
import { LogOut, UserRound, UsersRound, type LucideIcon } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { api, type Perfil } from "@/lib/api";
import { cn } from "@/lib/utils";

import { AvatarConAnillo, InsigniaRol } from "./AvatarRol";
import { nombreDelRol, PerfilPanel } from "./PerfilPanel";
import { UsuariosPanel } from "./UsuariosPanel";

export function MenuUsuario({ perfil }: { perfil: Perfil }) {
  const router = useRouter();
  const cliente = useQueryClient();
  const quieto = useReducedMotion();
  const [abierto, setAbierto] = useState(false);
  const [verPerfil, setVerPerfil] = useState(false);
  const [verUsuarios, setVerUsuarios] = useState(false);
  const gestiona = perfil.permissions.includes("gestionar_usuarios");

  async function salir() {
    await api.salir();
    // Se limpia la cache: sin esto el perfil viejo sobrevive y la pantalla de
    // entrada rebota al tablero.
    cliente.clear();
    router.push("/entrar");
  }

  const opciones: { icono: LucideIcon; texto: string; alElegir: () => void; peligro?: boolean }[] = [
    { icono: UserRound, texto: "Mi perfil", alElegir: () => setVerPerfil(true) },
    ...(gestiona
      ? [{ icono: UsersRound, texto: "Usuarios", alElegir: () => setVerUsuarios(true) }]
      : []),
  ];

  return (
    <>
      {/* modal={false}: con el menu modal, abrir un panel desde una de sus
          opciones dejaba la pagina sin poder hacer clic al cerrarlo. */}
      <DropdownMenu modal={false} open={abierto} onOpenChange={setAbierto}>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" className="h-9 gap-2 px-1" aria-label="Menú de usuario">
            <AvatarConAnillo
              rol={perfil.role}
              url={perfil.avatar_url}
              nombre={perfil.display_name}
              email={perfil.email}
              tamano="xs"
              enLinea
            />
            <span className="hidden max-w-40 truncate text-xs text-muted-foreground md:inline">
              {perfil.display_name ?? perfil.email}
            </span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-64 overflow-hidden p-0">
          {/* El muelle va dentro del contenido y no en el contenedor de Radix:
              ese ya anima su propia entrada y las dos se pisarian. */}
          <motion.div
            initial={quieto ? false : { opacity: 0, y: -8, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ type: "spring", stiffness: 420, damping: 26 }}
            className="origin-top-right p-1"
          >
            <DropdownMenuLabel className="relative overflow-hidden rounded-md p-3 font-normal">
              {/* Un velo de la paleta detras de la cabecera: dice "esta es tu
                  cuenta" sin otra tarjeta mas. */}
              <span
                aria-hidden
                className="absolute inset-0 bg-[radial-gradient(120%_120%_at_0%_0%,color-mix(in_oklab,var(--primary)_16%,transparent),transparent_60%),radial-gradient(90%_90%_at_100%_100%,color-mix(in_oklab,var(--atencion)_14%,transparent),transparent_60%)]"
              />
              <span className="relative flex items-center gap-3">
                <AvatarConAnillo
                  rol={perfil.role}
                  url={perfil.avatar_url}
                  nombre={perfil.display_name}
                  email={perfil.email}
                  tamano="md"
                  enLinea
                />
                <span className="min-w-0 space-y-1">
                  <span className="block truncate text-sm font-semibold text-foreground">
                    {perfil.display_name ?? perfil.email.split("@")[0]}
                  </span>
                  <InsigniaRol rol={perfil.role} etiqueta={nombreDelRol(perfil)} />
                </span>
              </span>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            {opciones.map((o, i) => (
              <Opcion key={o.texto} {...o} indice={i} quieto={Boolean(quieto)} />
            ))}
            <DropdownMenuSeparator />
            <Opcion
              icono={LogOut}
              texto="Salir"
              alElegir={salir}
              indice={opciones.length}
              quieto={Boolean(quieto)}
              peligro
            />
          </motion.div>
        </DropdownMenuContent>
      </DropdownMenu>

      <PerfilPanel perfil={perfil} abierto={verPerfil} onAbierto={setVerPerfil} />
      {gestiona && (
        <UsuariosPanel abierto={verUsuarios} onAbierto={setVerUsuarios} miEmail={perfil.email} />
      )}
    </>
  );
}

function Opcion({
  icono: Icono,
  texto,
  alElegir,
  indice,
  quieto,
  peligro,
}: {
  icono: LucideIcon;
  texto: string;
  alElegir: () => void;
  indice: number;
  quieto: boolean;
  peligro?: boolean;
}) {
  return (
    <DropdownMenuItem onSelect={alElegir} className="group gap-2.5 py-2" asChild>
      <motion.div
        initial={quieto ? false : { opacity: 0, x: 6 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 0.04 + indice * 0.04, duration: 0.18 }}
      >
        <span
          className={cn(
            "flex size-7 items-center justify-center rounded-md bg-muted transition-transform duration-200",
            "group-hover:-rotate-6 group-hover:scale-110 group-focus:-rotate-6 group-focus:scale-110",
            "motion-reduce:transition-none motion-reduce:group-hover:transform-none",
            peligro ? "text-muted-foreground group-hover:text-destructive" : "text-primary",
          )}
        >
          <Icono className="size-4" aria-hidden />
        </span>
        <span className="transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transform-none">
          {texto}
        </span>
      </motion.div>
    </DropdownMenuItem>
  );
}
