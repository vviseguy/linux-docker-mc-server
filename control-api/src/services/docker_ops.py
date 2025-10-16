from __future__ import annotations
import docker
from pathlib import Path
from typing import Optional
import os
import re
from pathlib import PurePosixPath


def default_java_image(java_version: int) -> str:
    return f"eclipse-temurin:{java_version}-jre"


def _parse_java_from_text(content: str) -> list[str] | None:
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    # remove comment lines for sh/bat
    lines = [l for l in lines if not l.lower().startswith("rem ") and not l.startswith("#")]
    # join lines with line continuation markers
    joined: list[str] = []
    buf = ""
    for line in lines:
        if line.endswith("^") or line.endswith("\\"):
            buf += line[:-1] + " "
        else:
            buf += line
            joined.append(buf)
            buf = ""
    if buf:
        joined.append(buf)
    for line in joined:
        if re.search(r"\bjava\b", line, re.IGNORECASE):
            parts = re.split(r"\s+", line)
            return parts
    return None


def parse_start_bat(bat_path: Path) -> list[str] | None:
    if not bat_path.exists():
        return None
    content = bat_path.read_text(encoding="utf-8", errors="ignore")
    return _parse_java_from_text(content)


def parse_start_sh(sh_path: Path) -> list[str] | None:
    if not sh_path.exists():
        return None
    content = sh_path.read_text(encoding="utf-8", errors="ignore")
    return _parse_java_from_text(content)


class DockerManager:
    def __init__(self):
        self.client = docker.from_env()

    def _container_host_path_for(self, container_path: Path) -> Optional[str]:
        """
        Translate a path inside this control-api container (e.g., /app/data/xyz)
        to the corresponding host path by inspecting this container's mounts.
        Returns None if mapping cannot be determined.
        """
        try:
            # Default to the configured container name from compose
            self_name = os.getenv("CONTROL_API_CONTAINER_NAME", "mc-control-api")
            c = self.client.containers.get(self_name)
            mounts = c.attrs.get("Mounts", [])
            c_path = str(container_path)
            best = None
            best_len = -1
            for m in mounts:
                dest = m.get("Destination")
                src = m.get("Source")
                if not dest or not src:
                    continue
                # Choose the longest matching destination prefix
                if c_path.startswith(dest) and len(dest) > best_len:
                    best = (dest, src)
                    best_len = len(dest)
            if best is None:
                return None
            dest, src = best
            rel = os.path.relpath(c_path, dest)
            host_path = os.path.normpath(os.path.join(src, rel))
            return host_path
        except Exception:
            return None

    def ensure_image(self, image: str):
        try:
            self.client.images.get(image)
        except docker.errors.ImageNotFound:
            self.client.images.pull(image)

    def start_container(
        self,
        name: str,
        repo_host_dir: Path,
        ports: dict[int, int],
        env: dict[str, str] | None,
        command: list[str],
        java_image: str,
        workdir: str = "/data",
    ):
        self.ensure_image(java_image)
        # Mount the repo as /data. If we're running inside a container, translate to host path.
        src_path = str(repo_host_dir.resolve())
        host_src = self._container_host_path_for(repo_host_dir)
        if host_src:
            src_path = host_src
        binds = {src_path: {"bind": "/data", "mode": "rw"}}
        # Default MC server ports
        port_map = {f"{p}/tcp": p for p in ports.keys()}
        container = self.client.containers.run(
            java_image,
            name=name,
            command=command,
            detach=True,
            working_dir=workdir,
            volumes=binds,
            ports=port_map,
            environment=env or {},
            stdin_open=True,
            tty=True,
        )
        return container

    def start_itzg_container(
        self,
        name: str,
        server_host_dir: Path,
        ports: dict[int, int],
        env: dict[str, str] | None,
        image: str = "itzg/minecraft-server:latest",
    ):
        self.ensure_image(image)
        src_path = str(server_host_dir.resolve())
        host_src = self._container_host_path_for(server_host_dir)
        if host_src:
            src_path = host_src
        binds = {src_path: {"bind": "/data", "mode": "rw"}}
        port_map = {f"{p}/tcp": p for p in ports.keys()}
        container = self.client.containers.run(
            image,
            name=name,
            detach=True,
            volumes=binds,
            ports=port_map,
            environment=env or {},
            stdin_open=True,
            tty=True,
        )
        return container

    def stop_container(self, name: str, timeout: int = 10):
        try:
            c = self.client.containers.get(name)
            c.stop(timeout=timeout)
            c.remove()
            return True
        except docker.errors.NotFound:
            return False

    def container_status(self, name: str) -> Optional[str]:
        try:
            c = self.client.containers.get(name)
            return c.status
        except docker.errors.NotFound:
            return None

    def stream_logs(self, name: str, on_line):
        c = self.client.containers.get(name)
        for chunk in c.logs(stream=True, follow=True, tail=10):
            try:
                line = chunk.decode("utf-8", errors="ignore").rstrip()
                if line:
                    on_line(line)
            except Exception:
                continue
