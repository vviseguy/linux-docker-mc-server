from dataclasses import dataclass, field
from pathlib import Path
import os
import yaml


@dataclass
class RepoConfig:
    url: str = ""
    branch: str = "main"
    session_branch_prefix: str = "sessions"
    path: str = "data"  # where to clone locally (relative to /app)
    token: str | None = None
    username: str | None = None


@dataclass
class RconConfig:
    enable: bool = True
    port: int = 25575
    password: str = "change_me"
    host: str = "host.docker.internal"


@dataclass
class AppConfig:
    admin_token: str | None = None
    sync_interval_seconds: int = 300
    repo: RepoConfig = field(default_factory=RepoConfig)
    rcon: RconConfig = field(default_factory=RconConfig)
    logs_dir: str = "logs"
    mc_container_name: str = "mc-server"
    java_version: int = 21  # default for modern Paper 1.20+/1.21
    java_image: str | None = None  # override image; if None, uses eclipse-temurin:{java_version}-jre
    xms_gb: int = 2
    xmx_gb: int = 4
    extra_jvm_flags: list[str] = field(default_factory=list)  # e.g., ["-XX:+UseG1GC"]
    git_enabled: bool = False


class Settings:
    def __init__(self):
        # Default to the control-api directory when running locally; containers can set APP_ROOT=/app
        default_root = Path(__file__).resolve().parents[1]
        self.root = Path(os.getenv("APP_ROOT", str(default_root)))
        self.path = self.root / "config.yaml"
        self.config = self._load()

    def _load(self) -> AppConfig:
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        else:
            data = {}

        # env overrides
        admin_token = os.getenv("ADMIN_TOKEN", data.get("admin_token"))
        sync_interval_seconds = int(os.getenv("SYNC_INTERVAL_SECONDS", data.get("sync_interval_seconds", 300)))

        repo = data.get("repo", {})
        rcon = data.get("rcon", {})

        # Parse env bool for git toggle
        def env_bool(name: str, default: bool) -> bool:
            v = os.getenv(name)
            if v is None:
                return default
            return str(v).strip().lower() in {"1", "true", "yes", "on"}

        cfg = AppConfig(
            admin_token=admin_token,
            sync_interval_seconds=sync_interval_seconds,
            repo=RepoConfig(
                url=repo.get("url", ""),
                branch=repo.get("branch", "main"),
                session_branch_prefix=repo.get("session_branch_prefix", "sessions"),
                path=repo.get("path", "data"),
                token=os.getenv("GIT_TOKEN", repo.get("token")),
                username=os.getenv("GIT_USERNAME", repo.get("username")),
            ),
            rcon=RconConfig(
                enable=bool(rcon.get("enable", True)),
                port=int(rcon.get("port", 25575)),
                password=rcon.get("password", "change_me"),
                host=rcon.get("host", "host.docker.internal"),
            ),
            logs_dir=data.get("logs_dir", "logs"),
            mc_container_name=data.get("mc_container_name", "mc-server"),
            java_version=int(data.get("java_version", 21)),
            java_image=data.get("java_image"),
            xms_gb=int(data.get("xms_gb", 2)),
            xmx_gb=int(data.get("xmx_gb", 4)),
            extra_jvm_flags=data.get("extra_jvm_flags", []),
            git_enabled=env_bool("GIT_ENABLED", bool(data.get("git_enabled", False))),
        )
        return cfg


settings = Settings()
