"""Perfiles de potencia estilo G-Helper (Whisper / Standard / Boost).

Traducción a Linux estándar (sin hacks, todo writable por sysfs):

  G-Helper        Linux
  ─────────────   ────────────────────────────────────────────────────
  Whisper         governor=powersave · EPP=power · boost=0
  Standard        governor=schedutil · EPP=balanced_performance · boost=1
  Boost           governor=performance · EPP=performance · boost=1

RIzen→Ryzen: amd_pstate (kernel ≥ 6.1) e Intel comparten la interfaz EPP.
Con kernels/ISO sin EPP (Mint retro), cae a `ondemand`/`conservative`.
"""

import glob
import os

PROFILES = {
    "whisper":  {"governor": "powersave",           "epp": "power", "boost": 0},
    "standard": {"governor": "schedutil",           "epp": "balanced_performance", "boost": 1},
    "boost":    {"governor": "performance",         "epp": "performance", "boost": 1},
}

CPU_BASE = "/sys/devices/system/cpu"
GOV_GLOB = f"{CPU_BASE}/cpu*/cpufreq"


def _boost_paths():
    return [
        f"{CPU_BASE}/cpufreq/boost",          # genérico acpi-cpufreq / amd_pstate
        f"{CPU_BASE}/intel_pstate/no_turbo",  # intel (invertido)
    ]


class PowerModes:
    def available(self) -> dict:
        """Qué hay en el sistema (para la GUI mostrar disabled lo que falte)."""
        out = {
            "governors": [],
            "epp": os.path.exists(glob.glob(f"{GOV_GLOB}/energy_performance_preference")[0])
                   if glob.glob(f"{GOV_GLOB}/energy_performance_preference") else False,
            "boost": any(os.path.exists(p) for p in _boost_paths()),
        }
        gov_file = glob.glob(f"{GOV_GLOB}/scaling_available_governors")
        if gov_file:
            try:
                out["governors"] = open(gov_file[0]).read().split()
            except OSError:
                pass
        return out

    def current(self) -> dict:
        cur = {"governor": None, "epp": None, "boost": None}
        gov = glob.glob(f"{GOV_GLOB}/scaling_governor")
        if gov:
            try:
                cur["governor"] = open(gov[0]).read().strip()
            except OSError:
                pass
        epp = glob.glob(f"{GOV_GLOB}/energy_performance_preference")
        if epp:
            try:
                cur["epp"] = open(epp[0]).read().strip()
            except OSError:
                pass
        if os.path.exists(f"{CPU_BASE}/cpufreq/boost"):
            try:
                cur["boost"] = int(open(f"{CPU_BASE}/cpufreq/boost").read())
            except (OSError, ValueError):
                pass
        return cur

    def guess_profile(self) -> str:
        c = self.current()
        if c["governor"] == "performance":
            return "boost"
        if c["epp"] == "power" or c["governor"] in ("powersave", "conservative"):
            return "whisper"
        return "standard"

    def apply(self, name: str, write=lambda path, val: _write(path, val)) -> bool:
        """Aplica un perfil. `write` es inyectable (GUI injecta pkexec)."""
        cfg = PROFILES.get(name)
        if not cfg:
            return False
        ok = False

        # governor + epp en todas las CPUs
        for gov in glob.glob(f"{GOV_GLOB}/scaling_governor"):
            ok = write(gov, cfg["governor"]) or ok
        if cfg["epp"]:
            for epp in glob.glob(f"{GOV_GLOB}/energy_performance_preference"):
                write(epp, cfg["epp"])

        # boost (global); intel_pstate/no_turbo es invertido
        if cfg["boost"] is not None:
            if os.path.exists(f"{CPU_BASE}/cpufreq/boost"):
                write(f"{CPU_BASE}/cpufreq/boost", cfg["boost"])
            if os.path.exists(f"{CPU_BASE}/intel_pstate/no_turbo"):
                write(f"{CPU_BASE}/intel_pstate/no_turbo",
                      0 if cfg["boost"] else 1)
        return ok


def _write(path, value):
    try:
        with open(path, "w") as f:
            f.write(str(value))
        return True
    except (OSError, PermissionError):
        return False
