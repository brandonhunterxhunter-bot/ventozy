"""Política de seguridad del daemon. Contiene toda Anti-Daño logic.

Riesgos reales de un control de ventiladores mal hecho:
  1. PWM demasiado bajo con carga alta → sobrecalentamiento → throttling,
     degradación de componentes o apagón de emergencia.
  2. Escrituras en el path incorrecto (por ejemplo fan?_input en vez de pwm?).
  3. Fallos de lectura de sensores silenciosos → daemon "ciego" dejando
     PWM fijo mientras la temperatura sube.
  4. Daemon muerto dejando PWM fijo por siempre.
     → si muere el control manual, el kernel SIEMPRE debe retomarlo.

Mitigaciones: umbral de temperatura crítica (auto-reversa), verificación de
escritura, reintentos limitados y reversión al control del kernel ante
cualquier anomalía. El piso min_pwm siempre respetado.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SafetyPolicy:
    warn_temp: float = 85.0        # aviso (solo log)
    critical_temp: float = 95.0    # al cruzarse → auto() inmediato y exit(75)
    max_read_failures: int = 3     # lecturas fallidas de sensor antes de rendirse
    verify_writes: bool = True
    cooldown_s: float = 30.0       # tras una emergencia, no reintentar antes de esto


class SafetyWatchdog:
    """Envuelve al daemon. Decide si es seguro aplicar un PWM; si no,
    revierte al control del kernel y lo reporta por stderr.

    Estado consultable (lo usa la UI para mostrar banners de seguridad):
      - disabled_reason: motivo del último bloqueo (None = todo OK)
      - healthy: True si no hay emergencia activa
    """

    def __init__(self, device, policy: Optional[SafetyPolicy] = None):
        self.device = device
        self.policy = policy or SafetyPolicy()
        self.read_failures = 0
        self.disabled_reason: Optional[str] = None
        self.last_applied: Optional[int] = None
        self._cooldown_until = 0.0   # monotónico

    @property
    def healthy(self) -> bool:
        return self.disabled_reason is None

    def in_cooldown(self) -> bool:
        import time
        return time.monotonic() < self._cooldown_until

    def clear(self):
        """Rehabilitación manual (botón de la UI tras revisar el equipo)."""
        if self.in_cooldown():
            return False
        self.disabled_reason = None
        self.read_failures = 0
        return True

    # -- evaluaciones ----------------------------------------------
    def evaluate_temps(self, temps: dict) -> Optional[str]:
        """Devuelve motivo de emergencia si procede."""
        if not temps:
            self.read_failures += 1
            if self.read_failures >= self.policy.max_read_failures:
                return "sensores ilegibles"
            return None
        self.read_failures = 0
        hottest = max(temps.values())
        if hottest >= self.policy.critical_temp:
            return f"{hottest:.0f} °C ≥ crítico {self.policy.critical_temp:.0f} °C"
        return None

    def check_safe_to_write(self, target: int) -> Optional[str]:
        """El piso min_pwm del equipo no se permite violar."""
        if not self.device.fans:
            return "sin ventiladores detectados"
        if target < getattr(self.device, "min_pwm", 0) and target != 0:
            return "PWM por debajo del piso de hardware"
        return None

    # -- acción segura ---------------------------------------------
    def apply(self, target: int) -> tuple:
        """Devuelve (pwm_aplicado, motivo_o_None). Respeta el cooldown."""
        if self.disabled_reason is not None or self.in_cooldown():
            return (-1, self.disabled_reason or "cooldown activo")
        reason = self.evaluate_temps(self.device.temperatures())
        if reason:
            self.emergency(reason)
            return (-1, reason)
        reason = self.check_safe_to_write(target)
        if reason:
            self.emergency(reason)
            return (-1, reason)
        self.device.apply_pwm(target)
        if self.policy.verify_writes and not self._verify(target):
            return (target, "la escritura no se verificó")
        self.last_applied = target
        return (target, None)

    def _verify(self, expected: int) -> bool:
        """Confirma que al menos un ventilador refleja el PWM escrito.
        Algunos chips redondean, así que permitimos ±8."""
        for fan in self.device.fans:
            read = fan.read()
            if read is None:
                continue
            if abs(read - expected) <= 8:
                return True
        return False

    def emergency(self, reason: str):
        """Revierte SIEMPRE al control del kernel, sea cual sea el problema.
        El cooldown impide ciclos frenético de emergencia→reintento→emergencia."""
        import time
        if self.disabled_reason is None:
            self.disabled_reason = reason
        self._cooldown_until = time.monotonic() + self.policy.cooldown_s
        self.device.auto()
        self.last_applied = None
        import sys
        print(f"[ventozy] ⚠ EMERGENCIA: {reason}. "
              f"Revertido al control automático del kernel. "
              f"(cooldown {self.policy.cooldown_s:.0f}s)", file=sys.stderr)
        try:
            from ..providers.notify import notify
            notify("⚠ Ventozy — EMERGENCIA",
                   f"{reason}\nControl del kernel restaurado.",
                   urgency="critical", timeout=8000)
        except Exception:
            pass
