#!/usr/bin/env python3
"""Genera assets/ventozy-icon.png (256x256) — logo moderno de Ventozy.

Viable SIN PIL ni dependencias: dibuja píxel a píxel y codifica PNG
 manualmente con zlib. El logo: tarjeta redondeada oscura con degradado,
ventilador de 6 aspas en degradado azul→cian y hub brillante.

Uso: python3 assets/make_icon.py [salida.png]
"""

import math
import struct
import sys
import zlib

S = 256                     # tamaño
Cx = Cy = S / 2
R = 96                      # radio del ventilador
HUB = 30                    # radio del hub
CARD = 18                   # margen de la tarjeta

# paleta moderna
BG_TOP = (0x20, 0x22, 0x2b)
BG_BOT = (0x0c, 0x0d, 0x11)
BLADE_IN = (0x2b, 0x7c, 0xd3)    # azul
BLADE_OUT = (0x20, 0xd3, 0xc4)   # cian


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def blend(base, fore, alpha):
    return tuple(int(base[i] * (1 - alpha) + fore[i] * alpha) for i in range(3))


def inside_card(x, y):
    # tarjeta redondeada: rect con radio 44
    r = 44.0
    x0, y0, x1, y1 = CARD, CARD, S - CARD, S - CARD
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return False
    # esquinas
    for cx, cy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        if abs(x - cx) > (x1 - x0) / 2 - r / 2 or False:
            pass
    # más simple: distancia a la esquina más cercana
    nx = min(max(x, x0 + r), x1 - r)
    ny = min(max(y, y0 + r), y1 - r)
    return (x - nx) ** 2 + (y - ny) ** 2 <= r * r or (x0 + r <= x <= x1 - r or y0 + r <= y <= y1 - r)


def blade_alpha(angle, radius):
    """Devuelve 1.0 dentro del aspa según (ángulo, radio) polares."""
    span = math.radians(34)          # anchura del aspa
    n = 6                            # número de aspas
    a = (angle % (2 * math.pi / n))
    # desplaza el aspa hacia atrás para dar 'curva' visual
    a = (a - radius / R * 0.55) % (2 * math.pi / n)
    if a < span:
        proxim = 1.0 - abs(a / span - 0.5) * 2     # 0 en el borde, 1 en el centro
        fade = 1.0 - max(0.0, (radius - R * 0.97) / (R * 0.03))
        return max(0.0, min(1.0, proxim * 1.4)) * fade
    return 0.0


def render(pixels):
    for y in range(S):
        for x in range(S):
            # fondo degradado
            col = lerp(BG_TOP, BG_BOT, y / S)
            if inside_card(x, y):
                # degradado radial del ventilador
                dx, dy = x - Cx, y - Cy
                radius = math.hypot(dx, dy)
                ang = math.atan2(dy, dx)
                if radius <= R:
                    ba = blade_alpha(ang, radius)
                    if radius <= HUB:
                        # hub con brillo
                        t = 1 - radius / HUB
                        hub = lerp((0x9a, 0xe6, 0xff), BLADE_IN, 0.35)
                        col = blend(col, hub, 0.95)
                    elif blade_alpha(ang, radius) > 0:
                        t = radius / R
                        col = blend(col, lerp(BLADE_IN, BLADE_OUT, t), max(0.4, ba))
                    else:
                        # anillo entre aspas: fondo con leve tinte azul
                        col = blend(col, (0x18, 0x2c, 0x44), 0.35)
                else:
                    # aro exterior fino
                    if R + 3 >= radius >= R - 2:
                        col = blend(col, (0x3a, 0xd3, 0xc4), 0.55)
                # borde de la tarjeta
                edge = min(x - CARD, S - CARD - x, y - CARD, S - CARD - y)
                if edge < 2:
                    col = blend(col, (0x3a, 0x3b, 0x42), 0.7)
            pixels.extend(col)         # orden RGBA correcto: R,G,B,A
            pixels.append(255)
    return pixels


def write_png(path, pixels):
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)

    ihdr = struct.pack(">IIBBBBB", S, S, 8, 6, 0, 0, 0)   # RGBA 8bit
    raw = b"".join(b"\x00" + bytes(pixels[i * S * 4:(i + 1) * S * 4])
                   for i in range(S))
    idat = zlib.compress(raw, 9)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", ihdr))
        f.write(chunk(b"IDAT", idat))
        f.write(chunk(b"IEND", b""))


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "ventozy-icon.png"
    px = render([])
    write_png(out, px)
    print(f"icono escrito: {out} ({S}x{S})")


if __name__ == "__main__":
    main()
