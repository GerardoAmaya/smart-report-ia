/**
 * Lo que los tres recorridos comparten.
 *
 * **Los reportes entran por el webhook de verdad**, con su secreto y su payload
 * de Telegram. No hay endpoints de prueba ni escrituras directas a la base: un
 * recorrido que monta su escenario por un atajo deja de probar el camino que
 * recorre una persona.
 *
 * Lo unico redirigido es a que servidor le habla el bot, que es una variable de
 * entorno. El codigo que corre es el mismo de produccion.
 */
import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const API = process.env.E2E_API_URL ?? "http://localhost:8000";

export function password(): string {
  const p = process.env.DEMO_PASSWORD;
  if (!p) throw new Error("DEMO_PASSWORD hace falta para las pruebas extremo a extremo");
  return p;
}

function secreto(): string {
  const s = process.env.TELEGRAM_WEBHOOK_SECRET;
  if (!s) throw new Error("TELEGRAM_WEBHOOK_SECRET hace falta: el webhook falla cerrado");
  return s;
}

type RespuestaConBotones = {
  reply_markup?: { inline_keyboard: { text: string; callback_data: string }[][] };
};

/** Los botones que trae una respuesta del webhook. */
export function botonesDe(r: RespuestaConBotones): { texto: string; data: string }[] {
  return (r.reply_markup?.inline_keyboard ?? [])
    .flat()
    .map((b) => ({ texto: b.text, data: b.callback_data }));
}

let siguienteUpdate = Date.now() % 1_000_000;
const nuevoUpdateId = () => ++siguienteUpdate;

/** Un usuario distinto por corrida, para que las pruebas no se pisen. */
export function usuarioNuevo(): string {
  return String(900_000_000 + Math.floor(Math.random() * 90_000_000));
}

const LAT0 = 13.6929;
const LON0 = -89.2182;

/**
 * Cada corrida trabaja en su propio sitio del mapa.
 *
 * Sin esto, los reportes de una corrida se agrupan con los de la anterior —que
 * es el comportamiento **correcto** del sistema, porque estan a metros— y las
 * afirmaciones sobre "cuantos hay en el caso" se vuelven imposibles de escribir.
 * Un kilometro de separacion basta: el umbral de duda son ochenta metros.
 */
const CORRIDA_KM = Math.floor(Math.random() * 400) + 20;

/** Coordenadas desplazadas por metros medidos, no por grados inventados. */
export function desplazar(metros: number): { lat: number; lon: number } {
  return { lat: LAT0 + (metros + CORRIDA_KM * 1000) / 111_320, lon: LON0 };
}

async function alWebhook(api: APIRequestContext, payload: unknown) {
  const r = await api.post(`${API}/webhooks/telegram`, {
    data: payload,
    headers: { "X-Telegram-Bot-Api-Secret-Token": secreto() },
  });
  expect(r.ok(), await r.text()).toBeTruthy();
  return r.json();
}

/** Manda una foto, como la manda Telegram. */
export async function mandarFoto(
  api: APIRequestContext,
  usuario: string,
  texto?: string,
): Promise<void> {
  const id = nuevoUpdateId();
  await alWebhook(api, {
    update_id: id,
    message: {
      message_id: id,
      date: Math.floor(Date.now() / 1000),
      chat: { id: Number(usuario), type: "private" },
      from: { id: Number(usuario), is_bot: false, first_name: "Vecina" },
      photo: [
        { file_id: `e2e-${id}`, file_unique_id: `u${id}`, width: 721, height: 1280, file_size: 180_000 },
      ],
      ...(texto ? { caption: texto } : {}),
    },
  });
}

/** Manda la ubicacion con el boton nativo. */
export async function mandarUbicacion(
  api: APIRequestContext,
  usuario: string,
  metros = 0,
): Promise<void> {
  const id = nuevoUpdateId();
  const { lat, lon } = desplazar(metros);
  await alWebhook(api, {
    update_id: id,
    message: {
      message_id: id,
      date: Math.floor(Date.now() / 1000),
      chat: { id: Number(usuario), type: "private" },
      from: { id: Number(usuario), is_bot: false, first_name: "Vecina" },
      location: { latitude: lat, longitude: lon },
    },
  });
}

/**
 * Pulsa un boton del bot y **devuelve lo que el webhook contesta**.
 *
 * La respuesta importa: el bot no manda mensajes aparte para contestar a un
 * boton —la fase 1 decidio que el webhook no hace llamadas de red salientes—,
 * asi que los botones siguientes vienen en el cuerpo de esta misma respuesta.
 */
export async function pulsarBoton(
  api: APIRequestContext,
  usuario: string,
  data: string,
): Promise<RespuestaConBotones> {
  const id = nuevoUpdateId();
  return alWebhook(api, {
    update_id: id,
    callback_query: {
      id: `cb${id}`,
      from: { id: Number(usuario), is_bot: false, first_name: "Vecina" },
      chat_instance: "x",
      data,
      message: {
        message_id: id,
        date: Math.floor(Date.now() / 1000),
        chat: { id: Number(usuario), type: "private" },
        from: { id: 1, is_bot: true, first_name: "Bot" },
        text: "¿Es correcto?",
      },
    },
  });
}

/**
 * Abre sesion en el **contexto de peticiones**, que es distinto del navegador.
 *
 * Playwright mantiene dos contextos separados: `page` tiene sus cookies y
 * `request` las suyas. Una prueba que entra por la interfaz y luego consulta la
 * API con `request` recibe 401, y el sintoma —"cases es undefined"— no apunta a
 * la sesion.
 */
export async function entrarPorApi(api: APIRequestContext): Promise<void> {
  const r = await api.post(`${API}/auth/demo`, { data: { password: password() } });
  expect(r.ok(), await r.text()).toBeTruthy();
}

export async function entrarComoPrueba(page: Page): Promise<void> {
  await page.goto("/entrar");
  await page.getByLabel("Usuario de prueba").fill(password());
  await page.getByRole("button", { name: /entrar a mirar/i }).click();
  await expect(page.getByRole("button", { name: "Salir" })).toBeVisible();
}

/**
 * Espera a que el trabajador haga lo suyo.
 *
 * Sondea en vez de dormir un rato fijo: un `sleep` generoso hace la suite lenta
 * y uno corto la hace intermitente, y una prueba que falla a veces enseña a
 * ignorar el rojo.
 */
export async function esperarA<T>(
  intento: () => Promise<T | null>,
  queEspera: string,
  limiteMs = 30_000,
): Promise<T> {
  const hasta = Date.now() + limiteMs;
  while (Date.now() < hasta) {
    const r = await intento();
    if (r !== null && r !== undefined) return r;
    await new Promise((res) => setTimeout(res, 500));
  }
  throw new Error(`se agoto la espera de: ${queEspera}`);
}

export const TELEGRAM_FALSO = process.env.E2E_TELEGRAM_URL ?? "http://localhost:8099";

type Mensaje = { chat_id: string; texto: string; botones: { texto: string; data: string }[] };

/**
 * Lo que el bot le mando a una persona.
 *
 * Es por donde una prueba puede pulsar un boton **sin inventarse su
 * contenido**: el bot manda los botones por Telegram, el Telegram falso los
 * guarda, y la prueba pulsa el que pulsaria una persona. Reconstruir el
 * callback_data a mano seria adivinar, y el dia que cambie el formato la prueba
 * seguiria verde sobre algo que ya no existe.
 */
export async function mensajesDelBot(api: APIRequestContext, usuario: string): Promise<Mensaje[]> {
  const r = await api.get(`${TELEGRAM_FALSO}/bot1/_enviados`);
  const { result } = await r.json();
  return (result as Mensaje[]).filter((m) => m.chat_id === usuario);
}

/** Espera a que el bot mande botones a esa persona y los devuelve. */
export async function esperarBotones(
  api: APIRequestContext,
  usuario: string,
  prefijo: string,
): Promise<{ texto: string; data: string }[]> {
  return esperarA(async () => {
    const mensajes = await mensajesDelBot(api, usuario);
    for (const m of [...mensajes].reverse()) {
      const coincide = m.botones.filter((b) => b.data.startsWith(prefijo));
      if (coincide.length) return coincide;
    }
    return null;
  }, `que el bot mande botones "${prefijo}" a ${usuario}`);
}

/**
 * El reporte completo, por el camino de verdad: foto, ubicacion, y la
 * categoria **corregida a mano**.
 *
 * Se corrige en vez de confirmar por un motivo que no es de conveniencia: la
 * foto que sirve el Telegram falso es un patron generado, no un bache, y el
 * modelo responde `no_es_reporte` — **acertando**. Una persona ante eso corrige,
 * asi que la prueba corrige. De paso queda cubierto el camino de correccion, y
 * la categoria deja de depender de lo que el modelo opine de una imagen
 * sintetica, que es justo lo que haria la prueba intermitente.
 */
export async function reportarCompleto(
  api: APIRequestContext,
  opciones: { metros?: number; texto: string; categoria?: string },
): Promise<{ usuario: string; casoId: string }> {
  const usuario = usuarioNuevo();
  const etiqueta = opciones.categoria ?? "Calle o acera";

  await mandarFoto(api, usuario, opciones.texto);
  await mandarUbicacion(api, usuario, opciones.metros ?? 0);

  // La pregunta si llega por Telegram: la manda el trabajador al terminar de
  // clasificar, que es una llamada fuera del webhook.
  const confirmar = await esperarBotones(api, usuario, "n:");

  // Las categorias no: vienen en la respuesta del webhook, porque contestar a
  // un boton no puede costar una llamada de red saliente.
  const categorias = botonesDe(await pulsarBoton(api, usuario, confirmar[0].data));
  const elegida = categorias.find((b) => b.texto === etiqueta);
  if (!elegida) {
    throw new Error(
      `el bot no ofrecio "${etiqueta}"; ofrecio: ${categorias.map((b) => b.texto).join(", ")}`,
    );
  }
  await pulsarBoton(api, usuario, elegida.data);

  const casoId = await esperarA(async () => {
    const r = await buscarMiCaso(api, opciones.texto).catch(() => null);
    return r?.casoId ?? null;
  }, `que "${opciones.texto}" quede en un caso`);

  return { usuario, casoId };
}

/** El caso donde quedo *mi* reporte, buscado por el texto que la prueba eligio. */
export async function buscarMiCaso(
  api: APIRequestContext,
  texto: string,
): Promise<{ casoId: string; clasificacionId: string | null }> {
  return esperarA(async () => {
    const { cases } = await (await api.get(`${API}/board/cases?limite=200`)).json();
    for (const c of cases) {
      const d = await (await api.get(`${API}/board/cases/${c.id}`)).json();
      const mio = d.reports.find((r: { caption?: string }) => r.caption === texto);
      if (mio) return { casoId: c.id, clasificacionId: mio.classification?.id ?? null };
    }
    return null;
  }, `que aparezca el reporte con texto "${texto}"`);
}
