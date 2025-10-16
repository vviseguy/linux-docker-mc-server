from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os
from .settings import settings
from .routers import server, chat, config as cfg
from .scheduler import start_scheduler, shutdown_scheduler

app = FastAPI(title="Minecraft Control API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cfg.router, prefix="/api/config", tags=["config"])
app.include_router(server.router, prefix="/api/server", tags=["server"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.on_event("startup")
def _on_startup():
    start_scheduler()


@app.on_event("shutdown")
def _on_shutdown():
    shutdown_scheduler()


# Optionally serve the built SPA if present
def _mount_spa_if_present(_app: FastAPI):
    # Prefer explicit env var if provided (e.g., set SPA_DIR=/app/www in container)
    candidates: list[Path] = []
    spa_env = os.getenv("SPA_DIR")
    if spa_env:
        candidates.append(Path(spa_env))
    # Common dev path: project/web/dist (when running locally)
    candidates.append((settings.root.parent / "web" / "dist").resolve())
    # Common container path where compose can mount the build output
    candidates.append(Path("/app/www"))

    for p in candidates:
        try:
            if p.exists() and (p / "index.html").exists():
                # Mount at root; API remains at /api/* because routers are registered first
                _app.mount("/", StaticFiles(directory=str(p), html=True), name="spa")
                break
        except Exception:
            continue


_mount_spa_if_present(app)
