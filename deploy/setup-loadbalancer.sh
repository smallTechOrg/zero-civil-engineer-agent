#!/usr/bin/env bash
# Attach the VM to the project's EXISTING Global External Application Load
# Balancer so it serves a custom domain over HTTPS. Does NOT create a new LB
# frontend (IP / proxy / forwarding rule) — it adds a backend for the VM, a
# host rule on the existing URL map, and a managed cert on the existing proxy.
# Idempotent — safe to re-run. See deploy/DOMAIN.md.
set -euo pipefail

# --- config (override via env) ------------------------------------------------
PROJECT="${PROJECT:-ai-agent-boilerplate0}"
ZONE="${ZONE:-us-central1-b}"
INSTANCE="${INSTANCE:-ir-civil-agent}"
DOMAIN="${DOMAIN:-zero-rail-agent.smalltech.in}"
APP_PORT="${APP_PORT:-8001}"

# EXISTING shared load balancer (discovered in this project) — reused, not created
EXISTING_URL_MAP="${EXISTING_URL_MAP:-https-staging}"
EXISTING_HTTPS_PROXY="${EXISTING_HTTPS_PROXY:-https-staging-target-proxy}"
EXISTING_FORWARDING_RULE="${EXISTING_FORWARDING_RULE:-staging-lb}"

# NEW backend resources for the VM (safe to create — not part of the shared LB)
HC_NAME=ir-agent-hc
IG_NAME=ir-agent-ig
BE_NAME=ir-agent-backend
CERT_NAME=ir-agent-cert
PM_NAME=ir-agent-matcher

g() { gcloud --project "$PROJECT" "$@"; }
have() { g "$@" --format="value(name)" >/dev/null 2>&1; }

echo "==> 1/6 Health check ($HC_NAME → /health:$APP_PORT)"
have compute health-checks describe "$HC_NAME" --global \
  || g compute health-checks create http "$HC_NAME" --global \
       --port "$APP_PORT" --request-path /health

echo "==> 2/6 Unmanaged instance group ($IG_NAME) + VM + named port"
have compute instance-groups unmanaged describe "$IG_NAME" --zone "$ZONE" \
  || g compute instance-groups unmanaged create "$IG_NAME" --zone "$ZONE"
g compute instance-groups unmanaged list-instances "$IG_NAME" --zone "$ZONE" \
    --format='value(instance)' 2>/dev/null | grep -q "/$INSTANCE\$" \
  || g compute instance-groups unmanaged add-instances "$IG_NAME" \
       --zone "$ZONE" --instances "$INSTANCE"
g compute instance-groups unmanaged set-named-ports "$IG_NAME" \
  --zone "$ZONE" --named-ports "http:$APP_PORT"

echo "==> 3/6 Backend service ($BE_NAME, EXTERNAL_MANAGED — matches the shared LB)"
have compute backend-services describe "$BE_NAME" --global \
  || g compute backend-services create "$BE_NAME" --global \
       --protocol HTTP --port-name http \
       --health-checks "$HC_NAME" \
       --load-balancing-scheme EXTERNAL_MANAGED
g compute backend-services list-backends "$BE_NAME" --global \
    --format='value(group)' 2>/dev/null | grep -q "/$IG_NAME\$" \
  || g compute backend-services add-backend "$BE_NAME" --global \
       --instance-group "$IG_NAME" --instance-group-zone "$ZONE"

echo "==> 4/6 Host rule on EXISTING url map ($EXISTING_URL_MAP): $DOMAIN → $BE_NAME"
if g compute url-maps describe "$EXISTING_URL_MAP" --global \
     --format='value(hostRules[].hosts)' 2>/dev/null | grep -q "$DOMAIN"; then
  echo "    host rule for $DOMAIN already present — skipping"
else
  g compute url-maps add-path-matcher "$EXISTING_URL_MAP" --global \
    --path-matcher-name "$PM_NAME" \
    --default-service "$BE_NAME" \
    --new-hosts "$DOMAIN"
fi

echo "==> 5/6 Managed cert ($CERT_NAME) + append to EXISTING proxy ($EXISTING_HTTPS_PROXY)"
have compute ssl-certificates describe "$CERT_NAME" --global \
  || g compute ssl-certificates create "$CERT_NAME" --global --domains "$DOMAIN"
CURRENT_CERTS="$(g compute target-https-proxies describe "$EXISTING_HTTPS_PROXY" --global \
  --format='value(sslCertificates.map().basename().list())')"
if echo "$CURRENT_CERTS" | grep -q "$CERT_NAME"; then
  echo "    $CERT_NAME already attached — skipping"
else
  g compute target-https-proxies update "$EXISTING_HTTPS_PROXY" --global \
    --ssl-certificates "${CURRENT_CERTS},${CERT_NAME}"
fi

echo "==> 6/6 Done."
LB_IP="$(g compute forwarding-rules describe "$EXISTING_FORWARDING_RULE" --global \
  --format='value(IPAddress)')"
echo ""
echo "  Existing load balancer IP:  $LB_IP  (shared — do not change)"
echo ""
echo "  NEXT: create this DNS record at your DNS provider for smalltech.in:"
echo "      Type=A   Name=zero-rail-agent   Value=$LB_IP   TTL=300"
echo ""
echo "  Then watch the managed cert (ACTIVE once DNS resolves; 10-60 min):"
echo "      gcloud compute ssl-certificates describe $CERT_NAME --global \\"
echo "        --project $PROJECT --format='value(managed.status)'"
echo ""
echo "  When ACTIVE:  https://$DOMAIN  →  the app (root redirects to /app/)."
