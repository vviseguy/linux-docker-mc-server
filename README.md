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

## Using your host's Git credentials (Linux)

You have two good options. Pick one based on your workflow:

1. Host-side clone (recommended and simplest)

- Clone your Minecraft repo on the host into the `data/` folder, and point `control-api/config.yaml` to `repo.path: data` (default).
- The API will detect the existing clone and use it, including your host's Git remotes/credentials.

Commands (Linux):

```bash
mkdir -p data
git clone <your-repo-url> data
# Optionally checkout the main branch configured in config.yaml
cd data && git checkout <main-branch>
```

Notes:

- If you use SSH remotes, ensure your host has working SSH keys/agent; the container just sees the files under `data/` and doesn't need to authenticate until it pushes via your configured remote. If you want pushes from inside the container to reuse your host SSH, see option 2 below.

2. Let the container use credentials

- HTTPS with Personal Access Token (PAT):

  - In `.env` (loaded by docker-compose), set:
    - `GIT_USERNAME=your-username`
    - `GIT_TOKEN=your-token` (scopes: repo read/write)
  - Use `https://github.com/owner/repo.git` in `config.yaml`. The API injects the token into the remote URL for clone/push.

- SSH agent + config (Linux):
  - Ensure your SSH agent is running and has your key: `ssh-add -l` should list a key.
  - Mount your SSH agent socket and git configs into the container. In `docker-compose.yml` under `control-api.volumes`, uncomment and adapt:
    ```yaml
    - ${SSH_AUTH_SOCK}:${SSH_AUTH_SOCK}
    - ~/.gitconfig:/root/.gitconfig:ro
    - ~/.ssh:/root/.ssh:ro
    ```
  - Also set `SSH_AUTH_SOCK` in the container environment by exporting it before `docker compose up` or adding it in an env_file. Then use an SSH remote like `git@github.com:owner/repo.git` in `config.yaml`.

With either method, the API will:

- Pull `main`, create a session branch, autosave commits, and push to origin.
- On stop, merge the session into `main` (favoring session’s content on conflicts).

Tip: If the repo is already cloned under `data/`, the API reuses it and will update the origin URL with injected HTTPS credentials when `GIT_USERNAME`/`GIT_TOKEN` are provided.

## Host-side Git agent (recommended for security)

If you don't want to expose your Git credentials to the container, run a small host-side agent that performs the git operations for the container using your host credentials.

1. Start the agent on the host (run in systemd, tmux, screen, etc.):

```bash
# from project root
python3 host_git_agent.py --data-dir ./data
```

2. When the API needs to perform a git action, it will drop a JSON request into `data/.ctl/requests/` and wait for a response in `data/.ctl/responses/`.

3. The agent will perform a whitelisted set of actions using the host's git and credentials:

- clone, pull, create_session_branch, commit_all, push, merge_to_main_overwrite_current

Security notes:

- The agent only accepts requests placed inside `data/.ctl/requests` and will restrict operations to paths under `data/`.
- Only the specific actions above are allowed; arbitrary commands are not executed.

This setup lets the container run the server while your host keeps private keys or PATs and performs authenticated git operations on behalf of the container.

## Troubleshooting

Clean up old containers and images (Docker)

Common maintenance commands. Be careful with prune commands; they remove stopped containers/images/networks.

List containers and stop/remove the dashboard and server containers:

PowerShell (Windows):

```powershell
# List all containers
docker ps -a

# Stop the control API and the MC server container if present
docker stop mc-control-api; docker stop mc-server

# Remove them
docker rm mc-control-api; docker rm mc-server

# Remove any dangling/stopped containers (optional)
docker container prune -f

# List images and remove any you no longer need (optional)
docker images
# Example:
# docker rmi <IMAGE_ID>

# Remove unused images/networks (optional)
docker image prune -a -f; docker network prune -f

# If you used Docker volumes elsewhere and want to clean them (not required here as we bind-mount ./data and ./logs)
docker volume ls
docker volume prune -f
```

Compose-specific:

```powershell
# From the project root
docker compose down

# Rebuild and start fresh after changes
docker compose up -d --build
```

Notes:

- This project bind-mounts `./data` and `./logs`. The commands above do not delete those folders. Manage them with normal file operations if needed.
- The MC server container is created dynamically by the API as `mc-server` (configurable via `mc_container_name`). The control API container is named `mc-control-api`.
