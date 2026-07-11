#!/usr/bin/env bash
# One-time VM setup for the IR Civil Engineer Agent. Run ONCE on a fresh VM as a
# sudo-capable user:
#
#   gcloud compute scp deploy/bootstrap.sh ir-civil-agent:~ \
#     --zone us-central1-b --project ai-agent-boilerplate0
#   gcloud compute ssh ir-civil-agent \
#     --zone us-central1-b --project ai-agent-boilerplate0 \
#     --command 'sudo bash bootstrap.sh'
#
# Idempotent: safe to re-run. It does NOT start the service — the first
# successful "Deploy to VM" GitHub Action ships the code and starts it.
set -euo pipefail

APP_DIR=/opt/ir-agent
SERVICE=ir-agent
SERVICE_USER=iragent

echo "==> 1/5 Swap (2 GB, idempotent)"
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "==> 2/5 System packages (git, python, OpenCASCADE/matplotlib libs)"
apt-get update
apt-get install -y git python3.11 python3.11-venv libgl1 libglu1-mesa ca-certificates curl

echo "==> 3/5 uv (system-wide at /usr/local/bin)"
if ! command -v /usr/local/bin/uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh \
    | env UV_INSTALL_DIR=/usr/local/bin INSTALLER_NO_MODIFY_PATH=1 sh
fi

echo "==> 4/5 Service user + app dir"
id -u "${SERVICE_USER}" >/dev/null 2>&1 \
  || useradd --system --create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
mkdir -p "${APP_DIR}/data/artifacts"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}"

echo "==> 5/5 systemd unit"
cat > "/etc/systemd/system/${SERVICE}.service" <<'UNIT'
[Unit]
Description=IR Civil Engineer Agent (FastAPI + LangGraph)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=iragent
Group=iragent
WorkingDirectory=/opt/ir-agent
ExecStart=/usr/local/bin/uv run python -m src
Restart=on-failure
RestartSec=5
Environment=PATH=/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable "${SERVICE}"

echo ""
echo "==> Bootstrap complete."
echo "    The service is enabled but NOT started (no code yet)."
echo "    Push to main (or run the 'Deploy to VM' workflow) to ship + start it."
echo "    App will serve at:  http://<EXTERNAL_IP>:8001/app/"
