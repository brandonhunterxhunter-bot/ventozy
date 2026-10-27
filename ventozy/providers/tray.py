"""Icono de bandeja (panel de Cinnamon/MATE/GNOME) con menú rápido.

Depende de gi + AppIndicator (ubuntu: gir1.2-appindicator3-0.1).
Opcional: sin él, el resto funciona igual. Instalar: 
    sudo apt install gir1.2-appindicator3-0.1 (Mint ya lo trae normalmente)

Ejecutar: python3 run.py tray
"""

import os


def available() -> bool:
    try:
        import gi  # noqa
        gi.require_version("AppIndicator3", "0.1")
        return True
    except (ImportError, ValueError):
        return False


def run(device) -> int:
    """Bucle del tray (bloquea). Menú: modos de fan, GPU, salir."""
    if not available():
        print("[tray] Falta gir1.2-appindicator3-0.1:")
        print("     sudo apt install gir1.2-appindicator3-0.1")
        return 1

    import gi
    gi.require_version("AppIndicator3", "0.1")
    from gi.repository import AppIndicator3
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    import signal

    icon_path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), "assets", "ventozy-icon.png")
    from .notify import notify

    current = {"profile": "balanced"}

    def set_profile(_src, name):
        try:
            from ..service import FanDaemon
            d = FanDaemon(device)
            if d.start_profile(name):
                d.step()          # aplica YA a ambos fans
                current["profile"] = name
                notify("Ventozy", f"Ventiladores: {device.profiles[name].label}")
        except Exception as e:
            notify("Ventozy", f"⚠ {e}", urgency="critical")

    def toggle_gpu(_src):
        from .gpu import GpuSwitch
        g = GpuSwitch()
        mode = "auto" if g.state() != "auto" else "on"
        if g.set_mode(mode):
            notify("Ventozy", f"GPU dedicada → "
                               f"{'ahorro' if mode == 'auto' else 'activa'}")

    def quit_tray(_src):
        try:
            device.auto()          # seguridad: restaurar control del kernel
        finally:
            Gtk.main_quit()

    menu = Gtk.Menu()
    for name, prof in device.profiles.items():
        item = Gtk.MenuItem(label=prof.label)
        item.connect("activate", lambda _s, n=name: set_profile(_s, n))
        menu.append(item)
    menu.append(Gtk.SeparatorMenuItem())
    item_gpu = Gtk.MenuItem(label="🎮 GPU dedicada: alternar")
    item_gpu.connect("activate", toggle_gpu)
    menu.append(item_gpu)
    menu.append(Gtk.SeparatorMenuItem())
    item_quit = Gtk.MenuItem(label="Salir (restaura Auto)")
    item_quit.connect("activate", quit_tray)
    menu.append(item_quit)
    menu.show_all()
    indicator.set_menu(menu)

    signal.signal(signal.SIGINT, lambda *_: Gtk.main_quit())
    print("[tray] Ventozy en la bandeja. Ctrl+C para salir.")
    try:
        Gtk.main()
    except KeyboardInterrupt:
        pass
    return 0
