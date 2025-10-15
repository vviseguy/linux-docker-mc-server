# Linux Docker Minecraft Server with Web Control

This project lets you run a Minecraft server in Docker on a Linux machine and control it (start/restart/stop-if-empty) via a minimal FastAPI service. You can call the API from a static site (e.g., GitHub Pages).

- Minecraft container: itzg/minecraft-server
- Control API: FastAPI + Docker SDK + RCON (checks if players are online before stopping)
- Auth: simple bearer token
- Config: `.env` file
 - Optional Git sync: pull your world/config/plugins from a Git repo into `/data`; push changes back on stop or periodically

## What the Minecraft image does

We use `itzg/minecraft-server`, a popular Docker image that runs a Minecraft server with lots of config via environment variables. Highlights:

- `EULA`: must be TRUE to run (accept Mojang EULA)
- `MEMORY`: Java heap (e.g., `2G`)
- `TYPE`: the distribution (e.g., `VANILLA`, `PAPER`, `PURPUR`, `FORGE`, `FABRIC`, `CUSTOM`)
- `VERSION`: the Minecraft version (e.g., `1.21.1`, `LATEST`)
- `ENABLE_RCON`, `RCON_PASSWORD`, `RCON_PORT`: enables RCON for automation
- `ENABLE_QUERY`: enables query protocol
- `OPS`: comma-separated list of operator usernames

If `TYPE=CUSTOM`, the image runs the jar file you specify via `CUSTOM_SERVER` (we auto-detect when a jar is present under `/data`).

## Topology

- Internet -> your DNS (A record) -> Linux host public IP
- Open ports: 25565 (MC), 8080 (control API)
- GitHub Pages calls the control API with a bearer token

## Prerequisites on Linux host

- Docker and Docker Compose installed
- Public IP or port-forwarding from your router for TCP/UDP 25565 and TCP 8080
- A data directory (e.g., `/opt/minecraft/data`) with enough disk space

## Setup

1) Copy env and edit:

```bash
cp .env.example .env
nano .env
```

Key values:
- `API_TOKEN`: a long random string
- `CORS_ORIGIN`: your GitHub Pages origin (e.g., `https://youruser.github.io`)
- `MC_DATA_DIR`: absolute path on the host for world data (e.g., `/opt/minecraft/data`)
- `SERVER_PORT`: default 25565
- `RCON_PASSWORD`: any secret (not exposed publicly)
- (Optional) Git sync:
	- `GIT_REPO`: Git URL of your world/config repository (HTTPS or SSH)
	- `GIT_BRANCH`: branch name (default `main`)
	- `GIT_AUTO_PUSH`: true to push changes on stop
	- `GIT_PUSH_INTERVAL_SECONDS`: periodic push interval (not enabled by default loop)
	- `GIT_IGNORE_SERVER_PROPERTIES`: true to avoid committing your local `server.properties`

2) Create data directory and accept EULA:

```bash
sudo mkdir -p /opt/minecraft/data
sudo chown $USER:$USER /opt/minecraft -R
```

3) Build and start control API only (first time):

```bash
docker compose build control-api
docker compose up -d control-api
```

4) Start Minecraft via API:

```bash
curl -H "Authorization: Bearer $API_TOKEN" http://localhost:8080/start
```

The control API will create/start the container with your `.env` configuration and mount `/opt/minecraft/data`.

## Control API endpoints

- `GET /healthz`: no auth
- `GET /status`: container status and online players
- `POST /start`: create/start the server
- `POST /restart`: restart the server
- `POST /stop`: stop only if no players are online
- `POST /git/pull`: force a repo pull into `/data`
- `POST /git/push`: commit and push changes from `/data`

Auth: `Authorization: Bearer <API_TOKEN>`

## Exposing ports and testing

Ensure your firewall and router allow:
- TCP/UDP 25565 to your host
- TCP 8080 to your host (or serve behind a reverse proxy and TLS)

Local tests on the Linux host:
```bash
# API health
curl http://localhost:8080/healthz
# API status (requires token)
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8080/status

# Check port listeners
ss -tulpen | grep -E ":(25565|8080)\b"
```

Remote tests (from another machine):
```bash
# Control API
curl -H "Authorization: Bearer YOUR_TOKEN" http://YOUR_HOST_OR_DOMAIN:8080/status
# Minecraft SRV (TCP)
nc -zv YOUR_HOST_OR_DOMAIN 25565
```

## GitHub Pages front-end

Use `web/index.html` as a simple static page. Host it on GitHub Pages and set:
- API base: `https://your-domain:8080` (or your reverse-proxied HTTPS URL)
- API token: your token

In `.env`, set `CORS_ORIGIN=https://youruser.github.io` so browsers can call your API.

## Script parsing and custom jar detection

If your repo includes a `start.sh` or `start.bat`, we try to parse a simple `java ... -jar YourServer.jar ...` line and extract:
- The jar filename to run
- JVM memory flags (-Xms/-Xmx) and `nogui` if present

Parsing succeeds for straightforward scripts; if it fails, we fall back to autodetecting a jar in `/data`:
- Prefer `server.jar`
- Otherwise match common names like `paper-*.jar`, `purpur-*.jar`, etc.
- If exactly one `.jar` is present, use it

Memory behavior:
- If the script sets `-Xms` and `-Xmx` to the same value, we set `MEMORY` to that value for the container (letting the image manage the rest)
- Otherwise, we pass the specific flags via `JVM_OPTS`

## Admin interaction (in-server)

- Use RCON from the control API internally. If you want CLI access, exec into the container:
```bash
docker exec -it mc-server rcon-cli
# or attach to console
docker attach mc-server
```

## Notes on security

- The control API mounts `/var/run/docker.sock` to manage the MC container. This is powerful; protect the API with a strong token, restrict `CORS_ORIGIN`, and ideally place it behind TLS and a reverse proxy (Caddy/Nginx).
- RCON is not published to the internet. It's used only via the internal Docker network.
- Git credentials: for private repos over SSH, mount keys or use deploy tokens. This example installs git in the API container but does not set up SSH keys — prefer HTTPS with PAT or add secret management separately.

## Update/maintenance

- To update the server image:
```bash
docker compose pull mc
# restart via API or docker compose
```

- Backups: archive `/opt/minecraft/data` regularly.

## Troubleshooting

- Control API logs:
```bash
docker logs -f mc-control-api
```
- Minecraft logs:
```bash
docker logs -f mc-server
```
- Permission issues on data dir: ensure the host path exists and is writable.
- Custom JAR not detected: ensure `.jar` is at the root of `/data` and named `server.jar` (preferred) or a recognizable pattern like `paper-*.jar`. When detected, container switches to `TYPE=CUSTOM`.
