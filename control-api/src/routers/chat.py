from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..settings import settings
from ..services.docker_ops import DockerManager
from ..services.rcon_bridge import say, run_command
from ..state import runtime

router = APIRouter()


@router.websocket("/ws")
async def chat_ws(ws: WebSocket):
    await ws.accept()
    try:
        await ws.send_text("Connected to chat. Type to send, use /command for server commands.")

        dm = DockerManager()

        # Stream logs in background
        import asyncio

        loop = asyncio.get_event_loop()
        stop_flag = False

        def on_line(line: str):
            # Simple filter; forward all lines for now
            # Future: parse chat-specific lines
            try:
                loop.create_task(ws.send_text(line))
            except RuntimeError:
                pass
            if not runtime.online and "Done (" in line and ")! For help, type" in line:
                runtime.online = True

        async def logs_task():
            try:
                dm.stream_logs(settings.config.mc_container_name, on_line)
            except Exception:
                await ws.send_text("Log stream unavailable. Is the server running?")

        bg = loop.create_task(logs_task())

        while True:
            msg = await ws.receive_text()
            txt = msg.strip()
            if not txt:
                continue
            if txt.startswith("/"):
                out = run_command(
                    settings.config.rcon.host, settings.config.rcon.port, settings.config.rcon.password, txt[1:]
                )
            else:
                out = say(settings.config.rcon.host, settings.config.rcon.port, settings.config.rcon.password, txt)
            await ws.send_text(out)
    except WebSocketDisconnect:
        # Connection closed
        try:
            bg.cancel()
        except Exception:
            pass
