# Guía para contribuir un equipo nuevo

## 0. Requisitos previos

- Linux con kernel nuevo (≥ 5.10 recomendado)
- Permisos para escribir en `/sys/class/hwmon/<x>/pwm?` (root o reglas udev)

## 1. Diagnóstico del hardware

```bash
python3 run.py status
lsmod | grep -Ei "asus|nct|k10temp|coretemp"
for h in /sys/class/hwmon/hwmon*; do echo "== $h: $(cat $h/name)"; ls "$h" | grep -E 'pwm|fan|temp'; done
```

Comprueba si al escribir `0-255` en el `pwm?` cambia la velocidad (¡empieza
con valores altos, 128+, por seguridad!). El RPM debe verse en el `fan?_input`
asociado.

## 2. Elige la vía

### A. JSON declarativo (recomendado para la mayoría)

Crea `configs/<tu-marca>-<modelo>.json` con el patrón
`generic-template.json`. Se autodetecta todo si dejas `fans`/`sensors`
vacíos. Esperamos que tu PR solo toque ese archivo.

### B. Adaptador de código (para hardware con lógica especial)

```python
# devices/acme_xg99.py
from ..core.sysfs import Fan, Sensor, list_hwmons
from .base import Device, DeviceInfo, Profile, register

@register
class AcmeXG99(Device):
    MATCH = ["xg99"]   # substring de /sys/class/dmi/id (lowercase)

    def __init__(self):
        ...rellena info, profiles, fans, sensors...

    def temperatures(self) -> dict: ...
    def fan_rpms(self) -> list: ...
```

Crea `configs/<marca>-<modelo>.json` con `"prefer": "code-adapter"` y
`"info"` para documentarlo.

## 3. Verificaciones antes de enviar el PR

- [ ] `python3 run.py status` detecta el equipo y sus sensores/fans
- [ ] `python3 run.py daemon balanced` con histéresis estable (sin oscilación)
- [ ] Auto oficial de tu equipo se recupera con Ctrl+C
- [ ] Si tu PWM tiene piso de hardware, declara `min_pwm` y lo documentas
- [ ] `README.md` lista tu equipo en la tabla de soportados

## 4. Seguridad

No permitas que la curva baje del PWM mínimo físico de tu equipo:
puede provocar throttling o apagados. Usa `min_pwm` generosamente.
