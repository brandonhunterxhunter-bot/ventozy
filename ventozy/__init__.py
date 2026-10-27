"""
ventozy — Control de ventiladores para portátiles en Linux.

Arquitectura (para contribuir):

    core/       → motor genérico agnóstico de hardware (sysfs, curvas, daemon)
    devices/    → adaptadores por modelo de equipo (uno por laptop soportada)
    configs/    → configuración declarativa JSON por equipo (fuera del código)
    providers/  → integraciones opcionales (asusctl, GPU switch, etc.)
    ui/         → interfaz (Tk). No conoce hardware: solo consume la API Device

Reglas para contribuir un equipo nuevo:
  1. El código core NO debe referenciar modelos ni rutas específicas.
  2. Todo hardware específico vive en devices/<marca>_<modelo>.py o en
     configs/<marca>-<modelo>.json (ver configs/generic-template.json).
  3. Un Device declara: sensores, ventiladores, límites y curvas.
"""
__version__ = "0.3.0"
