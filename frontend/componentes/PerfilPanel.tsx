"use client";

/**
 * Mi perfil: la foto, el nombre que ven los demás, y lo que no se cambia aquí.
 *
 * El correo y el rol se enseñan pero no se editan: el correo lo dice Google y
 * el rol lo da administración. Un formulario que dejara cambiarlos sería una
 * promesa que la API no cumple.
 *
 * El invitado ve su perfil pero no lo cambia: es una cuenta que comparte todo
 * el público, y lo que uno escribiera ahí lo vería el siguiente que entra.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Camera, LoaderCircle, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { api, type Perfil } from "@/lib/api";
import { hace } from "@/lib/textos";

import { Avatar } from "./Avatar";

export function nombreDelRol(perfil: Pick<Perfil, "role" | "permissions">): string {
  if (perfil.role === "admin") return "Administración";
  if (perfil.role === "operator") return "Despacho";
  return perfil.permissions.includes("despachar") ? "Invitado" : "Invitado · solo mira";
}

export function PerfilPanel({
  perfil,
  abierto,
  onAbierto,
}: {
  perfil: Perfil;
  abierto: boolean;
  onAbierto: (v: boolean) => void;
}) {
  return (
    <Sheet open={abierto} onOpenChange={onAbierto}>
      {/* Con el prefijo de lado: el Sheet trae `data-[side=right]:w-3/4` y
          `sm:max-w-sm`, que pisan un `w-full` suelto y dejaban el panel a tres
          cuartos en el celular. */}
      <SheetContent
        side="right"
        className="gap-0 p-0 data-[side=right]:w-full data-[side=right]:sm:max-w-md"
      >
        <SheetHeader className="border-b px-5 py-4">
          <SheetTitle>Mi perfil</SheetTitle>
          <SheetDescription>Cómo te ven los demás en el tablero.</SheetDescription>
        </SheetHeader>
        {/* Se monta de nuevo al abrir: el borrador del nombre parte siempre
            del perfil actual y no de lo que quedó escrito la vez anterior. */}
        {abierto && <Contenido perfil={perfil} />}
      </SheetContent>
    </Sheet>
  );
}

function Contenido({ perfil }: { perfil: Perfil }) {
  const cliente = useQueryClient();
  const archivo = useRef<HTMLInputElement>(null);
  const [nombre, setNombre] = useState(perfil.display_name ?? "");
  const editable = perfil.role !== "demo";

  const alCambiar = (p: Perfil) => cliente.setQueryData(["yo"], p);
  const fallo = (e: Error) => toast.error(e.message);

  const subir = useMutation({
    mutationFn: api.subirFoto,
    onSuccess: (p) => {
      alCambiar(p);
      toast.success("Foto actualizada");
    },
    onError: fallo,
  });
  const quitar = useMutation({
    mutationFn: api.quitarFoto,
    onSuccess: (p) => {
      alCambiar(p);
      toast.success(p.avatar_url ? "Volviste a la foto de Google" : "Foto quitada");
    },
    onError: fallo,
  });
  const guardar = useMutation({
    mutationFn: api.cambiarNombre,
    onSuccess: (p) => {
      alCambiar(p);
      toast.success("Nombre guardado");
    },
    onError: fallo,
  });

  const limpio = nombre.trim();
  const nombreValido = limpio.length >= 1 && limpio.length <= 64 && !/[<>]/.test(limpio);
  const cambioNombre = limpio !== (perfil.display_name ?? "");
  // Solo se puede quitar la foto propia: la de Google no vive aquí.
  const tieneFotoPropia = Boolean(perfil.avatar_propio);

  return (
    <div className="space-y-6 overflow-y-auto px-5 py-5">
      <div className="flex items-center gap-4">
        <Avatar
          url={perfil.avatar_url}
          nombre={perfil.display_name}
          email={perfil.email}
          className="size-20 text-xl"
        />
        {editable ? (
          <div className="flex flex-wrap gap-2">
            {/* `image/*` y no una lista cerrada: en el celular eso es lo que
                ofrece la cámara además de la galería. */}
            <input
              ref={archivo}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) subir.mutate(f);
                e.target.value = "";
              }}
            />
            <Button
              size="sm"
              variant="outline"
              onClick={() => archivo.current?.click()}
              disabled={subir.isPending}
            >
              {subir.isPending ? <LoaderCircle className="animate-spin" /> : <Camera />}
              {subir.isPending ? "Subiendo…" : perfil.avatar_url ? "Cambiar foto" : "Subir foto"}
            </Button>
            {tieneFotoPropia && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => quitar.mutate()}
                disabled={quitar.isPending}
              >
                <Trash2 />
                Quitar
              </Button>
            )}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            La cuenta de prueba es compartida: su nombre y su foto no se cambian.
          </p>
        )}
      </div>

      <form
        className="space-y-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (nombreValido && cambioNombre) guardar.mutate(limpio);
        }}
      >
        <Label htmlFor="nombre-perfil">Nombre visible</Label>
        <div className="flex gap-2">
          <Input
            id="nombre-perfil"
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            maxLength={64}
            disabled={!editable}
            aria-invalid={limpio.length > 0 && !nombreValido}
          />
          {editable && (
            <Button
              type="submit"
              disabled={!nombreValido || !cambioNombre || guardar.isPending}
            >
              Guardar
            </Button>
          )}
        </div>
        {limpio.length > 0 && !nombreValido && (
          <p className="text-xs text-destructive">Entre 1 y 64 caracteres, sin &lt; ni &gt;.</p>
        )}
      </form>

      <dl className="space-y-3 border-t pt-5 text-sm">
        <Dato etiqueta="Correo" valor={perfil.email} />
        <Dato etiqueta="Rol" valor={nombreDelRol(perfil)} />
        <Dato
          etiqueta="Última entrada"
          valor={perfil.last_login_at ? hace(perfil.last_login_at) : "—"}
        />
      </dl>
    </div>
  );
}

function Dato({ etiqueta, valor }: { etiqueta: string; valor: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="text-muted-foreground">{etiqueta}</dt>
      <dd className="truncate text-right">{valor}</dd>
    </div>
  );
}
