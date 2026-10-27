#!/usr/bin/env python3
"""Ventozy — control ventiladores + GPU para portátiles Linux.

  python3 run.py                 → interfaz gráfica
  python3 run.py status          → diagnóstico de hardware
  python3 run.py daemon quiet    → daemon seguro (quiet | balanced | turbo)
  python3 run.py doctor          ← diagnóstico en un comando
  python3 run.py gpu auto        → gráficos integrados (ahorro)
  python3 run.py gpu on          → gráficos dedicados siempre activos
  python3 run.py install         → registra y activa el servicio systemd
  python3 run.py uninstall       → detiene y elimina el servicio
  python3 run.py hotkeys         → atajos: Fn+F5 modo fans · Fn+↑/↓ brillo teclado
  python3 run.py tray            → icono en el panel (Cinnamon/MATE/GNOME)
  python3 run.py adaptive 75     → modo adaptativo (menos ruido)
  python3 run.py import-nbfc --list "asus"        → catálogo de configs validadas nbfc-linux
  python3 run.py import-nbfc --install "ASUS/TUF Gaming FA506NC.json"
                                                  → importa a configs/ (soporta tu modelo)
  python3 run.py list            → equipos soportados
"""

import os
import shutil
import subprocess
import sys
import urllib.error

from ventozy.devices import detect

PROFILE_ALIAS = {"ruido": "quiet", "silencio": "quiet", "perf": "turbo",
                 "performance": "turbo", "equilibrado": "balanced"}


def doctor(device=None) -> int:
    """Diagnóstico de un comando: todo lo que la comunidad pregunta en issues."""
    import shutil
    checks = []

    def add(name, ok, hint=""):
        checks.append((name, ok, hint))

    # 1. entorno
    import platform
    add(f"Python {sys.version.split()[0]}", True)
    try:
        import tkinter  # noqa
        add("GUI (tkinter)", True)
    except ImportError:
        add("GUI (tkinter)", False, "sudo apt install python3-tk")
    try:
        import evdev  # noqa
        add("Hotkeys (evdev)", True)
    except ImportError:
        add("Hotkeys (evdev)", False, "sudo apt install python3-evdev")
    add("asusctl (opcional)", shutil.which("asusctl") is not None,
        "asus-linux.org — desbloquea curvas RGB/Aura oficiales")

    # 2. hardware
    device = device or detect()
    add(f"Equipo detectado: {device.info.model}", True)
    add(f"Ventiladores ({len(device.fans)})", bool(device.fans),
        "sudo modprobe asus-nb-wmi k10temp")
    add(f"Sensores ({len(device.sensors)})", bool(device.sensors),
        "sudo modprobe k10temp")
    if device.fans:
        probe = [f.read() for f in device.fans]
        add("Lectura PWM", all(v is not None for v in probe),
            "¿cables del hwmon? ver dmesg")
        writable = any(_probe_write(f) for f in device.fans)
        add("Escritura PWM (root)", writable,
            "corre con sudo, o añade regla udev de escritura")

    # 3. sensores de la batería / energía
    if device.battery_path:
        add("Límite batería (health charging)", os.path.exists(device.battery_path))
    from ventozy.providers.gpu import GpuSwitch
    g = GpuSwitch()
    add("GPU dedicada switch", g.available,
        "sin dGPU NVIDIA o módulo nvidia sin cargar")

    # 4. estado del daemon systemd
    try:
        r = subprocess.run(["systemctl", "is-active", "ventozy"],
                           capture_output=True, text=True)
        state = r.stdout.strip() or "unknown"
        active = state == "active"
        add(f"Servicio systemd ventozy: {state}", active,
            "sudo python3 run.py install")
    except OSError:
        pass

    print("\n> ventozy doctor")
    for name, ok, hint in checks:
        symbol = "✅" if ok else ("⚠ " if hint else "❌")
        print(f"  {symbol} {name}")
        if not ok and hint:
            print(f"       → {hint}")
    # posibles problemas de seguridad del save de curvas
    from ventozy.core.store import load as load_store
    saved = load_store()
    if saved.get("profiles"):
        print(f"\n  ℹ curvas personalizadas activas: "
              f"{', '.join(saved['profiles'])} ~ ~/.config/ventozy/curves.json")
    return 0


def _probe_write(fan):
    """Test de escritura NO destructivo: escribe el valor actual leído.

    Nota: escribir pwm? sin tocar pwm?_enable puede, en drivers raros,
    cambiar el modo del ventilador. Si el daemon está activo puede haber
    una carrera benigna (el daemon re-escribe su PWM al siguiente tick);
    ejecútalo preferiblemente con el daemon parado."""
    cur = fan.read()
    if cur is None:
        return False
    try:
        with open(fan.path, "w") as fh:
            fh.write(str(cur))
        return True
    except (OSError, PermissionError):
        return False


def gpu_cmd(arg: str) -> int:
    from ventozy.providers.gpu import GpuSwitch
    g = GpuSwitch()
    if arg == "state":
        print("Estado:", g.state())
        for d in g.devices:
            print("  ", d)
        return 0
    if not g.available:
        print("⚠  No se detectó GPU dedicada NVIDIA en el bus PCI.")
        return 1
    if arg in ("auto", "on"):
        label = {"auto": "integrada / ahorro (la GPU duerme sin uso)",
                 "on": "dedicada siempre activa"}[arg]
        try:
            ok = g.set_mode(arg)
        except (OSError, PermissionError):
            ok = False
        if ok:
            print(f"✅ GPU dedicada → {label}")
            return 0
        print("❌ Permisos insuficientes. Ejecuta con sudo:")
        print(f"   sudo python3 run.py gpu {arg}")
        return 1
    print(__doc__)
    return 2


def install_systemd() -> int:
    src = os.path.dirname(os.path.abspath(__file__))
    dst = "/opt/ventozy"
    if os.path.abspath(__file__) != os.path.join(dst, "run.py"):
        print(f"Copiando código a {dst} ...")
        try:
            os.makedirs(dst, exist_ok=True)
            for item in ("ventozy", "configs", "system", "assets"):
                s = os.path.join(src, item)
                if os.path.isdir(s):
                    shutil.copytree(s, os.path.join(dst, item),
                                    dirs_exist_ok=True)
            for f in ("run.py", "README.md"):
                if os.path.isfile(os.path.join(src, f)):
                    shutil.copy(os.path.join(src, f), dst)
        except (OSError, shutil.Error) as e:
            print(f"❌ error copiando código: {e}")
            return 1
    try:
        os.chmod(dst, 0o755)
        for root, dirs, files in os.walk(dst):
            for d in dirs:
                os.chmod(os.path.join(root, d), 0o755)
            for fn in files:
                os.chmod(os.path.join(root, fn), 0o644)
    except OSError:
        pass
    svc = os.path.join(src, "system", "ventozy.service")
    target = "/etc/systemd/system/ventozy.service"
    try:
        if os.path.isfile(svc):
            shutil.copy(svc, target)
        else:  # fallback: servicio mínimo embebido
            with open(target, "w") as f:
                f.write(f"""[Unit]
Description=Ventozy — control seguro de ventiladores
After=multi-user.target

[Service]
Type=simple
Restart=always
RestartSec=30
RestartForceExitStatus=75
SuccessExitStatus=75
ExecStart=/usr/bin/env python3 {os.path.join(dst, "run.py")} daemon balanced
WorkingDirectory={dst}
Nice=15
CPUSchedulingPolicy=idle
User=root

[Install]
WantedBy=multi-user.target
""")
    except OSError as e:
        print(f"❌ error instalando servicio: {e}")
        return 1
    for c in ("systemctl daemon-reload", "systemctl enable --now ventozy"):
        if os.system(c) != 0:
            print("❌ falló:", c)
            return 1
    print(f"✅ ventozy daemon instalado y activo al arranque ({dst}).")
    print("   Estado: systemctl status ventozy")
    print("   Logs:   journalctl -u ventozy -f")
    return 0


def uninstall_systemd() -> int:
    os.system("systemctl disable --now ventozy")
    try:
        os.remove("/etc/systemd/system/ventozy.service")
    except OSError:
        pass
    os.system("systemctl daemon-reload")
    print("✅ Servicio desinstalado.")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        return gui()
    cmd, *rest = sys.argv[1:]

    if cmd == "doctor":
        doctor()          # doctor() ya hace device = device or detect()
        return 0

    if cmd == "gpu":
        return gpu_cmd(rest[0] if rest else "state")
    if cmd == "power":
        from ventozy.providers.power import PowerModes
        arg = rest[0] if rest else "state"
        pm = PowerModes()
        if arg == "state":
            print("Actual:", pm.current())
            print("Disponible:", pm.available())
            print("Perfil estimado:", pm.guess_profile())
            return 0
        if arg in PowerModes.PROFILES:
            try:
                ok = pm.apply(arg)
            except (OSError, PermissionError):
                ok = False
            if ok:
                print(f"✅ potencia → {arg}")
                return 0
            print("❌ Permisos insuficientes: sudo python3 run.py power", arg)
            return 1
        print(__doc__)
        return 2

    if cmd == "autoswitch":
        from ventozy.providers.autoswitch import AutoSwitchDaemon
        ac = rest[0] if len(rest) > 0 else "balanced"
        dc = rest[1] if len(rest) > 1 else "quiet"
        AutoSwitchDaemon(detect(), ac=ac, dc=dc).run_forever()
        return 0

    if cmd == "import-nbfc":
        from ventozy.providers import nbfc
        arg = rest[0] if rest else "help"
        try:
            if arg in ("--list", "list"):
                q = rest[1] if len(rest) > 1 else ""
                matches = nbfc.search(q) if q else nbfc.search(".")
                for m in matches[:50]:
                    print(f"  {m.get('NotebookVendor', '?'):12} | "
                          f"{m.get('NotebookModel', '?'):40} | "
                          f"{m.get('ConfigFilename', '?')}")
                print(f"({len(matches)} resultados · catálogo de nbfc-linux)")
                return 0
            if arg in ("--search", "search"):
                hits = nbfc.search(" ".join(rest[1:]) or "")
                for m in hits[:20]:
                    print(f"  [{m.get('NotebookVendor', '?')}] "
                          f"{m.get('NotebookModel', '?')} → "
                          f"{m.get('ConfigFilename', '?')}")
                return 0
            if arg in ("--install", "install"):
                path = nbfc.install_model(" ".join(rest[1:]))
                print(f"✅ config Ventozy creada: {path}")
                print("   Verifica con:  sudo python3 run.py doctor")
                return 0
        except (urllib.error.URLError, OSError) as e:
            print(f"⚠ sin acceso a internet ({e.__class__.__name__}).")
            print("   El catálogo NBFC está en GitHub; revisa conexión.")
            return 1
        print(__doc__)
        return 2

    if cmd == "tray":
        from ventozy.providers.tray import run as tray_run
        return tray_run(detect())

    if cmd == "adaptive":
        from ventozy.providers.adaptive import AdaptiveController
        target = float(rest[0]) if rest else 75.0
        AdaptiveController(detect(), target=target).run_forever()
        return 0

    if cmd == "hotkeys":
        from ventozy.providers.hotkeys import HotkeyDaemon
        print("Ventozy hotkeys: Fn+F5 → modo fans · Fn+↑/↓ → brillo teclado")
        print("Ctrl+C para salir limpio (libera el grab)\n")
        HotkeyDaemon(detect()).run()
        return 0
    if cmd == "install":
        return install_systemd()
    if cmd == "uninstall":
        return uninstall_systemd()

    device = detect()
    if not device.fans:
        print("⚠  No se detectó PWM en /sys/class/hwmon.")
        print("   Prueba: sudo modprobe asus-nb-wmi k10temp")
        return 1

    if cmd == "status":
        print(f"Equipo: {device.info.model} ({device.info.vendor})")
        print(f"Perfiles: quiet | balanced | turbo")
        for f in device.fans:
            print(f"   Ventilador: {f.path}")
        for s in device.sensors:
            print(f"   Sensor: {s.path}")
        if device.battery_path:
            lim = device.battery_limit_current()
            print(f"   Límite de batería: {lim if lim else 'sin límite'}")
        print()
        for k, v in device.temperatures().items():
            print(f"   {k}: {v:.1f} °C")
        for i, r in enumerate(device.fan_rpms(), 1):
            print(f"   Fan{i}: {r} RPM")
        return 0

    if cmd == "daemon":
        prof = (rest[0] if rest else "balanced").lower().strip()
        prof = PROFILE_ALIAS.get(prof, prof)
        from ventozy.service import FanDaemon
        d = FanDaemon(device)
        if not d.start_profile(prof):
            print(f"❌ perfil '{prof}' desconocido (quiet | balanced | turbo)")
            return 2
        d.run_forever(prof)
        return 0

    if cmd == "list":
        print("Adaptadores de código: asus_tuf_fa506nc")
        print("Configs declarativas:  configs/*.json (comunidad)")
        return 0

    print(__doc__)
    return 2


def gui() -> int:
    device = detect()
    try:
        from ventozy.ui import MainWindow
    except ImportError:
        print("Falta tkinter:  sudo apt install python3-tk")
        return 1
    MainWindow(device).mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
