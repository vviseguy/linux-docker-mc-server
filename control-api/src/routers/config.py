from fastapi import APIRouter
from ..settings import settings

router = APIRouter()


@router.get("")
def get_config():
    # Do not return secrets like admin token or RCON password
    cfg = settings.config
    return {
        "repo": {
            "url": cfg.repo.url,
            "branch": cfg.repo.branch,
            "session_branch_prefix": cfg.repo.session_branch_prefix,
            "path": cfg.repo.path,
        },
        "rcon": {
            "enable": cfg.rcon.enable,
            "port": cfg.rcon.port,
            "host": cfg.rcon.host,
        },
        "sync_interval_seconds": cfg.sync_interval_seconds,
    }
