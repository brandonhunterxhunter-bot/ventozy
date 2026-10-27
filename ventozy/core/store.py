"""Persistencia de curvas editadas por el usuario (la GUI conserva tus
ajustes entre reinicios).

Ubicación: ~/.config/ventozy/curves.json  (respeta XDG_CONFIG_HOME)

Formato (JSON simple, diffable y respaldable):
    {"profiles": {"balanced": [[45, 80], [60, 120], ...], ...},
     "battery_limit": 80}

Solo curvas + límite de batería: lo demás (detección de hardware, perfiles
base) sonódigo, no estado del usuario.
"""

import json
import os
import threading

_LOCK = threading.Lock()


def _path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "ventozy", "curves.json")


def load() -> dict:
    """Devuelve el formato guardado o {} si no existe (jamás lanza)."""
    with _LOCK:
        try:
            with open(_path()) as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}


def save_profiles(device) -> bool:
    """Guarda las curvas del device y el límite de batería actual."""
    profiles = {}
    for name, prof in device.profiles.items():
        profiles[name] = [[t, p] for (t, p) in prof.curve]
    with _LOCK:
        try:
            os.makedirs(os.path.dirname(_path()), exist_ok=True)
            data = {"profiles": profiles}
            cur = device.battery_limit_current()
            if cur:
                data["battery_limit"] = cur
            tmp = _path() + ".tmp"
            with open(tmp, "w") as f:
                json.dump(data, f, indent=1)
            os.replace(tmp, _path())          # atómico: nunca corromper
            return True
        except (OSError, ValueError):
            return False


def apply_to(device) -> int:
    """Aplica lo guardado al device tras su detección. Devuelve n. de overrides.
    Guarda además las curvas 'de fábrica' para poder restaurarlas (reset)."""
    saved = load().get("profiles") or {}
    applied = 0
    device._factory_curves = {}
    for name, curve in saved.items():
        if name not in device.profiles:
            continue
        try:
            pts = sorted((int(t), int(p)) for t, p in curve)
        except (TypeError, ValueError):
            continue
        if pts:
            if name not in device._factory_curves:
                device._factory_curves[name] = list(device.profiles[name].curve)
            device.profiles[name].curve = pts
            applied += 1
    # límite de batería persistido
    lim = load().get("battery_limit")
    if lim and device.battery_path:
        try:
            device.battery_limit(int(lim))
        except (OSError, ValueError):
            pass
    return applied


def reset():
    try:
        os.remove(_path())
    except OSError:
        pass
