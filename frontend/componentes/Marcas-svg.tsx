/**
 * Marcas de terceros, en linea.
 *
 * Lucide no trae logotipos a proposito —son marcas registradas— y Font Awesome
 * los trae simplificados. Para el boton de Google eso no alcanza: sus
 * lineamientos de marca piden el logotipo multicolor exacto, y una "G" gris de
 * un pack generico no lo cumple.
 *
 * En linea y no como dependencia: son dos SVG. Traer tres paquetes de iconos
 * para esto seria pagar mucho por poco, y ademas mezclaria iconos rellenos con
 * los de trazo de Lucide, que se nota.
 */

export function MarcaGoogle({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden focusable="false">
      <path
        fill="#4285F4"
        d="M23.06 12.25c0-.85-.08-1.67-.22-2.45H12v4.63h6.2a5.3 5.3 0 0 1-2.3 3.48v2.9h3.72c2.18-2 3.44-4.96 3.44-8.46Z"
      />
      <path
        fill="#34A853"
        d="M12 23.5c3.11 0 5.72-1.03 7.62-2.79l-3.72-2.89c-1.03.69-2.35 1.1-3.9 1.1-3 0-5.54-2.03-6.45-4.75H1.71v2.98A11.5 11.5 0 0 0 12 23.5Z"
      />
      <path
        fill="#FBBC05"
        d="M5.55 14.17a6.9 6.9 0 0 1 0-4.41V6.78H1.71a11.51 11.51 0 0 0 0 10.37l3.84-2.98Z"
      />
      <path
        fill="#EA4335"
        d="M12 5.01c1.69 0 3.21.58 4.4 1.72l3.3-3.3C17.71 1.52 15.1.5 12 .5 7.51.5 3.63 3.08 1.71 6.78l3.84 2.98C6.46 7.04 9 5.01 12 5.01Z"
      />
    </svg>
  );
}

export function MarcaTelegram({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden focusable="false">
      <path
        fill="currentColor"
        d="M11.94 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm4.64 6.86-1.55 7.32c-.12.52-.42.65-.86.4l-2.37-1.75-1.15 1.1c-.13.13-.23.24-.48.24l.17-2.42 4.4-3.98c.2-.17-.04-.26-.3-.1L8.99 12.1l-2.34-.73c-.51-.16-.52-.51.11-.76l9.13-3.52c.42-.15.8.1.66.77Z"
      />
    </svg>
  );
}
