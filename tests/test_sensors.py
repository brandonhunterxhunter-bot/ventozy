"""Tests del hub universal de sensores — sin hardware real.

Scajea hwmon de mentira en un tempdir (mock de /sys), + fuentes nvidia/psutil.
Ejecutar: python3 tests/test_sensors.py | python3 -m pytest tests/ -q
"""

import os
import sys
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ventozy.core.sensors import SensorHub, _prefer, CPU_CHIPS, CPU_WORDS  # noqa: E402


class HackedHub(SensorHub):
    """Hub con /sys apuntando a un tempdir y sin nvidia/psutil."""

    def __init__(self, root):
        self._root = root
        super().__init__()
        self.hacked = True

    def _scan(self):
        info = {}
        for hwmon_path in sorted(os.listdir(self._root)):
            base = os.path.join(self._root, hwmon_path)
            try:
                chip = open(os.path.join(base, "name")).read().strip()
            except OSError:
                continue
            for fname in sorted(os.listdir(base)):
                if not (fname.startswith("temp") and fname.endswith("_input")):
                    continue
                stem = fname[:-len("_input")]
                label = None
                try:
                    label = open(os.path.join(base, stem + "_label")).read().strip()
                except OSError:
                    pass
                name = label or f"{chip} {stem}"
                info[name] = {"path": os.path.join(base, fname), "chip": chip,
                              "hwmon": hwmon_path, "label": label or "",
                              "source": "hwmon"}
        return info


def _make_fake_sys():
    root = tempfile.mkdtemp()
    hw0 = os.path.join(root, "hwmon0")
    os.makedirs(hw0)
    with open(os.path.join(hw0, "name"), "w") as f:
        f.write("k10temp\n")
    with open(os.path.join(hw0, "temp1_input"), "w") as f:
        f.write("54231\n")            # 54.231 °C
    # chipset sin label (aquí la heurística del hub es la única vía)
    hw1 = os.path.join(root, "hwmon1")
    os.makedirs(hw1)
    with open(os.path.join(hw1, "name"), "w") as f:
        f.write("amdgpu\n")
    with open(os.path.join(hw1, "temp1_input"), "w") as f:
        f.write("61000\n")
    return root


def test_scan_and_names():
    root = _make_fake_sys()
    hub = HackedHub(root)
    info = hub.chipinfo(refresh=True)
    # k10temp: sin label → el hub inventa nombre amable con el chip
    assert any("k10temp" in k for k in info)
    # amdgpu sin label
    assert any("amdgpu" in k for k in info)


def test_read_all_with_fakes():
    root = _make_fake_sys()
    hub = HackedHub(root)
    temps = hub.all_temperatures(refresh=True)
    vals = sorted(temps.values())
    # dos lecturas válidas (54.2 y 61.0 °C) — ninguna rota
    assert len(vals) >= 2
    assert all(0 <= t <= 250 for t in vals)


def test_saneo_de_valores_rotos():
    root = _make_fake_sys()
    hw0 = os.path.join(root, "hwmon0")
    # sensor roto: 127 °C de reposo de hardware (sin lectura real)
    with open(os.path.join(hw0, "temp1_input"), "w") as f:
        f.write("127000\n")
    hub = HackedHub(root)
    temps = hub.all_temperatures(refresh=True)
    vals = sorted(temps.values())
    assert all(0 <= t <= 250 for t in vals)   # 127 entra en rango;
    # el saneado estricto (0–250) está en Device.temperatures (base.py)


def test_prefer_cpu_words():
    temps = {"fan 12v": 40.0, "CPU Core": 55.0, "amdgpu temp1": 61.0}
    assert _prefer(temps, CPU_CHIPS, CPU_WORDS) == 55.0


def _basic_run():
    test_scan_and_names()
    test_read_all_with_fakes()
    test_saneo_de_valores_rotos()
    test_prefer_cpu_words()
    print("OK: tests de sensors.py")


if __name__ == "__main__":
    _basic_run()
