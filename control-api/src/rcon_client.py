from __future__ import annotations

from contextlib import contextmanager
from typing import List
import socket

from mcrcon import MCRcon

from .config import settings


class RconClient:
    def __init__(self, host: str | None = None, port: int | None = None, password: str | None = None):
        self.host = host or settings.rcon_host
        self.port = port or settings.rcon_port
        self.password = password or settings.rcon_password

    @contextmanager
    def connect(self):
        client = MCRcon(self.host, self.password, port=self.port)
        client.connect()
        try:
            yield client
        finally:
            try:
                client.disconnect()
            except Exception:
                pass

    def list_players(self) -> List[str]:
        # use the /list command, parse output like: "There are 0 of a max of 20 players online:"
        with self.connect() as c:
            resp = c.command("list")
        # naive parse
        parts = resp.split(":")
        if len(parts) > 1:
            names = parts[1].strip()
            return [n.strip() for n in names.split(",") if n.strip()] if names else []
        return []

    def run_command(self, cmd: str) -> str:
        with self.connect() as c:
            return c.command(cmd)

    def send_message(self, message: str, target: str | None = None) -> str:
        # If target provided, use tell, else use say
        with self.connect() as c:
            if target:
                return c.command(f"tell {target} {message}")
            return c.command(f"say {message}")
