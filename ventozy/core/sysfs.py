"""Acceso genérico a /sys/class/hwmon. Sin conocimiento de modelos concretos."""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Sensor:
    hwmon: str          # id del hwmon, ej. "hwmon2"
    label: str          # archivo, ej. "temp1_input"
    chip: str           # nombre del driver, ej. "k10temp"

    @property
    def path(self) -> str:
        return f"/sys/class/hwmon/{self.hwmon}/{self.label}"

    def temperature(self) -> Optional[float]:
        try:
            with open(self.path) as f:
                return int(f.read().strip()) / 1000
        except (OSError, ValueError):
            return None


@dataclass
class Fan:
    hwmon: str
    file: str           # ej. "pwm1"

    @property
    def path(self) -> str:
        return f"/sys/class/hwmon/{self.hwmon}/{self.file}"

    @property
    def enable_path(self) -> str:
        return self.path + "_enable"

    @property
    def rpm_path(self) -> str:
        return f"/sys/class/hwmon/{self.hwmon}/fan{self.file[-1]}_input"

    def read(self) -> Optional[int]:
        try:
            with open(self.path) as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return None

    def read_rpm(self) -> Optional[int]:
        try:
            with open(self.rpm_path) as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return None

    def write(self, value: int) -> bool:
        try:
            with open(self.path, "w") as f:
                f.write(str(value))
            return True
        except (OSError, PermissionError):
            return False

    def set_auto(self, mode: str = "2") -> bool:
        """mode: '0' = manual, '2' = automático del kernel."""
        try:
            with open(self.enable_path, "w") as f:
                f.write(mode)
            return True
        except (OSError, PermissionError):
            return False


def list_hwmons() -> dict:
    """Devuelve {hwmon_id: chip_name}."""
    out = {}
    try:
        ids = sorted(os.listdir("/sys/class/hwmon"))
    except OSError:
        return out
    for h in ids:
        chip = _read(f"/sys/class/hwmon/{h}/name") or "unknown"
        out[h] = chip
    return out


def _read(path: str):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None
