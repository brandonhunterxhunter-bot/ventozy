"""Device API: contratos que todo adaptador de equipo debe implementar.

Un "Device" describe el hardware sin asumir dónde están las cosas:
declara sus sensores y ventiladores (objetos de core.sysfs) y sus
perfiles de curva. El core y la UI solo hablan con esta API.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..core.sysfs import Fan, Sensor, _read


@dataclass
class Profile:
    """Un perfil de ventilación (equivalente a los de G-Helper)."""
    name: str                                  # "quiet", "balanced", "turbo"...
    label: str                                 # texto mostrado, con emoji
    curve: List[tuple]                         # [(temp, pwm), ...]
    min_pwm: int = 0                           # piso de hardware


@dataclass
class DeviceInfo:
    model: str                  # ej. "ASUS TUF Gaming A15 FA506NC"
    vendor: str
    notes: str = ""


class Device(ABC):
    """Contrato comunitario. Para agregar tu portátil, hereda de aquí."""

    info: DeviceInfo
    sensors: List[Sensor]
    fans: List[Fan]
    profiles: Dict[str, Profile]
    min_pwm: int = 0            # piso global de hardware del equipo
    battery_path: Optional[str] = None

    # ---------- API que usa el core y la UI ----------
    def temperatures(self) -> Dict[str, float]:
        """Temperaturas REALES y agnósticas de chipset (core.sensors.hub).

        Devuelve {nombre: °C} con todas las fuentes disponibles: hwmon
        (k10temp/coretemp/zenpower/asus_ec/it87/amdgpu/...), nvidia-smi y
        psutil. El daemon usa la MÁS CALIENTE para las curvas, de modo que
        el control es válido en cualquier portátil sin adaptar código."""
        from ..core.sensors import hub
        out = {}
        for name, t in hub().all_temperatures().items():
            if 0 <= t <= 250:               # saneado (sensores rotos dan 127⁵)
                out[name] = t
        return out

    @abstractmethod
    def fan_rpms(self) -> List[int]:
        """Lista de RPM actual por ventilador."""

    def apply_pwm(self, value: int) -> None:
        """Escritura en TODOS los ventiladores (CPU + GPU), con reintentos.

        Notas de estabilidad:
          - Algunos chips (asus-nb-wmi) no exponen pwmX_enable: la escritura
            manual de pwmX ya cambia la velocidad igualmente.
          - Reintentamos para atravesar rebajas transitorias de sysfs
            (p. ej. la EC ocupada al cambiar el perfil de energía).
        """
        from ..core.curve import clamp_pwm
        import time
        value = clamp_pwm(value, self.min_pwm)
        for fan in self.fans:
            fan.set_auto("0")
            for _ in range(3):
                if fan.write(value):
                    break
                time.sleep(0.05)
            # verifica que ambos fans (y cada uno) reflejen el valor pedido
            read = fan.read()
            if read is not None and abs(read - value) > 16:
                print(f"[ventozy] ⚠ PWM no aceptado en {fan.path} "
                      f"(pedimos {value}, queda en {read})")

    def auto(self) -> None:
        for fan in self.fans:
            fan.set_auto("2")

    def profile(self, name: str) -> Optional[Profile]:
        return self.profiles.get(name)

    # ---------- batería (opcional) ----------
    def battery_limit(self, percent: int) -> bool:
        if not (self.battery_path and 20 <= percent <= 100):
            return False
        try:
            with open(self.battery_path, "w") as f:
                f.write(str(percent))
            return True
        except OSError:
            return False

    def battery_limit_current(self) -> Optional[int]:
        if not self.battery_path:
            return None
        try:
            return int(_read(self.battery_path) or "")
        except (OSError, ValueError):
            return None


# ---------------------------------------------------------------------------
# Registro + detección
# ---------------------------------------------------------------------------
_REGISTRY: Dict[type, list] = {}


def register(cls: type):
    """Decorador: usa el atributo de clase MATCH (lista, lowercase) con DMI."""
    _REGISTRY[cls] = [p.lower() for p in getattr(cls, "MATCH", [])]
    return cls


def detect() -> Optional["Device"]:
    """Detecta el equipo leyendo DMI (/sys/class/dmi/id) y elige Device."""
    product = (_read("/sys/class/dmi/id/product_name") or "").lower()
    board = (_read("/sys/class/dmi/id/board_name") or "").lower()

    # 1) Adaptadores de código (precisión máxima, lógica especial)
    for cls, patterns in _REGISTRY.items():
        if any(p in product or p in board for p in patterns):
            return cls()

    # 2) Configs JSON declarativas (la vía de la comunidad: solo un .json)
    from .generic import GenericDevice, load_config
    cfg = load_config(product, board)
    if cfg:
        return GenericDevice.from_dict(cfg)

    # 3) Fallback universal para cualquier notebook con hwmon PWM
    return GenericDevice()
