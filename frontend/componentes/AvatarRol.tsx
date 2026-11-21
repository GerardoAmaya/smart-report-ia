"use client";

/**
 * La cara de alguien con su rol a la vista: un anillo de color y una insignia.
 *
 * El rol se ve antes de leerse. Administración lleva el anillo verde a ámbar
 * —los dos colores del proyecto— girando despacio; despacho, verde; el
 * invitado, gris y quieto, porque solo mira. El giro es CSS y lento: un menú
 * que se abre veinte veces al día no puede costar un render por cuadro, y con
 * «movimiento reducido» se queda quieto.
 */
import { Eye, HardHat, ShieldCheck, type LucideIcon } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";

import { cn } from "@/lib/utils";

import { Avatar } from "./Avatar";

export type Rol = "admin" | "operator" | "demo";

type Visual = {
  etiqueta: string;
  icono: LucideIcon;
  /** El anillo: un gradiente cónico que gira, o un color fijo. */
  anillo: string;
  gira: boolean;
  /** Fondo y texto de la insignia. */
  insignia: string;
};

export const ROL_VISUAL: Record<Rol, Visual> = {
  admin: {
    etiqueta: "Administración",
    icono: ShieldCheck,
    anillo: "conic-gradient(from 0deg, var(--primary), var(--atencion), var(--primary))",
    gira: true,
    insignia: "bg-primary/12 text-primary ring-1 ring-primary/25",
  },
  operator: {
    etiqueta: "Despacho",
    icono: HardHat,
    anillo:
      "conic-gradient(from 0deg, var(--primary), color-mix(in oklab, var(--primary) 35%, transparent), var(--primary))",
    gira: true,
    insignia: "bg-primary/10 text-primary ring-1 ring-primary/20",
  },
  demo: {
    etiqueta: "Invitado",
    icono: Eye,
    anillo: "color-mix(in oklab, var(--muted-foreground) 45%, transparent)",
    gira: false,
    insignia: "bg-muted text-muted-foreground ring-1 ring-border",
  },
};

export function AvatarConAnillo({
  rol,
  url,
  nombre,
  email,
  tamano = "sm",
  enLinea = false,
  className,
}: {
  rol: Rol;
  url?: string | null;
  nombre?: string | null;
  email: string;
  tamano?: "xs" | "sm" | "md" | "lg" | "xl";
  /** El punto verde de «está dentro». Solo para la propia sesión: de los demás no se sabe. */
  enLinea?: boolean;
  className?: string;
}) {
  const visual = ROL_VISUAL[rol];
  const quieto = useReducedMotion();
  // Anillo = caja - (avatar + 2 x separacion), partido en dos. La primera
  // version hacia el avatar casi del tamaño de la caja y el anillo quedaba
  // tapado: se veia una cara sin color de rol.
  const medidas = {
    xs: { caja: "size-7", avatar: "size-5 text-[9px]", grosor: "p-[1.5px]", punto: "size-2" },
    sm: { caja: "size-10", avatar: "size-[30px] text-[11px]", grosor: "p-[2px]", punto: "size-2.5" },
    md: { caja: "size-12", avatar: "size-[37px] text-xs", grosor: "p-[2px]", punto: "size-3" },
    lg: { caja: "size-16", avatar: "size-[50px] text-base", grosor: "p-[3px]", punto: "size-3.5" },
    xl: { caja: "size-28", avatar: "size-[90px] text-2xl", grosor: "p-[4px]", punto: "size-5" },
  }[tamano];

  return (
    <span className={cn("relative inline-flex shrink-0", medidas.caja, className)}>
      {/* El anillo va en una capa aparte que gira debajo del avatar: girar el
          avatar entero giraria tambien la foto. */}
      <span
        aria-hidden
        className={cn(
          "absolute inset-0 rounded-full",
          visual.gira && "animate-[spin_7s_linear_infinite] motion-reduce:animate-none",
        )}
        style={{ background: visual.anillo }}
      />
      <span
        className={cn(
          "relative m-auto inline-flex rounded-full bg-background",
          medidas.grosor,
        )}
      >
        <Avatar url={url} nombre={nombre} email={email} className={medidas.avatar} />
      </span>
      {enLinea && (
        <motion.span
          aria-hidden
          initial={quieto ? false : { scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ type: "spring", stiffness: 500, damping: 18, delay: 0.15 }}
          className={cn(
            "absolute right-0 bottom-0 rounded-full bg-primary ring-2 ring-background",
            medidas.punto,
          )}
        />
      )}
    </span>
  );
}

/** El rol en una píldora con su ícono: escudo, casco u ojo. */
export function InsigniaRol({
  rol,
  etiqueta,
  className,
}: {
  rol: Rol;
  /** Para decir «Invitado · solo mira» en vez del nombre corto. */
  etiqueta?: string;
  className?: string;
}) {
  const visual = ROL_VISUAL[rol];
  const Icono = visual.icono;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
        visual.insignia,
        className,
      )}
    >
      <Icono className="size-3.5" aria-hidden />
      {etiqueta ?? visual.etiqueta}
    </span>
  );
}

/**
 * Unas cuantas caras apiladas y «+N»: quién tiene acceso, de un vistazo.
 *
 * Propia y no la de Magic UI (avatar-circles): aquella exige foto —sin ella
 * queda un hueco—, hace de cada cara un enlace que no lleva a ninguna parte y
 * trae colores fijos que no siguen la paleta ni el modo oscuro.
 */
export function AvatarApilados({
  personas,
  maximo = 5,
  className,
}: {
  personas: { rol: Rol; url?: string | null; nombre?: string | null; email: string }[];
  maximo?: number;
  className?: string;
}) {
  const quieto = useReducedMotion();
  const vistas = personas.slice(0, maximo);
  const resto = personas.length - vistas.length;
  return (
    <span className={cn("flex items-center -space-x-2", className)}>
      {vistas.map((p, i) => (
        <motion.span
          key={p.email}
          initial={quieto ? false : { opacity: 0, x: -6, scale: 0.8 }}
          animate={{ opacity: 1, x: 0, scale: 1 }}
          transition={{ delay: i * 0.05, type: "spring", stiffness: 420, damping: 24 }}
          title={p.nombre ?? p.email}
          className="rounded-full ring-2 ring-background"
        >
          <AvatarConAnillo rol={p.rol} url={p.url} nombre={p.nombre} email={p.email} tamano="xs" />
        </motion.span>
      ))}
      {resto > 0 && (
        <span className="z-10 flex size-7 items-center justify-center rounded-full bg-muted text-[10px] font-semibold text-muted-foreground ring-2 ring-background">
          +{resto}
        </span>
      )}
    </span>
  );
}
