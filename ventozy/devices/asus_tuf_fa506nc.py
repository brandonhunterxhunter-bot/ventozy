"""ASUS TUF Gaming A15 FA506NC (Ryzen 5 7535HS + RTX 3050).

Los adaptadores codificados solo se usan cuando el equipo necesita lógica
especial que un JSON no puede expresar. Para el FA506NC:
  - PWM asus-nb-wmi con piso de hardware ~30 % (≈77/255)
  - Sensor de temperatura AMD: k10temp / zenpower
  - Límite de carga de batería vía charge_control_end_threshold
"""

import os
from typing import Dict, List

from ..core.sysfs import Fan, Sensor, list_hwmons
from .base import Device, DeviceInfo, Profile, register

MIN_PWM = 77  # protección de hardware: el TUF no baja de ~30 %

PROFILES = {
    "quiet":    Profile("quiet", "🔇  Silencio",     [(50, 60), (65, 110), (75, 180), (83, 240), (90, 255)], MIN_PWM),
    "balanced": Profile("balanced", "⚖️  Equilibrado", [(45, 80), (60, 120), (70, 190), (80, 240), (88, 255)], MIN_PWM),
    "turbo":    Profile("turbo", "🚀  Turbo",          [(40, 110), (55, 160), (65, 210), (75, 255)],          MIN_PWM),
}


def _find_fans() -> List[Fan]:
    fans = []
    for hwmon, chip in list_hwmons().items():
        try:
            entries = sorted(os.listdir(f"/sys/class/hwmon/{hwmon}"))
        except OSError:
            continue
        if "asus" in chip or "nct" in chip:
            for name in entries:
                if name.startswith("pwm") and len(name) == 4 and name[3].isdigit():
                    fans.append(Fan(hwmon=hwmon, file=name))
    return fans


def _find_sensors() -> List[Sensor]:
    for hwmon, chip in list_hwmons().items():
        if chip in ("k10temp", "zenpower"):
            return [Sensor(hwmon=hwmon, label="temp1_input", chip=chip)]
    return []


@register
class AsusTufFA506NC(Device):
    """Las temperaturas las pone core.sensors.hub (Device base):
    hardware-agnosticCPU + la dGPU vía nvidia-smi. Este adaptador ya NO
    depende de k10temp/zenpower — funciona con cualquier kernel/chip."""

    MATCH = ["fa506nc", "fa506"]  # DMI: product_name / board_name (lowercase)

    def __init__(self):
        self.info = DeviceInfo(
            model="ASUS TUF Gaming A15 FA506NC",
            vendor="ASUSTeK",
            notes="PWM mínimo de hardware ~30 % (77). asus-nb-wmi.")
        self.min_pwm = MIN_PWM
        self.battery_path = "/sys/class/power_supply/BAT0/charge_control_end_threshold"
        self.profiles = PROFILES
        self.fans = _find_fans()
        # declarativos solo para `status`; temperature está en el hub universal
        self.sensors = _find_sensors()

    def temperatures(self) -> Dict[str, float]:
        """CPU (el hub elige el driver de temperatura disponible) + GPU dGPU."""
        from ..core.sensors import hub
        h = hub()
        out: Dict[str, float] = {}
        tcpu = h.cpu_temp()
        if tcpu is not None:
            out["CPU"] = tcpu
        tgpu = h.gpu_temp()
        if tgpu is not None:      # la RTX 3050 se enfría por convergencia here,
            out["GPU"] = tgpu     # pero conviene vigilarla con la misma curva
        return out or super().temperatures()

    def fan_rpms(self) -> List[int]:
        rpms = []
        for fan in self.fans:
            r = fan.read_rpm()
            if r is not None:
                rpms.append(r)
        return rpms
