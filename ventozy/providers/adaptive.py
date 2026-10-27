"""Modo adaptativo: busca el menor PWM que mantenga la temp bajo el objetivo.

Diferencia clave con la curva fija de "Silencio" (¿por qué la comunidad lo
ama?):
  - Curva fija: PWM alto aunque la CPU esté fría → ventilación innecesaria.
  - Adaptativo: prueba objetivos bajos y 'cae' a la última velocidad estable
    mientras la temperatura siga cómoda → acústica mínima sin riesgo.

Estrategia híbrida bifase (sólo segura, no teórica):
  FASE PROTECCIÓN  si temp ≥ objetivo+4: sube rápido (+8/tick) hasta estabiliz.
  FASE EXPERIMENTO si temp lleva ≥ 3 ticks fríos: baja un paso (−3 PWM) y
                   verifica en el siguiente tick; si la temperatura sube,
                   el próximo ciclo se encarga de recuperarla.
 Sin complicaciones de tuning; fácil de auditar ( comunidad).
Integrado al SafetyWatchdog del core: toda emergencia respeta el mismo
protocolo core.safety (auto + exit(75)). CLI: ventozy adaptive [°C]
"""

import time

from ..core.safety import SafetyWatchdog
from ..devices import Device

UP_STEP = 8       # sube rápido ante calor (protección térmica primero)
DOWN_STEP = 3     # baja lento, para no disparar re-subidas
HOLD_TICKS = 4    # ticks estables necesarios para intentar bajar


class AdaptiveController:
    def __init__(self, device: Device, target: float = 75.0,
                 check_interval: float = 3.0):
        self.device = device
        self.target = target
        self.check_interval = check_interval
        self.watchdog = SafetyWatchdog(device)
        self.pwm = None
        self.kicks = 0    # ticks consecutivos con temp < target-3

    # ------------------------------------------------------------
    def tick(self):
        """Una decisión. Devuelve (pwm, estado_str). Implementa ambos fases."""
        temps = self.device.temperatures()
        emergency = self.watchdog.evaluate_temps(temps)
        if emergency:
            self.watchdog.emergency(emergency)
            return -1, emergency
        if not temps or not self.device.fans:
            self.watchdog.emergency("sin sensores → re-modo seguro (auto)")
            return -1, "no data"

        hottest = max(max(temps.values()), 0.0)
        floor = getattr(self.device, "min_pwm", 0)
        # arranque: resolver PWM inicial con la curva balanced (si hay)
        if self.pwm is None:
            prof = self.device.profiles.get("balanced") \
                or next(iter(self.device.profiles.values()), None)
            base = prof.curve[0][1] if prof and prof.curve else max(floor + 20, 80)
            self.pwm = max(floor, min(255, int(base)))

        # FASE 1: protección (sube rápido)
        if hottest >= self.target + 4:
            new = min(255, self.pwm + UP_STEP)
            self.kicks = 0
            self.pipeline(new)
            return new, f"protección ({hottest:.0f}°C ≥ {self.target:.0f}+4)"

        # no sabes si puedes bajar: requiere estabilidad sostenida
        if hottest < self.target - 3:
            self.kicks += 1
        else:
            self.kicks = 0

        # FASE 2: experimento de subiq (prueba PWM-1, verifica al próximo tick)
        if self.kicks >= HOLD_TICKS and self.pwm > floor:
            new = max(floor, self.pwm - DOWN_STEP)
            self.pipeline(new)
            self.kicks = 0
            return new, f"experimento (baja a {new}, verifica {self.check_interval}s)"

        self.pipeline(self.pwm)   # reafirma el PWM estable (por si algo lo tocó)
        return self.pwm, f"estable ({hottest:.0f}°C → PWM {self.pwm})"

    def pipeline(self, value):
        self.device.apply_pwm(value)
        self.pwm = value

    # ------------------------------------------------------------
    def run_forever(self, log=print):
        import signal
        import sys

        def _safe_auto(*_):
            self.device.auto()
            log("\n[adaptive] detenido — control del kernel restaurado.")
            sys.exit(0)

        signal.signal(signal.SIGINT, _safe_auto)
        signal.signal(signal.SIGTERM, _safe_auto)

        log(f"[adaptive] objetivo {self.target:.0f} °C · intervalo "
            f"{self.check_interval}s · min_pwm floor "
            f"{getattr(self.device, 'min_pwm', 0)}")
        while True:
            try:
                pwm, state = self.tick()
                if pwm == -1:      # watchdog con guardia
                    import sys
                    sys.exit(75)
                log(f"[adaptive] {state}")
            except (OSError, PermissionError, ValueError) as e:
                self.watchdog.emergency(f"error I/O: {e}")
                import sys
                sys.exit(75)
            time.sleep(self.check_interval)
