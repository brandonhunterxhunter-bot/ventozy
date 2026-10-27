"""Capa universal de sensores de temperatura — independiente del chipset.

El núcleo de Ventozy NO debe asumir que existe k10temp, coretemp, zenpower
o asus_ec. Este hub agrega TODAS las fuentes disponibles con detección
genérica y función de "el sensor que importa a tiempo real".

Fuentes (en orden de preferencia, todas opcionales):
  1. /sys/class/hwmon/*/temp*_input  (la estándar del kernel, en la que
     caen CHIPSETES: k10temp, coretemp, zenpower, asus_ec, it87, nct6775,
     thinkpad, acpitz, amdgpu, nouveau, iwlwifi, ...)
     → usa `tempX_label` cuando existe, y heurística de nombre en caso contrario
  2. `nvidia-smi --query-gpu=temperature.gpu`  → dGPU NVIDIA independiente
     de que el driver publique hwmon (nvidia en algunos equipos NO lo hace)
  3. psutil.sensors_temperatures()  (opcional; ya instalado en muchas distros)

Device.temperatures() ahora delega aquí; los adaptadores NO deben tocar
ningún path de temperatura.
"""

import glob
import os
import shutil
import subprocess
import threading
import time as _mod_time


# chips que son indiscutiblemente CPU (por si la etiqueta no existe)
CPU_CHIPS = {"k10temp", "zenpower", "coretemp", "cpu_thermal", "x86_pkg_temp"}
GPU_CHIPS = {"amdgpu", "radeon", "nouveau", "nvidia"}
# lablas que confrotan directo
CPU_WORDS = ("cpu", "tdie", "tctl", "package", "core")
GPU_WORDS = ("gpu",)


class SensorHub:
    _shared = None
    _lock = threading.Lock()
    _ttl = 0.6                  # cache corta: lectura barata + real-time

    def __init__(self):
        self._cache = None        # ({name: float}, ts)
        self._chipinfo = None     # {name: {"chip": chip, "hwmon": h, "label": ...}}

    # naming -----------------------------------------------------------
    def _scan(self):
        info = {}
        for hwmon_path in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
            try:
                chip = open(os.path.join(hwmon_path, "name")).read().strip()
            except OSError:
                continue
            for temp_file in sorted(glob.glob(f"{hwmon_path}/temp*_input")):
                base = temp_file.rsplit("_", 1)[0]
                key = os.path.basename(base)
                label = None
                try:
                    label = open(base + "_label").read().strip()
                except OSError:
                    pass
                name = label or series_of(chip, key)
                info[name] = {"path": temp_file, "chip": chip,
                              "hwmon": os.path.basename(hwmon_path),
                              "label": label or "", "source": "hwmon"}
        return info

    def chipinfo(self, refresh=False):
        with self._lock:
            if self._chipinfo is None or refresh:
                try:
                    self._chipinfo = self._scan()
                except OSError:
                    self._chipinfo = {}
        return self._chipinfo

    # lecturas ----------------------------------------------------------
    def _read_hwmon(self):
        out = {}
        for name, meta in self.chipinfo().items():
            try:
                out[name] = int(open(meta["path"]).read().strip()) / 1000
            except (OSError, ValueError):
                continue
        return out

    def _read_nvidia(self):
        if not shutil.which("nvidia-smi"):
            return {}
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=temperature.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2)
            vals = [float(v) for v in r.stdout.strip().splitlines() if v.strip()]
            return {f"NVIDIA GPU {i + 1}": t for i, t in enumerate(vals)}
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return {}

    def _read_psutil(self):
        try:
            import psutil
        except ImportError:
            return {}
        out = {}
        try:
            for name, entries in (psutil.sensors_temperatures() or {}).items():
                for e in entries:
                    if e.current:
                        key = e.label or name
                        out.setdefault(f"{name} {key}"[:32] if e.label else name,
                                       float(e.current))
        except Exception:
            pass
        return out

    def all_temperatures(self, refresh=False):
        """Dict {nombre_humano: °C} con todas las fuentes; cache TTL corta."""
        with self._lock:
            if self._cache is not None and not refresh:
                temps, ts = self._cache
                if _mod_time.time() - ts < self._ttl:
                    return temps
        temps = {}
        temps.update(self._read_hwmon())
        temps.update(self._read_nvidia())
        temps.update(self._read_psutil())
        # nombres repetidos entre fuentes: los hwmon ganan (vienen primero)
        with self._lock:
            self._cache = (temps, _mod_time.time())
        return temps

    def cpu_temp(self):
        return _prefer(self.all_temperatures(), CPU_CHIPS, CPU_WORDS)

    def gpu_temp(self):
        return _prefer(self.all_temperatures(), GPU_CHIPS, GPU_WORDS)

    def coolest_of(self):     # para curvas que mezclan CPU+GPU
        t = self.all_temperatures()
        return max(t.values()) if t else None

    def describe(self):
        return self.chipinfo()


def series_of(chip, key):
    """Nombre amable cuando el driver no da label: 'k10temp temp1' etc."""
    return f"{chip} {key}"


def _prefer(temps, chips, words):
    """Primera temperatura del grupo pedido.
    - Primero las etiquetas claras ('CPU Core', 'Tdie', 'GPU'...)
    - Luego los nombres de chip conocidos (k10temp..., amdgpu...)
    - Si nada matchea: primera lectura válida (mejor que no controlar).
    """
    for name, t in temps.items():
        if any(w in name.lower() for w in words):
            return t
    for name, t in temps.items():
        if any(c in name.lower() for c in chips):
            return t
    return _first_real(temps)


def _first_real(temps):
    for t in temps.values():
        return t
    return None


_hub = None


def hub():
    global _hub
    if _hub is None:
        with SensorHub._lock:
            if _hub is None:
                _hub = SensorHub()
    return _hub   # singleton
