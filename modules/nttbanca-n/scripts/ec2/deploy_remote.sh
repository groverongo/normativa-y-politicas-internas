#!/usr/bin/env bash
# Se ejecuta DENTRO de la EC2 (lo lanza scripts/aws_deploy_ec2.sh vía SSM, como root).
# Instala o actualiza la API y la deja corriendo como servicio systemd en el puerto 80.
#
# Uso: deploy_remote.sh <url-del-paquete> <región> <parámetro-de-configuración>

set -euo pipefail

PKG_URL="$1"
REGION="$2"
ENV_PARAM="$3"

APP_USER=nttbanca
BASE=/opt/nttbanca
RELEASE="$BASE/releases/$(date +%Y%m%d%H%M%S)"

export DEBIAN_FRONTEND=noninteractive

echo "==> Esperando a que termine el arranque de la instancia"
cloud-init status --wait >/dev/null 2>&1 || true

echo "==> Paquetes del sistema"
# Salida silenciada: SSM solo guarda 24.000 caracteres y apt los llenaría.
if ! dpkg -s python3-venv >/dev/null 2>&1; then
  apt-get -o DPkg::Lock::Timeout=600 update -qq >/dev/null
  apt-get -o DPkg::Lock::Timeout=600 install -y -qq python3-venv python3-pip >/dev/null
fi
python3 --version

echo "==> Usuario de servicio"
id "$APP_USER" >/dev/null 2>&1 || useradd --system --home-dir "$BASE" --shell /usr/sbin/nologin "$APP_USER"

echo "==> Código nuevo en $RELEASE"
mkdir -p "$RELEASE"
curl -fsSL "$PKG_URL" | tar -xz -C "$RELEASE"

echo "==> Dependencias"
[ -d "$BASE/venv" ] || python3 -m venv "$BASE/venv"
"$BASE/venv/bin/pip" install -q --upgrade pip
"$BASE/venv/bin/pip" install -q -r "$RELEASE/requirements.txt"

echo "==> Configuración desde Parameter Store ($ENV_PARAM)"
(
  umask 077
  "$BASE/venv/bin/python" - "$REGION" "$ENV_PARAM" > "$RELEASE/.env" <<'PY'
import sys

import boto3

region, name = sys.argv[1], sys.argv[2]
param = boto3.client("ssm", region_name=region).get_parameter(Name=name, WithDecryption=True)
print(param["Parameter"]["Value"])
PY
)
chown -R "$APP_USER:$APP_USER" "$RELEASE"

echo "==> Migraciones de base de datos"
# Antes de cambiar de release: si fallan, la versión anterior sigue atendiendo.
(cd "$RELEASE" && sudo -u "$APP_USER" "$BASE/venv/bin/python" -m app.db.migrate)

ln -sfn "$RELEASE" "$BASE/current"

echo "==> Servicio systemd"
cat > /etc/systemd/system/nttbanca.service <<'UNIT'
[Unit]
Description=NttBanca API (FastAPI)
After=network-online.target
Wants=network-online.target

[Service]
User=nttbanca
Group=nttbanca
WorkingDirectory=/opt/nttbanca/current
ExecStart=/opt/nttbanca/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 80 --proxy-headers
# Permite escuchar en el puerto 80 sin ser root
AmbientCapabilities=CAP_NET_BIND_SERVICE
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable nttbanca >/dev/null 2>&1
systemctl restart nttbanca

echo "==> Verificación local"
for _ in $(seq 1 30); do
  curl -fsS -o /dev/null http://127.0.0.1/health && break
  sleep 1
done
if ! curl -fsS http://127.0.0.1/health; then
  journalctl -u nttbanca -n 60 --no-pager
  exit 1
fi
echo
echo "/health/db -> $(curl -sS http://127.0.0.1/health/db)"
echo "/health/s3 -> $(curl -sS http://127.0.0.1/health/s3)"

# Conserva solo los últimos 3 releases
ls -1dt "$BASE"/releases/* | tail -n +4 | xargs -r rm -rf

echo "==> Despliegue terminado"
