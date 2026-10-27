#!/bin/bash
# ============================================================
#  build-deb.sh — genera ventozy_<versión>_all.deb (Linux Mint/Debian)
#  Uso:   bash packaging/build-deb.sh
#
#  El .deb instala:
#    - /opt/ventozy                                   (código + assets)
#    - /usr/bin/ventozy                               (ejecutable en PATH)
#    - /usr/share/applications/ventozy.desktop        (menú de apps)
#    - /usr/share/icons/hicolor/…/ventozy.svg|png     (icono nítido, vector)
#    - /lib/systemd/system/ventozy[.hotkeys].service  (autostart al boot)
#    - /usr/share/polkit-1/actions/com.ventozy.policy
#  postinst levanta los servicios; prerm los revierte (desinstalación limpia).
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION=$(grep -m1 '^Version:' "$ROOT/packaging/deb/control" | cut -d' ' -f2)
WORK=$(mktemp -d)
DEB="$WORK/DEBIAN"
trap 'rm -rf "$WORK"' EXIT

# ---------- árbol de instalación ----------
mkdir -p "$DEB" \
         "$WORK/opt/ventozy" \
         "$WORK/usr/bin" \
         "$WORK/usr/share/applications" \
         "$WORK/usr/share/icons/hicolor/scalable/apps" \
         "$WORK/usr/share/icons/hicolor/128x128/apps" \
         "$WORK/usr/share/polkit-1/actions" \
         "$WORK/lib/systemd/system"

# ---------- código ----------
cp -r "$ROOT/ventozy" "$WORK/opt/ventozy/"
cp "$ROOT/run.py" "$ROOT/README.md" "$WORK/opt/ventozy/"
mkdir -p "$WORK/opt/ventozy/assets"
cp "$ROOT/assets/make_icon.py" "$WORK/opt/ventozy/assets/" 2>/dev/null || true
cp "$ROOT/assets/ventozy-icon.png" "$WORK/opt/ventozy/assets/" 2>/dev/null || true
find "$WORK/opt/ventozy" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
chmod -R a+rX "$WORK/opt/ventozy"

# ---------- ejecutable ----------
cat > "$WORK/usr/bin/ventozy" <<'EOF'
#!/bin/bash
# como root ya (sudo/systemd): ejecuta directo
if [ "$(id -u)" -eq 0 ]; then
    exec python3 /opt/ventozy/run.py "$@"
fi
# usuario normal: eleva con pkexec; conserva HOME (persistencia de curvas
# en ~/.config/ventozy) y DISPLAY/XAUTHORITY (que Tk abra la ventana)
exec pkexec env \
    DISPLAY="${DISPLAY:-:0}" \
    XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}" \
    HOME="$HOME" \
    python3 /opt/ventozy/run.py "$@"
EOF
chmod 755 "$WORK/usr/bin/ventozy"

# ---------- iconos ----------
cp "$ROOT/assets/ventozy-logo.svg" \
   "$WORK/usr/share/icons/hicolor/scalable/apps/ventozy.svg"
(
  cd "$ROOT/assets" && python3 make_icon.py "$WORK/usr/share/icons/hicolor/128x128/apps/ventozy.png"
) 2>/dev/null || cp "$ROOT/assets/ventozy-icon.png" \
   "$WORK/usr/share/icons/hicolor/128x128/apps/ventozy.png"

# ---------- menú ----------
cat > "$WORK/usr/share/applications/ventozy.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Ventozy
GenericName=Control de ventiladores y GPU
Comment=Ventiladores, curvas, GPU, batería y teclado — estilo G-Helper en Linux
Exec=ventozy
Icon=ventozy
Categories=Utility;System;GTK;
Keywords=fan;ventiladores;gpu;temperatura;curva;
StartupNotify=true
Terminal=false
EOF

# ---------- servicios ----------
cp "$ROOT/system/ventozy.service" "$WORK/lib/systemd/system/"
cp "$ROOT/system/ventozy-hotkeys.service" "$WORK/lib/systemd/system/"

# ---------- polkit ----------
cat > "$WORK/usr/share/polkit-1/actions/com.ventozy.policy" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE policyconfig PUBLIC
 "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN"
 "http://www.freedesktop.org/software/polkit/policyconfig.dtd">
<policyconfig>
 <action id="com.ventozy.modify">
  <description>Controlar ventiladores/GPU/teclado con Ventozy</description>
  <message>Ventozy necesita permiso para controlar el hardware</message>
  <annotate key="org.freedesktop.policykit.exec.path">/usr/bin/python3</annotate>
  <annotate key="org.freedesktop.policykit.exec.argv1">/opt/ventozy/run.py</annotate>
  <defaults>
   <allow_any>auth_admin_keep</allow_any>
   <allow_inactive>auth_admin_keep</allow_inactive>
   <allow_active>auth_admin_keep</allow_active>
  </defaults>
 </action>
</policyconfig>
EOF

# ---------- hooks del paquete ----------
cp "$ROOT/packaging/deb/postinst" "$DEB/postinst"
chmod 755 "$DEB/postinst"
cp "$ROOT/packaging/deb/control" "$DEB/control"

cat > "$DEB/prerm" <<'EOF'
#!/bin/sh
set -e
if command -v systemctl >/dev/null; then
    systemctl stop ventozy-hotkeys.service 2>/dev/null || true
    systemctl stop ventozy.service 2>/dev/null || true
    systemctl disable ventozy-hotkeys.service 2>/dev/null || true
    systemctl disable ventozy.service 2>/dev/null || true
fi
exit 0
EOF
chmod 755 "$DEB/prerm"

cat > "$DEB/postrm" <<'EOF'
#!/bin/sh
if command -v systemctl >/dev/null; then
    systemctl daemon-reload || true
fi
exit 0
EOF
chmod 755 "$DEB/postrm"

# ---------- empaquetar ----------
OUT="$(pwd)/ventozy_${VERSION}_all.deb"
cd "$WORK"
dpkg-deb --root-owner-group --build "$WORK" "$OUT"

echo ""
echo "✅ Paquete generado: $OUT  ($(du -h "$OUT" | cut -f1))"
echo "   En Linux Mint:  sudo apt install ./ventozy_${VERSION}_all.deb"
echo "                   (o doble clic en el gestor de paquetes)"
echo "   Desinstalar:    sudo apt remove ventozy   (reversión completa)"
