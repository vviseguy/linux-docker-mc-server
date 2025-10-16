from __future__ import annotations
from mcrcon import MCRcon
from contextlib import contextmanager


@contextmanager
def rcon_conn(host: str, port: int, password: str):
    rc = MCRcon(host, password, port=port)
    rc.connect()
    try:
        yield rc
    finally:
        rc.disconnect()


def list_players(host: str, port: int, password: str) -> list[str]:
    with rcon_conn(host, port, password) as rc:
        resp = rc.command("list")
        # Typical: "There are 0 of a max of 20 players online:"
        # Or: "There are 2 of a max of 20 players online: player1, player2"
        if ":" in resp:
            names = resp.split(":", 1)[1].strip()
            if names:
                return [n.strip() for n in names.split(",") if n.strip()]
        return []


def say(host: str, port: int, password: str, message: str) -> str:
    with rcon_conn(host, port, password) as rc:
        return rc.command(f"say {message}")


def run_command(host: str, port: int, password: str, cmd: str) -> str:
    with rcon_conn(host, port, password) as rc:
        return rc.command(cmd)
