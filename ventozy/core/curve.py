"""Ventozy: matemática de curvas. Pura, testeable, sin I/O."""

from typing import List, Optional, Tuple

Point = Tuple[int, int]  # (temp_c, pwm)


def interpolate(curve: List[Point], temp: float) -> int:
    """Interpolación lineal entre puntos de la curva (°C → PWM 0-255)."""
    if not curve:
        return 255
    curve = sorted(curve)
    if temp <= curve[0][0]:
        return curve[0][1]
    if temp >= curve[-1][0]:
        return curve[-1][1]
    for (t0, p0), (t1, p1) in zip(curve, curve[1:]):
        if t0 <= temp <= t1:
            if t1 == t0:
                return p1
            return int(p0 + (p1 - p0) * (temp - t0) / (t1 - t0))
    return curve[-1][1]


def hysteresis(current: int, target: int, step: int = 3) -> int:
    """Evita oscilación del PWM: solo cambia si la diferencia supera `step`."""
    if abs(target - current) < step:
        return current
    return target


def clamp_pwm(value: int, minimum: int = 0) -> int:
    """Aplica piso mínimo de hardware (ej. el TUF no baja de ~77)."""
    return max(minimum, min(255, value))


def ramp(current: Optional[int], target: int, rate: int = 12) -> int:
    """Limitador de rampa: cambia el PWM a lo sumo `rate` por iteración.

    ¿Por qué? Saltos bruscos de 0→255 estresan los rodamientos (cambios de
    dirección a máx. velocidad cada pocos segundos) y suenan a "jato".
    Además, subir a tope progresivamente evita picos de corriente on el
    PWM a 25 kHz del chipset.
    """
    if current is None:
        return target
    delta = target - current
    if abs(delta) <= rate:
        return target
    return current + rate * (1 if delta > 0 else -1)


def ramp_up_fast_down(current: Optional[int], target: int,
                      up_rate: int = 12, down_rate: int = 6) -> int:
    """Rampa asimétrica: sube rápido (protección térmica), baja lento
    (estabilidad de RPM y menos ciclos). Es el patrón de los controladores
    de fábrica de los portátiles."""
    if current is None:
        return target
    if target > current:
        return ramp(current, target, up_rate)
    if target < current:
        return ramp(current, target, down_rate)
    return target
