"""Auto-switch estilo G-Helper: cambia perfil según cargador/batería.

En AC → perfil "balanced" (o el configurado). En batería → "quiet".
Muy eficiente: solo un chequeo de 1 archivo cada 10 s.

Uso:
    sudo python3 run.py autoswitch [ac_profile] [dc_profile]
    (por defecto balanced / quiet)
"""

import os
import time

from .devices import Device

AC_GLOBS = ["/sys/class/power_supply/A*/online"]
DEFAULT_AC = "balanced"
DEFAULT_DC = "quiet"
CHECK_S = 10


def on_ac() -> bool:
    """True si hay corriente conectada (o no se sabe)."""
    import glob as g
    for pattern in AC_GLOBS:
        for p in g.glob(pattern):
            try:
                return open(p).read().strip() == "1"
            except OSError:
                continue
    return True   # no detectado: asumir AC (más seguro: más ventilación)


class AutoSwitchDaemon:
    def __init__(self, device: Device, ac: str = DEFAULT_AC,
                 dc: str = DEFAULT_DC, interval: int = CHECK_S):
        self.device = device
        self.ac_profile = ac
        self.dc_profile = dc
        self.interval = interval
        self.last_state = None
        self.stop_flag = False
        import threading
        self._lock = threading.Lock()

    def step(self, log=print):
        state = "ac" if on_ac() else "dc"
        if state == self.last_state:
            return None
        self.last_state = state
        target = self.ac_profile if state == "ac" else self.dc_profile
        prof = self.device.profiles.get(target)
        if not prof:
            log(f"[autoswitch] perfil '{target}' no existe")
            return None
        from ..service import FanDaemon
        d = FanDaemon(self.device)
        # para AC/DC solo aplica el perfil una vez (arranca su curva)
        if d.start_profile(target):
            pwm = d.step()
            log(f"[autoswitch] {state.upper()} → '{prof.label}' (PWM {pwm})")
        # adaptar también la potencia: batería → whisper, AC → standard
        from .power import PowerModes
        pm = PowerModes()
        try:
            pm.apply("whisper" if state == "dc" else "standard")
        except OSError:
            pass
        return state

    def run_forever(self, log=print):
        def clean(*_):
            self.device.auto()
            log("\n[autoswitch] detenido — control del kernel restaurado.")
            sys.exit(0)
        import signal
        signal.signal(signal.SIGINT, clean)
        signal.signal(signal.SIGTERM, clean)
        log(f"[autoswitch] AC='{self.ac_profile}' · batería='{self.dc_profile}' · "
            f"chequeo cada {self.interval}s")
        while True:
            try:
                self.step(log)
            except (OSError, PermissionError) as e:
                log(f"[autoswitch] I/O: {e}")
            time.sleep(self.interval)
