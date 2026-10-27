"""Auto-importa todos los adaptadores para que sus @register corran."""

import importlib
import pkgutil


def import_all():
    for m in pkgutil.iter_modules(__path__):
        if m.name not in ("base", "generic", "__init__"):
            importlib.import_module(f"{__name__}.{m.name}")


import_all()

from .base import Device, DeviceInfo, Profile, detect, register  # noqa: E402,F401
