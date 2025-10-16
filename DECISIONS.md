# Architecture and Decisions Log

## Manual Java runtime

- We run the server by calling `java -Xms{X}G -Xmx{X}G [flags] -jar <server.jar> --nogui` inside a generic Java container (Eclipse Temurin), not via a prebuilt MC image.
- Memory (Xms/Xmx) and extra JVM flags are configurable in `control-api/config.yaml` and can be overridden per start via the API.

## Server jar detection

- Prefer extracting the `-jar` target from `start.sh` (Linux) or `start.bat` (Windows) if present.
- If not found, fall back to selecting by prefix: `paper*`, `purpur*`, `pufferfish*`, `spigot*`, `server*`, else the largest `*.jar` in the repo root.

## Java version

- Default `java_version` is 21; modern Paper requires Java 21 per official docs.
- You can override the container image with `java_image`; otherwise it uses `eclipse-temurin:{java_version}-jre`.

## RCON and EULA

- On first start, `server.properties` is updated to enable RCON, set the RCON port and password, and `eula.txt` is set to `eula=true`.
- `server.properties` is excluded from Git.

## Git workflow

- On start: pull main and create `sessions/YYYYMMDD-HHMMSS` branch.
- Periodic sync: a background scheduler commits/pushes changes every `sync_interval_seconds`.
- On stop: final commit/push, merge session into main, overwriting main with the session state if conflicts arise.

## Networking

- API container connects to RCON via `host.docker.internal` on Linux (compose sets `extra_hosts: host-gateway`).

## UI/UX decisions

- Chat-first layout with Start/Stop/Restart controls.
- Toasts show start configuration and “online” detection based on logs.
- Memory controls in side panel; UI sends overrides to the backend.
