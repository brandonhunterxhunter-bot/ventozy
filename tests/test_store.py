"""Tests de persistencia de curvas (core/store) con config temporal."""

import os
import sys
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# redirigir la config del usuario a un tmpdir con XDG_CONFIG_HOME
tmp = tempfile.mkdtemp()
os.environ["XDG_CONFIG_HOME"] = tmp

from ventozy.core.store import apply_to, load, save_profiles  # noqa: E402
from ventozy.providers.adaptive import AdaptiveController  # noqa: E402


class FakeProfile:
    def __init__(self, curve):
        self.curve = list(curve)


class FakeDevice:
    info = type("I", (), {"model": "t", "vendor": "t", "notes": ""})
    min_pwm = 0
    battery_path = None

    def __init__(self):
        # por instancia (como hace la librería real); uno compartido
        # filtraría el estado del primer device al segundo artificialmente
        self.profiles = {"balanced": FakeProfile([(45, 80), (60, 120)]),
                         "turbo": FakeProfile([(40, 110)])}

    def temperatures(self):
        return {}

    def fan_rpms(self):
        return []

    def apply_pwm(self, v):
        pass

    def auto(self):
        pass

    def battery_limit_current(self):
        return None

    def battery_limit(self, v):
        return True


def test_roundtrip():
    d = FakeDevice()
    d.profiles["balanced"].curve = [(45, 90), (60, 130)]   # edit de usuario
    assert save_profiles(d) is True
    data = load()
    assert "balanced" in data["profiles"]

    d2 = FakeDevice()
    n = apply_to(d2)
    assert n == 2   # también «turbo» aunque no se editó
    assert d2.profiles["balanced"].curve == [(45, 90), (60, 130)]
    # y guardó originales para restaurar
    assert d2._factory_curves["balanced"] == [(45, 80), (60, 120)]


def _basic_run():
    test_roundtrip()
    print("OK: tests de store.py (persistencia)")


if __name__ == "__main__":
    _basic_run()
