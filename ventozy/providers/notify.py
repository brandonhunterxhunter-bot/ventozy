"""Notificaciones de escritorio (Freedesktop: Mint/Cinnamon/GNOME/KDE).

`notify-send` está presente de serie en Mint. Si no existe, no-op silencioso:
nunca rompe el flujo de control del daemon por una notificación.

Uso:
    from ventozy.providers.notify import notify
    notify("Ventozy", "Modo Turbo activado 🚀")
"""

import shutil
import subprocess


def available() -> bool:
    return shutil.which("notify-send") is not None


def notify(title: str, body: str = "", urgency: str = "normal",
           timeout: int = 3000) -> bool:
    """urgency: low | normal | critical (critical usa el sonido del sistema
    en la mayoría de escritorios — ideal para el watchdog)."""
    if not available():
        return False
    try:
        subprocess.Popen(
            ["notify-send", "-a", "Ventozy", "-u", urgency,
             "-t", str(timeout), title, body],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False
