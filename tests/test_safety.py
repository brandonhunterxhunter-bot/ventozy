"""Tests del watchdog de seguridad con FakesDevice (sin sysfs real).

Ejecutar:  python3 -m pytest tests/ -q   |  python3 tests/test_safety.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ventozy.core.safety import SafetyPolicy, SafetyWatchdog
from ventozy.service import FanDaemon


class FakeFan:
    def __init__(self, pwm=128, min_hw=0):
        self.value = pwm
        self.auto_mode = False
        self.min_hw = min_hw

    def read(self):
        return self.value

    def write(self, v):
        if v < self.min_hw:
            return False
        self.value = v
        return True

    def set_auto(self, mode="2"):
        self.auto_mode = bool(mode != "0")
        return True


class FakeDevice:
    """Device de pega: cumple la misma interfaz que la API Device."""
    min_pwm = 0
    info = type("I", (), {"model": "Test", "vendor": "t", "notes": ""})
    profiles = {}

    def __init__(self, temps=60.0, fans=None):
        self._temps = temps
        self.fans = fans or [FakeFan()]
        self.min_pwm = 77 if isinstance(self.fans[0], FakeFan) and self.fans[0].min_hw else 0

    def temperatures(self):
        return {"CPU": self._temps}

    def fan_rpms(self):
        return [3000]

    def apply_pwm(self, v):
        for f in self.fans:
            f.set_auto("0")
            f.write(v)

    def auto(self):
        for f in self.fans:
            f.set_auto("2")

    # para que el watchdog considere el piso min_pwm
    @property
    def min_pwm(self):
        return self._min_pwm

    @min_pwm.setter
    def min_pwm(self, v):
        self._min_pwm = v


def test_normal_apply():
    d = FakeDevice(temps=60.0)
    d._min_pwm = 0
    wd = SafetyWatchdog(d)
    pwm, problem = wd.apply(140)
    assert problem is None and pwm == 140
    assert wd.healthy


def test_critical_temp_triggers_emergency():
    d = FakeDevice(temps=60.0)
    d._min_pwm = 0
    wd = SafetyWatchdog(d)
    d._temps = 97.0
    pwm, problem = wd.apply(200)
    assert pwm == -1
    assert not wd.healthy
    assert all(f.auto_mode for f in d.fans)   # ¡reversión al kernel!


def test_silent_sensors_revert():
    """Daemon ciego: constantes fans failures → auto() y bloqueo."""
    d = FakeDevice(temps=60.0)
    d._min_pwm = 0
    wd = SafetyWatchdog(d)
    out = None
    for _ in range(3):                       # 3 fallos de lectura
        d._temps = None                      # temperatures() devolviendo vacío
        d.temperatures = lambda: {}
        out = wd.apply(120)
    assert out[0] == -1 and not wd.healthy
    assert all(f.auto_mode for f in d.fans)


def test_min_pwm_floor_blocks_write():
    d = FakeDevice(temps=60.0)
    d._min_pwm = 50
    wd = SafetyWatchdog(d)
    pwm, problem = wd.apply(10)
    assert pwm == -1 and problem and "piso" in problem


def test_cooldown_prevents_bounce():
    """Tras una emergencia no reintenta hasta que pase el cooldown."""
    d = FakeDevice(temps=97.0)
    d._min_pwm = 0
    wd = SafetyWatchdog(d, policy=SafetyPolicy(cooldown_s=3600))
    wd.apply(200)
    assert not wd.healthy
    # aunque vuelva la temperatura normal, sigue bloqueado (cooldown)
    d._temps = 50.0
    pwm, problem = wd.apply(120)
    assert pwm == -1


def test_daemon_emergency_exit_code():
    d = FakeDevice(temps=60.0)
    d._min_pwm = 0
    daemon = FanDaemon(d, interval=0.1)
    daemon.start_profile("balanced") if "balanced" in daemon.profiles else None
    if daemon.curve_pts is None:
        daemon.curve_pts, daemon.min_pwm = [(50, 100)], 0
    d._temps = 99.0
    assert daemon.step() == FanDaemon.EXIT_SAFETY
    assert all(f.auto_mode for f in d.fans)


def _basic_run():
    test_normal_apply()
    test_critical_temp_triggers_emergency()
    test_silent_sensors_revert()
    test_min_pwm_floor_blocks_write()
    test_cooldown_prevents_bounce()
    test_daemon_emergency_exit_code()
    print("OK: tests de safety.py + FanDaemon")


if __name__ == "__main__":
    _basic_run()
