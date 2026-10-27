"""Tests de la matemática de curvas — puros, sin hardware.

Ejecutar:  cd fan-control-linux && python3 -m pytest tests/ -q
(sin pytest: python3 tests/test_core.py para chequeo básico)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ventozy.core.curve import clamp_pwm, hysteresis, interpolate, ramp, ramp_up_fast_down


def test_interpolate_basics():
    curve = [(45, 80), (60, 120), (70, 190)]
    assert interpolate(curve, 30) == 80      # por debajo del primer punto
    assert interpolate(curve, 90) == 190     # por encima del último
    assert interpolate(curve, 45) == 80
    assert interpolate(curve, 60) == 120


def test_interpolate_linear():
    curve = [(40, 100), (60, 200)]
    # a mitad del tramo: 150
    assert interpolate(curve, 50) == 150
    # primer cuarto: 125
    assert interpolate(curve, 45) == 125


def test_interpolate_empty():
    assert interpolate([], 50) == 255


def test_hysteresis():
    assert hysteresis(128, 130) == 128   # cambio < step → no cambia
    assert hysteresis(128, 160) == 160   # cambio grande → cambia


def test_clamp():
    assert clamp_pwm(300, 77) == 255
    assert clamp_pwm(10, 77) == 77       # piso de hardware respetado
    assert clamp_pwm(-5) == 0


def test_ramp_limits_rate():
    assert ramp(None, 200) == 200        # primer tick: sin rampa
    assert ramp(100, 200, rate=12) == 112
    assert ramp(200, 100, rate=12) == 188
    assert ramp(100, 105, rate=12) == 105  # dentro del rate → directo


def test_ramp_up_fast_down():
    # sube rápido (12/tick), baja lento (6/tick)
    assert ramp_up_fast_down(100, 160) == 112
    assert ramp_up_fast_down(160, 100) == 154


def _basic_run():
    test_interpolate_basics()
    test_interpolate_linear()
    test_interpolate_empty()
    test_hysteresis()
    test_clamp()
    test_ramp_limits_rate()
    test_ramp_up_fast_down()
    print("OK: tests de curve.py")


if __name__ == "__main__":
    _basic_run()
