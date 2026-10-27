"""Retroiluminación de teclado (ASUS TUF y compatibles).

Dos capas, de mayor a menor control:
  1. Brillo:   /sys/class/leds/asus::kbd_backlight/brightness   (estándar kernel)
  2. Color:    requiere asusctl (proyecto oficial asus-linux.org) que habla
               con el controlador aura/multinumérico del kernel. El FA506NC
               tiene zona única (Single-Zone RGB) de firmware: los colores
               se eligen de la paleta del firmware y asusctl los expone.

Nota Fn+↑/↓: el firmware también puede tener su propio atajo; este daemon
garantiza el comportamiento aunque el ASUS layout cambie de distro en distro.
"""

import glob
import os


def find_led():
    """Devuelve la ruta base del LED de teclado ASUS."""
    candidates = [
        "/sys/class/leds/asus::kbd_backlight",
        "/sys/class/leds/asus::kbd_backlight_aux",
        "/sys/class/leds/tpacpi::kbd_backlight",  # ThinkPad fallback genérico
    ]
    for d in candidates:
        if os.path.isdir(d):
            return d
    # último recurso: cualquier led con 'kbd' en el nombre
    for d in sorted(glob.glob("/sys/class/leds/*kbd*")):
        return d
    return None


class KbdBacklight:
    def __init__(self):
        self.base = find_led()
        self.asusctl = os.path.exists("/usr/bin/asusctl") or \
            os.system("command -v asusctl >/dev/null") == 0

    @property
    def available(self) -> bool:
        return self.base is not None

    # ---------- brillo ----------
    def max_brightness(self) -> int:
        if not self.base:
            return 0
        try:
            return int(open(f"{self.base}/max_brightness").read().strip())
        except (OSError, ValueError):
            return 3  # valor típico ASUS (0-3)

    def brightness(self) -> int:
        if not self.base:
            return 0
        try:
            return int(open(f"{self.base}/brightness").read().strip())
        except (OSError, ValueError):
            return 0

    def set_brightness(self, value: int) -> bool:
        if not self.base:
            return False
        v = max(0, min(self.max_brightness(), value))
        try:
            with open(f"{self.base}/brightness", "w") as f:
                f.write(str(v))
            return True
        except (OSError, PermissionError):
            return False

    def brightness_step(self, delta: int) -> bool:
        """Fn+↑/↓: paso ±1 (con wrap → si sta al máximo, subez no hace nada)."""
        return self.set_brightness(self.brightness() + delta)

    # ---------- color (requiere asusctl / Aura) ----------
    PALETTE = [
        ("Blanco",     "ffffff"),
        ("Rojo",       "ff3333"),
        ("Naranja",    "ff8800"),
        ("Amarillo",   "ffee00"),
        ("Verde",      "22cc44"),
        ("Cian",       "20d3c4"),
        ("Azul",       "2b7cd3"),
        ("Violeta",    "a34bff"),
        ("Rosa",       "ff4d8d"),
    ]

    @property
    def colors_available(self) -> bool:
        """Solo los equipos con Aura RGB soportan color; el FA506NC tiene
        Single-Zone RGB de firmware → disponible vía asusctl."""
        return self.asusctl

    def set_color(self, hex_rgb: str, mode: str = "static") -> bool:
        """hex_rgb sin '#', p. ej. '2b7cd3'. Usa asusctl si está."""
        if not self.colors_available:
            return False
        import subprocess
        try:
            subprocess.run(["asusctl", "led-mode", mode], check=False,
                           capture_output=True)
            r = subprocess.run(["asusctl", "keyboard-color", hex_rgb],
                               check=False, capture_output=True)
            if r.returncode != 0:
                # versiones nuevas: `asusctl aura --color`
                subprocess.run(["asusctl", "aura", "--color", hex_rgb],
                               check=False, capture_output=True)
            return True
        except FileNotFoundError:
            return False
