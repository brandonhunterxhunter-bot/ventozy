"""Tests del conversor NBFC → Ventozy con un config real de git repos.

Usa un fixture incrustado con el esquema real de nbfc-linux
(share/nbfc/Configs/...). El conversor nunca debe necesitar la red aquí.
Ejecutar: python3 tests/test_nbfc.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ventozy.providers.nbfc import to_ventozy, _fan_configs, _thresholds_curve  # noqa: E402

# esquema real nbfc-linux (shape simplificado pero dhábil → sistema)
NBFC_SAMPLE = {
    "Vendor": "ASUS",
    "NotebookModel": "TUF Gaming FA506NC",
    "FanConfig": {
        "Fan": {"FanDisplayName": "CPU fan",
                "WriteRegister": 55, "ReadRegister": 112,
                "MinFanValue": 100, "MaxFanValue": 240},
        "Fan2": {"FanDisplayName": "GPU fan",
                 "WriteRegister": 89, "ReadRegister": 114,
                 "MinFanValue": 100, "MaxFanValue": 240},
    },
    "TemperatureThresholds": [
        {"TargetFanSpeed": 0, "TargetTemperature": 40},
        {"TargetFanSpeed": 40, "TargetTemperature": 60},
        {"TargetFanSpeed": 70, "TargetTemperature": 70},
        {"TargetFanSpeed": 100, "TargetTemperature": 80},
    ],
}


def test_thresholds_curves_converted():
    curve = _thresholds_curve(NBFC_SAMPLE)
    assert curve == [(40, 0), (60, 102), (70, 178), (80, 255)]


def test_fans_detected_and_named():
    fans = _fan_configs(NBFC_SAMPLE)
    assert len(fans) == 2
    assert any(f["suggestion"]["file"] == "pwm1" for f in fans)
    assert any(f["suggestion"]["file"] == "pwm2" for f in fans)


def test_converted_config_structure():
    out = to_ventozy(NBFC_SAMPLE, {"NotebookModel": "TUF Gaming FA506NC",
                                   "NotebookVendor": "ASUS"})
    assert "fa506nc" in [m.lower() for m in out["match"]] or \
           "tuf gaming fa506nc" in " ".join(out["match"]).lower()
    assert out["info"]["credit"].startswith("https://github.com/nbfc-linux")
    assert "Importado del catálogo nbfc-linux" in out["info"]["notes"]
    names = [p["name"] for p in out["profiles"]]
    assert {"quiet", "balanced", "turbo"} <= set(names)
    # la curva de base es la del catálogo (verificable a mano)
    bal = next(p for p in out["profiles"] if p["name"] == "balanced")
    assert bal["curve"] == [(40, 0), (60, 102), (70, 178), (80, 255)]
    # turbo/se quedó dentro de 0-255
    assert all(0 <= p <= 255 for _, p in bal["curve"])


def test_fallback_when_no_thresholds():
    cfg = dict(NBFC_SAMPLE)
    cfg.pop("TemperatureThresholds")
    out = to_ventozy(cfg)
    names = [p["name"] for p in out["profiles"]]
    assert {"quiet", "balanced", "turbo"} <= set(names)   # genéricas seguras


def _basic_run():
    test_thresholds_curves_converted()
    test_fans_detected_and_named()
    test_converted_config_structure()
    test_fallback_when_no_thresholds()
    print("OK: tests de nbfc.py (integración con el catálogo comunitario)")


if __name__ == "__main__":
    _basic_run()
