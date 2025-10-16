from dataclasses import dataclass
from typing import Optional


@dataclass
class RuntimeState:
    session_branch: Optional[str] = None
    container_name: str = "mc-server"
    repo_url_override: Optional[str] = None
    online: bool = False


runtime = RuntimeState()
