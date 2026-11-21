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
 *
 * Tarjetas y no una tabla: es una lista de personas, no de registros, y la
 * cara y el color del rol se reconocen antes que una columna de texto.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Clock,
  HardHat,
  LoaderCircle,
  MailPlus,
  Search,
  Send,
  ShieldCheck,
  UserCheck,
  UserX,
  UsersRound,
} from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useMemo, useState } from "react";
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
} from "@/components/ui/alert-dialog";
import { BorderBeam } from "@/components/ui/border-beam";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
import { cn } from "@/lib/utils";

import { AvatarApilados, AvatarConAnillo, InsigniaRol, ROL_VISUAL } from "./AvatarRol";
import { Contador } from "./Contador";

type Filtro = "todos" | "admin" | "operator" | "sin-acceso";

const FILTROS: { valor: Filtro; texto: string }[] = [
  { valor: "todos", texto: "Todos" },
  { valor: "admin", texto: "Administración" },
  { valor: "operator", texto: "Despacho" },
  { valor: "sin-acceso", texto: "Sin acceso" },
];

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
          quedaba en su ancho por defecto y las tarjetas se apretaban. */}
      <SheetContent
        side="right"
        className="gap-0 p-0 data-[side=right]:w-full data-[side=right]:sm:max-w-2xl"
      >
        <SheetHeader className="border-b px-5 py-4">
          <SheetTitle className="flex items-center gap-2">
            <UsersRound className="size-4 text-primary" aria-hidden />
            Usuarios
          </SheetTitle>
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
  const quieto = useReducedMotion();
  const { data, isLoading, error } = useQuery({ queryKey: ["usuarios"], queryFn: api.usuarios });
  const [filtro, setFiltro] = useState<Filtro>("todos");
  const [busqueda, setBusqueda] = useState("");

  const refrescar = () => cliente.invalidateQueries({ queryKey: ["usuarios"] });

  const usuarios = useMemo(() => data?.usuarios ?? [], [data]);
  const conAcceso = usuarios.filter((u) => u.is_active).length;
  const visibles = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    return usuarios.filter((u) => {
      if (filtro === "sin-acceso" && u.is_active) return false;
      if ((filtro === "admin" || filtro === "operator") && (u.role !== filtro || !u.is_active))
        return false;
      if (!q) return true;
      return `${u.display_name ?? ""} ${u.email}`.toLowerCase().includes(q);
    });
  }, [usuarios, filtro, busqueda]);

  const cuantos = (f: Filtro) =>
    f === "todos"
      ? usuarios.length
      : f === "sin-acceso"
        ? usuarios.length - conAcceso
        : usuarios.filter((u) => u.is_active && u.role === f).length;

  return (
    <div className="space-y-5 overflow-y-auto px-5 py-5">
      <Autorizar alAutorizar={refrescar} />

      {/* --- Cuántos y cuáles --- */}
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <span className="flex items-baseline gap-2">
            <span className="font-mono text-3xl font-semibold tracking-tight tabular-nums">
              <Contador valor={conAcceso} />
            </span>
            <span className="text-sm text-muted-foreground">
              {conAcceso === 1 ? "persona con acceso" : "personas con acceso"}
            </span>
          </span>
          <AvatarApilados
            className="ml-auto"
            personas={usuarios
              .filter((u) => u.is_active)
              .map((u) => ({ rol: u.role, url: u.avatar_url, nombre: u.display_name, email: u.email }))}
          />
        </div>

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <div role="tablist" aria-label="Filtrar por rol" className="flex flex-wrap gap-1.5">
            {FILTROS.map((f) => {
              const activo = filtro === f.valor;
              return (
                <button
                  key={f.valor}
                  type="button"
                  role="tab"
                  aria-selected={activo}
                  onClick={() => setFiltro(f.valor)}
                  className={cn(
                    "relative rounded-full px-3 py-1 text-xs font-medium transition-colors",
                    "focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                    activo ? "text-primary-foreground" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {/* La pildora se desliza de un filtro al otro: dice "cambiaste
                      de vista" sin que la lista salte de golpe. */}
                  {activo && (
                    <motion.span
                      layoutId="filtro-usuarios"
                      className="absolute inset-0 rounded-full bg-primary"
                      transition={
                        quieto ? { duration: 0 } : { type: "spring", stiffness: 500, damping: 35 }
                      }
                    />
                  )}
                  <span className="relative">
                    {f.texto} <span className="opacity-70">{cuantos(f.valor)}</span>
                  </span>
                </button>
              );
            })}
          </div>
          <div className="relative sm:ml-auto sm:w-48">
            <Search
              aria-hidden
              className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              type="search"
              aria-label="Buscar por nombre o correo"
              placeholder="Buscar persona"
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              className="h-8 pl-8 text-sm"
            />
          </div>
        </div>
      </div>

      {/* --- Las personas --- */}
      <section aria-label="Usuarios autorizados">
        {isLoading && (
          <div className="grid gap-3 md:grid-cols-2">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-36 w-full rounded-2xl" />
            ))}
          </div>
        )}
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {(error as Error).message}
          </p>
        )}
        {data && visibles.length === 0 && (
          <Vacio buscando={busqueda.trim().length > 0 || filtro !== "todos"} />
        )}
        <motion.ul layout={!quieto} className="grid gap-3 md:grid-cols-2">
          <AnimatePresence initial={!quieto}>
            {visibles.map((u, i) => (
              <Tarjeta
                key={u.id}
                usuario={u}
                indice={i}
                soyYo={u.email === miEmail}
                alCambiar={refrescar}
              />
            ))}
          </AnimatePresence>
        </motion.ul>
      </section>
    </div>
  );
}

/** Autorizar un correo: la tarjeta destacada de arriba. El sobre sale volando al enviar. */
function Autorizar({ alAutorizar }: { alAutorizar: () => void }) {
  const quieto = useReducedMotion();
  const [email, setEmail] = useState("");
  const [rol, setRol] = useState<Usuario["role"]>("operator");
  const [enviados, setEnviados] = useState(0);

  const autorizar = useMutation({
    mutationFn: () => api.autorizarUsuario(email.trim(), rol),
    onSuccess: (u) => {
      setEnviados((n) => n + 1);
      toast.success("Correo autorizado", {
        description: `${u.email} ya puede entrar con Google como ${ROL_VISUAL[u.role].etiqueta.toLowerCase()}.`,
      });
      setEmail("");
      alAutorizar();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <form
      className="relative overflow-hidden rounded-2xl border border-primary/25 bg-gradient-to-br from-primary/8 via-card to-[color-mix(in_oklab,var(--atencion)_8%,var(--card))] p-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (email.trim()) autorizar.mutate();
      }}
    >
      {!quieto && (
        <BorderBeam
          size={70}
          duration={10}
          borderWidth={1.5}
          colorFrom="var(--primary)"
          colorTo="var(--atencion)"
        />
      )}
      <div className="mb-3 flex items-center gap-3">
        <span className="relative flex size-10 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-sm">
          {/* El sobre se va volando y vuelve uno nuevo: confirma el envio sin
              tapar el aviso de abajo. */}
          <AnimatePresence mode="popLayout" initial={false}>
            <motion.span
              key={enviados}
              initial={quieto ? false : { y: 14, opacity: 0, scale: 0.6 }}
              animate={{ y: 0, x: 0, opacity: 1, scale: 1, rotate: 0 }}
              exit={quieto ? undefined : { x: 28, y: -22, rotate: -20, opacity: 0 }}
              transition={{ type: "spring", stiffness: 380, damping: 22 }}
              className="flex"
            >
              {autorizar.isPending ? (
                <Send className="size-4.5" aria-hidden />
              ) : (
                <MailPlus className="size-4.5" aria-hidden />
              )}
            </motion.span>
          </AnimatePresence>
        </span>
        <div>
          <label htmlFor="correo-nuevo" className="text-sm font-semibold">
            Autorizar un correo
          </label>
          <p className="text-xs text-muted-foreground">
            Entra con Google con ese correo, y nada más.
          </p>
        </div>
      </div>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Input
          id="correo-nuevo"
          type="email"
          inputMode="email"
          autoComplete="off"
          placeholder="nombre@institucion.gob.sv"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="bg-background/80 sm:flex-1"
        />
        <SelectorRol
          valor={rol}
          alCambiar={setRol}
          etiqueta="Rol del correo nuevo"
          className="bg-background/80 sm:w-48"
        />
        <Button type="submit" disabled={!email.trim() || autorizar.isPending}>
          {autorizar.isPending ? <LoaderCircle className="animate-spin" /> : <Send />}
          Autorizar
        </Button>
      </div>
    </form>
  );
}

function SelectorRol({
  valor,
  alCambiar,
  etiqueta,
  deshabilitado,
  className,
}: {
  valor: Usuario["role"];
  alCambiar: (r: Usuario["role"]) => void;
  etiqueta: string;
  deshabilitado?: boolean;
  className?: string;
}) {
  return (
    <Select
      value={valor}
      onValueChange={(v) => alCambiar(v as Usuario["role"])}
      disabled={deshabilitado}
    >
      <SelectTrigger className={cn("w-44", className)} aria-label={etiqueta}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="operator">
          <HardHat className="text-primary" aria-hidden />
          Despacho
        </SelectItem>
        <SelectItem value="admin">
          <ShieldCheck className="text-primary" aria-hidden />
          Administración
        </SelectItem>
      </SelectContent>
    </Select>
  );
}

function Tarjeta({
  usuario,
  indice,
  soyYo,
  alCambiar,
}: {
  usuario: Usuario;
  indice: number;
  soyYo: boolean;
  alCambiar: () => void;
}) {
  const quieto = useReducedMotion();
  const [confirmar, setConfirmar] = useState(false);
  const nombre = usuario.display_name ?? usuario.email.split("@")[0];

  const cambiar = useMutation({
    mutationFn: (c: { role?: Usuario["role"]; is_active?: boolean }) =>
      api.cambiarUsuario(usuario.id, c),
    onSuccess: (u, c) => {
      if (c.is_active === false) toast.success("Acceso quitado", { description: u.email });
      else if (c.is_active === true) toast.success("Acceso devuelto", { description: u.email });
      else
        toast.success(`Ahora es de ${ROL_VISUAL[u.role].etiqueta.toLowerCase()}`, {
          description: u.email,
        });
      alCambiar();
    },
    // El mensaje de la API ya viene en español y dice por que: "no puedes
    // quitarte el rol a ti mismo", "tiene que quedar al menos un admin".
    onError: (e: Error) => toast.error("No se pudo hacer el cambio", { description: e.message }),
  });

  return (
    <motion.li
      layout={!quieto}
      initial={quieto ? false : { opacity: 0, y: 14 }}
      animate={{ opacity: usuario.is_active ? 1 : 0.6, y: 0, filter: usuario.is_active ? "none" : "saturate(0.2)" }}
      exit={quieto ? undefined : { opacity: 0, scale: 0.96 }}
      transition={{ duration: 0.25, delay: quieto ? 0 : Math.min(indice, 8) * 0.04 }}
      className={cn(
        "group relative flex flex-col gap-3 rounded-2xl border bg-card p-4 transition-shadow",
        "hover:shadow-[0_12px_30px_-18px_rgb(0_0_0/0.35)]",
        soyYo && "ring-1 ring-primary/30",
      )}
    >
      <div className="flex items-start gap-3">
        <AvatarConAnillo
          rol={usuario.role}
          url={usuario.avatar_url}
          nombre={usuario.display_name}
          email={usuario.email}
          tamano="md"
        />
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2 text-sm font-semibold">
            <span className="truncate">{nombre}</span>
            {soyYo && (
              <span className="shrink-0 rounded-full bg-primary px-1.5 py-px text-[10px] font-semibold text-primary-foreground">
                Tú
              </span>
            )}
          </p>
          <p className="truncate text-xs text-muted-foreground">{usuario.email}</p>
          <p className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
            <Clock className="size-3" aria-hidden />
            {usuario.last_login_at ? `Entró ${hace(usuario.last_login_at)}` : "Todavía no ha entrado"}
          </p>
        </div>
        <Interruptor
          activo={usuario.is_active}
          etiqueta={`Acceso de ${usuario.email}`}
          deshabilitado={soyYo || cambiar.isPending}
          alCambiar={(v) => (v ? cambiar.mutate({ is_active: true }) : setConfirmar(true))}
        />
      </div>

      {/* El rol una sola vez: como selector si se puede cambiar, como insignia
          si no (uno mismo, o sin acceso). Las dos cosas juntas repetian la
          misma palabra en cada tarjeta. */}
      <div className="flex items-center gap-2 border-t pt-3">
        {!usuario.is_active ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
            <UserX className="size-3.5" aria-hidden />
            Sin acceso · era de {ROL_VISUAL[usuario.role].etiqueta.toLowerCase()}
          </span>
        ) : soyYo ? (
          // Quitarse el rol a sí mismo lo rechaza la API; aquí ni se ofrece.
          <InsigniaRol rol={usuario.role} />
        ) : (
          <SelectorRol
            valor={usuario.role}
            deshabilitado={cambiar.isPending}
            alCambiar={(r) => r !== usuario.role && cambiar.mutate({ role: r })}
            etiqueta={`Rol de ${usuario.email}`}
            className="h-8 w-44 text-xs"
          />
        )}
      </div>

      <AlertDialog open={confirmar} onOpenChange={setConfirmar}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <span className="mb-1 flex size-11 items-center justify-center rounded-full bg-muted text-muted-foreground">
              <UserX className="size-5" aria-hidden />
            </span>
            <AlertDialogTitle>¿Le quitamos el acceso a {nombre}?</AlertDialogTitle>
            <AlertDialogDescription>
              Deja de poder entrar desde su siguiente clic, aunque tenga el tablero abierto. Lo
              que despachó queda como está, y le puedes devolver el acceso cuando quieras con el
              mismo interruptor.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Mejor no</AlertDialogCancel>
            <AlertDialogAction onClick={() => cambiar.mutate({ is_active: false })}>
              Quitar acceso
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </motion.li>
  );
}

/** Un interruptor de verdad (role="switch"), con la perilla que se desliza. */
function Interruptor({
  activo,
  etiqueta,
  deshabilitado,
  alCambiar,
}: {
  activo: boolean;
  etiqueta: string;
  deshabilitado?: boolean;
  alCambiar: (v: boolean) => void;
}) {
  const quieto = useReducedMotion();
  return (
    <button
      type="button"
      role="switch"
      aria-checked={activo}
      aria-label={etiqueta}
      disabled={deshabilitado}
      onClick={() => alCambiar(!activo)}
      className={cn(
        "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full p-0.5 transition-colors duration-200",
        "focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:outline-none",
        "disabled:cursor-not-allowed disabled:opacity-50",
        activo ? "justify-end bg-primary" : "justify-start bg-muted-foreground/30",
      )}
    >
      <motion.span
        layout={!quieto}
        transition={{ type: "spring", stiffness: 600, damping: 32 }}
        className="flex size-5 items-center justify-center rounded-full bg-background shadow-sm"
      >
        {activo ? (
          <UserCheck className="size-3 text-primary" aria-hidden />
        ) : (
          <UserX className="size-3 text-muted-foreground" aria-hidden />
        )}
      </motion.span>
    </button>
  );
}

/** Cuando el filtro o la búsqueda no dejan a nadie. */
function Vacio({ buscando }: { buscando: boolean }) {
  const quieto = useReducedMotion();
  return (
    <motion.div
      initial={quieto ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col items-center gap-3 rounded-2xl border border-dashed px-6 py-10 text-center"
    >
      <div aria-hidden className="relative flex h-16 w-24 items-center justify-center">
        <motion.span
          className="absolute left-1 flex size-11 items-center justify-center rounded-full bg-primary/10 text-primary"
          animate={quieto ? undefined : { y: [0, -4, 0] }}
          transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
        >
          <ShieldCheck className="size-5" />
        </motion.span>
        <motion.span
          className="absolute right-1 flex size-11 items-center justify-center rounded-full bg-[color-mix(in_oklab,var(--atencion)_14%,transparent)] text-[var(--atencion)]"
          animate={quieto ? undefined : { y: [0, -4, 0] }}
          transition={{ duration: 3, repeat: Infinity, ease: "easeInOut", delay: 0.6 }}
        >
          <HardHat className="size-5" />
        </motion.span>
        <span className="absolute flex size-12 items-center justify-center rounded-full border-2 border-background bg-muted text-muted-foreground">
          <Search className="size-5" />
        </span>
      </div>
      <div>
        <p className="text-sm font-medium">
          {buscando ? "Nadie coincide con eso" : "Todavía no hay nadie más"}
        </p>
        <p className="text-xs text-muted-foreground">
          {buscando
            ? "Prueba con otro nombre, otro correo u otro filtro."
            : "Autoriza un correo arriba y aparecerá aquí."}
        </p>
      </div>
    </motion.div>
  );
}
