from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
