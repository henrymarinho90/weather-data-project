# Deploying the Weather ELT Pipeline on an OVH VPS with Coolify

Repository: https://github.com/henrymarinho90/weather-data-project (branch `main`)

This guide deploys the whole stack (Postgres, Airflow, dbt, Superset, the MCP servers, backups) on one VPS through Coolify's **Docker Compose** build pack. Only the Superset dashboard is published on the internet. Airflow, Postgres and the MCP servers stay private and are reached through an SSH tunnel.

> **Status:** the repository's CI runs the configuration this guide uses (the env block from `make coolify-env`, root user, auto-detected dbt path, fresh checkout) on every push. Two Coolify-specific details have not been confirmed on a real Coolify install yet: the **Preserve Repository During Deployment** setting (step 6) and whether Coolify renames containers (step 9). Check both on your first deploy.

---

## 1. Server requirements

| Item | Minimum |
|---|---|
| OS | Ubuntu 24.04 |
| RAM | 8 GB (the stack idles at about 3 GB, Coolify needs about 2 GB) |
| CPU | 4 vCPU |
| Disk | 80 GB (images take about 10 GB, plus data and backups) |
| Software | Coolify installed (official install script) |
| DNS | An A record, e.g. `superset.yourdomain.com`, pointing to the VPS IP |

## 2. Secure the server first

- Log in with SSH keys only (disable password login).
- In the OVH network firewall or `ufw`, allow only ports **22, 80 and 443**.
- Port 8000 (Coolify UI): keep it open only until Coolify has its own HTTPS domain, then close it.
- Every port the stack publishes is bound to `127.0.0.1`, so nothing else is reachable from outside, even though Docker bypasses `ufw` for published ports.

## 3. Generate the environment variables (on your laptop)

From a checkout of the repository:

```bash
make coolify-env > coolify.env
```

This prints every setting with freshly generated secrets, plus the values a Coolify deploy needs (`HOST_UID=0`, `HOST_GID=0`, empty `DBT_HOST_PATH` for auto-detection). Open `coolify.env` and set:

| Variable | Value |
|---|---|
| `DOCKER_GID` | Run on the **VPS**: `stat -c %g /var/run/docker.sock` |
| `SUPERSET_PUBLIC_URL` | `https://superset.yourdomain.com` |
| `WEATHERSTACK_API_KEY` and `USE_MOCK_API=false` | Only if you want live data (otherwise mock mode, no API calls) |
| `WEATHERSTACK_API_URL` | Leave empty (HTTPS). Only if your Weatherstack plan rejects HTTPS (error 105): `http://api.weatherstack.com/current`, which sends the key unencrypted |
| `ALERT_WEBHOOK_URL` | Optional: Slack or Discord incoming webhook for failure alerts |

Then:

1. Store the whole file in your password manager.
2. Delete `coolify.env` from your laptop.

> **Never change `SUPERSET_SECRET_KEY` or `AIRFLOW_FERNET_KEY` after the first deploy.** Superset and Airflow use them to encrypt stored passwords; a new key makes them unreadable (also in restored backups).

## 4. Create the resource in Coolify

1. Open your project and click **+ New → Public Repository**.
2. Repository URL: `https://github.com/henrymarinho90/weather-data-project`, branch `main`.
3. Build Pack: **Docker Compose**.
4. Docker Compose location: `/docker-compose.yaml`.
5. Continue.

## 5. Paste the environment variables

1. Open the resource's **Environment Variables**.
2. Switch to **Developer view**.
3. Paste the edited block and save.

## 6. Keep the repository files on the server

Turn on **Preserve Repository During Deployment**. The services bind-mount files from the repository (DAGs, scripts, Superset config, nginx config, backup scripts), so those files must exist on the server, not only inside the build.

*The setting's name and location may differ between Coolify versions.*

## 7. Publish only Superset

1. In the resource's service list, give the **superset** service the domain `https://superset.yourdomain.com:8088`. The `:8088` suffix tells Coolify's proxy which container port to use; Coolify issues the Let's Encrypt certificate.
2. Leave **every other service without a domain** (Airflow, Postgres, MCP servers, gateway).

## 8. Deploy

Click **Deploy**. The first deploy takes about 10–15 minutes: Airflow's image is 3 GB, and the Superset and MCP images are built on the server.

Check the deploy logs for:

- `db` reported as healthy.
- `superset_init` exited with code 0.
- In the Airflow log: `start.sh: DBT_HOST_PATH=/data/coolify/applications/<id>/dbt`.

## 9. First-time setup

SSH into the VPS and look up the container names (Coolify may rename them):

```bash
docker ps --format '{{.Names}}'
```

Then run, using the real names:

```bash
# Create the Superset connection, datasets, charts and dashboard
docker exec <superset_app> python /app/docker/superset_setup.py

# Optional: 30 days of synthetic history so the dashboard has data immediately
docker exec <airflow_container> python /opt/airflow/api-request/seed_test_data.py --days 30

# Turn on the twice-daily schedule (08:00 and 20:00 UTC)
docker exec <airflow_container> airflow dags unpause api-dbt-orchestrator

# Airflow admin password (generated on first start, kept on the airflow_logs volume across redeploys)
docker exec <airflow_container> cat /opt/airflow/logs/.auth/passwords.json
```

You can also run these from Coolify's **Terminal** tab for each service.

## 10. Check that it works

- [ ] `https://superset.yourdomain.com` loads with a valid certificate.
- [ ] Log in as `admin` with `SUPERSET_ADMIN_PASSWORD` from your env block.
- [ ] `https://superset.yourdomain.com/superset/dashboard/weather/` shows the Weather Dashboard.
- [ ] Through the tunnel (step 11), Airflow shows `api-dbt-orchestrator` unpaused, and a manual run turns green (ingest → dbt build → freshness check).
- [ ] After the first night: run `docker exec <db_backup> /opt/backup/verify.sh` and get `OK: row counts match the live database`.

## 11. Private access: SSH tunnel

Airflow, Postgres and the MCP servers have no public domain. Open a tunnel from your laptop:

```bash
ssh -N \
  -L 8081:127.0.0.1:8081 \
  -L 5434:127.0.0.1:5434 \
  -L 5008:127.0.0.1:5008 -L 5009:127.0.0.1:5009 -L 5010:127.0.0.1:5010 \
  -L 5011:127.0.0.1:5011 -L 5012:127.0.0.1:5012 \
  ubuntu@<vps-ip>
```

While it runs:

| On your laptop | Server service |
|---|---|
| http://localhost:8081 | Airflow |
| `localhost:5434` | Postgres (psql, DBeaver) |
| http://localhost:5008/mcp | Superset MCP |
| http://localhost:5009/mcp/ | Airflow MCP |
| http://localhost:5010/mcp | dbt MCP |
| http://localhost:5011/sse | Postgres MCP |
| http://localhost:5012/mcp | Docker MCP (off on servers: needs `COMPOSE_PROFILES=docker-mcp`, see `.env.example`) |

The repository's `.mcp.json` works unchanged with Claude Code while the tunnel is open.

## 12. Backups

The `db_backup` service dumps all three databases plus the roles every day at 02:00 UTC into `backups/` in the application folder, and keeps 7 days. That folder is on the **same disk** as the data, so also:

- Turn on OVH's automated VPS backup or snapshots.
- Copy `backups/` offsite every night, for example with `rclone` to OVH Object Storage, from a cron job on the VPS.
- Test a restore regularly with `verify.sh` (step 10).

## 13. Updates

1. Push to `main`.
2. Press **Redeploy** in Coolify, or enable its GitHub auto-deploy webhook.

Data lives in Docker volumes and survives redeploys. **Never regenerate or replace the env block**; edit individual values instead.

## 14. Troubleshooting

| Symptom | Fix |
|---|---|
| `permission denied` on `/var/run/docker.sock` (dbt task) | `DOCKER_GID` is wrong: re-run `stat -c %g /var/run/docker.sock` on the VPS |
| dbt task fails with `is not an absolute path` | Auto-detection failed: set `DBT_HOST_PATH=/data/coolify/applications/<id>/dbt` |
| `network ... not found` (dbt task) | Set `DOCKER_NETWORK` to the stack's network name (`docker network ls`) |
| Superset returns 502 | The domain is missing the `:8088` suffix |
| A service fails with "port is already allocated" | Another app on the VPS uses 8081, 8089, 5434 or 5008–5012: change `POSTGRES_HOST_PORT` or the port in `docker-compose.yaml` |
| A second copy of the stack won't start | Container names are fixed: one copy per server |
| Files missing inside containers (DAG not found, nginx config missing) | **Preserve Repository During Deployment** is off (step 6) |
| `check_source_freshness` fails | The newest observation is over 25 h old: the DAG was paused, or the API keeps returning a cached observation |

## 15. Security notes

- **Airflow must not be public.** It runs in development mode (`airflow standalone`) with a plaintext-password login, and it can control the server's Docker daemon (root-equivalent). Use the tunnel only.
- **Superset is the only public service.** The admin password is randomly generated: keep it in your password manager. Create separate non-admin accounts for anyone who only views the dashboard.
- **The MCP servers have no login.** Never give them a domain.
- **Secrets are in Coolify's environment variables** and in your password manager only. Nothing secret is in the repository.
