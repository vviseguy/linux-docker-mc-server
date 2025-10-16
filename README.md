# Minecraft Control Dashboard

A web dashboard (backend API + SPA frontend) to manage and observe a Minecraft server stored in a GitHub repository. It can:

- Start/stop/restart your Minecraft server in Docker
- Stream chat via WebSocket and send commands (RCON)
- Show basic server info and player list
- Pull your server repo before launch, create a session branch, and periodically push world data
- On stop, push final changes and merge session branch into main
- Excludes `server.properties` from Git operations (local-only)

## Structure

- `control-api/` FastAPI backend
- `web/` React + Vite + TypeScript frontend
- `docker-compose.yml` Orchestration for API + MC container (MC container is generic; MC start is driven by repo's start script)
- `data/` Local clone of the configured GitHub repo (ignored by Git)

## Quick start

1. Configure backend in `control-api/config.yaml` (set `repo.url`, desired ports, etc.)
2. Ensure Docker is running.
3. Run the backend locally or via compose.
4. Use the UI to start/stop and chat.

Note: The backend will enable RCON in `server.properties` on first start and will not commit that file.

## Security

- Minimal by default. Configure an `ADMIN_TOKEN` in `.env` to protect write APIs.
- RCON password is set and kept local. The backend connects to RCON and clients connect to the backend WebSocket.

## Runtime configuration

- `control-api/config.yaml` lets you configure:
  - repo.url, branch, session_branch_prefix, path
  - rcon.host, rcon.port, rcon.password (server.properties is updated on first run)
  - java_version (default 21), java_image (optional override), xms_gb, xmx_gb, extra_jvm_flags
  - sync_interval_seconds (autosave cadence)
- Start API supports per-start overrides for memory, flags, and Java image/version.

## API highlights

- POST `/api/server/start` Start server from configured repo; returns image/command/ports.
- POST `/api/server/stop` Stop server; blocks if players are online unless `force=true`.
- POST `/api/server/save` Manual “save now” and commit/push to session branch.
- GET `/api/server/status` Container state + online flag.
- GET `/api/server/info` Players + online flag (and future stats).

## UI tips

- The chat panel streams server logs; you’ll see a toast when the server is online.
- Use the side panel to adjust Xms/Xmx before starting. Set an admin token if you enabled ADMIN_TOKEN.

## License

MIT
