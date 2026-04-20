#!/usr/bin/env bash
# Instalación en contenedor LXC Debian/Ubuntu (ej. plantilla debian-12 / ubuntu-22.04).
# Ejecutar como root dentro del CT: bash install-lxc-debian.sh
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/mant_v2}"
APP_USER="${APP_USER:-mant}"
APP_GROUP="${APP_GROUP:-mant}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Ejecuta este script como root dentro del LXC."
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  python3 python3-venv python3-pip ca-certificates

if ! id -u "${APP_USER}" >/dev/null 2>&1; then
  useradd --system --home "${INSTALL_DIR}" --shell /usr/sbin/nologin "${APP_USER}"
fi

mkdir -p "${INSTALL_DIR}"
chown "${APP_USER}:${APP_GROUP}" "${INSTALL_DIR}"

echo ""
echo "Copia el contenido del proyecto (carpeta con 'web/', sin incluir .venv) a: ${INSTALL_DIR}"
echo "  Ejemplo desde tu PC: scp -r mant_v2/* root@CT_IP:${INSTALL_DIR}/"
echo "Luego crea ${INSTALL_DIR}/config.json y ${INSTALL_DIR}/.env (ver .env.example)."
echo ""
read -r -p "¿Ya está el código en ${INSTALL_DIR}? [s/N] " ok
if [[ ! "${ok}" =~ ^[sSyY]$ ]]; then
  echo "Copia los archivos y vuelve a ejecutar este script."
  exit 1
fi

if [[ ! -f "${INSTALL_DIR}/web/main.py" ]]; then
  echo "No encuentro ${INSTALL_DIR}/web/main.py — revisa la ruta del proyecto."
  exit 1
fi

sudo -u "${APP_USER}" python3 -m venv "${INSTALL_DIR}/.venv"
sudo -u "${APP_USER}" "${INSTALL_DIR}/.venv/bin/pip" install --upgrade pip
sudo -u "${APP_USER}" "${INSTALL_DIR}/.venv/bin/pip" install -r "${INSTALL_DIR}/web/requirements.txt"

chown -R "${APP_USER}:${APP_GROUP}" "${INSTALL_DIR}"

install -m 0644 "${INSTALL_DIR}/deploy/mant-v2.service" /etc/systemd/system/mant-v2.service
systemctl daemon-reload
systemctl enable mant-v2.service
systemctl restart mant-v2.service
systemctl --no-pager status mant-v2.service

echo ""
echo "Servicio activo. Prueba: http://IP_DEL_CT:8000"
echo "Logs: journalctl -u mant-v2 -f"
