from fastapi import Header, HTTPException
from .settings import settings


def require_admin_token(x_admin_token: str | None = Header(default=None)):
    cfg_token = settings.config.admin_token
    if cfg_token and x_admin_token != cfg_token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True
