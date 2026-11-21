/**
 * Lo que mueve el mapa: columnas que crecen, la orbita lenta y el pulso de lo
 * urgente.
 *
 * **Cada movimiento dice algo o no existe.** Las columnas crecen cuando
 * aparecen o cambian —eso es un dato nuevo—; el pulso va solo en lo urgente y
 * abierto, para que signifique algo; la camara gira sola solo cuando nadie
 * esta usando el mapa, y se detiene al primer toque. Quien pide menos
 * movimiento no ve nada de esto.
 *
 * Todo por requestAnimationFrame y con su `detener`: el mapa se desmonta al
 * cambiar de pestaña del tablero, y un bucle que sobrevive al mapa pinta sobre
 * un lienzo que ya no existe.
 */
import type { Map as MapLibreMap } from "maplibre-gl";

export const FUENTE_COLUMNAS = "columnas";
export const FUENTE_PULSO = "pulso";
export const CAPAS_PULSO = ["pulso-3d-a", "pulso-3d-b"] as const;

/** Quien pidio menos movimiento no ve la camara volar: cambia en el sitio. */
export function sinMovimiento(): boolean {
  return (
    typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

const salidaSuave = (t: number) => 1 - Math.pow(1 - t, 3);

/**
 * Columnas que crecen desde el suelo.
 *
 * La altura de cada columna se multiplica por el estado `h` de su elemento
 * (ver la expresion en Mapa.tsx): sin estado vale 1 y la columna esta entera.
 * Animar es llevar `h` de `desde` a 1 en las columnas que importan, sin tocar
 * la expresion ni los datos: un `setPaintProperty` por cuadro reharia todas
 * las columnas, esto solo las que crecen.
 */
export function crearCrecimiento(m: MapLibreMap) {
  let cuadro = 0;
  let enCurso = new Map<string, number>();

  const fijar = (clave: string, h: number) => {
    if (!m.getSource(FUENTE_COLUMNAS)) return;
    m.setFeatureState({ source: FUENTE_COLUMNAS, id: clave }, { h });
  };

  const detener = () => {
    cancelAnimationFrame(cuadro);
    // Lo que estaba a medias queda entero: una columna congelada a la mitad
    // diria un numero que no es.
    for (const clave of enCurso.keys()) fijar(clave, 1);
    enCurso = new Map();
  };

  /** `desde`: clave de la columna → fraccion de su altura final en la que empieza. */
  const animar = (desde: Map<string, number>, { retraso = 0, duracion = 900 } = {}) => {
    detener();
    if (desde.size === 0 || sinMovimiento()) return;
    enCurso = desde;
    // El estado inicial va antes del primer cuadro: si no, la columna se vería
    // entera un instante y luego caeria al suelo para crecer.
    for (const [clave, h] of desde) fijar(clave, h);
    const inicio = performance.now() + retraso;
    const paso = (ahora: number) => {
      const t = Math.min(1, Math.max(0, (ahora - inicio) / duracion));
      const e = salidaSuave(t);
      for (const [clave, h0] of enCurso) fijar(clave, h0 + (1 - h0) * e);
      if (t < 1) cuadro = requestAnimationFrame(paso);
      else enCurso = new Map();
    };
    cuadro = requestAnimationFrame(paso);
  };

  return { animar, detener };
}

/**
 * La camara gira sola, despacio, cuando nadie toca el mapa.
 *
 * Una vuelta cada 90 s: lo bastante lenta para que no maree a quien mira de
 * reojo, lo bastante rapida para que se note que esta viva. Empieza tras 8 s
 * sin tocar nada y se detiene **al primer contacto** —boton, rueda, tecla,
 * dedo o pasar sobre una columna—: un mapa que se mueve mientras alguien
 * intenta apuntar es peor que uno quieto.
 */
export function crearOrbita(m: MapLibreMap, { esperaMs = 8000, vueltaMs = 90_000 } = {}) {
  let temporizador: ReturnType<typeof setTimeout> | undefined;
  let cuadro = 0;
  let girando = false;
  let destruida = false;

  const parar = () => {
    girando = false;
    cancelAnimationFrame(cuadro);
    clearTimeout(temporizador);
  };

  const girar = () => {
    if (destruida || document.visibilityState !== "visible" || sinMovimiento()) return;
    // Si la camara todavia se mueve (el encuadre, o la inercia de un arrastre),
    // se espera un poco mas en vez de pelear con ella.
    if (m.isMoving()) {
      temporizador = setTimeout(girar, 1000);
      return;
    }
    girando = true;
    let antes = performance.now();
    const paso = (ahora: number) => {
      if (!girando) return;
      const dt = Math.min(64, ahora - antes);
      antes = ahora;
      m.setBearing(m.getBearing() + (dt * 360) / vueltaMs);
      cuadro = requestAnimationFrame(paso);
    };
    cuadro = requestAnimationFrame(paso);
  };

  const programar = () => {
    parar();
    if (destruida || sinMovimiento()) return;
    temporizador = setTimeout(girar, esperaMs);
  };

  // Cualquier contacto detiene y vuelve a contar desde cero.
  const contenedor = m.getContainer();
  const eventos = ["pointerdown", "wheel", "keydown", "touchstart"] as const;
  for (const e of eventos) contenedor.addEventListener(e, programar, { passive: true });
  const sobreColumna = () => programar();
  m.on("mousemove", "columnas-3d", sobreColumna);

  // Con la pestaña del navegador oculta no se gira: nadie mira, y al volver
  // la camara estaria en cualquier parte.
  const visibilidad = () => (document.visibilityState === "visible" ? programar() : parar());
  document.addEventListener("visibilitychange", visibilidad);

  programar();

  return {
    destruir() {
      destruida = true;
      parar();
      for (const e of eventos) contenedor.removeEventListener(e, programar);
      m.off("mousemove", "columnas-3d", sobreColumna);
      document.removeEventListener("visibilitychange", visibilidad);
    },
  };
}

/** Pixeles por metro en el plano del mapa, a este zoom y latitud. */
function pixelesPorMetro(zoom: number, lat: number): number {
  return (512 * 2 ** zoom) / (40_075_016.686 * Math.cos((lat * Math.PI) / 180));
}

/**
 * El pulso de lo urgente en 3D: dos ondas en el suelo, bajo la columna.
 *
 * Una capa `circle` tendida sobre el plano del mapa y por debajo de edificios
 * y columnas, que la tapan donde corresponde: la onda se ve salir de la base.
 * Se anima el radio y la opacidad a 30 cuadros por segundo, que para una onda
 * lenta no se distingue de 60 y le ahorra la mitad del trabajo a la tarjeta
 * grafica. Sin puntos urgentes, el bucle ni arranca.
 */
export function crearPulso(m: MapLibreMap, radioCelda: () => number, { cicloMs = 2400 } = {}) {
  let cuadro = 0;
  let ultimo = 0;
  let activo = false;

  const pintar = (ahora: number) => {
    if (!activo) return;
    cuadro = requestAnimationFrame(pintar);
    if (ahora - ultimo < 33) return;
    ultimo = ahora;
    if (!CAPAS_PULSO.every((id) => m.getLayer(id))) return;
    const base = radioCelda() * 0.86 * pixelesPorMetro(m.getZoom(), m.getCenter().lat);
    CAPAS_PULSO.forEach((id, i) => {
      const fase = ((ahora / cicloMs) + i / CAPAS_PULSO.length) % 1;
      m.setPaintProperty(id, "circle-radius", base * (0.95 + 1.35 * fase));
      m.setPaintProperty(id, "circle-stroke-opacity", 0.85 * (1 - fase) ** 1.6);
    });
  };

  const parar = () => {
    activo = false;
    cancelAnimationFrame(cuadro);
  };

  const arrancar = () => {
    if (activo || sinMovimiento() || document.visibilityState !== "visible") return;
    activo = true;
    cuadro = requestAnimationFrame(pintar);
  };

  const visibilidad = () => (document.visibilityState === "visible" ? arrancar() : parar());
  document.addEventListener("visibilitychange", visibilidad);

  return {
    /** Arranca o para segun haya algo urgente que senalar. */
    hayUrgentes(si: boolean) {
      if (si) arrancar();
      else parar();
    },
    destruir() {
      parar();
      document.removeEventListener("visibilitychange", visibilidad);
    },
  };
}

/**
 * El pulso de lo urgente en 2D: dos anillos que salen del pin.
 *
 * Con la Web Animations API y no con una clase de CSS: transform y opacidad
 * van al compositor, no repintan el mapa, y no hace falta tocar la hoja de
 * estilos global por algo que solo vive aqui.
 */
export function anillosDeUrgencia(el: HTMLElement, color: string) {
  if (sinMovimiento()) return;
  el.style.position = "relative";
  el.style.overflow = "visible";
  for (let i = 0; i < 2; i++) {
    const anillo = document.createElement("span");
    anillo.setAttribute("aria-hidden", "true");
    anillo.style.cssText = `
      position:absolute; inset:-2px; border-radius:9999px; pointer-events:none;
      border:2px solid ${color}; opacity:0;
    `;
    el.appendChild(anillo);
    anillo.animate(
      [
        { transform: "scale(1)", opacity: 0.7 },
        { transform: "scale(2.5)", opacity: 0 },
      ],
      { duration: 2400, delay: i * 1200, iterations: Infinity, easing: "cubic-bezier(.2,.6,.35,1)" },
    );
  }
}
