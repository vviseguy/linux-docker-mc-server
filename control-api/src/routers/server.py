from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from pathlib import Path
from ..settings import settings
from ..state import runtime
from ..services.docker_ops import DockerManager, parse_start_bat, parse_start_sh, default_java_image
from ..services.rcon_bridge import list_players
from ..utils.server_properties import ensure_rcon_and_eula
from ..security import require_admin_token
import os
from typing import Optional
import re

router = APIRouter()


class StartRequest(BaseModel):
    repo_url: str | None = None  # optional override to queue a different server
    xms_gb: int | None = None
    xmx_gb: int | None = None
    extra_jvm_flags: list[str] | None = None
    java_version: int | None = None
    java_image: str | None = None
    server_name: str | None = None  # choose subfolder under data by normalized name


def _normalize_name(s: str) -> str:
    # lower, remove all non-alphanumeric characters
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _is_runnable_dir(p: Path) -> bool:
    return ((p / "start.sh").exists() or (p / "start.bat").exists() or any(p.glob("*.jar")))


def _list_runnable_servers(base: Path) -> list[dict]:
    items: list[dict] = []
    # Prefer subdirectories; include base if it is runnable too
    for child in sorted([d for d in base.iterdir() if d.is_dir() and not d.name.startswith('.')]):
        if _is_runnable_dir(child):
            items.append({
                "name": child.name,
                "normalized": _normalize_name(child.name),
                "path": str(child.relative_to(base))
            })
    if _is_runnable_dir(base):
        items.insert(0, {"name": "root", "normalized": _normalize_name("root"), "path": "."})
    return items


@router.get("/servers")
def list_servers():
    cfg = settings.config
    from ..settings import settings as _settings
    base = (_settings.root / cfg.repo.path)
    base.mkdir(parents=True, exist_ok=True)
    return {"servers": _list_runnable_servers(base)}


@router.post("/start")
def start_server(body: StartRequest, _: bool = Depends(require_admin_token)):
    cfg = settings.config
    # Git is removed; repo_url is ignored. We just use the local data directory.

    # Use configured app root (works locally and in container)
    from ..settings import settings as _settings

    data_dir = _settings.root / cfg.repo.path
    data_dir.mkdir(parents=True, exist_ok=True)

    # Detect server root: either data_dir itself or a nested subfolder containing a server jar/start script
    def find_server_root(base: Path) -> Path:
        # If base has start script or jar, use it
        if (base / "start.sh").exists() or (base / "start.bat").exists() or list(base.glob("*.jar")):
            return base
        # Look one level down for a folder with jar or start script
        for child in sorted([p for p in base.iterdir() if p.is_dir()]):
            if child.name.startswith('.'):
                continue
            if (child / "start.sh").exists() or (child / "start.bat").exists() or list(child.glob("*.jar")):
                return child
        return base

    # If a server_name is provided, match it to a subfolder (normalized)
    if body.server_name:
        wanted = _normalize_name(body.server_name)
        candidates = _list_runnable_servers(data_dir)
        match = next((c for c in candidates if c["normalized"] == wanted), None)
        if not match:
            raise HTTPException(status_code=404, detail=f"Server '{body.server_name}' not found. Available: {', '.join([c['name'] for c in candidates])}")
        server_root = (data_dir / match["path"]).resolve()
        if not _is_runnable_dir(server_root):
            raise HTTPException(status_code=400, detail=f"Selected folder '{match['name']}' is not runnable (no jar or start script)")
    else:
        server_root = find_server_root(data_dir)
    session_branch = None
    runtime.session_branch = None

    # Ensure RCON and EULA
    server_port = ensure_rcon_and_eula(server_root, cfg.rcon.port, cfg.rcon.password)

    # Build java command manually to control memory and flags
    # Detect server jar from start scripts first
    start_sh = server_root / "start.sh"
    start_bat = server_root / "start.bat"
    detected_jar_name: str | None = None
    cmd_from_sh = parse_start_sh(start_sh)
    cmd_from_bat = parse_start_bat(start_bat) if not cmd_from_sh else None
    cmd_candidates = cmd_from_sh or cmd_from_bat
    if cmd_candidates:
        # find -jar argument and its value
        if "-jar" in cmd_candidates:
            try:
                idx = cmd_candidates.index("-jar")
                detected_jar_name = cmd_candidates[idx + 1].strip("\"'")
                # If a path is included, take basename
                if "/" in detected_jar_name or "\\" in detected_jar_name:
                    detected_jar_name = detected_jar_name.replace("\\", "/").split("/")[-1]
            except Exception:
                detected_jar_name = None

    # Fallback: prefer paper/purpur/pufferfish/spigot/server, else largest *.jar
    jars = sorted([p for p in server_root.glob("*.jar")], key=lambda p: (-p.stat().st_size, p.name))
    jar = None
    if detected_jar_name:
        candidate = server_root / detected_jar_name
        if candidate.exists():
            jar = candidate
    if not jar:
        for pref in ("paper", "purpur", "pufferfish", "spigot", "server"):
            for p in jars:
                if p.name.lower().startswith(pref):
                    jar = p
                    break
            if jar:
                break
    if not jar and jars:
        jar = jars[0]
    if not jar:
        raise HTTPException(status_code=400, detail="No server .jar found in repo root")

    xms_val = body.xms_gb if body.xms_gb is not None else cfg.xms_gb
    xmx_val = body.xmx_gb if body.xmx_gb is not None else cfg.xmx_gb
    xms = f"-Xms{xms_val}G"
    xmx = f"-Xmx{xmx_val}G"
    flags = [xms, xmx] + (
        (body.extra_jvm_flags or []) if body.extra_jvm_flags is not None else (cfg.extra_jvm_flags or [])
    )
    command = ["java", *flags, "-jar", jar.name, "--nogui"]

    env = {
        "EULA": "TRUE",
    }

    ports = {server_port: server_port, cfg.rcon.port: cfg.rcon.port}

    dm = DockerManager()
    # Stop any existing container first
    dm.stop_container(cfg.mc_container_name)
    desired_java_version = body.java_version if body.java_version is not None else cfg.java_version
    java_image = body.java_image or cfg.java_image or default_java_image(desired_java_version)
    container = dm.start_container(
        name=cfg.mc_container_name,
        repo_host_dir=server_root,
        ports=ports,
        env=env,
        command=command,
        java_image=java_image,
        workdir="/data",
    )
    # server starting, not yet online until logs show 'Done (...)'
    runtime.online = False
    return {
        "started": True,
        "container": container.name,
        "session_branch": session_branch,
        "java_image": java_image,
        "command": command,
        "ports": ports,
        "xms_gb": xms_val,
        "xmx_gb": xmx_val,
        "extra_jvm_flags": flags,
    }


@router.post("/stop")
def stop_server(force: bool = False, _: bool = Depends(require_admin_token)):
    cfg = settings.config
    # If not force, check players are offline
    if not force and cfg.rcon.enable:
        try:
            players = list_players(cfg.rcon.host, cfg.rcon.port, cfg.rcon.password)
        except Exception:
            players = []
        if players:
            raise HTTPException(status_code=409, detail=f"Players online: {', '.join(players)}")

    # Stop container
    dm = DockerManager()
    stopped = dm.stop_container(cfg.mc_container_name)

    # No git actions; just stop
    # reset online flag after stop
    runtime.online = False

    return {"stopped": stopped}


@router.post("/save")
def save_now(_: bool = Depends(require_admin_token)):
    cfg = settings.config
    # Ask server to save and then commit/push
    try:
        from ..services.rcon_bridge import run_command

        run_command(cfg.rcon.host, cfg.rcon.port, cfg.rcon.password, "save-all flush")
    except Exception:
        pass
    # No git actions
    return {"saved": False, "branch": None}


@router.post("/restart")
def restart_server(_dep: bool = Depends(require_admin_token)):
    stop_server(force=True)
    return start_server(StartRequest())


@router.get("/status")
def status():
    cfg = settings.config
    from ..services.docker_ops import DockerManager

    try:
        dm = DockerManager()
        st = dm.container_status(cfg.mc_container_name)
        docker_available = True
    except Exception:
        # Docker daemon is not reachable (e.g., Docker Desktop not running)
        st = "docker-unavailable"
        docker_available = False
    from ..state import runtime

    return {
        "running": st == "running",
        "online": runtime.online,
        "container": cfg.mc_container_name,
        "status": st,
        "docker_available": docker_available,
    }


@router.get("/info")
def info():
    cfg = settings.config
    players: list[str] = []
    if cfg.rcon.enable:
        try:
            players = list_players(cfg.rcon.host, cfg.rcon.port, cfg.rcon.password)
        except Exception:
            players = []
    return {
        "version": None,
        "players": players,
        "uptime_seconds": 0,
        "online": runtime.online,
    }
