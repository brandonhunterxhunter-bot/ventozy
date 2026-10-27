"""Interfaz Tk. NO conoce hardware: solo consume la API Device.

Cada "sección" es un Frame con método opcional `refresh()`; se agregan
en MainWindow.__init__. Nunca tocar sysfs aquí.
"""

import tkinter as tk
from tkinter import messagebox
from typing import Optional

from ..devices import Device

REFRESH_MS = 1000          # tiempo real con cache TTL corta (casi 0 CPU)

STYLE = {
    "bg": "#1e1f24",
    "panel": "#26272c",
    "accent": "#2b7cd3",
    "idle": "#2d2e34",
    "fg": "white",
    "dim": "#888888",
}


def make_button(parent, text, cmd, selected=False):
    return tk.Button(parent, text=text, command=cmd, cursor="hand2",
                     bg=STYLE["accent"] if selected else STYLE["idle"],
                     fg=STYLE["fg"], activebackground="#3a3b42",
                     activeforeground=STYLE["fg"], relief="flat",
                     font=("Segoe UI", 10), padx=12, pady=6)


class MainWindow(tk.Tk):
    """Ventana principal compuesta por secciones intercambiables."""

    def __init__(self, device: Device):
        super().__init__()
        self.device = device
        self.title("Ventozy · " + getattr(device.info, "model", ""))
        self.configure(bg=STYLE["bg"])
        self.geometry("620x760")
        self.resizable(False, False)

        header = tk.Frame(self, bg=STYLE["bg"])
        header.pack(fill="x", pady=(14, 4))
        tk.Label(header, text="⚡ Ventozy", bg=STYLE["bg"], fg="#4db8ff",
                 font=("Segoe UI", 16, "bold")).pack(side="left", padx=16)
        tk.Label(header, text=getattr(device.info, "model", ""),
                 bg=STYLE["bg"], fg=STYLE["dim"]).pack(side="right", padx=16)

        # curvas editadas por el usuario sobreviven al reinicio
        try:
            from ..core.store import apply_to
            apply_to(device)
        except Exception:
            pass

        # orden de secciones (agregar/quitar aquí para cambiar la GUI)
        self.panel_status = StatusSection(self, device)
        self.panel_daemon = DaemonSection(self, device)   # antes de profiles:
        self.panel_profiles = ProfilesSection(self, device)  # select() lo usa
        self.panel_gpu = GpuSection(self, device)
        self.panel_curve = CurveSection(self, device)
        self.panel_manual = ManualSection(self, device)
        self.panel_battery = BatterySection(self, device)
        self.panel_power = PowerSection(self, device)
        self.panel_extras = ExtrasSection(self, device)
        self.panel_keyboard = KeyboardSection(self, device)
        self.panel_service = ServiceSection(self, device)

        self.tick()

    def tick(self):
        self.panel_status.refresh()
        self.panel_gpu.refresh()
        self.after(REFRESH_MS, self.tick)


class Section(tk.LabelFrame):
    """Base de sección: frame interno y estilos comunes."""

    def __init__(self, parent: "MainWindow", device: Device, title: str):
        self.app = parent
        self.device = device
        super().__init__(parent, text=title, bg=STYLE["panel"], fg="#cccccc",
                         font=("Segoe UI", 9), bd=1, relief="solid")
        self.pack(fill="x", padx=16, pady=8)
        self.inner = tk.Frame(self, bg=STYLE["panel"])
        self.inner.pack(fill="x", padx=10, pady=8)

    def refresh(self):
        pass


class StatusSection(Section):
    def __init__(self, parent, device):
        super().__init__(parent, device, "Estado del sistema")
        self.lbl_temps = tk.Label(self.inner, text="--", bg=STYLE["panel"],
                                  fg="white", font=("Segoe UI", 11, "bold"))
        self.lbl_rpm = tk.Label(self.inner, text="--", bg=STYLE["panel"],
                                fg="#9ad14b", font=("Segoe UI", 11, "bold"))
        self.lbl_bat = tk.Label(self.inner, text="", bg=STYLE["panel"],
                                fg=STYLE["dim"], font=("Segoe UI", 11, "bold"))
        self.lbl_temps.pack(side="left", padx=8)
        self.lbl_rpm.pack(side="left", padx=8)
        self.lbl_bat.pack(side="left", padx=8)

    def refresh(self):
        """Tiempo real: TODOS los sensores del hub (hwmon/GPU/batería del chasis).
        La más caliente se resalta; es la que guía las curvas del daemon."""
        temps = self.device.temperatures()
        if temps:
            hottest_name = max(temps, key=temps.get)
            items = []
            for name, v in sorted(temps.items()):
                mark = "▸" if name == hottest_name else " "
                items.append(f"{mark} {name} {v:.0f}°C")
            txt = " ".join(items)
        else:
            txt = "-- (sin sensores aún)"
        hot = any(v > 85 for v in temps.values()) if temps else False
        self.lbl_temps.configure(text=txt, fg="#e05656" if hot else "white")
        rpms = self.device.fan_rpms()
        self.lbl_rpm.configure(
            text="Fans " + " / ".join(f"{r} r/m" for r in rpms) if rpms
                 else "Fans -- r/m")
        if self.device.battery_path:
            import pathlib
            cap = self.device.battery_path.replace(
                "charge_control_end_threshold", "capacity")
            limit = self.device.battery_limit_current()
            try:
                v = int(pathlib.Path(cap).read_text().strip())
            except (OSError, ValueError):
                v = None
            lim = f" → máx {limit} %" if limit else ""
            self.lbl_bat.configure(text=f"Bat {v if v is not None else '?'} %{lim}")


class ProfilesSection(Section):
    """Modos estilo G-Helper: Silencio / Equilibrado / Turbo / Auto."""

    def __init__(self, parent, device):
        super().__init__(parent, device, "Modos de ventilador")
        self.buttons = {}
        default = "balanced" if "balanced" in device.profiles else \
            next(iter(device.profiles), None)
        for name, prof in device.profiles.items():
            b = make_button(self.inner, prof.label,
                            lambda n=name: self.select(n),
                            selected=(name == default))
            b.pack(side="left", padx=4)
            self.buttons[name] = b
        b_auto = make_button(self.inner, "⏻  Auto", lambda: self.select(None),
                             selected=(default is None))
        b_auto.pack(side="left", padx=4)
        self.buttons["__auto__"] = b_auto
        self.selected = default
        if default:
            self.app.after(100, lambda: self.select(default, announce=False))
        else:
            self.app.after(100, lambda: self.app.panel_daemon.stop())

    def _daemon(self):
        """Devuelve la sección del daemon o None si aún no existe (orden de
        construcción de la GUI). Evita AttributeError al iniciar."""
        return getattr(self.app, "panel_daemon", None)

    def select(self, name, announce=True):
        self.selected = name
        for n, b in self.buttons.items():
            active = (n == name or (n == "__auto__" and name is None))
            b.configure(bg=STYLE["accent"] if active else STYLE["idle"])
        if name is None:
            d = self._daemon()
            if d:
                d.stop()
            self.device.auto()
            if announce:
                messagebox.showinfo(
                    "Auto", "Control automático del kernel restaurado ✅")
            return
        d = self._daemon()
        if d:
            d.start(name)


class GpuSection(Section):
    """Gráficos integrada ↔ dedicada vía runtime PM (cero hacks, reversible)."""

    def __init__(self, parent, device):
        super().__init__(parent, device, "Gráficos (integrada ↔ dedicada)")
        from ..providers.gpu import GpuSwitch
        self.switch = GpuSwitch()
        self.lbl_state = tk.Label(self.inner, text="", bg=STYLE["panel"],
                                  fg=STYLE["dim"], font=("Segoe UI", 10))
        if not self.switch.available:
            tk.Label(self.inner, text="Sin GPU dedicada NVIDIA detectada",
                     bg=STYLE["panel"], fg=STYLE["dim"]).pack()
            return
        self.b_igpu = make_button(self.inner, "🖥  Integrada (ahorro)",
                                  lambda: self.set("auto"))
        self.b_dgpu = make_button(self.inner, "🎮  Dedicada (siempre lista)",
                                  lambda: self.set("on"))
        self.b_igpu.pack(side="left", padx=4)
        self.b_dgpu.pack(side="left", padx=4)
        self.lbl_state.pack(side="left", padx=8)
        self.refresh()

    def set(self, mode):
        if not self.switch.set_mode(mode):
            messagebox.showwarning(
                "Permisos", "Se necesitan permisos root.\nEjecuta:\n"
                            f"  sudo python3 run.py gpu {mode}")
        self.refresh()

    def refresh(self):
        if not self.switch.available:
            return
        s = self.switch.state()
        self.lbl_state.configure(
            fg=STYLE["accent"] if s == "on" else STYLE["dim"],
            text={"on": "🎮 dedicada activa",
                  "auto": "💾 ahorro (auto)",
                  "?": ""}.get(s, ""))
        self.b_igpu.configure(bg=STYLE["accent"] if s == "auto" else STYLE["idle"])
        self.b_dgpu.configure(bg=STYLE["accent"] if s == "on" else STYLE["idle"])


class CurveSection(Section):
    """Editor de curvas con puntos arrastrables, como los fan curves de G-Helper.

    - Eje X: temperatura (30–95 °C). Eje Y: PWM (0 abajo, 255 arriba).
    - Arrastra los puntos; la curva se aplica al perfil elegido en el desplegable
      y también al daemon que esté corriendo ese perfil.
    - Restricciones de seguridad: el PWM no baja del piso min_pwm del equipo
      y la temperatura mínima editable es 35 °C.
    """

    W, H, PAD = 320, 150, 24
    T_MIN, T_MAX = 35, 95

    def __init__(self, parent, device):
        super().__init__(parent, device, "Curva editable del perfil")
        import tkinter.ttk as ttk
        self.profile_name = tk.StringVar()
        names = list(device.profiles) or ["balanced"]
        self.profile_name.set(names[0])
        row = tk.Frame(self.inner, bg=STYLE["panel"])
        row.pack(fill="x")
        ttk.Combobox(row, textvariable=self.profile_name, values=names,
                     state="readonly", width=14).pack(side="left", padx=4)
        make_button(self.inner, "Aplicar ahora", self.apply_now).pack(
            side="left", padx=4)
        make_button(self.inner, "↺ Original", self.reset_factory).pack(
            side="left", padx=4)

        self.canvas = tk.Canvas(self.inner, width=self.W, height=self.H,
                                bg="#17181b", highlightthickness=1,
                                highlightbackground="#3a3b42")
        self.canvas.pack(pady=4)
        self._bind()
        self.reload_curve()

    # -- conversiones ------------------------------------------------
    def _t2x(self, t):
        span = self.W - 2 * self.PAD
        return self.PAD + (t - self.T_MIN) / (self.T_MAX - self.T_MIN) * span

    def _p2y(self, p):
        span = self.H - 2 * self.PAD
        return self.H - self.PAD - p / 255 * span

    def _x2t(self, x):
        span = self.W - 2 * self.PAD
        t = self.T_MIN + (x - self.PAD) / span * (self.T_MAX - self.T_MIN)
        return max(self.T_MIN, min(self.T_MAX, int(round(t))))

    def _y2p(self, y):
        span = self.H - 2 * self.PAD
        p = (self.H - self.PAD - y) / span * 255
        return max(self.min_pwm, min(255, int(round(p))))

    @property
    def min_pwm(self):
        return getattr(self.device, "min_pwm", 0)

    # -- estado ------------------------------------------------------
    def _curve(self):
        prof = self.device.profiles.get(self.profile_name.get())
        return prof.curve if prof else []

    def set_curve(self, pts):
        name = self.profile_name.get()
        prof = self.device.profiles.get(name)
        if not prof:
            return
        pts = sorted(pts, key=lambda p: p[0])
        prof.curve = [tuple(p) for p in pts]
        # persistencia: tus curvas sobreviven al reinicio (core.store)
        try:
            from ..core.store import save_profiles
            save_profiles(self.device)
        except OSError:
            pass
        # si el daemon corre este perfil, actualizarlo al vuelo
        d = self.app.panel_daemon
        if d.daemon and d.daemon.curve_pts is not None:
            cur = getattr(d.daemon, "profile_name", None)
            if cur == name or d.running:
                d.daemon.curve_pts = prof.curve
        self._draw()

    def reload_curve(self):
        self._draw()

    # -- dibujo ------------------------------------------------------
    def _draw(self):
        c = self.canvas
        c.delete("all")
        # reglas
        for t in range(40, 96, 20):
            c.create_line(self._t2x(t), self.PAD, self._t2x(t), self.H - self.PAD,
                          fill="#26272c")
        # banda del piso de hardware
        if self.min_pwm > 0:
            y0 = self._p2y(self.min_pwm)
            c.create_rectangle(self.PAD, y0, self.W - self.PAD, self.H - self.PAD,
                               fill="#241a10", outline="")
            c.create_text(self.W - self.PAD - 4, y0 + 7, text=f"min {self.min_pwm}",
                          fill="#e6a23c", anchor="e", font=("Segoe UI", 7))
        pts = self._curve()
        if not pts:
            return
        # líneas
        coords = [c_ for p in pts for c_ in (self._t2x(p[0]), self._p2y(p[1]))]
        c.create_line(*coords, fill="#4db8ff", width=2, smooth=True)
        # puntos
        for i, (t, p) in enumerate(pts):
            x, y = self._t2x(t), self._p2y(p)
            r = 6
            c.create_oval(x - r, y - r, x + r, y + r, fill="#2b7cd3",
                          outline="white", tags=f"pt{i}")
            c.create_text(x, y - 12, text=f"{t}°:{p}", fill="#cccccc",
                          font=("Segoe UI", 7), tags=f"pt{i}")

    # -- interacción -------------------------------------------------
    def _bind(self):
        self.canvas.bind("<Button-1>", self._down)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._up)
        self._drag_i = None

    def _down(self, ev):
        # coge el punto más cercano (y crea uno si está lejos)
        pts = self._curve()
        if not pts:
            return
        best, bi = 1e9, None
        for i, (t, p) in enumerate(pts):
            d2 = (self._t2x(t) - ev.x) ** 2 + (self._p2y(p) - ev.y) ** 2
            if d2 < best:
                best, bi = d2, i
        if best > 26 ** 2:      # doble clic en zona libre → añade punto
            t, p = self._x2t(ev.x), self._y2p(ev.y)
            pts.append((t, p))
            bi = len(pts) - 1
        self._drag_i = bi
        self._apply_drag(ev)

    def _drag(self, ev):
        self._apply_drag(ev)

    def _apply_drag(self, ev):
        if self._drag_i is None:
            return
        pts = [list(p) for p in self._curve()]
        if not pts:
            return
        i = self._drag_i
        # límites de vecindad: no cruzar al vecino (curva monotónica en X)
        lo = pts[i - 1][0] + 1 if i > 0 else self.T_MIN
        hi = pts[i + 1][0] - 1 if i < len(pts) - 1 else self.T_MAX
        t = max(lo, min(hi, self._x2t(ev.x)))
        pts[i] = [t, self._y2p(ev.y)]
        self.set_curve(pts)

    def _up(self, ev):
        self._drag_i = None

    def reset_factory(self):
        """Vuelve a la curva de fábrica del adaptador de este equipo."""
        from ..core import store
        name = self.profile_name.get()
        factory = getattr(self.device, "_factory_curves", {}).get(name)
        if factory:
            self.device.profiles[name].curve = list(factory)
        store.reset()
        self._draw()

    def apply_now(self):
        prof = self.device.profiles.get(self.profile_name.get())
        if not prof or not self.device.fans:
            return
        self.app.panel_daemon.stop()
        # PWM del punto de la curva acorde a la temperatura actual
        temps = self.device.temperatures()
        if temps:
            from ..core.curve import interpolate
            target = max(interpolate(prof.curve, max(temps.values())), self.min_pwm)
            self.device.apply_pwm(target)
        self.app.panel_daemon.set_note(f"curva '{prof.label}' aplicada")


class ManualSection(Section):
    def __init__(self, parent, device):
        super().__init__(parent, device, "PWM manual (0–255)")
        self.min_pwm = getattr(device, "min_pwm", 0)
        # piso visual: impide slider por debajo del mínimo de hardware
        self.var = tk.IntVar(value=max(160, self.min_pwm))
        frame = tk.Frame(self.inner, bg=STYLE["panel"])
        frame.pack(fill="x")
        tk.Scale(frame, from_=self.min_pwm, to=255, orient="horizontal",
                 variable=self.var, bg=STYLE["panel"], fg="white",
                 highlightthickness=0, troughcolor="#17181b",
                 length=280, showvalue=True).pack(side="left")
        if self.min_pwm > 0:
            tk.Label(frame, text=f"min\n{self.min_pwm}", bg=STYLE["panel"],
                     fg="#e6a23c", font=("Segoe UI", 8), justify="center"
                     ).pack(side="left", padx=4)
        make_button(self.inner, "Aplicar PWM", self.apply).pack(side="left", padx=4)
        make_button(self.inner, "Restaurar Auto", self.auto).pack(side="left", padx=4)

    def apply(self):
        self.app.panel_daemon.stop()  # el daemon no debe pelear con el manual
        self.device.apply_pwm(self.var.get())
        self.app.panel_daemon.set_note(f"PWM manual = {self.var.get()}")

    def auto(self):
        self.device.auto()
        self.app.panel_profiles.select(None, announce=False)
        self.app.panel_daemon.set_note("control del kernel (auto)")


class BatterySection(Section):
    """Límite de carga de batería (health charging, como G-Helper)."""

    BUTTON_VALUES = [60, 80, 100]

    def __init__(self, parent, device):
        super().__init__(parent, device, "Límite de carga de batería")
        if not device.battery_path:
            tk.Label(self.inner, text="No soportado en este equipo",
                     bg=STYLE["panel"], fg=STYLE["dim"]).pack()
            return
        self.buttons = {}
        current = device.battery_limit_current()
        for v in self.BUTTON_VALUES:
            b = make_button(self.inner, f"{v} %",
                            lambda val=v: self.set(val),
                            selected=(current == v))
            b.pack(side="left", padx=4)
            self.buttons[v] = b

    def set(self, value):
        if self.device.battery_limit(value):
            for v, b in self.buttons.items():
                b.configure(bg=STYLE["accent"] if v == value else STYLE["idle"])


class PowerSection(Section):
    """Whisper / Standard / Boost — la "power mode" de G-Helper.

    Traducción estándar: governor + EPP + boost (ver providers/power.py).
    Detección del perfil actual se marca con acento; se refresca con el tick.
    """

    LABELS = {"whisper": "🤫  Whisper", "standard": "📊  Standard",
              "boost": "⚡  Boost"}

    def __init__(self, parent, device):
        super().__init__(parent, device, "Perfil de potencia (CPU)")
        from ..providers.power import PowerModes
        self.pm = PowerModes()
        self.buttons = {}
        avail = self.pm.available()
        for name, label in self.LABELS.items():
            b = make_button(self.inner, label,
                            lambda n=name: self.set(n))
            b.pack(side="left", padx=4)
            self.buttons[name] = b
        self.lbl_state = tk.Label(self.inner, text="", bg=STYLE["panel"],
                                  fg=STYLE["dim"], font=("Segoe UI", 9))
        self.lbl_state.pack(side="left", padx=8)

    def set(self, name):
        import os
        import subprocess
        script = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "run.py")
        try:
            r = subprocess.run(["pkexec", "python3", script, "power", name],
                               capture_output=True, text=True)
            ok = r.returncode == 0
        except FileNotFoundError:
            ok = False
        self.lbl_state.configure(
            text=f"✅ {name}" if ok else "❌ (root necesario)",
            fg="#9ad14b" if ok else "#e05656")
        self.refresh()

    def refresh(self):
        cur = self.pm.guess_profile()
        for n, b in self.buttons.items():
            b.configure(bg=STYLE["accent"] if n == cur else STYLE["idle"])


class ExtrasSection(Section):
    """Funciones extra estilo G-Helper: limpieza de polvo y auto-switch."""

    def __init__(self, parent, device):
        super().__init__(parent, device, "Extras · G-Helper en Linux")
        # --- limpieza de polvo (fans al 100 % un rato) ---
        make_button(self.inner, "🧹  Limpieza de polvo (30 s)",
                    self.dust).pack(side="left", padx=4)
        # --- auto-switch AC/batería ---
        self.b_auto = make_button(self.inner, "🔌  Auto AC/batería: OFF",
                                  self.toggle_autoswitch, selected=False)
        self.b_auto.pack(side="left", padx=4)
        self.auto_thread = None

    def dust(self, seconds=30):
        if not messagebox.askyesno(
                "Limpieza de polvo",
                f"Los ventiladores irán al 100 % durante {seconds} s\n"
                "para expulsar el polvo acumulado. ¿Adelante?"):
            return
        self.app.panel_daemon.stop()
        device = self.device

        def blast():
            device.apply_pwm(255)
            time.sleep(seconds)
            device.auto()
        import threading
        import time
        t = threading.Thread(target=blast, daemon=True)
        t.start()
        self.app.after(0, lambda: self.app.panel_daemon.set_note(
            "🧹 fans al 100 % 30 s…"))
        self.app.after((seconds + 2) * 1000, lambda:
                       self.app.panel_daemon.set_note(
                           "🧹 limpieza terminada (kernel auto)"))

    def toggle_autoswitch(self):
        if self.auto_thread is None:
            from ..providers.autoswitch import AutoSwitchDaemon
            self.asd = AutoSwitchDaemon(self.device)
            import threading

            def loop():
                import time as _t
                while getattr(self, "asd", None) and not self.asd.stop_flag:
                    try:
                        self.asd.step(log=print)
                    except Exception:
                        pass
                    _t.sleep(self.asd.interval)
            self.b_auto.configure(text="🔌  Auto AC/batería: ON",
                                  bg=STYLE["accent"])
            self.auto_thread = threading.Thread(target=loop, daemon=True)
            self.auto_thread.start()
            self.app.panel_daemon.set_note("auto-switch activo (10 s)")
        else:
            self.asd.stop_flag = True   # el loop muere en el siguiente tick
            self.auto_thread = None
            self.b_auto.configure(text="🔌  Auto AC/batería: OFF",
                                  bg=STYLE["idle"])
            self.app.panel_daemon.set_note("auto-switch detenido")


class KeyboardSection(Section):
    """Retroiluminación del teclado: brillo (sysfs) + colores a elección.

    Los colores usan asusctl si existe (Aura/firmware RGB del TUF).
    Fn+↑/↓ en caliente también funcionan vía el daemon de hotkeys; esto es
    la versión con botones.
    """

    def __init__(self, parent, device):
        super().__init__(parent, device, "Retroiluminación del teclado")
        from ..providers.kbd import KbdBacklight
        self.kbd = KbdBacklight()
        self.lbl_state = tk.Label(self.inner, text="", bg=STYLE["panel"],
                                  fg=STYLE["dim"], font=("Segoe UI", 10))
        if not self.kbd.available:
            tk.Label(self.inner, text="Sin LED de teclado detectable",
                     bg=STYLE["panel"], fg=STYLE["dim"]).pack()
            return
        # -- brillo --
        self.max_b = self.kbd.max_brightness()
        self.brightness = self.kbd.brightness()
        make_button(self.inner, "Brillo −", lambda: self._step(-1)).pack(side="left", padx=4)
        make_button(self.inner, "Brightness +", lambda: self._step(+1)).pack(side="left", padx=4)
        self.lbl_state.pack(side="left", padx=8)
        self.lbl_state.configure(text=f"{self.brightness}/{self.max_b}")

        # -- colores (rejilla de botones con su propio color) --
        row = tk.Frame(self.inner, bg=STYLE["panel"])
        row.pack(fill="x", pady=(6, 0))
        if not self.kbd.colors_available:
            tk.Label(row, text="Colores: instala asusctl (asus-linux.org)",
                     bg=STYLE["panel"], fg=STYLE["dim"],
                     font=("Segoe UI", 9)).pack(side="left", padx=4)
        else:
            for nombre, hexcolor in self.kbd.PALETTE:
                b = tk.Button(row, bg=f"#{hexcolor}", width=3, relief="flat",
                              cursor="hand2", activebackground=f"#{hexcolor}",
                              borderwidth=0,
                              command=lambda hx=hexcolor, n=nombre:
                                  self.set_color(hx, n))
                tip = getattr(b, "tooltip", None)
                b.pack(side="left", padx=2)
                b.attr_tip = tk.Label(row, text="")
            # color personalizado
            self.custom = tk.Entry(row, width=9, bg="#17181b", fg="white",
                                   insertbackground="white", relief="flat")
            self.custom.insert(0, "#2b7cd3")
            self.custom.pack(side="left", padx=6)
            make_button(row, "Color propio", self._custom).pack(
                side="left", padx=2)

    def _step(self, delta):
        if self.kbd.brightness_step(delta):
            self.lbl_state.configure(
                text=f"{self.kbd.brightness()}/{self.max_b}")

    def set_color(self, hexcolor, nombre=""):
        import subprocess
        ok = False
        try:
            subprocess.run(["pkexec", "asusctl", "led-mode", "static"],
                           capture_output=True)
            r = subprocess.run(["pkexec", "asusctl", "keyboard-color", hexcolor],
                               capture_output=True, text=True)
            ok = r.returncode == 0
            if not ok:  # versiones nuevas de asusctl
                r2 = subprocess.run(["pkexec", "asusctl", "aura",
                                     "--color", hexcolor],
                                    capture_output=True, text=True)
                ok = r2.returncode == 0
        except FileNotFoundError:
            pass
        self.lbl_state.configure(
            text=f"Color: {nombre or hexcolor} ✅" if ok else "❌ sin color (asusctl)",
            fg="#9ad14b" if ok else "#e05656")

    def _custom(self):
        hexv = self.custom.get().strip().lstrip("#")
        if len(hexv) == 6:
            self.set_color(hexv, "")


class ServiceSection(Section):
    """Instalación del servicio systemd (autostart, consumo mínimo)."""

    def __init__(self, parent, device):
        super().__init__(parent, device, "Servicio del sistema")
        make_button(self.inner, "▶  Instalar / activar autostart",
                    self.install).pack(side="left", padx=4)
        make_button(self.inner, "⏹  Detener servicio", self.stop).pack(side="left", padx=4)
        make_button(self.inner, "ℹ️  Acerca de", self.about).pack(side="left", padx=4)
        self.lbl = tk.Label(self.inner, text="", bg=STYLE["panel"],
                            fg=STYLE["dim"], font=("Segoe UI", 9))
        self.lbl.pack(side="left", padx=8)

    def _svc_active(self) -> bool:
        import subprocess
        try:
            r = subprocess.run(["systemctl", "is-active", "ventozy"],
                               capture_output=True, text=True)
            return r.stdout.strip() == "active"
        except OSError:
            return False

    def install(self):
        import os
        import subprocess
        script = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "run.py")
        # 1er intento: el CLI propio (registrado en /opt). 2º: install.sh
        ok = False
        try:
            r = subprocess.run(["pkexec", "python3", script, "install"],
                               capture_output=True, text=True)
            ok = r.returncode == 0
        except FileNotFoundError:
            ok = False
        if not ok:
            install_sh = os.path.join(os.path.dirname(script), "install.sh")
            try:
                r = subprocess.run(["pkexec", "bash", install_sh],
                                   capture_output=True, text=True)
                ok = r.returncode == 0
            except FileNotFoundError:
                ok = False
        self.lbl.configure(text="✅ autostart activo" if ok
                           else "❌ instala manual (install.sh)")

    def stop(self):
        import subprocess
        try:
            subprocess.run(["pkexec", "systemctl", "stop", "ventozy"],
                           capture_output=True)
        except FileNotFoundError:
            pass
        self.lbl.configure(text="⏹ servicio detenido")

    def refresh(self):
        self.lbl.configure(
            text=("✅ activo" if self._svc_active() else ""))

    def about(self):
        messagebox.showinfo(
            "Acerca de Ventozy",
            "Ventozy — control ventiladores + GPU para portátiles Linux\n\n"
            "• Backend: sysfs estándar (hwmon), cero hacks\n"
            "• Seguridad: watchdog ≥ 95 °C → vuelve siempre a auto()\n"
            "• Modos: Silencio / Equilibrado / Turbo / Auto\n"
            "• GPU: runtime PM reversible\n\n"
            "Aporta tu equipo: configs/generic-template.json")


class DaemonSection(Section):
    """Loop de curva embebido en la GUI (sin daemon CLI). Muestra el estado
    del watchdog y un botón para rehabilitar tras revisar el equipo."""

    def __init__(self, parent, device):
        super().__init__(parent, device, "Control por curva y seguridad")
        from ..service import FanDaemon
        self.daemon = FanDaemon(device)
        self.running = False
        self.lbl = tk.Label(self.inner, text="⏸ detenido", bg=STYLE["panel"],
                            fg=STYLE["dim"], font=("Segoe UI", 10))
        self.lbl.pack(side="left", padx=8)
        self.b_reset = make_button(self.inner, "♻  Reintentar tras fallo",
                                   self.reset_watchdog)
        self.b_reset.pack_forget()  # solo visible cuando hubo una emergencia

    def reset_watchdog(self):
        if self.daemon.watchdog.clear():
            self.b_reset.pack_forget()
            self.lbl.configure(text="✅ watchdog rehabilitado", fg="#9ad14b")
            if self.app.panel_profiles.selected:
                self.start(self.app.panel_profiles.selected)

    def emergency_banner(self, reason: str):
        self.running = False
        self.lbl.configure(text=f"⚠ {reason} → control del kernel",
                           fg="#e05656")
        self.b_reset.pack(side="left", padx=4)

    def start(self, profile_name: str):
        prof = self.device.profiles[profile_name]
        self.daemon.curve_pts = prof.curve
        self.daemon.min_pwm = prof.min_pwm
        self.daemon.profile_name = profile_name
        self.running = True
        self.lbl.configure(text=f"▶ {prof.label}", fg=STYLE["accent"])
        try:
            self.daemon.step()   # respuesta inmediata: ambos fans ya se mueven
            from ..providers.notify import notify
            notify("Ventozy", f"Ventiladores → {prof.label}")
        except Exception:
            pass
        self._schedule()

    def stop(self):
        self.running = False
        self.lbl.configure(text="⏸ detenido", fg=STYLE["dim"])
        self.b_reset.pack_forget()

    def set_note(self, note: str):
        self.running = False
        self.lbl.configure(text=f"✋ {note}", fg=STYLE["dim"])

    def _schedule(self):
        if not self.running:
            return
        try:
            result = self.daemon.step()
        except Exception as e:
            self.device.auto()
            self.emergency_banner(f"{e.__class__.__name__}: {e}")
            messagebox.showwarning(
                "Seguridad",
                f"Se perdió el control:\n{e}\n\nEl kernel retomó el control "
                "automático. Corrige el problema y pulsa 'Reintentar'.")
            return
        if result == self.daemon.EXIT_SAFETY:
            reason = self.daemon.watchdog.disabled_reason or "fallo de seguridad"
            self.emergency_banner(reason)
            messagebox.showwarning(
                "Seguridad Ventozy",
                f"El watchdog detuvo el control:\n{reason}\n\n"
                "El kernel retomó el control automático de los ventiladores. "
                "Cuando revises el equipo, pulsa 'Reintentar tras fallo'.")
            return
        self.after(2000, self._schedule)
