"""Device genérico + carga de configs declarativas JSON.

Este adaptador intenta funcionar en CUALQUIER portátil Linux:
detecta hwmons con PWM arbitrarios y los controla. Es el fallback
y la base de los configs/*.json de la comunidad.
"""

import json
import os
from typing import Dict, List, Optional

from ..core.sysfs import Fan, Sensor, _read, list_hwmons
from .base import Device, DeviceInfo, Profile


def load_config(product: str, board: str) -> Optional[dict]:
    """Busca en configs/*.json un equipo cuyo campo 'match' coincida."""
    cfg_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "configs")
    if not os.path.isdir(cfg_dir):
        return None
    for fn in sorted(os.listdir(cfg_dir)):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(cfg_dir, fn)) as f:
                cfg = json.load(f)
        except (OSError, ValueError):
            continue
        pats = [p.lower() for p in cfg.get("match", [])]
        if any(p in product or p in board for p in pats):
            return cfg
    return None


def _materialize(cfg: dict) -> tuple:
    """Construye (fans, sensors) desde el JSON si declara rutas; si no,
    autodetecta escaneando todos los hwmons."""
    fans, sensors = [], []

    for f in cfg.get("fans", []):
        fans.append(Fan(hwmon=f["hwmon"], file=f["file"]))

    for s in cfg.get("sensors", []):
        sensors.append(Sensor(hwmon=s["hwmon"], label=s["label"], chip=s.get("chip", "")))

    if not fans or not sensors:
        auto_fans, auto_sensors = autodetect(chips=cfg.get("sensor_chips"))
        fans = fans or auto_fans
        sensors = sensors or auto_sensors
    return fans, sensors


def autodetect(chips: Optional[List[str]] = None) -> tuple:
    """Escaneo universal de hwmon."""
    fans, sensors = [], []
    for hwmon, chip in list_hwmons().items():
        base = f"/sys/class/hwmon/{hwmon}"
        try:
            entries = sorted(os.listdir(base))
        except OSError:
            continue
        for name in entries:
            if name.startswith("pwm") and len(name) == 4 and name[3].isdigit():
                fans.append(Fan(hwmon=hwmon, file=name))
        if chips and chip not in chips:
            continue
        for name in entries:
            if name.endswith("_input") and name.startswith("temp"):
                sensors.append(Sensor(hwmon=hwmon, label=name, chip=chip))
    # orden estable: los chips térmicos conocidos primero
    sensors.sort(key=lambda s: 0 if s.chip in ("k10temp", "coretemp", "zenpower") else 1)
    return fans, sensors


class GenericDevice(Device):
    """Device configurable por JSON (configs/generic-template.json).

    Cómo contribuir tu notebook con SOLO un archivo:
    copia configs/generic-template.json → configs/<tu-eqipo>.json,
    completa match/fans/sensors/profiles y listo."""

    def __init__(self):
        self.info = DeviceInfo(model="Generic Linux laptop", vendor="community",
                               notes="Fallback universal por autodetección de hwmon.")
        self.min_pwm = 0
        self.battery_path = None
        self.profiles = {}
        self._cfg: dict = {}
        self.fans: List[Fan] = []
        self.sensors: List[Sensor] = []

    # -- reconfiguración runtime (usado por from_dict) --
    def reload(self, cfg: dict) -> None:
        self._cfg = cfg or {}
        if self._cfg:
            info = self._cfg.get("info")
            if info:
                self.info = DeviceInfo(**info)
            self.min_pwm = self._cfg.get("min_pwm", 0)
            self.battery_path = self._cfg.get("battery_path")
            self.profiles = {
                p["name"]: Profile(name=p["name"], label=p["label"],
                                   curve=[tuple(pt) for pt in p["curve"]],
                                   min_pwm=p.get("min_pwm", self.min_pwm))
                for p in self._cfg.get("profiles", [])
            }
        self.fans, self.sensors = _materialize(self._cfg)

    @classmethod
    def from_dict(cls, cfg: dict) -> "GenericDevice":
        dev = cls()
        dev.reload(cfg)
        return dev

    # ---------- API ----------
    def temperatures(self) -> Dict[str, float]:
        """TODO tarjeta cliente se decide en core.sensors.hub (universal).
        Basta llamar al base: funciona sin k10temp, con it87, asus_ec, etc."""
        return super().temperatures()

    def fan_rpms(self) -> List[int]:
        rpms = []
        for fan in self.fans:
            r = fan.read_rpm()
            if r is not None:
                rpms.append(r)
        return rpms
