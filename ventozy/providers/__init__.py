"""Integraciones opcionales. Cada provider se activa solo si es aplicable."""

from abc import ABC, abstractmethod
from typing import Optional


class Provider(ABC):
    """Integración voluntaria (asusctl, switch de GPU, perfiles, etc.)."""

    id: str

    @abstractmethod
    def available(self) -> bool:
        ...

    @abstractmethod
    def apply(self, *args, **kwargs) -> bool:
        ...


class AsusctlProvider(Provider):
    """Perfiles de rendimiento oficiales de asus-linux.org (opcional)."""
    id = "asusctl"

    def available(self) -> bool:
        import shutil
        return shutil.which("asusctl") is not None

    def apply(self, profile: Optional[str] = None, battery: Optional[int] = None) -> bool:
        import shutil
        import subprocess
        if not self.available():
            return False
        if profile:
            subprocess.run(["asusctl", "profile", profile], check=False)
        if battery is not None:
            bat = shutil.which("asusctl-battery")
            if bat:
                subprocess.run([bat, "-c", str(battery)], check=False)
        return True


PROVIDERS = [AsusctlProvider()]


def find(provider_id: str) -> Optional[Provider]:
    for p in PROVIDERS:
        if p.id == provider_id and p.available():
            return p
    return None
