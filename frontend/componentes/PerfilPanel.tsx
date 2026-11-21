"use client";

/**
 * Mi perfil: la foto, el nombre que ven los demás, y lo que no se cambia aquí.
 *
 * El correo y el rol se enseñan pero no se editan: el correo lo dice Google y
 * el rol lo da administración. Un formulario que dejara cambiarlos sería una
 * promesa que la API no cumple.
 *
 * El invitado ve su perfil pero no lo cambia: es una cuenta que comparte todo
 * el público, y lo que uno escribiera ahí lo vería el siguiente que entra. Se
 * le explica en vez de enseñarle un formulario gris deshabilitado, que parece
 * roto y no dice por qué.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Camera, Check, Clock, Eye, ImageUp, LoaderCircle, Mail, Pencil, Trash2, X } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState, type DragEvent } from "react";
import { toast } from "sonner";

import { BorderBeam } from "@/components/ui/border-beam";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { api, PerfilSchema, type Perfil } from "@/lib/api";
import { hace } from "@/lib/textos";
import { cn } from "@/lib/utils";

import { AvatarConAnillo, InsigniaRol } from "./AvatarRol";
import { Aurora } from "./ResumenVivo";

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
        {/* Se monta de nuevo al abrir: el borrador del nombre y la vista previa
            parten siempre de cero y no de lo que quedó la vez anterior. */}
        {abierto && <Contenido perfil={perfil} />}
      </SheetContent>
    </Sheet>
  );
}

// El mismo tope que la API (MAX_PHOTO_BYTES): avisar aqui ahorra subir veinte
// megas para que el servidor diga que no.
const TOPE_BYTES = 20 * 1024 * 1024;

function Contenido({ perfil }: { perfil: Perfil }) {
  const cliente = useQueryClient();
  const quieto = useReducedMotion();
  const editable = perfil.role !== "demo";
  // Cada guardado sube este numero y vuelve a disparar el destello.
  const [festejo, setFestejo] = useState(0);

  const alCambiar = (p: Perfil) => cliente.setQueryData(["yo"], p);

  const quitar = useMutation({
    mutationFn: api.quitarFoto,
    onSuccess: (p) => {
      alCambiar(p);
      toast.success(p.avatar_url ? "Volviste a la foto de Google" : "Foto quitada");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="space-y-5 overflow-y-auto px-5 py-5">
      {/* --- La tarjeta de la persona --- */}
      <motion.section
        initial={quieto ? false : { opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: "easeOut" }}
        className="relative overflow-hidden rounded-2xl border bg-card/60 px-5 pt-6 pb-5"
      >
        <Aurora />
        {/* El borde que recorre la tarjeta solo si se permite el movimiento: el
            componente de Magic UI anima en bucle y no mira esa preferencia. */}
        {!quieto && (
          <BorderBeam
            size={90}
            duration={9}
            borderWidth={1.5}
            colorFrom="var(--primary)"
            colorTo="var(--atencion)"
          />
        )}
        <div className="relative flex flex-col items-center text-center">
          <div className="relative">
            <AvatarConAnillo
              rol={perfil.role}
              url={perfil.avatar_url}
              nombre={perfil.display_name}
              email={perfil.email}
              tamano="xl"
              enLinea
            />
            <Destello clave={festejo} />
          </div>
          <div className="mt-4 w-full">
            <Nombre perfil={perfil} editable={editable} alGuardar={alCambiar} />
          </div>
          <InsigniaRol rol={perfil.role} etiqueta={nombreDelRol(perfil)} className="mt-2" />
        </div>
      </motion.section>

      {editable ? (
        <SubirFoto
          perfil={perfil}
          alGuardar={(p) => {
            alCambiar(p);
            setFestejo((n) => n + 1);
            toast.success("Foto actualizada", { description: "Ya la ven los demás." });
          }}
          alQuitar={() => quitar.mutate()}
          quitando={quitar.isPending}
        />
      ) : (
        <SoloLectura />
      )}

      {/* --- Los datos que no se editan --- */}
      <dl className="divide-y rounded-2xl border bg-card/60">
        <Dato icono={Mail} etiqueta="Correo" valor={perfil.email} />
        <Dato
          icono={Clock}
          etiqueta="Última entrada"
          valor={perfil.last_login_at ? hace(perfil.last_login_at) : "Es tu primera vez"}
        />
      </dl>
    </div>
  );
}

/** El nombre, editable ahí mismo: el lápiz se vuelve ✓ mientras se escribe. */
function Nombre({
  perfil,
  editable,
  alGuardar,
}: {
  perfil: Perfil;
  editable: boolean;
  alGuardar: (p: Perfil) => void;
}) {
  const quieto = useReducedMotion();
  const [editando, setEditando] = useState(false);
  const [nombre, setNombre] = useState(perfil.display_name ?? "");
  const actual = perfil.display_name ?? perfil.email.split("@")[0];

  const guardar = useMutation({
    mutationFn: api.cambiarNombre,
    onSuccess: (p) => {
      alGuardar(p);
      setEditando(false);
      toast.success("Nombre guardado");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const limpio = nombre.trim();
  const valido = limpio.length >= 1 && limpio.length <= 64 && !/[<>]/.test(limpio);
  const cambio = limpio !== (perfil.display_name ?? "");

  const icono = (
    <AnimatePresence mode="wait" initial={false}>
      <motion.span
        key={editando ? "listo" : "lapiz"}
        initial={quieto ? false : { rotate: -90, scale: 0.5, opacity: 0 }}
        animate={{ rotate: 0, scale: 1, opacity: 1 }}
        exit={quieto ? undefined : { rotate: 90, scale: 0.5, opacity: 0 }}
        transition={{ duration: 0.18 }}
        className="flex"
      >
        {editando ? <Check className="size-4" /> : <Pencil className="size-4" />}
      </motion.span>
    </AnimatePresence>
  );

  if (!editable) {
    return <p className="truncate text-xl font-semibold tracking-tight">{actual}</p>;
  }

  if (!editando) {
    return (
      <div className="flex items-center justify-center gap-1.5">
        <p className="truncate text-xl font-semibold tracking-tight">{actual}</p>
        <Button
          size="icon"
          variant="ghost"
          className="size-8 rounded-full text-muted-foreground hover:text-primary"
          aria-label="Cambiar mi nombre"
          onClick={() => {
            setNombre(perfil.display_name ?? "");
            setEditando(true);
          }}
        >
          {icono}
        </Button>
      </div>
    );
  }

  return (
    <form
      className="mx-auto max-w-xs space-y-1.5"
      onSubmit={(e) => {
        e.preventDefault();
        if (!valido) return;
        if (!cambio) setEditando(false);
        else guardar.mutate(limpio);
      }}
    >
      <div className="flex items-center gap-1.5">
        <Input
          autoFocus
          aria-label="Nombre visible"
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          onKeyDown={(e) => e.key === "Escape" && setEditando(false)}
          maxLength={64}
          aria-invalid={limpio.length > 0 && !valido}
          className="h-9 bg-background/80 text-center text-base font-medium"
        />
        <Button
          type="submit"
          size="icon"
          className="size-9 shrink-0 rounded-full"
          aria-label="Guardar nombre"
          disabled={!valido || guardar.isPending}
        >
          {guardar.isPending ? <LoaderCircle className="size-4 animate-spin" /> : icono}
        </Button>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="size-9 shrink-0 rounded-full"
          aria-label="Cancelar"
          onClick={() => setEditando(false)}
        >
          <X className="size-4" />
        </Button>
      </div>
      {limpio.length > 0 && !valido && (
        <p className="text-xs text-destructive">Entre 1 y 64 caracteres, sin &lt; ni &gt;.</p>
      )}
    </form>
  );
}

/**
 * Subir una foto: se arrastra o se elige, se ve recortada como va a quedar, y
 * solo entonces se guarda.
 *
 * La vista previa recorta al centro y en círculo, igual que el servidor: lo
 * que se aprueba es lo que va a salir, no la foto entera.
 */
function SubirFoto({
  perfil,
  alGuardar,
  alQuitar,
  quitando,
}: {
  perfil: Perfil;
  alGuardar: (p: Perfil) => void;
  alQuitar: () => void;
  quitando: boolean;
}) {
  const quieto = useReducedMotion();
  const entrada = useRef<HTMLInputElement>(null);
  const [encima, setEncima] = useState(false);
  const [previa, setPrevia] = useState<{ archivo: File; url: string } | null>(null);
  const [progreso, setProgreso] = useState<number | null>(null);

  // La URL de la vista previa ocupa memoria hasta que se suelta.
  useEffect(
    () => () => {
      if (previa) URL.revokeObjectURL(previa.url);
    },
    [previa],
  );

  function elegir(archivo: File | undefined) {
    if (!archivo) return;
    if (!archivo.type.startsWith("image/")) {
      toast.error("Eso no es una imagen", { description: "Elige una foto JPG, PNG o WebP." });
      return;
    }
    if (archivo.size > TOPE_BYTES) {
      toast.error("La foto es demasiado grande", { description: "El tope son 20 MB." });
      return;
    }
    setPrevia({ archivo, url: URL.createObjectURL(archivo) });
  }

  async function guardar() {
    if (!previa) return;
    setProgreso(0);
    try {
      const p = await subirConProgreso(previa.archivo, setProgreso);
      setPrevia(null);
      alGuardar(p);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setProgreso(null);
    }
  }

  const soltar = (e: DragEvent) => {
    e.preventDefault();
    setEncima(false);
    elegir(e.dataTransfer.files?.[0]);
  };

  return (
    <section aria-label="Foto de perfil" className="space-y-2">
      {/* `image/*` y no una lista cerrada: en el celular eso es lo que ofrece
          la cámara además de la galería. */}
      <input
        ref={entrada}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          elegir(e.target.files?.[0]);
          e.target.value = "";
        }}
      />

      <AnimatePresence mode="wait" initial={false}>
        {previa ? (
          <motion.div
            key="previa"
            initial={quieto ? false : { opacity: 0, scale: 0.97 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={quieto ? undefined : { opacity: 0, scale: 0.97 }}
            className="flex items-center gap-4 rounded-2xl border bg-card/60 p-4"
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- una URL local del navegador, no una imagen del sitio */}
            <img
              src={previa.url}
              alt="Vista previa de tu nueva foto"
              className="size-20 shrink-0 rounded-full object-cover ring-2 ring-primary/40"
            />
            <div className="min-w-0 flex-1 space-y-2">
              <p className="text-sm font-medium">¿Así está bien?</p>
              <p className="text-xs text-muted-foreground">
                Se recorta al centro, como la ves aquí.
              </p>
              {progreso !== null ? (
                <div
                  role="progressbar"
                  aria-label="Subiendo la foto"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(progreso * 100)}
                  className="h-1.5 overflow-hidden rounded-full bg-muted"
                >
                  <motion.div
                    className="h-full rounded-full bg-gradient-to-r from-primary to-[var(--atencion)]"
                    animate={{ width: `${Math.max(6, progreso * 100)}%` }}
                    transition={{ duration: quieto ? 0 : 0.2 }}
                  />
                </div>
              ) : (
                <div className="flex gap-2">
                  <Button size="sm" onClick={guardar}>
                    <Check />
                    Guardar foto
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setPrevia(null)}>
                    Cancelar
                  </Button>
                </div>
              )}
            </div>
          </motion.div>
        ) : (
          <motion.button
            key="zona"
            type="button"
            initial={quieto ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={quieto ? undefined : { opacity: 0 }}
            onClick={() => entrada.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setEncima(true);
            }}
            onDragLeave={() => setEncima(false)}
            onDrop={soltar}
            className={cn(
              "group flex w-full items-center gap-4 rounded-2xl border-2 border-dashed p-4 text-left transition-colors",
              "focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
              encima
                ? "border-primary bg-primary/8"
                : "border-border hover:border-primary/50 hover:bg-primary/4",
            )}
          >
            <span
              className={cn(
                "flex size-12 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary transition-transform duration-300",
                "group-hover:-translate-y-0.5 group-hover:rotate-[-8deg] motion-reduce:transform-none",
                encima && "scale-110",
              )}
            >
              {encima ? <ImageUp className="size-5" /> : <Camera className="size-5" />}
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-medium">
                {encima
                  ? "Suéltala aquí"
                  : perfil.avatar_url
                    ? "Cambiar mi foto"
                    : "Ponle cara a tu cuenta"}
              </span>
              <span className="block text-xs text-muted-foreground">
                Arrástrala aquí o toca para elegirla. En el celular, también con la cámara.
              </span>
            </span>
          </motion.button>
        )}
      </AnimatePresence>

      {/* Solo se puede quitar la foto propia: la de Google no vive aquí. */}
      {perfil.avatar_propio && !previa && (
        <Button
          size="sm"
          variant="ghost"
          className="text-muted-foreground hover:text-destructive"
          onClick={alQuitar}
          disabled={quitando}
        >
          {quitando ? <LoaderCircle className="animate-spin" /> : <Trash2 />}
          Quitar mi foto
        </Button>
      )}
    </section>
  );
}

/** El invitado: por qué aquí no se cambia nada, dicho con simpatía. */
function SoloLectura() {
  const quieto = useReducedMotion();
  return (
    <motion.section
      initial={quieto ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1, duration: 0.3 }}
      className="flex gap-3 rounded-2xl border border-dashed bg-card/60 p-4"
    >
      <motion.span
        aria-hidden
        animate={quieto ? undefined : { scaleY: [1, 1, 0.1, 1, 1] }}
        transition={{ duration: 4, repeat: Infinity, times: [0, 0.46, 0.5, 0.54, 1] }}
        className="flex size-10 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground"
      >
        <Eye className="size-5" />
      </motion.span>
      <div className="space-y-1">
        <p className="text-sm font-medium">Esta es la cuenta compartida de prueba</p>
        <p className="text-xs leading-relaxed text-muted-foreground">
          Aquí no se cambia nada: el nombre o la foto que pusieras los vería la siguiente persona
          que entre. Recorre todo el tablero con calma; despachar queda para el equipo.
        </p>
      </div>
    </motion.section>
  );
}

function Dato({
  icono: Icono,
  etiqueta,
  valor,
}: {
  icono: typeof Mail;
  etiqueta: string;
  valor: string;
}) {
  return (
    <div className="flex items-center gap-3 px-4 py-3 text-sm">
      <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <Icono className="size-4" aria-hidden />
      </span>
      <dt className="text-muted-foreground">{etiqueta}</dt>
      <dd className="ml-auto min-w-0 truncate text-right font-medium">{valor}</dd>
    </div>
  );
}

/**
 * Un destello corto alrededor del avatar al guardar la foto: un anillo que se
 * abre y unas chispas en los dos colores del proyecto. Medio segundo y se va.
 */
function Destello({ clave }: { clave: number }) {
  const quieto = useReducedMotion();
  if (clave === 0 || quieto) return null;
  const chispas = Array.from({ length: 10 }, (_, i) => (i / 10) * Math.PI * 2);
  return (
    <span key={clave} aria-hidden className="pointer-events-none absolute inset-0">
      <motion.span
        className="absolute inset-0 rounded-full ring-2 ring-primary"
        initial={{ scale: 1, opacity: 0.8 }}
        animate={{ scale: 1.6, opacity: 0 }}
        transition={{ duration: 0.7, ease: "easeOut" }}
      />
      {chispas.map((a, i) => (
        <motion.span
          key={i}
          className={cn(
            "absolute top-1/2 left-1/2 size-1.5 rounded-full",
            i % 2 ? "bg-[var(--atencion)]" : "bg-primary",
          )}
          initial={{ x: "-50%", y: "-50%", scale: 1, opacity: 1 }}
          animate={{
            x: `calc(-50% + ${Math.cos(a) * 78}px)`,
            y: `calc(-50% + ${Math.sin(a) * 78}px)`,
            scale: 0.2,
            opacity: 0,
          }}
          transition={{ duration: 0.65, ease: "easeOut", delay: 0.05 }}
        />
      ))}
    </span>
  );
}

// --- Subida con progreso ---

// XMLHttpRequest y no fetch: fetch no informa cuanto lleva subido, y una foto
// del celular por datos moviles tarda lo bastante como para que una barra
// quieta parezca colgada. Misma URL base que lib/api.ts.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function subirConProgreso(archivo: File, alProgreso: (p: number) => void): Promise<Perfil> {
  return new Promise((resolver, rechazar) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}/auth/yo/foto`);
    // La sesion va en cookie, igual que en el resto del cliente.
    xhr.withCredentials = true;
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) alProgreso(e.loaded / e.total);
    };
    xhr.onload = () => {
      if (xhr.status === 401) {
        rechazar(new Error("Tu sesión se cerró. Vuelve a entrar."));
        return;
      }
      let cuerpo: unknown = null;
      try {
        cuerpo = JSON.parse(xhr.responseText);
      } catch {
        // Sin cuerpo legible: se cae al mensaje generico de abajo.
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        const detalle = (cuerpo as { detail?: unknown } | null)?.detail;
        rechazar(new Error(typeof detalle === "string" ? detalle : `Error ${xhr.status}`));
        return;
      }
      const leido = PerfilSchema.safeParse(cuerpo);
      if (leido.success) resolver(leido.data);
      else rechazar(new Error("La respuesta del servidor no se entendió."));
    };
    xhr.onerror = () => rechazar(new Error("Sin conexión con el servidor."));
    const cuerpo = new FormData();
    cuerpo.append("archivo", archivo);
    xhr.send(cuerpo);
  });
}
