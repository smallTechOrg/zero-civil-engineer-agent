#!/usr/bin/env bash
# Runs ON THE VM (as root, via `sudo bash /tmp/deploy-remote.sh`), invoked by
# .github/workflows/deploy.yml. Expects /tmp/bundle.tar.gz, /tmp/deploy.env, and
# a bootstrapped host (see bootstrap.sh: iragent user, /opt/ir-agent, uv, unit).
set -euo pipefail

APP_DIR=/opt/ir-agent
SERVICE=ir-agent
SERVICE_USER=iragent

echo "==> Unpacking bundle into ${APP_DIR}"
mkdir -p "${APP_DIR}"
tar xzf /tmp/bundle.tar.gz -C "${APP_DIR}"

echo "==> Installing .env (0600, owned by ${SERVICE_USER})"
install -o "${SERVICE_USER}" -g "${SERVICE_USER}" -m 600 /tmp/deploy.env "${APP_DIR}/.env"

echo "==> Fixing ownership"
mkdir -p "${APP_DIR}/data/artifacts"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}"

echo "==> uv sync (prod deps) + alembic upgrade"
sudo -u "${SERVICE_USER}" --set-home env PATH=/usr/local/bin:/usr/bin:/bin \
  bash -lc "cd ${APP_DIR} && uv sync --no-dev && uv run alembic upgrade head"

echo "==> Restarting ${SERVICE}"
systemctl restart "${SERVICE}"
sleep 2
systemctl --no-pager --lines=10 status "${SERVICE}" || true

echo "==> Cleaning up /tmp"
rm -f /tmp/bundle.tar.gz /tmp/deploy.env /tmp/deploy-remote.sh

echo "==> Deploy complete."
