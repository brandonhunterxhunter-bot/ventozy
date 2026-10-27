"""Importador de configs NBFC → formato declarativo Ventozy.

El pryecto nbfc-linux mantiene UN CATÁLOGO COMUNITARIO MANTENIDO:
  https://github.com/nbfc-linux/nbfc-linux (share/nbfc/model_support.json)
  + Configs/<Vendor>/<Model>.json  — miles de notebooks validados x usuarios.

Ufrmamos ese catálogo como fuente de datos (con créditos al pie del JSON
generado) y convertimos su formato (índices EC, umbrales de temperatura) al
nuestro (sysfs hwmon declarativo). Así Ventozy soporta de entrada la MISMA
lista de equipos que nbfc-linux, bajo nuestro motor seguro.

Comandos:
    python3 run.py import-nbfc --list "nicholas"
    python3 run.py import-nbfc --search "FA506"
    python3 run.py import-nbfc --install "ASUS/TUF Gaming FA506NC.json"

Nota honesta: los configs NBFC identifican ventiladores por mapas del
EC (números), no por sysfs. No podemos garantizar 1:1 en todos; el
convertidor mantiene nuestra autodetección de hwmon como primera opción
y usa la sabiduría del catálogo (fans, umbrales, min/max) como guía.
"""

import json
import os
import urllib.parse
import urllib.request
from typing import Optional

NBFC_RAW = "https://raw.githubusercontent.com/nbfc-linux/nbfc-linux/master/share/nbfc"
MODEL_SUPPORT = f"{NBFC_RAW}/model_support.json"
CONFIGS_DIR = f"{NBFC_RAW}/Configs"

PCT_TO_PWM = 255 / 100.0


def _get(url: str, timeout: int = 10) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def _config_url(filename: str) -> str:
    return f"{CONFIGS_DIR}/{urllib.parse.quote(filename)}"


# ---------------------------------------------------------------------------
def search(query: str) -> list:
    """Lista de modelos del catálogo nbfc que matchean un substring."""
    data = json.loads(_get(MODEL_SUPPORT).decode("utf-8"))
    q = query.lower()
    return [m for m in data
            if q in str(m.get("ProductName", "")).lower()
            or q in str(m.get("NotebookModel", "")).lower()
            or q in str(m.get("NotebookVendor", "")).lower()]


def fetch_config(filename: str) -> dict:
    return json.loads(_get(_config_url(filename)).decode("utf-8"))


# ---------------------------------------------------------------------------
def _thresholds_curve(cfg: dict) -> Optional[list]:
    """Convierte los umbrales (%) de NBFC a nuestra curva [(°C, PWM)].
    Soporta los formatos históricos: list de {'TargetFanSpeed': %, 'TargetTemperature': °C}
    o de {'CriticalTemperature': ..., 'TargetFanSpeed': ...}."""
    points = []
    for variant in ("TemperatureThresholds", "Thresholds", "FanSpeedRules"):
        ths = cfg.get(variant)
        if not isinstance(ths, list) or not ths:
            continue
        for th in ths:
            t = th.get("TargetTemperature") or th.get("CriticalTemperature") or \
                th.get("Temperature")
            s = th.get("TargetFanSpeed", th.get("FanSpeed"))
            if t is None or s is None:
                continue
            try:
                t = float(t)
                s = float(s)
            except (TypeError, ValueError):
                continue
            if s <= 100:                 # NBFC usa % (0-100)
                s = int(round(s * PCT_TO_PWM))
            points.append((int(t), int(max(0, min(255, s)))))
        if points:
            return sorted(points)
    return None


def _fan_configs(cfg: dict) -> list:
    fc = cfg.get("FanConfig") or {}
    fans = []
    for i, key in enumerate(sorted(fc)):
        f = fc[key]
        fans.append({
            "name": f.get("FanDisplayName", f"Fan {i + 1}"),
            "suggestion": {
                # pista habilitante: el catalogo dice cuántos fans hay,
                # pero Ventozy los re-detecta en sysfs (safer)
                "file": f"pwm{i + 1}",
                "min": f.get("MinFanValue"),
                "max": f.get("MaxFanValue"),
            },
        })
    return fans


def to_ventozy(nbfc_cfg: dict, info: Optional[dict] = None) -> dict:
    """Conversor NBFC JSON → config declarativa de Ventozy."""
    match = []
    for k in ("ProductName", "NotebookModel", "NotebookVendor"):
        v = (info or {}).get(k) or nbfc_cfg.get(k)
        if v:
            match.append(str(v))

    curve = _thresholds_curve(nbfc_cfg)
    fans = _fan_configs(nbfc_cfg)
    vendor = nbfc_cfg.get("Vendor") or (info or {}).get("NotebookVendor", "nbfc")

    out = {
        "match": [m[:80] for m in match] or ["_NBFC_SIN_MATCH_"],
        "info": {
            "model": (info or {}).get("NotebookModel") or
                     nbfc_cfg.get("NotebookModel") or match and match[0] or "?",
            "vendor": str(vendor),
            "notes": f"Importado del catálogo nbfc-linux "
                     f"('{(info or {}).get('ConfigFilename', '?')}'). "
                     f"Fans re-detectados en sysfs; corre 'ventozy doctor' "
                     f"tras instalar para verificar el equipo.",
            "credit": "https://github.com/nbfc-linux/nbfc-linux",
        },
        "fans": [{"hwmon": "auto", "file": f["suggestion"]["file"]} for f in fans],
        "profiles": [],  # lleno abajo
    }

    if curve:
        out["profiles"].append({
            "name": "balanced",
            "label": "⚖️  Equilibrado (de NBFC)",
            "curve": curve,
            "min_pwm": min(p for _, p in curve),
        })
        # derivar quiet y turbo del mismo conocimiento del catálogo
        lows = [(t, max(0, p - 40)) for (t, p) in curve]
        highs = [(t, min(255, p + 40)) for (t, p) in curve]
        out["profiles"].append({
            "name": "quiet", "label": "🔇  Silencio (de NBFC)",
            "curve": lows, "min_pwm": 0})
        out["profiles"].append({
            "name": "turbo", "label": "🚀  Turbo (de NBFC)",
            "curve": highs, "min_pwm": min(p for _, p in highs)})
    else:
        # su config no declara umbrales: usa curvas genéricas conservadoras
        out["profiles"] = [
            {"name": "quiet", "label": "🔇  Silencio",
             "curve": [[50, 60], [65, 120], [75, 190], [85, 255]], "min_pwm": 0},
            {"name": "balanced", "label": "⚖️  Equilibrado",
             "curve": [[45, 80], [60, 130], [70, 190], [80, 240], [88, 255]],
             "min_pwm": 0},
            {"name": "turbo", "label": "🚀  Turbo",
             "curve": [[40, 110], [55, 160], [65, 210], [75, 255]], "min_pwm": 0},
        ]
    return out


def install_model(filename: str, cfg_dir: Optional[str] = None) -> str:
    """Descarga y escribe configs/<model>.json en el proyecto. Devuelve path."""
    if cfg_dir is None:
        root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        cfg_dir = os.path.join(root, "configs")
    info_list = search(os.path.basename(filename))
    info = next((m for m in info_list
                 if m.get("ConfigFilename") == filename), None)
    cfg = fetch_config(filename)
    ventozy_cfg = to_ventozy(cfg, info)
    # nombre de archivo saneado
    safe = os.path.basename(filename).replace("/", "-").replace(" ", "-")
    if not safe.lower().endswith(".json"):
        safe += ".json"
    out_path = os.path.join(cfg_dir, f"nbfc-{safe}")
    os.makedirs(cfg_dir, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(ventozy_cfg, f, indent=1, ensure_ascii=False)
    return out_path
