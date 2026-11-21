"use client";

/**
 * Quién puede entrar al tablero. Solo administración lo ve.
 *
 * **Autorizar no crea cuentas.** Google dice quién es; esta lista dice si puede
 * entrar. Autorizar un correo solo deja pasar a esa persona cuando entre con
 * Google; no le llega nada.
 *
 * Las reglas que evitan dejar el tablero sin dueño las decide la API —nadie se
 * desactiva ni se quita el rol a sí mismo, siempre queda un administrador
 * activo—; aquí solo se evita ofrecer lo que va a fallar, y si falla, se dice
 * por qué con el mensaje de la API.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LoaderCircle, UserPlus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type Usuario } from "@/lib/api";
import { hace } from "@/lib/textos";

import { Avatar } from "./Avatar";

const ROLES: Record<Usuario["role"], string> = {
  operator: "Despacho",
  admin: "Administración",
};

export function UsuariosPanel({
  abierto,
  onAbierto,
  miEmail,
}: {
  abierto: boolean;
  onAbierto: (v: boolean) => void;
  miEmail: string;
}) {
  return (
    <Sheet open={abierto} onOpenChange={onAbierto}>
      {/* Con el prefijo de lado, igual que en Mi perfil: sin el, el Sheet se
          quedaba en su ancho por defecto y la fila de cada usuario se apretaba. */}
      <SheetContent
        side="right"
        className="gap-0 p-0 data-[side=right]:w-full data-[side=right]:sm:max-w-2xl"
      >
        <SheetHeader className="border-b px-5 py-4">
          <SheetTitle>Usuarios</SheetTitle>
          <SheetDescription>
            Quién puede entrar al tablero. Autorizar un correo no le manda nada: solo lo deja
            pasar cuando entre con Google.
          </SheetDescription>
        </SheetHeader>
        {abierto && <Contenido miEmail={miEmail} />}
      </SheetContent>
    </Sheet>
  );
}

function Contenido({ miEmail }: { miEmail: string }) {
  const cliente = useQueryClient();
  const { data, isLoading, error } = useQuery({ queryKey: ["usuarios"], queryFn: api.usuarios });

  const refrescar = () => cliente.invalidateQueries({ queryKey: ["usuarios"] });

  return (
    <div className="space-y-6 overflow-y-auto px-5 py-5">
      <Autorizar alAutorizar={refrescar} />

      <section aria-label="Usuarios autorizados" className="space-y-2">
        {isLoading && (
          <div className="space-y-2">
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        )}
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {(error as Error).message}
          </p>
        )}
        {data?.usuarios.map((u) => (
          <Fila key={u.id} usuario={u} soyYo={u.email === miEmail} alCambiar={refrescar} />
        ))}
      </section>
    </div>
  );
}

function Autorizar({ alAutorizar }: { alAutorizar: () => void }) {
  const [email, setEmail] = useState("");
  const [rol, setRol] = useState<Usuario["role"]>("operator");

  const autorizar = useMutation({
    mutationFn: () => api.autorizarUsuario(email.trim(), rol),
    onSuccess: (u) => {
      toast.success("Correo autorizado", {
        description: `${u.email} ya puede entrar con Google como ${ROLES[u.role].toLowerCase()}.`,
      });
      setEmail("");
      alAutorizar();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <form
      className="space-y-2 rounded-xl border bg-card p-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (email.trim()) autorizar.mutate();
      }}
    >
      <Label htmlFor="correo-nuevo">Autorizar un correo</Label>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Input
          id="correo-nuevo"
          type="email"
          inputMode="email"
          autoComplete="off"
          placeholder="nombre@institucion.gob.sv"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="sm:flex-1"
        />
        <Select value={rol} onValueChange={(v) => setRol(v as Usuario["role"])}>
          <SelectTrigger className="sm:w-44" aria-label="Rol del correo nuevo">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="operator">Despacho</SelectItem>
            <SelectItem value="admin">Administración</SelectItem>
          </SelectContent>
        </Select>
        <Button type="submit" disabled={!email.trim() || autorizar.isPending}>
          {autorizar.isPending ? <LoaderCircle className="animate-spin" /> : <UserPlus />}
          Autorizar
        </Button>
      </div>
    </form>
  );
}

function Fila({
  usuario,
  soyYo,
  alCambiar,
}: {
  usuario: Usuario;
  soyYo: boolean;
  alCambiar: () => void;
}) {
  const cambiar = useMutation({
    mutationFn: (c: { role?: Usuario["role"]; is_active?: boolean }) =>
      api.cambiarUsuario(usuario.id, c),
    onSuccess: (u, c) => {
      if (c.is_active === false) toast.success("Acceso quitado", { description: u.email });
      else if (c.is_active === true) toast.success("Acceso devuelto", { description: u.email });
      else toast.success(`Ahora es ${ROLES[u.role].toLowerCase()}`, { description: u.email });
      alCambiar();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    // En el celular cada usuario es una tarjeta apilada; en pantalla ancha, una
    // fila con todo a la vista.
    <div
      className={
        "flex flex-col gap-3 rounded-xl border p-3 md:flex-row md:items-center " +
        (usuario.is_active ? "bg-card" : "bg-muted/40 opacity-75")
      }
    >
      <div className="flex min-w-0 flex-1 items-center gap-3 md:min-w-56">
        <Avatar
          url={usuario.avatar_url}
          nombre={usuario.display_name}
          email={usuario.email}
          className="size-9 text-xs"
        />
        <div className="min-w-0">
          <p className="flex items-center gap-2 truncate text-sm font-medium">
            {usuario.display_name ?? usuario.email.split("@")[0]}
            {soyYo && <Badge variant="secondary">Tú</Badge>}
            {!usuario.is_active && <Badge variant="outline">Sin acceso</Badge>}
          </p>
          <p className="truncate text-xs text-muted-foreground">{usuario.email}</p>
          <p className="text-xs text-muted-foreground">
            {usuario.last_login_at
              ? `Entró ${hace(usuario.last_login_at)}`
              : "Todavía no ha entrado"}
          </p>
        </div>
      </div>

      <div className="flex shrink-0 flex-wrap items-center gap-2">
        <Select
          value={usuario.role}
          onValueChange={(v) => cambiar.mutate({ role: v as Usuario["role"] })}
          // Quitarse el rol a sí mismo lo rechaza la API; aquí ni se ofrece.
          disabled={soyYo || cambiar.isPending}
        >
          <SelectTrigger className="w-40" aria-label={`Rol de ${usuario.email}`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="operator">Despacho</SelectItem>
            <SelectItem value="admin">Administración</SelectItem>
          </SelectContent>
        </Select>

        {usuario.is_active ? (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="outline" size="sm" disabled={soyYo || cambiar.isPending}>
                Quitar acceso
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>¿Quitarle el acceso a {usuario.email}?</AlertDialogTitle>
                <AlertDialogDescription>
                  Deja de poder entrar desde su siguiente clic, aunque tenga el tablero abierto.
                  Lo que despachó queda como está, y se le puede devolver el acceso cuando haga
                  falta.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancelar</AlertDialogCancel>
                <AlertDialogAction onClick={() => cambiar.mutate({ is_active: false })}>
                  Quitar acceso
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        ) : (
          <Button
            variant="outline"
            size="sm"
            onClick={() => cambiar.mutate({ is_active: true })}
            disabled={cambiar.isPending}
          >
            Devolver acceso
          </Button>
        )}
      </div>
    </div>
  );
}
