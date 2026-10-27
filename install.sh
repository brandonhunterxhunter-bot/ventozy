#!/usr/bin/env bash
# Instalador de Ventozy para Linux — registro, arranque automático, mínimo consumo.
# Uso:  sudo bash install.sh
set -e

SRC="$(cd "$(dirname "$0")" && pwd)"
DST=/opt/ventozy
SVC=/etc/systemd/system/ventozy.service

# ---------- 1. código en /opt ----------
mkdir -p "$DST"
cp -r "$SRC"/ventozy "$SRC"/configs "$SRC"/system "$SRC"/assets \
      "$SRC"/run.py "$SRC"/README.md "$DST"/
chmod -R a+rX "$DST"

# ---------- 2. dependencias ----------
command -v python3 >/dev/null || { echo "Falta python3"; exit 1; }
python3 -c "import tkinter" 2>/dev/null || \
    apt-get install -y python3-tk 2>/dev/null || \
    pacman -S --noconfirm python tk 2>/dev/null || true

# ---------- 3. módulos del kernel recomendados ----------
modprobe k10temp 2>/dev/null || true
modprobe asus-nb-wmi 2>/dev/null || true
echo "k10temp" > /etc/modules-load.d/ventozy.conf 2>/dev/null || true
echo "asus-nb-wmi" >> /etc/modules-load.d/ventozy.conf 2>/dev/null || true

# ---------- 4. servicio systemd (arranque automático, consumo mínimo) ----------
cp "$SRC/system/ventozy.service" "$SVC"
systemctl daemon-reload
systemctl enable --now ventozy

# ---------- 3b. servicio de hotkeys (Fn+F5 modo fans, Fn+↑/↓ teclado) ----------
if [ -f "$SRC/system/ventozy-hotkeys.service" ]; then
    cp "$SRC/system/ventozy-hotkeys.service" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable ventozy-hotkeys 2>/dev/null && systemctl start ventozy-hotkeys || true
fi
# dependencias de hotkeys (evdev) y notifications (notify-send ya viene)
python3 -c "import evdev" 2>/dev/null || \
    apt-get install -y python3-evdev 2>/dev/null || \
    pacman -S --noconfirm python-evdev 2>/dev/null || true
# tray (opcional; Mint lo trae de serie)
command -v notify-send >/dev/null || apt-get install -y libnotify-bin 2>/dev/null || true
command -v python3 && python3 -c "import gi" 2>/dev/null || \
    apt-get install -y gir1.2-appindicator3-0.1 2>/dev/null || true

# ---------- 5. icono de menú + lanzadores ----------
mkdir -p /usr/share/icons/hicolor/128x128/apps
python3 "$DST/assets/make_icon.py" /usr/share/icons/hicolor/128x128/apps/ventozy-icon.png \
    || python3 "$SRC/assets/make_icon.py" /usr/share/icons/hicolor/128x128/apps/ventozy-icon.png \
    || true   # el icono es cosmético: no aborta la instalación
gtk-update-icon-cache -f /usr/share/icons/hicolor 2>/dev/null || true

cat > /usr/share/applications/ventozy.desktop <<EOF
[Desktop Entry]
Name=Ventozy
Comment=Control de ventiladores y GPU (estilo G-Helper)
Exec=/usr/local/bin/ventozy
Icon=/usr/share/icons/hicolor/128x128/apps/ventozy-icon.png
Type=Application
Categories=Utility;System;
StartupNotify=true
EOF

# ---------- 6. ejecutables en PATH ----------
# Wrapper ELEVADO (root, 755) al que apunta la política polkit.
# pkexec autoriza según exec.path de la política: debe ser este binario,
# no /usr/bin/env ni python3 genérico (regresión corregida).
# - HOME sale del PKEXEC_UID (persistencia en ~/.config/ventozy del usuario)
# - DISPLAY/XAUTHORITY llegan como argumentos --venv-* (pkexec borra el env)
cat > "$DST/ventozy-launch" <<'EOF'
#!/bin/bash
venv_display=""; venv_xauth=""; rest=()
while [ $# -gt 0 ]; do
    case "$1" in
        --venv-display) venv_display="$2"; shift 2 ;;
        --venv-xauth)   venv_xauth="$2";   shift 2 ;;
        *)              rest+=("$1");      shift ;;
    esac
done
if [ -n "${PKEXEC_UID:-}" ]; then
    export HOME="$(getent passwd "$PKEXEC_UID" | cut -d: -f6)"
fi
export DISPLAY="${venv_display:-${DISPLAY:-:0}}"
export XAUTHORITY="${venv_xauth:-${XAUTHORITY:-$HOME/.Xauthority}}"
exec /usr/bin/python3 /opt/ventozy/run.py "${rest[@]}"
EOF
chmod 755 "$DST/ventozy-launch"

# política pkexec que APLICA de verdad al wrapper (exec.path exacto).
# auth_admin_keep: contraseña la primera vez, recordada 5 min (UAC).
cat > /usr/share/polkit-1/actions/com.ventozy.policy <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE policyconfig PUBLIC "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN"
 "http://www.freedesktop.org/software/polkit/policykit-1/policyconfig.dtd">
<policyconfig>
 <action id="com.ventozy.modify">
  <description>Control de ventiladores/GPU/teclado de Ventozy</description>
  <message>Se necesita permiso para controlar el hardware</message>
  <annotate key="org.freedesktop.policykit.exec.path">/opt/ventozy/ventozy-launch</annotate>
  <defaults>
   <allow_any>auth_admin_keep</allow_any>
   <allow_inactive>auth_admin_keep</allow_inactive>
   <allow_active>auth_admin_keep</allow_active>
  </defaults>
 </action>
</policyconfig>
EOF
# `ventozy` → GUI con icono y botones (permisos via pkexec → wrapper, como
# G-Helper). El usuario pasa DISPLAY/XAUTHORITY como args del wrapper; el
# wrapper (root) fija HOME del usuario desde PKEXEC_UID.
cat > /usr/local/bin/ventozy <<EOF
#!/bin/bash
if [ "\$(id -u)" -eq 0 ]; then
    exec python3 $DST/run.py "\$@"
fi
exec pkexec $DST/ventozy-launch \\
    --venv-display "\${DISPLAY:-:0}" \\
    --venv-xauth "\${XAUTHORITY:-\$HOME/.Xauthority}" \\
    "\$@"
EOF
chmod +x /usr/local/bin/ventozy
# `ventozy-gui` → GUI como USUARIO normal, sin pkexec ni contraseña
# (lecturas de estado funcionan; las escrituras elevan con `ventozy`).
cat > /usr/local/bin/ventozy-gui <<EOF
#!/bin/bash
exec python3 $DST/run.py "\$@"
EOF
chmod +x /usr/local/bin/ventozy-gui
