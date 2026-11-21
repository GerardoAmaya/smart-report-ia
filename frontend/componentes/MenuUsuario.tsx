"use client";

/**
 * Quién está dentro, y lo que se hace con la cuenta: perfil, usuarios y salir.
 *
 * El tema ya no vive aquí: va suelto en la barra, porque se cambia más de lo
 * que se pensaba —al pasar de la oficina a la calle— y escondido en un menú
 * nadie lo encontraba.
 *
 * Dice el rol en palabras. Un invitado que no sabe que solo mira se topa con
 * botones que no están y cree que el tablero está roto.
 */
import { useQueryClient } from "@tanstack/react-query";
import { LogOut, UserRound, UsersRound } from "lucide-react";
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

import { Avatar } from "./Avatar";
import { nombreDelRol, PerfilPanel } from "./PerfilPanel";
import { UsuariosPanel } from "./UsuariosPanel";

export function MenuUsuario({ perfil }: { perfil: Perfil }) {
  const router = useRouter();
  const cliente = useQueryClient();
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

  return (
    <>
      {/* modal={false}: con el menu modal, abrir un panel desde una de sus
          opciones dejaba la pagina sin poder hacer clic al cerrarlo. */}
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" className="h-8 gap-2 px-1.5" aria-label="Menú de usuario">
            <Avatar url={perfil.avatar_url} nombre={perfil.display_name} email={perfil.email} />
            <span className="hidden max-w-40 truncate text-xs text-muted-foreground md:inline">
              {perfil.display_name ?? perfil.email}
            </span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-60">
          <DropdownMenuLabel className="flex items-center gap-3 font-normal">
            <Avatar
              url={perfil.avatar_url}
              nombre={perfil.display_name}
              email={perfil.email}
              className="size-9 text-xs"
            />
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium">
                {perfil.display_name ?? perfil.email}
              </span>
              <span className="block truncate text-xs text-muted-foreground">
                {nombreDelRol(perfil)}
              </span>
            </span>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => setVerPerfil(true)}>
            <UserRound />
            Mi perfil
          </DropdownMenuItem>
          {gestiona && (
            <DropdownMenuItem onSelect={() => setVerUsuarios(true)}>
              <UsersRound />
              Usuarios
            </DropdownMenuItem>
          )}
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={salir}>
            <LogOut />
            Salir
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <PerfilPanel perfil={perfil} abierto={verPerfil} onAbierto={setVerPerfil} />
      {gestiona && (
        <UsuariosPanel abierto={verUsuarios} onAbierto={setVerUsuarios} miEmail={perfil.email} />
      )}
    </>
  );
}
