from __future__ import annotations
from pathlib import Path


def read_properties(path: Path) -> dict[str, str]:
    props: dict[str, str] = {}
    if not path.exists():
        return props
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            props[k.strip()] = v.strip()
    return props


def write_properties(path: Path, props: dict[str, str]):
    lines = [f"{k}={v}" for k, v in props.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_rcon_and_eula(repo_dir: Path, rcon_port: int, rcon_password: str):
    sp = repo_dir / "server.properties"
    props = read_properties(sp)

    changed = False
    if props.get("enable-rcon", "false").lower() != "true":
        props["enable-rcon"] = "true"
        changed = True
    if str(props.get("rcon.port", "")) != str(rcon_port):
        props["rcon.port"] = str(rcon_port)
        changed = True
    if props.get("rcon.password", "") != rcon_password:
        props["rcon.password"] = rcon_password
        changed = True
    if changed:
        write_properties(sp, props)

    # EULA
    eula = repo_dir / "eula.txt"
    eula.write_text("eula=true\n", encoding="utf-8")

    # Return useful values
    server_port = int(props.get("server-port", 25565)) if props.get("server-port") else 25565
    return server_port
