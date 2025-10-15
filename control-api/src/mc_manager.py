from __future__ import annotations

import docker
from docker.errors import NotFound, APIError
from typing import Dict, Any, Optional, Tuple
import os
import re

from .config import settings

DATA_DIR = "/data"  # path inside control-api container
from .git_sync import GitSync


class DockerMCManager:
    """
    Object-oriented wrapper for managing a Minecraft server container via Docker SDK.
    """

    def __init__(self, client: docker.DockerClient | None = None):
        self.client = client or docker.DockerClient(base_url=settings.docker_base_url)
        self.container_name = settings.mc_container_name
        self.image = settings.mc_image

    def _container(self):
        try:
            return self.client.containers.get(self.container_name)
        except NotFound:
            return None

    def desired_env(self) -> Dict[str, str]:
        env: Dict[str, str] = {
            "EULA": "TRUE" if settings.eula else "FALSE",
            "MEMORY": settings.memory,
            "TYPE": settings.server_type,
            "VERSION": settings.version,
            "ENABLE_RCON": "true" if settings.enable_rcon else "false",
            "RCON_PASSWORD": settings.rcon_password,
            "RCON_PORT": str(settings.rcon_port),
            "ENABLE_QUERY": "true",
        }
        # Prefer parsing a start script for custom jar and flags
        script_jar, jvm_opts, extra_args, memory_from_script = self.parse_start_script()
        if script_jar:
            env["TYPE"] = "CUSTOM"
            env["CUSTOM_SERVER"] = script_jar
            if memory_from_script:
                # Use memory from script if both Xmx==Xms; otherwise rely on JVM_OPTS
                env["MEMORY"] = memory_from_script
            if jvm_opts:
                env["JVM_OPTS"] = jvm_opts
            if extra_args:
                env["EXTRA_ARGS"] = extra_args
        else:
            # If a custom JAR is detected from git sync or data dir, switch to CUSTOM type
            jar = self.detect_custom_jar()
            if jar:
                env["TYPE"] = "CUSTOM"
                env["CUSTOM_SERVER"] = jar
        return env

    def detect_custom_jar(self) -> Optional[str]:
        """Return jar filename within /data to run if a custom jar is detected.
        Search order:
        - server.jar
        - paper-*.jar, purpur-*.jar, fabric-*.jar, forge-*.jar
        - Any single .jar in /data if unambiguous
        """
        data_dir = DATA_DIR
        candidates: list[str] = []
        try:
            for name in os.listdir(data_dir):
                if name.endswith(".jar"):
                    candidates.append(name)
        except FileNotFoundError:
            return None
        # prefer server.jar
        if "server.jar" in candidates:
            return "server.jar"
        for prefix in ("paper-", "purpur-", "fabric-", "forge-", "spigot-", "vanilla-", "quilt-"):
            for c in candidates:
                if c.startswith(prefix):
                    return c
        if len(candidates) == 1:
            return candidates[0]
        return None

    def enforce_server_properties(self) -> None:
        """Ensure server.properties has the correct RCON and server-port settings.
        This will add or update:
          rcon.port, rcon.password, enable-rcon, server-port
        """
        path = os.path.join(DATA_DIR, "server.properties")
        props: Dict[str, str] = {}
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        props[k] = v
        # set enforced values
        props["enable-rcon"] = "true" if settings.enable_rcon else "false"
        props["rcon.password"] = settings.rcon_password
        props["rcon.port"] = str(settings.rcon_port)
        props["server-port"] = str(settings.server_port)
        # write back
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for k, v in props.items():
                f.write(f"{k}={v}\n")

    def parse_start_script(self) -> Tuple[Optional[str], str, str, Optional[str]]:
        """Parse start.sh or start.bat for a simple 'java ... -jar X.jar ...' command.
        Returns: (jar_name, jvm_opts, extra_args, memory_from_script)
        - jar_name: basename within /data to run
        - jvm_opts: e.g. '-Xms2G -Xmx2G' if Xms/Xmx differ or need explicit flags
        - extra_args: e.g. 'nogui'
        - memory_from_script: if Xmx==Xms like '2G', we set MEMORY to this for itzg image
        """
        data_dir = DATA_DIR
        for fname in ("start.sh", "start.bat"):
            path = os.path.join(data_dir, fname)
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception:
                continue
            # Collapse naive line continuations (\\ for sh, ^ for bat)
            content = re.sub(r"\\\n", " ", content)
            content = re.sub(r"\^\r?\n", " ", content)
            # Find 'java ... -jar <file.jar> ...'
            m = re.search(r"java[^\n]*?-jar\s+([\w\-./\\:]+\.jar)([^\n]*)", content, flags=re.IGNORECASE)
            if not m:
                # Try across lines more flexibly
                m = re.search(r"java[\s\S]*?-jar\s+([\w\-./\\:]+\.jar)([\s\S]*?)\n", content, flags=re.IGNORECASE)
            if not m:
                continue
            jar_path = m.group(1).strip().strip('"')
            tail = m.group(2) if len(m.groups()) >= 2 else ""
            jar_name = os.path.basename(jar_path)
            # Extract -Xms and -Xmx from the whole java command region
            java_segment_match = re.search(r"java([^\n]*)", content, flags=re.IGNORECASE)
            segment = java_segment_match.group(0) if java_segment_match else content
            xmx = None
            xms = None
            xmx_m = re.search(r"-Xmx(\S+)", segment)
            xms_m = re.search(r"-Xms(\S+)", segment)
            if xmx_m:
                xmx = xmx_m.group(1)
            if xms_m:
                xms = xms_m.group(1)
            nogui = False
            if re.search(r"\bnogui\b", segment + " " + tail, flags=re.IGNORECASE):
                nogui = True
            jvm_opts_parts = []
            memory_from_script: Optional[str] = None
            if xmx and xms and xmx == xms:
                memory_from_script = xmx
            else:
                if xms:
                    jvm_opts_parts.append(f"-Xms{xms}")
                if xmx:
                    jvm_opts_parts.append(f"-Xmx{xmx}")
            jvm_opts = " ".join(jvm_opts_parts)
            extra_args = "nogui" if nogui else ""
            return jar_name, jvm_opts, extra_args, memory_from_script
        return None, "", "", None

    def ensure_container(self) -> docker.models.containers.Container:
        # Pre-start: git sync and server.properties enforcement
        gs = GitSync()
        if gs.configured():
            gs.ensure_repo()
            gs.pull()
        self.enforce_server_properties()
        container = self._container()
        if container:
            return container
        # Create the container with proper binds and ports
        binds = {settings.mc_data_dir: {"bind": "/data", "mode": "rw"}}
        port_bindings = {"25565/tcp": settings.server_port, "25565/udp": settings.server_port}
        container = self.client.containers.create(
            self.image,
            name=self.container_name,
            detach=True,
            environment=self.desired_env(),
            volumes=binds,
            ports=port_bindings,
            restart_policy={"Name": "unless-stopped"},
        )
        return container

    def start(self) -> Dict[str, Any]:
        container = self.ensure_container()
        if container.status != "running":
            container.start()
            container.reload()
        return {"status": container.status, "id": container.id}

    def stop(self) -> Dict[str, Any]:
        container = self._container()
        if not container:
            return {"status": "not-found"}
        if container.status == "running":
            container.stop(timeout=30)
            container.reload()
        return {"status": container.status}

    def restart(self) -> Dict[str, Any]:
        # Ensure latest content and properties before restart
        gs = GitSync()
        if gs.configured():
            gs.pull()
        self.enforce_server_properties()
        container = self._container() or self.ensure_container()
        container.restart(timeout=30)
        container.reload()
        return {"status": container.status}

    def status(self) -> Dict[str, Any]:
        container = self._container()
        if not container:
            return {"status": "not-created"}
        container.reload()
        return {
            "status": container.status,
            "id": container.id,
            "name": container.name,
            "image": container.image.tags,
        }
