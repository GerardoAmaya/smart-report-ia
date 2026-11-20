"""Foto de perfil del bot: una via con su linea pintada y un pin color cono.

Paleta de PLAN.md: asfalto, pintura de senalizacion, cono de obra.
Se dibuja a 4x y se reduce, para bordes suaves. Generada y no hecha a mano
por lo mismo que las capturas del README: lo que no se puede rehacer envejece.

    docker compose cp scripts/avatar-bot.py api:/tmp/ && \
    docker compose exec api python /tmp/avatar-bot.py /tmp/a.png /tmp/previa.png
"""

import math
import sys

from PIL import Image, ImageDraw

LADO = 640
K = 4
S = LADO * K

VERDE = (31, 111, 92)  # --verde, senalizacion
ASFALTO = (22, 24, 26)  # --tinta
PINTURA = (238, 239, 236)  # --fondo, pintura blanca
AMBAR = (199, 123, 35)  # --ambar, cono de obra

img = Image.new("RGB", (S, S), VERDE)
d = ImageDraw.Draw(img)


def p(x, y):
    return (x * S, y * S)


# La via, en perspectiva: ancha abajo, estrecha hacia el horizonte.
horizonte = 0.50
via = [p(0.43, horizonte), p(0.57, horizonte), p(0.98, 1.02), p(0.02, 1.02)]
d.polygon(via, fill=ASFALTO)

# Bordes de la via, la linea continua de los lados.
for (x0, x1) in ((0.43, 0.02), (0.57, 0.98)):
    d.line([p(x0, horizonte), p(x1, 1.02)], fill=PINTURA, width=int(0.012 * S))

# Linea central discontinua, cada tramo mas largo y ancho al acercarse.
y = 0.74
largo = 0.05
while y < 1.02:
    t = (y - horizonte) / (1.02 - horizonte)
    ancho = 0.006 + 0.022 * t
    d.polygon(
        [p(0.5 - ancho / 2, y), p(0.5 + ancho / 2, y),
         p(0.5 + ancho / 2 * 1.3, y + largo), p(0.5 - ancho / 2 * 1.3, y + largo)],
        fill=PINTURA,
    )
    y += largo * 2.1
    largo *= 1.35

# El pin: gota con la punta clavada en la via.
cx, cy, r = 0.5, 0.36, 0.17
punta = 0.70

# Cuerpo de la gota: circulo mas triangulo tangente.
ang = math.asin(r / (punta - cy))
tx = r * math.cos(ang)
ty = r * math.sin(ang)
d.polygon([p(cx - tx, cy + ty), p(cx + tx, cy + ty), p(cx, punta)], fill=AMBAR)
d.ellipse([p(cx - r, cy - r), p(cx + r, cy + r)], fill=AMBAR)

# El ojo del pin: blanco con un punto de asfalto, el lugar exacto.
ri = r * 0.46
d.ellipse([p(cx - ri, cy - ri), p(cx + ri, cy + ri)], fill=PINTURA)
rp = r * 0.17
d.ellipse([p(cx - rp, cy - rp), p(cx + rp, cy + rp)], fill=ASFALTO)

img = img.resize((LADO, LADO), Image.LANCZOS)
img.save(sys.argv[1], "PNG", optimize=True)

# Vista previa con el recorte circular que aplica Telegram.
mascara = Image.new("L", (LADO * K, LADO * K), 0)
ImageDraw.Draw(mascara).ellipse([0, 0, LADO * K, LADO * K], fill=255)
mascara = mascara.resize((LADO, LADO), Image.LANCZOS)
previa = Image.new("RGB", (LADO, LADO), (255, 255, 255))
previa.paste(img, mask=mascara)
previa.save(sys.argv[2], "PNG")
