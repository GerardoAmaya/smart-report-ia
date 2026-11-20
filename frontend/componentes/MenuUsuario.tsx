"use client";

/**
 * Quien esta dentro, y lo que se hace con la sesion: tema y salir.
 *
 * Juntos en un menu y no sueltos en el encabezado: son cosas que se tocan una
 * vez al dia, y sueltas le quitaban sitio a lo que se usa todo el rato.
 *
 * Dice el rol en palabras. Un invitado que no sabe que solo mira se topa con
 * botones que no estan y cree que el tablero esta roto.
 */
import { useQueryClient } from "@tanstack/react-query";
import { LogOut, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";

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

/** El rol en palabras, sacado de los permisos reales y no del nombre del rol:
 *  el invitado solo mira en produccion pero despacha en local y en las pruebas. */
function rol(perfil: Perfil): string {
  if (perfil.role === "admin") return "Administración";
  if (perfil.role === "operator") return "Despacho";
  return perfil.permissions.includes("despachar") ? "Invitado" : "Invitado · solo mira";
}

function iniciales(perfil: Perfil): string {
  const base = perfil.display_name ?? perfil.email;
  const partes = base.replace(/@.*/, "").split(/[\s._-]+/).filter(Boolean);
  return (partes[0]?.[0] ?? "?").concat(partes[1]?.[0] ?? "").toUpperCase();
}

export function MenuUsuario({ perfil }: { perfil: Perfil }) {
  const router = useRouter();
  const cliente = useQueryClient();
  const { resolvedTheme, setTheme } = useTheme();
  const oscuro = resolvedTheme === "dark";

  async function salir() {
    await api.salir();
    // Se limpia la cache: sin esto el perfil viejo sobrevive y la pantalla de
    // entrada rebota al tablero.
    cliente.clear();
    router.push("/entrar");
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="h-8 gap-2 px-1.5" aria-label="Menú de usuario">
          <span
            aria-hidden
            className="flex size-6 items-center justify-center rounded-full bg-primary text-[10px] font-semibold text-primary-foreground"
          >
            {iniciales(perfil)}
          </span>
          <span className="hidden max-w-40 truncate text-xs text-muted-foreground md:inline">
            {perfil.display_name ?? perfil.email}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel className="font-normal">
          <p className="truncate text-sm font-medium">{perfil.display_name ?? perfil.email}</p>
          <p className="truncate text-xs text-muted-foreground">{rol(perfil)}</p>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => setTheme(oscuro ? "light" : "dark")}>
          {oscuro ? <Sun /> : <Moon />}
          {oscuro ? "Tema claro" : "Tema oscuro"}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={salir}>
          <LogOut />
          Salir
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
