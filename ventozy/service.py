"""Daemon de control: loop con watchdog de seguridad y consumo mínimo.

Características de estabilidad:
  - intervalo por defecto 5 s (CPU casi 0 %)
  - toda escritura pasa por core.safety.SafetyWatchdog
  - ante sensores ilegibles / temperatura crítica / PWM no verificable,
    revierte al control automático del kernel y termina con código 75
    para que systemd lo reinicie con backoff.
"""

import signal
import sys
import time

from .core.curve import clamp_pwm, hysteresis, interpolate, ramp_up_fast_down
from .core.safety import SafetyWatchdog
from .devices import Device


class FanDaemon:
    EXIT_SAFETY = 75   # systemd lo reinicia con backoff

    def __init__(self, device: Device, profiles=None, interval: float = 5.0):
        self.device = device
        self.interval = interval
        self.profiles = profiles or device.profiles
        self.watchdog = SafetyWatchdog(device)
        self.current_pwm = None
        self.curve_pts = None
        self.min_pwm = 0
        self.running = False
        self._iterations = 0

    # ------------------------------------------------------------
    def start_profile(self, name: str) -> bool:
        prof = self.profiles.get(name)
        if not prof:
            return False
        self.curve_pts = prof.curve
        self.min_pwm = prof.min_pwm
        return True

    def stop(self):
        self.running = False

    # ------------------------------------------------------------
    def step(self):
        """Una iteración SEGURA: si algo va mal, revierte a auto y sale."""
        if self.curve_pts is None:  # perfil por defecto
            prof = next(iter(self.profiles.values()), None)
            if not prof:
                return -1
            self.curve_pts, self.min_pwm = prof.curve, prof.min_pwm

        if not self.device.fans:
            self.watchdog.emergency("sin ventiladores detectados")
            return self.EXIT_SAFETY

        temps = self.device.temperatures()
        emergency = self.watchdog.evaluate_temps(temps)
        if emergency:
            self.watchdog.emergency(emergency)
            return self.EXIT_SAFETY

        if not temps:
            return -1
        ref = max(max(temps.values()), 0.0)
        target = interpolate(self.curve_pts, ref)
        target = clamp_pwm(target, self.min_pwm)
        if self.current_pwm is not None:
            target = hysteresis(self.current_pwm, target)
        # rampa asimétrica: sube rápido ante calor, baja lento (menos ciclos)
        target = clamp_pwm(ramp_up_fast_down(self.current_pwm, target), self.min_pwm)
        applied, problem = self.watchdog.apply(target)
        if problem:
            # fallo no fatal (cooldown/verificación): reintenta en el próximo tick
            return applied if applied >= 0 else self.EXIT_SAFETY
        self.current_pwm = applied
        self._iterations += 1
        if self._iterations % 60 == 0:   # log cada ~5 min para journald
            print(f"[ventozy] Estado: {ref:.0f} °C → PWM {applied} ({applied*100//255}%)")
        return applied

    # ------------------------------------------------------------
    def run_forever(self, profile_name: str):
        prof = self.profiles.get(profile_name) or next(iter(self.profiles.values()))
        self.curve_pts = prof.curve
        self.min_pwm = prof.min_pwm
        if not self.device.fans:
            print("[ventozy] No hay ventiladores; no se inicia daemon.", file=sys.stderr)
            sys.exit(1)

        def on_exit(*_):
            self.device.auto()
            print("\n[ventozy] Detenido — control automático del kernel restaurado.")
            sys.exit(0)

        signal.signal(signal.SIGINT, on_exit)
        signal.signal(signal.SIGTERM, on_exit)

        print(f"[ventozy] {self.device.info.model} · perfil '{prof.label}' · "
              f"{len(self.device.fans)} fan · intervalo {self.interval}s")
        while True:
            try:
                r = self.step()
                if r == self.EXIT_SAFETY:
                    # salida limpia: systemd reintenta con backoff
                    sys.exit(self.EXIT_SAFETY)
            except (OSError, PermissionError, ValueError) as e:
                self.watchdog.emergency(
                    f"error de I/O: {e.__class__.__name__}: {e}")
                sys.exit(self.EXIT_SAFETY)
            time.sleep(self.interval)
