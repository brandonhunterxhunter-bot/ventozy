"""Tests del modo adaptativo: convergencia, protección y seguridad.

Ejecutar: python3 tests/test_adaptive.py | python3 -m pytest tests/ -q
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ventozy.providers.adaptive import AdaptiveController
from ventozy.service import FanDaemon


class FakeFan:
    def __init__(self, min_hw=0):
        self.value = None
        self.auto_mode = False
        self.min_hw = min_hw

    def read(self):
        return self.value

    def write(self, v):
        self.value = v
        return True

    def set_auto(self, mode="2"):
        self.auto_mode = mode != "0"
        return True


class FakeDevice:
    info = type("I", (), {"model": "T", "vendor": "t", "notes": ""})
    min_pwm = 0
    profiles = {"balanced": type("P", (), {"curve": [(60, 128)], "min_pwm": 0})()}

    def __init__(self, temps=70.0):
        self._temps = temps
        self.fans = [FakeFan()]
        self.writes = []

    def temperatures(self):
        return {"CPU": self._temps}

    def fan_rpms(self):
        return [3000]

    def apply_pwm(self, v):
        self.writes.append(v)
        for f in self.fans:
            f.set_auto("0")
            f.write(v)

    def auto(self):
        for f in self.fans:
            f.set_auto("2")


def test_converges_down_when_cool():
    """Temp fría sostenida → el PWM debe ir bajando (experimentos)."""
    d = FakeDevice(temps=66.0)
    c = AdaptiveController(d, target=75.0)
    pm = []
    for _ in range(30):
        pwm, _st = c.tick()
        pm.append(pwm)
    # nunca debe exceder 255 y, tras las fases frías, debe ir bajando
    assert all(p <= 255 for p in pm)
    assert pm[-1] < pm[0]


def test_heat_protection_rises_fast():
    """Golpe de calor (88 °C con objetivo 75) — súbelo rápido hasta estabilizar."""
    d = FakeDevice(temps=71.0)
    c = AdaptiveController(d, target=75.0)
    for _ in range(5):
        c.tick()
    d._temps = 88.0
    pwm0 = c.tick()[0]
    # con +8/tick debe subir, no dar saltos absurdos (≤ 255)
    assert pwm0 <= 255 and pwm0 > max(d.writes[:-1] or [0])


def test_emergency_defers_to_watchdog():
    d = FakeDevice(temps=60.0)
    c = AdaptiveController(d, target=75.0)
    for _ in range(3):
        c.tick()
    d._temps = 99.0
    pwm, _state = c.tick()
    assert pwm == -1
    assert all(f.auto_mode for f in d.fans)   # kernel retoma SIEMPRE
    assert not c.watchdog.healthy


def _basic_run():
    test_converges_down_when_cool()
    test_heat_protection_rises_fast()
    test_emergency_defers_to_watchdog()
    print("OK: tests de adaptive.py")


if __name__ == "__main__":
    _basic_run()
