# Lightsail production backend for 노래 실력 진단받기 (vocalfb).
#
# This directory is local package preparation only. It does not deploy.
# Do not scp, connect to AWS, or write real secrets from this README.

## Architecture

HTTPS terminator / reverse proxy (operator-managed, e.g. Lightsail load balancer or
host Nginx) → backend `127.0.0.1:8000` → FastAPI (Uvicorn workers=1) → Docker network PostgreSQL

- `BACKEND_REPLICAS=1`
- `ARTIFACT_STORAGE_MODE=LOCAL_PERSISTENT`
- `MULTI_INSTANCE_UNSAFE`
- Backend bind: loopback only (typical)
- Postgres: no public port

Entrypoint:

```text
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

The application uses `VAGENT_ENV` (not `APP_ENV`).

## A. Windows packaging

From `C:\VocalAgent` in PowerShell (packages the **current working tree**, including uncommitted files):

```powershell
.\scripts\package_lightsail_release.ps1
```

Outputs under `qa_output/production_release_v1/lightsail/`:

- `vocalfb-lightsail-release.tar.gz`
- `vocalfb-lightsail-release.sha256`
- `MANIFEST.txt`
- `DEPLOY_SOURCE_STATE.txt`

## B. Transfer tar.gz to Lightsail

Copy only the archive (not this whole repo). Example once SSH is available:

```text
scp vocalfb-lightsail-release.tar.gz ubuntu@LIGHTSAIL_HOST:/tmp/
```

Do not copy `.env`, certs, or keys in the same step.

## C. Extract into `/opt/vocalfb/app`

On the server:

```bash
sudo mkdir -p /opt/vocalfb/app
sudo tar -xzf /tmp/vocalfb-lightsail-release.tar.gz -C /opt/vocalfb/app
sudo chown -R root:root /opt/vocalfb/app
```

Expected layout includes `backend/`, `audio_analyzer/`, `alembic.ini`, `deploy/lightsail/`, `docs/legal/`.

## D. Create `/etc/vocalfb/vocalfb.env` manually

```bash
sudo cp /opt/vocalfb/app/.env.production.example /etc/vocalfb/vocalfb.env
sudo chmod 600 /etc/vocalfb/vocalfb.env
sudo nano /etc/vocalfb/vocalfb.env
```

Fill real values on the server only. `DATABASE_URL` must use Docker service hostname `postgres`:

```text
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@postgres:5432/vocalfb
RUNTIME_DIR=/var/lib/vocalfb/runtime
VAGENT_ENV=production
```

Keep `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` in sync with `DATABASE_URL`.

## E. Place mTLS cert/key manually

Required only when `PAYMENTS_ENABLED` or `TOSS_LOGIN_ENABLED` is true.

```bash
sudo mkdir -p /etc/vocalfb/secrets
sudo chmod 750 /etc/vocalfb/secrets
# copy cert/key from a private channel, never from git
sudo chmod 640 /etc/vocalfb/secrets/toss-client.crt /etc/vocalfb/secrets/toss-client.key
```

Set `TOSS_MTLS_CERT_PATH` and `TOSS_MTLS_KEY_PATH` to those paths.

## F. Permissions

```bash
sudo mkdir -p /var/lib/vocalfb/runtime /var/lib/vocalfb/postgres /etc/vocalfb/secrets
sudo chown -R 1000:1000 /var/lib/vocalfb/runtime
# postgres volume is owned by the postgres image user after first start — do not chown it to 1000
sudo chmod 750 /etc/vocalfb/secrets
sudo chmod 600 /etc/vocalfb/vocalfb.env
sudo chmod +x /opt/vocalfb/app/deploy/lightsail/deploy.sh /opt/vocalfb/app/deploy/lightsail/check_capacity.sh
```

## G. Run deploy.sh

```bash
cd /opt/vocalfb/app
sudo ./deploy/lightsail/deploy.sh
```

Sequence: preflight → build → Postgres health → `alembic upgrade head` → backend → `/health` → `/ready`.

If migration fails, the script exits and does **not** report a successful backend deploy. There is no automatic downgrade.

## H. Health / readiness

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
```

Also:

```text
GET /legal/terms
GET /legal/privacy
GET /legal/privacy-consent
```

## I. Restart test

```bash
cd /opt/vocalfb/app
docker compose --env-file /etc/vocalfb/vocalfb.env -f deploy/lightsail/docker-compose.production.yml restart
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
```

## J. Reboot persistence test

```bash
sudo reboot
```

After SSH is back:

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
# confirm /var/lib/vocalfb/postgres and /var/lib/vocalfb/runtime still have data
```

## K. Rollback application package

Keep the previous tar.gz. Stop backend, extract the previous archive into `/opt/vocalfb/app`, run `deploy.sh` again.

Do **not** run `alembic downgrade`. Payment/entitlement tables must remain readable.

## L. Nginx / HTTPS (live)

Current production (confirmed):

- Region: `ap-northeast-2` / AZ `ap-northeast-2a`
- Public origin: `https://54.116.187.5`
- Nginx `443` → `127.0.0.1:8000`
- Postgres: no public port; volume `/var/lib/vocalfb/postgres`
- Runtime: `/var/lib/vocalfb/runtime` (local persistent)
- Certbot: short-lived Let's Encrypt IP certificate; auto-renew enabled
  (`snap.certbot.renew.timer`); deploy hook reloads nginx
- `PUBLIC_BACKEND_BASE_URL=https://54.116.187.5`
- Miniapp `VITE_API_BASE` must match that origin

Optional later: add a branded hostname and re-issue certificates for that name.
Do not configure SSL against a placeholder hostname.

## Backup note

Lightsail Automatic snapshots are currently **OFF**. Enabling snapshots or
`pg_dump` is a separate ops task — not part of legal-doc updates.

## Capacity

```bash
sudo ./deploy/lightsail/check_capacity.sh
```

## Prices

Production display amounts come from Apps in Toss IAP. Do not hardcode production UI prices. Development mock catalog is ₩990 / ₩1,980 / ₩990.
