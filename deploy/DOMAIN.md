# Custom domain + HTTPS (existing load balancer)

Serve the app at **https://zero-rail-agent.smalltech.in** instead of
`http://34.136.42.41:8001/app/`, by attaching the VM to the project's
**existing** Global External Application Load Balancer (shared IP
`34.117.112.63`, proxy `https-staging-target-proxy`, url map `https-staging` —
which already fronts other `*.smalltech.in` subdomains).

We do **not** create a new LB frontend. We add, additively:

```
 existing LB (34.117.112.63, :443)
   proxy https-staging-target-proxy  ── SNI certs: api.smalltech.in, …, + ir-agent-cert (new)
   url map https-staging
     ├─ api.smalltech.in            → (existing backends)
     ├─ api-staging.smalltech.in    → (existing backends)
     └─ zero-rail-agent.smalltech.in → ir-agent-backend (NEW) → ir-agent-ig → VM :8001
 app root "/"  ──307──▶ /app/   (handled in the FastAPI app)
```

Everything stays **single-origin** (the app calls `/api/...` on the same host),
so no CORS is needed.

---

## One-time setup

### 1. Attach the VM to the existing LB

```bash
bash deploy/setup-loadbalancer.sh
```

Idempotent. It creates only VM-specific backend resources (health check
`/health:8001`, instance group `ir-agent-ig` with named port `http:8001`,
backend service `ir-agent-backend`), then **additively**:
- adds a host rule `zero-rail-agent.smalltech.in → ir-agent-backend` to the
  existing url map (existing host rules untouched), and
- creates a managed cert `ir-agent-cert` and **appends** it to the existing
  HTTPS proxy's cert list (existing certs preserved).

It prints the existing LB IP.

### 2. Point DNS at the load balancer

At whoever hosts `smalltech.in` DNS, add:

| Type | Name | Value | TTL |
|---|---|---|---|
| `A` | `zero-rail-agent` | `34.117.112.63` *(the existing LB IP)* | 300 |

### 3. Wait for the managed certificate

The cert only provisions **after** DNS resolves to the LB IP. Typically 10-60 min.

```bash
gcloud compute ssl-certificates describe ir-agent-cert --global \
  --project ai-agent-boilerplate0 --format='value(managed.status)'
# PROVISIONING → ACTIVE
```

When `ACTIVE`: **https://zero-rail-agent.smalltech.in** serves the app (root
redirects to `/app/`). Until then, `http://34.136.42.41:8001/app/` still works.

---

## Operate

```bash
# Cert status
gcloud compute ssl-certificates describe ir-agent-cert --global --format='value(managed.status,managed.domainStatus)'

# Is the VM healthy behind the LB?
gcloud compute backend-services get-health ir-agent-backend --global
```

## Teardown (remove ONLY what we added — never the shared LB)

```bash
P=ai-agent-boilerplate0
# 1. Detach our cert from the shared proxy (keep the others!). Re-list current
#    certs, drop ir-agent-cert, and re-set:
gcloud compute target-https-proxies update https-staging-target-proxy --global --project $P \
  --ssl-certificates staging-api-cert,https-smalltech,api-staging
# 2. Remove our host rule + path matcher from the shared url map:
gcloud compute url-maps remove-host-rule https-staging --global --project $P --host zero-rail-agent.smalltech.in
gcloud compute url-maps remove-path-matcher https-staging --global --project $P --path-matcher-name ir-agent-matcher
# 3. Delete our backend resources:
gcloud compute ssl-certificates delete ir-agent-cert --global --project $P -q
gcloud compute backend-services delete ir-agent-backend --global --project $P -q
gcloud compute instance-groups unmanaged delete ir-agent-ig --zone us-central1-b --project $P -q
gcloud compute health-checks delete ir-agent-hc --global --project $P -q
```

> Do **not** delete `staging-lb`, `https-staging-target-proxy`, or `https-staging`
> — they are shared with other `smalltech.in` services.

---

## The `AGENT_LLM_MODEL` variable

The Gemini model is set by the **`AGENT_LLM_MODEL`** GitHub repository variable,
written into the VM's `.env` on each deploy (`deploy.yml`). Change the model
without touching code:

```bash
gh variable set AGENT_LLM_MODEL --body "gemini-2.5-flash-lite"
```

Then re-deploy (push to `main`, or run the **Deploy to VM** workflow). If the
variable is unset, deploy falls back to `gemini-2.5-flash-lite`. The app reads
it via `settings.llm_model` (`src/llm/client.py`), so no code change is needed
to switch models.
