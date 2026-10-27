# Ventozy — Control de ventiladores modular para portátiles Linux

Proyecto comunitario: cada portátil soportado aporta sus propios "devices"
y "configs". Nada del código núcleo sabe qué hardware está controlando.

## Arquitectura (para contribuir)

```
run.py                  ← CLI + GUI (solo orquesta)
ventozy/
  core/
    sysfs.py            ← acceso genérico a /sys/class/hwmon
    curve.py            ← matemática pura: interpolar, histéresis, clamp
  devices/
    base.py             ← Device API (contrato) + registro/detección por DMI
    generic.py          ← fallback universal + carga de configs JSON
    <marca>_<model>.py  ← adaptadores de código (pocos, para casos raros)
  providers/            ← integraciones opcionales (asusctl, etc.)
  service.py            ← FanDaemon (loop, curva, histéresis)
  ui/                   ← GUI Tk. Secciones intercambiables. 0 sysfs aquí.
configs/
  generic-template.json ← plantilla para agregar tu notebook SOLO con JSON
  <marca>.json          ← configs declarativas por equipo
```

## Uso

```bash
python3 run.py               # GUI estilo G-Helper
python3 run.py status        # diagnóstico del hardware
python3 run.py daemon quiet  # daemon seguro (quiet | balanced | turbo)
python3 run.py gpu auto      # gráficos integrados (ahorro)
python3 run.py gpu on        # gráficos dedicados siempre activos
sudo python3 run.py install  # arranque automático con systemd
sudo python3 run.py hotkeys  # Fn+F5 modo fans · Fn+↑/↓ brillo teclado
python3 run.py list
python3 run.py doctor         # diagnóstico completo en un comando
```

## Persistencia de tu configuración

- Las **curvas personalizadas** (editor de la GUI) se guardan al momento en
  `~/.config/ventozy/curves.json` — sobreviven reinicios y actualizaciones.
  Botón **"↺ Original"** vuelve a la curva del adaptador de fábrica.
- El **límite de batería** también se recuerda y se re-aplica al arrancar la GUI.

## Diagnóstico: `ventozy doctor`

Comprueba en ~2 s todo lo que suele fallar y dice cómo arreglarlo:
python, tkinter, evdev, hwmon/PWM legible **y escribible**, sensores, batería,
GPU dedicada, servicio systemd, y si tienes curvas personalizadas activas.
Ideal como primer paso al reportar un issue.
```

## Agregar tu portátil (vía declarativa, sin código)

1. `cp configs/generic-template.json configs/<tu-marca>.json`
2. Cambia `"match"` (aparece en `/sys/class/dmi/id/product_name`).
3. Deja `fans`/`sensors` vacíos → autodetección universal, o especifica
   rutas exactas si tu equipo las necesita.
4. Ajusta curvas en `profiles`.

## Instalación "decente" para Linux Mint: paquete .deb 📦

```bash
bash packaging/build-deb.sh
sudo apt install ./ventozy_1.0.0_all.deb     # o doble clic en Mint
```

El .deb (dpkg oficial) instala:
- `/usr/bin/ventozy` — ejecutable real en el PATH (`ventozy`, `ventozy GUI`, doctor)
- `/usr/share/applications/ventozy.desktop` — aparece en el menú de apps con el icono
- `/usr/share/icons/hicolor/scalable/apps/ventozy.svg` — logo vectorial
  (nítido a cualquier resolución en Cinnamon: panel, dock, Alt-Tab)
- `/opt/ventozy` — código completo con assets
- `/lib/systemd/system/ventozy.service` + `ventozy-hotkeys.service` — autostart
  (daemon seguro al arranque + Fn+F5/Fn+↑/↓), enbailed en `postinst`
- política polkit `com.ventozy.modify` (password con memoria de 5 min)

**Desinstalación con reversión total**: `sudo apt remove ventozy` —

## Independencia de sensores (tiempo real)

El núcleo ya NO depende de que exista un driver concreto (`k10temp`,
`coretemp`, `zenpower`, `asus_ec`, `it87`...). `core/sensors.py` es un
**hub universal** que agrega en tiempo real todas las fuentes que haya:
- **hwmon** (la estándar del kernel): con `tempX_label` si el driver la da;
  si no, aplica heurística amilla (chip + palabra clave CPU/GPU).
- **`nvidia-smi`** para la GPU dedicada (independiente de si el driver
  publica hwmon o no — importante en NVIDIA).
- **`psutil`** si está instalado (opcional).
La GUI refresca a 1 s y muestra TODOS los sensores con un ▸ marcando el
más caliente — que es, precisamente, el que gobierna las curvas. Si tu
equipo no tiene `k10temp`, Ventozy controla igual; y si el día de mañana
tu kernel cambia el driver de temperatura, sigue funcionando.

## Ecosistema: proyectos probados que Ventozy integra

No reinventamos nada que ya funcione. Estas piezas están integradas con
crédito y trazabilidad:

| Proyecto | Qué adoptamos | Vía |
|---|---|---|
| **nbfc-linux** ⭐ | Catálogo comunitario de configs validadas (miles de modelos, umbrales exactos) | `ventozy import-nbfc` (providers/nbfc.py) |
| **asus-linux / asusctl** | RGB de teclado (Aura), perfiles de rendimiento oficiales | providers/kbd.py (opcional) |
| **psutil** | fuente extra de sensores en equipos raros | core/sensors.py (opcional) |
| **notify-send / libnotify** | notificaciones nativas de escritorio | providers/notify.py |
| **AppIndicator3** | icono y menú en el panel de Mint/Cinnamon | providers/tray.py |
| **quiet-fan** (bitwombat) | concepto del modo adaptativo escalera | providers/adaptive.py (reescrito con nuestro watchdog) |
| **supergfxctl** | Optimus hard-off (referenciado, no invocado) | documentado |

## Agregar tu portátil (con código)

Hereda de `ventozy/devices/base.py::Device`, implementa
`temperatures()` y `fan_rpms()`, marca `MATCH` y decora con `@register`.
Véase `devices/asus_tuf_fa506nc.py` de ejemplo.

## Reglas de oro

- El núcleo **nunca** referencia modelos ni paths específicos.
- Todo hardware vive en `devices/` (código) o `configs/` (declarativo).
- Todo lo de `core/curve.py` es puro y testable; manténlo así.
- La UI solo consume la API `Device`, nunca `/sys`.

---

## Atajos como G-Helper ⌨️

| Tecla | Acción | Cómo llega |
|---|---|---|
| **Fn+F5** | ciclo del modo de ventilador: Silencio → Equilibrado → Turbo | daemon evdev (servicio `ventozy-hotkeys`) |
| **Fn+↑/↓** | brillo de la retroiluminación del teclado | `KEY_KBDILLUMUP/DOWN` de `asus-nb-wmi` (cero risk de romper flechas normales) |

- Instalado y activado por `install.sh` (servicio `ventozy-hotkeys`, 40 MB cap,
  se auto-levanta en el arranque).
- Requiere `python3-evdev` (lo instala el script). El demostración: la GUI
  también tiene los botones de brillo y la paleta de colores.

## Colores de la retroiluminación del teclado 🎨

Interruptor brillo: botones `Brillo ±` en la GUI (LED `/sys/class/leds/asus::kbd_backlight`).
Colores: paleta de 9 colores predefinidos + campo **color propio** (hex, p. ej.
`#2b7cd3`). Por debajo usa `asusctl` (proyecto oficial asus-linux.org) — el
FA506NC tiene RGB Single-Zone del firmware con modos estático/etc.
Sin asusctl la GUI avisa: "instala asusctl". Estilo todo reversible.

## Paridad de funciones con G-Helper

| G-Helper (Windows) | Ventozy (Linux / Mint) | Funciona |
|---|---|---|
| Modos fan Silent/Balanced/Turbo | 🔇/⚖️/🚀 + Auto, curvas editables, both fans con reintentos | ✅ |
| Power mode Whisper/Standard/Boost | governor + EPP + boost (providers/power.py),cripts en botones | ✅ |
| Auto-switch fans en batería/cargador | AutoSwitchDaemon: AC→balanced, batería→quiet + whisper power | ✅ |
| GPU switch (iGPU/dGPU) | runtime PM reversible (providers/gpu.py) | ✅ |
| Keyboard backlight + RGB | brillo sysfs + paleta + hex custom vía asusctl | ✅ |
| Battery health charging | 60/80/100 % vía charge_control_end_threshold | ✅ |
| Dust cleaning (fans 100 %) | botón "🧹 Limpieza de polvo" 30 s | ✅ |
| Fn+F5 cambiar fans | hotkeys daemon Fn+F5 y Fn+↑/↓ | ✅ |
| Updater / servicio de fondo | systemd (autostart, idle-CPU, MemoryMax) | ✅ |

## Notas Linux Mint (Cinnamon)

- Ya funciona de serie: Cinnamon respeta el `.desktop` generado por
  `install.sh` (menú de apps, icono).
- Puedes añadir un applet al panel: right click panel → "Add applets" →
  "Notifications" o "Power modules", o crear keyboard shortcuts en
  Config → Keyboard → Shortcut (comando `ventozy status`) si prefieres
  delegar en el DE en lugar del daemon evdev.
- La política pkexec creada por install.sh pide la contraseña con memoria
  (5 min) — como G-Helper muestia UAC solo la primera vez.
- amd_pstate: usa kernel ≥ 6.1 de Mint para máximo control (governors).

## Bepping extra: notificaciones, bandeja y modo adaptativo

- **Notificaciones de escritorio** (`notify-send`): al cambiar de modo con
  Fn+F5 o la GUI aparece un toast "Ventiladores → Turbo"; ante una
  emergencia del watchdog sale `critical` (con sonido). Si `notify-send`
  no existe, todo mono sigue funcionando igual.
- **Icono en la bandeja** (panel de Cinnamon): `python3 run.py tray`
  → menú con los 3 modos, toggle de GPU dedicada y "Salir (restaura Auto)".
  Necesita `gir1.2-appindicator3-0.1` (Mint lo trae por defecto).
- **Modo adaptativo** (`ventozy adaptive 75`): como quiet-fan — busca
  TODO el menor PWM que mantenga la CPU bajo el objetivo °C. Sube rápido
  ante calor (+8/tick), baja lento (−3/tick) con verificación. Usa el
  mismo watchdog (95 °C → auto del kernel). Ideal para lectura/silencio
  nocturno, sonido por debajo del Turbo que no dispara re-subidas.

## Estabilidad extra (rampas y cooldown)

- **Rampa asimétrica de PWM** (`core/curve.py`): sube rápido ante calor
  (12 PWM/tick) y baja lento (6/tick). Menos "jato" de ventiladores, menos
  ciclos y sin picos de corriente.
- **Cooldown post-emergencia** (`core/safety.py`): tras un fallo, el
  watchdog no reintenta durante 30 s; evita oscilar emergencia→reintento.
- **Banner de seguridad en la GUI**: si el watchdog actúa, la interfaz se
  congela en modo kernel y ofrece el botón "♻ Reintentar tras fallo"
  (la rehabilitación manual exige que el cooldown haya expirado).
- **Tests sin hardware**: `python3 -m pytest tests/ -q` valida interpolación,
  histéresis, rampas, piso de PWM y las emergencias del watchdog con un
  `FakeDevice` (también: `python3 tests/test_safety.py` sin pytest).

## Seguridad: por qué un control fan puede dañar equipos

El peligro no es girar los fans, sino que el daemon **deje de ser responsable
del PWM sin revertir el control**. Ventozy lo mitiga así:

| Riesgo | Mitigación implementada |
|---|---|
| PWM fijo con daemon muerto | ante cualquier excepción I/O y en SIGTERM se llama `device.auto()` SIEMPRE |
| Sensores ilegibles ("daemon ciego") | watchdog: 3 fallos seguidos → auto() + exit(75) |
| Temperatura crítica (≥ 95 °C) | emergencia: auto() inmediato + exit(75) |
| Escribir en el path equivocado | solo se escribe `pwm?` y `pwm?_enable`; jamás `fan?_input` |
| PWM bajo el piso del hardware | `min_pwm` por equipo siempre respetado (TUF ≈ 77/255) |
| Escritura fallida en silencio | verificación de lectura post-escritura |
| CPU excesiva | `Nice=15` + `CPUSchedulingPolicy=idle` + intervalo de 5 s |
| Reinicio infinito si algo falla | systemd reintenta con 30 s de backoff y exit(75) |

## Arranque automático en segundo plano (consumo mínimo)

```bash
sudo bash install.sh        # código a /opt, servicio systemd, comando `ventozy`
```

- El daemon corre como root (necesario para escribir en `/sys`), pero con
  `Nice=15` + `CPUSchedulingPolicy=idle`: ~0 % CPU sostenida, ~10–15 MB RAM.
- Configura el perfil del daemon editando `ExecStart` en
  `system/ventozy.service` o cambiándolo con la GUI.
- Estado: `systemctl status ventozy` · logs: `journalctl -u ventozy -f`.

## Botón de gráficos (integrada ↔ dedicada), como G-Helper

| Botón | Qué hace |
|---|---|
| 🖥 Gráficos integrados | runtime PM del kernel: la GPU NVIDIA se apaga al no usarse, ahorro máximo y reversible |
| 🎮 Gráficos dedicados | `power/control = on`: la GPU queda siempre lista (juegos/render) |

Cambios de Optimus a nivel bootloader (Optimus hard-off) requieren
supergfxctl. Ventozy usa únicamente sysfs estándar (`power/control`),
cero kernel hacks → funciona en la gran mayoría de portátiles con NVIDIA.
