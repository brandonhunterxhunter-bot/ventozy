"""Botón de GPU dedicada ↔ integrada (runtime power management).

Es lo que hace G-Helper al "deshabilitar/habilitar" la GPU dedicada, pero
implementado con herramientas estándar del kernel (sin hacks):

  /sys/bus/pci/devices/<dgpu>/power/control = "auto"  → GPU se duerme sola
                                                        sin uso (ahorro)
  = "on" → despierta siempre (juegos/render)

100 % reversible, seguro y disponible en cualquier driver moderno.
Un "hard off" real (Optimus off, remove/rescan PCI) vive en supergfxctl;
aquí no se hace por seguridad del usuario.
"""

import glob
import os

NVIDIA_VENDOR = "0x10de"


def find_dgpu() -> list:
    """Paths de dispositivos NVIDIA display en el bus PCI."""
    out = []
    for d in sorted(glob.glob("/sys/bus/pci/devices/*")):
        try:
            vend = open(os.path.join(d, "vendor")).read().strip().lower()
            cls = open(os.path.join(d, "class")).read().strip().lower()
        except OSError:
            continue
        if vend == NVIDIA_VENDOR and cls.startswith("0x03"):
            out.append(d)
    return out


class GpuSwitch:
    """API lista para CLI y GUI."""

    def __init__(self):
        self.devices = find_dgpu()

    @property
    def available(self) -> bool:
        return bool(self.devices)

    def state(self) -> str:
        if not self.available:
            return "n/a"
        try:
            return open(os.path.join(self.devices[0], "power", "control")).read().strip()
        except OSError:
            return "?"

    def set_mode(self, mode: str) -> bool:
        """mode: 'on' (cierto siempre listo) | 'auto' (ahorro, GPU duerme)."""
        if mode not in ("on", "auto"):
            return False
        ok = False
        for d in self.devices:
            try:
                with open(os.path.join(d, "power", "control"), "w") as f:
                    f.write(mode)
                ok = True
            except (OSError, PermissionError):
                pass
        return ok
