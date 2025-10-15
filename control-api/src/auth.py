from fastapi import Header, HTTPException
from .config import settings

async def require_token(authorization: str | None = Header(default=None)) -> None:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization[7:]
    if token != settings.api_token:
        raise HTTPException(status_code=403, detail="Invalid token")
