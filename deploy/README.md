# CI/CD — deploy to the GCP VM

This directory + `.github/workflows/` wire up:

| Workflow | Trigger | What it does |
|---|---|---|
| `.github/workflows/ci.yml` | push to `main`/`cicd/**`, PRs to `main` | Frontend `pnpm build` + deterministic backend `pytest tests/unit` (no Gemini key → real-LLM tests auto-skip) + `alembic upgrade` migration smoke |
| `.github/workflows/ci-full.yml` | nightly 03:00 UTC + manual | The **full** suite including real-Gemini integration tests |
| `.github/workflows/deploy.yml` | push to `main` + manual | Build frontend → bundle → ship to VM → write `.env` → `uv sync` + migrate → restart `ir-agent` service |

Target VM: **`ir-civil-agent`**, zone `us-central1-b`, project `ai-agent-boilerplate0` (e2-small, 2 GB / 20 GB).

---

## One-time setup

### 1. Create a deploy service account + key (on your machine, `gcloud` authed)

```bash
PROJECT=ai-agent-boilerplate0
gcloud iam service-accounts create ir-agent-deployer \
  --display-name="IR agent CI/CD deployer" --project "$PROJECT"

SA="ir-agent-deployer@${PROJECT}.iam.gserviceaccount.com"

# Roles: SSH/SCP + manage the instance, and act as the VM's own service account.
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${SA}" --role="roles/compute.instanceAdmin.v1"
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${SA}" --role="roles/iam.serviceAccountUser"
# If the VM has OS Login enabled, also grant sudo-capable OS Login:
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${SA}" --role="roles/compute.osAdminLogin"

# Download the JSON key (paste its CONTENTS into the GCP_SA_KEY secret below).
gcloud iam service-accounts keys create key.json --iam-account "$SA"
```

### 2. Add GitHub secrets + variables

Repo → Settings → Secrets and variables → Actions.

**Secrets** (`gh secret set NAME`):

| Secret | Value |
|---|---|
| `GCP_SA_KEY` | full contents of `key.json` from step 1 |
| `AGENT_GEMINI_API_KEY` | your Google AI Studio key (used to write the VM `.env` and to run `ci-full`) |

**Variables** (`gh variable set NAME`):

| Variable | Value |
|---|---|
| `GCP_PROJECT` | `ai-agent-boilerplate0` |
| `GCP_ZONE` | `us-central1-b` |
| `GCP_INSTANCE` | `ir-civil-agent` |

CLI shortcut:

```bash
gh secret set GCP_SA_KEY < key.json
gh secret set AGENT_GEMINI_API_KEY --body "YOUR_GEMINI_KEY"
gh variable set GCP_PROJECT --body "ai-agent-boilerplate0"
gh variable set GCP_ZONE   --body "us-central1-b"
gh variable set GCP_INSTANCE --body "ir-civil-agent"
```

> ⚠️ `key.json` is a credential — delete it after uploading (`rm key.json`). Never commit it.

### 3. Open the app firewall port (once)

```bash
gcloud compute firewall-rules create allow-ir-civil-agent-8001 \
  --allow tcp:8001 --project ai-agent-boilerplate0 \
  --description "IR agent HTTP"
```

### 4. Bootstrap the VM (once)

```bash
gcloud compute scp deploy/bootstrap.sh ir-civil-agent:~ \
  --zone us-central1-b --project ai-agent-boilerplate0
gcloud compute ssh ir-civil-agent \
  --zone us-central1-b --project ai-agent-boilerplate0 \
  --command 'sudo bash bootstrap.sh'
```

This adds 2 GB swap, installs system libs + `uv`, creates the `iragent` service
user and `/opt/ir-agent`, and installs (enables, does not start) the
`ir-agent` systemd unit.

---

## Deploy

Any push to `main` (typically merging your PR) runs `deploy.yml`. To deploy
by hand: Actions → **Deploy to VM** → Run workflow.

Once green, the app is live at **`http://<EXTERNAL_IP>:8001/app/`**
(`gcloud compute instances list` for the IP).

## Operate (on the VM)

```bash
sudo systemctl status ir-agent      # health
sudo journalctl -u ir-agent -f      # live logs
sudo systemctl restart ir-agent     # manual restart
```

## Notes / gotchas

- **HTTP only** — the app is served on `:8001` over plain HTTP against the VM's
  IP (fine for a same-origin demo). No TLS/domain wired. Don't put the Gemini
  key anywhere client-facing.
- **First deploy is slow** — `uv sync` pulls OpenCASCADE (`build123d`) wheels
  (~1 GB). Later deploys reuse the cached venv.
- **SSH auth** — if `gcloud compute ssh` from the runner can't reach port 22,
  add `--tunnel-through-iap` to the scp/ssh steps in `deploy.yml` and grant the
  SA `roles/iap.tunnelResourceAccessor`.
- **Teardown after the demo** — `gcloud compute instances delete ir-civil-agent
  --zone us-central1-b` to stop billing.
