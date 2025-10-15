## AI agent guide for linux-docker-mc-server

This repo runs a Minecraft server in Docker and exposes a minimal control API (FastAPI) plus a static web UI.

- Services (see `docker-compose.yml`)
  - `control-api`: Python FastAPI that manages the MC container via Docker SDK, uses RCON for player checks/chat, and optionally syncs `/data` with a Git repo.
  - `mc`: The game server (`itzg/minecraft-server`) whose lifecycle and env are controlled by the API. Data volume is the shared `/data`.

### Architecture and key files
- FastAPI app: `control-api/src/main.py`
  - Auth via bearer token dependency: `require_token` in `auth.py`. Endpoints that mutate or read sensitive data include `dependencies=[Depends(require_token)]`.
  - Container control: `DockerMCManager` in `mc_manager.py` (create/start/stop/restart/status). Writes `server.properties` to enforce RCON/port on every start/restart.
  - RCON: `RconClient` in `rcon_client.py` (list players, run commands, chat via `say`). Connects to host `mc` (compose service) on `settings.rcon_port`; RCON is not exposed publicly.
  - Git sync: `GitSync` in `git_sync.py` (clone/pull/commit/push) operating on `/data`. On clean stop, pushes changes if enabled.
  - Chat history parsing: reads `/data/logs/latest.log` and extracts messages with simple regexes.
- Configuration: `control-api/src/config.py` uses `pydantic-settings` to load `.env` (e.g., token, CORS origin, MC image/type/version, ports, git repo info).
- Web UI (static): `web/index.html`, `web/app.ts` (compiled to `app.js`), and `web/logs.*` for a simple logs page.

### Control API endpoints (selected)

- `GET /healthz` (no auth)
- `GET /status` → { container status, players[], last_backup, server_name }
- `POST /start` | `POST /restart` | `POST /stop` (stop returns 409 if players are online)
- `POST /chat` body `{ message }` → uses RCON `say`
- `GET /chat/history?lines=N` → parses recent chat lines
- `POST /git/pull` | `POST /git/push`

### How pieces talk to each other

- Web UI fetches `${API_BASE}/...` with `Authorization: Bearer ${API_TOKEN}`; see `web/app.ts` (`doCall`, `sendChat`).
- FastAPI talks to Docker Engine via mounted `/var/run/docker.sock` (see compose). It creates the `mc` container with desired env and `/data` bind.
- Player awareness and chat go through RCON to the `mc` service on the compose network (not published to host by default).

### Important behaviors and conventions

- Start flow (`/start`): `GitSync.ensure_repo()+pull()` → `mc_manager.enforce_server_properties()` → ensure/create container → start.
- Stop flow (`/stop`): deny if players online (409); on success, `GitSync.commit_and_push()` and record timestamp in `/data/.mc_control_state.json`.
- Custom JAR detection (see `mc_manager.desired_env()`):
  - If `/data/start.sh|start.bat` contains `java ... -jar X.jar`, switch to `TYPE=CUSTOM`, set `CUSTOM_SERVER=X.jar`, parse `-Xms/-Xmx` to set `MEMORY` or `JVM_OPTS`, and include `nogui` when present.
  - Else auto-detect `server.jar` or common prefixes (`paper-*, purpur-*, fabric-*, forge-*, ...`).
- `server.properties` is rewritten with enforced keys: `enable-rcon`, `rcon.password`, `rcon.port`, `server-port`.
- CORS is locked to `settings.cors_origin` (set in `.env`). Use your GitHub Pages origin or `*` for testing.

### Dev/workflows agents should use

- Backend (containerized):
  - Build/run API only: optional commands (Linux host) → docker compose build control-api; docker compose up -d control-api.
  - Exercise API: call `GET /healthz` (no auth) and authenticated endpoints with `Authorization: Bearer ${API_TOKEN}` from `.env`.
- Frontend:
  - In `web/`: `npm i` then `npm run build` to produce `app.js`/`logs.js`. `index.html` expects `window.CONFIG = { API_BASE, API_TOKEN }` (placeholders are `%%API_BASE%%`, `%%API_TOKEN%%` for static hosting pipelines).

### Patterns to follow when extending

- New endpoints: add `dependencies=[Depends(require_token)]` unless explicitly public; return small Pydantic models (`ActionResponse`) or dicts for the UI.
- Docker interactions: go through `DockerMCManager`; keep env derivation logic centralized in `desired_env()` and keep `/data` as the single source of truth for server bits.
- If exposing new web actions, add a thin wrapper in `web/app.ts` using `doCall('path', 'METHOD')` and update the UI minimally.

### Integration knobs and envs (examples)

- Token and CORS: `API_TOKEN`, `CORS_ORIGIN` in `.env` → `Settings` → `auth.require_token` and FastAPI CORS middleware.
- MC runtime: `TYPE`, `VERSION`, `MEMORY`, `ENABLE_RCON`, `RCON_PASSWORD`, `SERVER_PORT` (via `.env` and enforced server.properties).
- Git sync: `GIT_REPO`, `GIT_BRANCH`, `GIT_AUTO_PUSH`, `GIT_IGNORE_SERVER_PROPERTIES`.

### Gotchas

- The target deployment is a Linux host with Docker and the UNIX socket mounted into `control-api`. RCON is intended for internal use only.
- Stopping while players are online is a hard 409 to prevent data loss; client should handle and surface the message.
- Chat history parsing is regex-based and may miss modded log formats; keep it simple or add parsers per format in `main.py`.

References: `control-api/src/main.py`, `mc_manager.py`, `rcon_client.py`, `git_sync.py`, `config.py`, `web/app.ts`, `docker-compose.yml`, README.md.
