"""Daemon de atajos globales estilo G-Helper (Fn+F5, Fn+↑, Fn+↓).

Cómo llegan las teclas en un ASUS:
  - Fn+F5    → nvfarr la mayoría de TUF emite KEY_F5 (y a veces tocada la WMI:
               `asus-nb-wmi` la mapea igualmente a KEY_F5).
  - Fn+↑/↓   → el firmware emite KEY_KBDILLUMUP / KEY_KBDILLUMDOWN a través
               de asus-nb-wmi (NO las flechas normales!). Así no capturamos
               las flechas de navegación jamás.

Acciones:
  F5                → ciclo del modo ventilador: quiet → balanced → turbo
  KBDILLUMUP/DOWN   → brillo del teclado, LED /sys asus::kbd_backlight

Necesita evdev (sudo apt install python3-evdev) y root (grab de /dev/input).
Instalar como servicio: está incluido en `sudo python3 run.py install`.
"""

import errno
import os
import sys
import time


class HotkeyDaemon:
    def __init__(self, device):
        self.device = device
        self.order = ["quiet", "balanced", "turbo"]
        self._idx_local = 0        # fallback si no hay daemon systemd
        self.kbd = None

    # ------------------------------------------------------------
    def _current_systemd_profile(self):
        """Intenta inferir del unit actual qué perfil está corriendo."""
        import subprocess
        try:
            r = subprocess.run(["systemctl", "show", "-p", "ExecStart",
                                "--value", "ventozy"], capture_output=True,
                               text=True, timeout=2)
            for name in self.order:
                if name in (r.stdout or "").lower():
                    return name
        except Exception:
            pass
        return None

    def cycle_fan_mode(self, log=print):
        """Cambia al siguiente perfil y lo aplica YA (ambos ventiladores)."""
        prev = self._current_systemd_profile()
        names = [n for n in self.order if n in self.device.profiles] or self.order
        try:
            new = names[(names.index(prev) + 1) % len(names)] if prev \
                else names[self._idx_local % len(names)]
        except ValueError:
            new = names[self._idx_local % len(names)]
        self._idx_local = (self._idx_local + 1) % len(names)

        from ..service import FanDaemon
        d = FanDaemon(self.device)
        if not d.start_profile(new):
            log(f"[hotkeys] perfil desconocido: {new}")
            return None
        pwm = d.step()
        prof = self.device.profiles[new]
        log(f"[hotkeys] Fn+F5 → {prof.label} (PWM {pwm})")
        try:
            from .notify import notify
            notify("Ventozy", f"Fn+F5 → ventiladores: {prof.label}")
        except Exception:
            pass
        # si systemd corre ventozy, actualiza el perfil persistente del unit
        try:
            import subprocess
            subprocess.run(["bash", "-c",
                "sudo sed -i 's|daemon [a-z]*|daemon %s|' "
                "/etc/systemd/system/ventozy.service && systemctl daemon-reload"
                % new], capture_output=True)
        except Exception:
            pass
        return new

    def keyboard_step(self, delta, log=print):
        if self.kbd is None:
            from .kbd import KbdBacklight
            self.kbd = KbdBacklight()
        if not self.kbd.available:
            log("[hotkeys] sin LED de teclado en sysfs")
            return False
        ok = self.kbd.brightness_step(delta)
        if ok:
            log(f"[hotkeys] Fn+{'↑' if delta > 0 else '↓'} → brillo teclado "
                f"{self.kbd.brightness()}/{self.kbd.max_brightness()}")
            try:
                from .notify import notify
                notify("Ventozy", f"Brillo teclado: "
                        f"{self.kbd.brightness()}/{self.kbd.max_brightness()}")
            except Exception:
                pass
        return ok

    # ------------------------------------------------------------
    def run(self, log=print):
        try:
            import evdev
        except ImportError:
            log("[hotkeys] Falta evdev: sudo apt install python3-evdev")
            sys.exit(1)
        from evdev import ecodes, KeyEvent
        import select

        TARGETS_DIGIT = {ecodes.KEY_F5}
        TARGETS_SLOTS = [ecodes.KEY_KBDILLUMUP, ecodes.KEY_KBDILLUMDOWN]

        devices = []
        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
                caps = dev.capabilities(quiet=True)
            except (OSError, PermissionError):
                continue
            key_numbers = set()
            for group in caps.values():
                key_numbers.update(group)
            wanted = TARGETS_DIGIT | set(TARGETS_SLOTS)
            if wanted & key_numbers and ecodes.EV_KEY in caps:
                try:
                    dev.grab()   # exclusivo: la tecla del firmware llega aquí
                    devices.append(dev)
                    log(f"[hotkeys] escuchando: {dev.name} ({dev.path})")
                except PermissionError:
                    log(f"[hotkeys] ⚠ necesita root/rule udev para {path}")
                except OSError as e:
                    if e.errno == errno.EACCES:
                        log(f"[hotkeys] ⚠ root requerido para {path}")

        if not devices:
            log("[hotkeys] ningún teclado capturado (¿permisos?).")
            log("        Añade regla udev o corre el servicio como root.")
            sys.exit(1)

        try:
            while True:
                r, _, _ = select.select(devices, [], [], 1.0)
                for dev in r:
                    try:
                        for event in dev.read():
                            if event.type != ecodes.EV_KEY:
                                continue
                            ke = KeyEvent(event)
                            if ke.keystate != KeyEvent.key_down:
                                continue
                            code = ke.keycode
                            if isinstance(code, list):
                                code = code[0] if code else ""
                            if code == "KEY_F5":
                                self.cycle_fan_mode(log)
                            elif code == "KEY_KBDILLUMUP":
                                self.keyboard_step(+1, log)
                            elif code == "KEY_KBDILLUMDOWN":
                                self.keyboard_step(-1, log)
                    except (BlockingIOError, OSError):
                        continue
        except KeyboardInterrupt:
            pass
        finally:
            log("[hotkeys] deteniendo, liberando teclados...")
            for dev in devices:
                try:
                    dev.ungrab()
                except OSError:
                    pass
