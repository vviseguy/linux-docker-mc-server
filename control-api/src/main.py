from __future__ import annotations

from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import settings
from .auth import require_token
from .mc_manager import DockerMCManager
from .rcon_client import RconClient
from .git_sync import GitSync
import json
import time
from pathlib import Path
from collections import deque
import re

app = FastAPI(title="MC Control API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_origin] if settings.cors_origin != "*" else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

mc = DockerMCManager()
rcon = RconClient()
git = GitSync()
STATE_FILE = Path("/data/.mc_control_state.json")
SERVER_PROPERTIES = Path("/data/server.properties")


def record_backup_ts():
    try:
        s = {"last_backup": int(time.time())}
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(s))
    except Exception:
        pass


def read_state() -> dict:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
    except Exception:
        pass
    return {}


def get_server_name() -> str:
    """Derive a friendly server name.
    Prefer 'motd' from server.properties, else fall back to container name, else generic.
    Strips Minecraft color codes (e.g., §a) and collapses newlines.
    """
    # Try MOTD from server.properties
    try:
        if SERVER_PROPERTIES.exists():
            motd = None
            with SERVER_PROPERTIES.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith("motd="):
                        motd = line.split("=", 1)[1].strip()
                        break
            if motd:
                # Strip color/formatting codes like §a, §l, etc.
                motd = re.sub(r"§.", "", motd)
                # Replace literal \n with separator for single-line subtitle
                motd = motd.replace("\\n", " • ")
                motd = motd.replace("\n", " • ")
                return motd.strip() or settings.mc_container_name
    except Exception:
        pass
    # Fallback to container name, then generic
    try:
        cont = mc.status()
        name = cont.get("name") if isinstance(cont, dict) else None
        if name:
            return name
    except Exception:
        pass
    return "Minecraft Server"


def tail_lines(path: Path, max_lines: int) -> list[str]:
    if not path.exists():
        return []
    dq = deque(maxlen=max_lines)
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                dq.append(line.rstrip("\n"))
    except Exception:
        return []
    return list(dq)


CHAT_RE_ANGLE = re.compile(r"^.*?<([^>]+)>\s*(.*)$")
TS_RE = re.compile(r"^(?:\[)?(\d{2}:\d{2}:\d{2})(?:\])?\s")


def parse_chat_lines(lines: list[str]) -> list[dict]:
    out = []
    for ln in lines:
        user = None
        text = None
        m = CHAT_RE_ANGLE.match(ln)
        if m:
            user = m.group(1)
            text = m.group(2)
        elif "[Server]" in ln and "INFO" in ln:
            # Server broadcast (say)
            user = "Server"
            # try to extract text after [Server]
            idx = ln.find("[Server]")
            if idx != -1:
                text = ln[idx + len("[Server]") :].strip()
        # timestamp if present
        ts_m = TS_RE.match(ln)
        ts = ts_m.group(1) if ts_m else None
        if user and text is not None:
            out.append({"ts": ts, "user": user, "text": text, "raw": ln})
    return out


class ActionResponse(BaseModel):
    status: str
    detail: dict | None = None


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/status", dependencies=[Depends(require_token)])
def status():
    s = mc.status()
    try:
        players = rcon.list_players() if settings.enable_rcon else []
    except Exception:
        players = []
    state = read_state()
    return {
        "container": s,
        "players": players,
        "last_backup": state.get("last_backup"),
        "server_name": get_server_name(),
    }


@app.post("/start", response_model=ActionResponse, dependencies=[Depends(require_token)])
def start():
    res = mc.start()
    return ActionResponse(status="started", detail=res)


@app.post("/stop", response_model=ActionResponse, dependencies=[Depends(require_token)])
def stop():
    # only stop if no players online
    try:
        players = rcon.list_players() if settings.enable_rcon else []
    except Exception:
        players = []
    if players:
        raise HTTPException(status_code=409, detail=f"Players online: {', '.join(players)}")
    res = mc.stop()
    # Push any changes to repo after a clean stop
    try:
        out = git.commit_and_push("Server stopped: save state")
        record_backup_ts()
    except Exception:
        pass
    return ActionResponse(status="stopped", detail=res)


class ChatRequest(BaseModel):
    message: str


@app.post("/chat", dependencies=[Depends(require_token)])
def chat(req: ChatRequest):
    # Broadcast a chat message using RCON: use 'say' command for public chat
    try:
        resp = rcon.send_message(f"[Web] {req.message}")
        return {"ok": True, "resp": resp}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chat/history", dependencies=[Depends(require_token)])
def chat_history(lines: int = 200):
    # Read latest.log and parse common chat patterns
    log_path = Path("/data/logs/latest.log")
    lines = max(10, min(lines, 2000))
    raw = tail_lines(log_path, lines)
    parsed = parse_chat_lines(raw)
    return {"count": len(parsed), "messages": parsed}


@app.post("/restart", response_model=ActionResponse, dependencies=[Depends(require_token)])
def restart():
    res = mc.restart()
    return ActionResponse(status="restarted", detail=res)


@app.post("/git/pull", dependencies=[Depends(require_token)])
def git_pull():
    out = git.pull()
    return {"ok": True, "output": out}


@app.post("/git/push", dependencies=[Depends(require_token)])
def git_push():
    out = git.commit_and_push("Manual push")
    return {"ok": True, "output": out}


# Serve the static web UI from /srv/www (mounted via docker-compose)
# Add this last so API routes above take precedence.
try:
    app.mount("/", StaticFiles(directory="/srv/www", html=True), name="static")
except Exception:
    # If the directory isn't present (e.g., in dev), skip mounting.
    pass
