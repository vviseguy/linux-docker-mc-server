from dataclasses import dataclass


@dataclass
class RuntimeState:
    container_name: str = "mc-server"
    online: bool = False


runtime = RuntimeState()
