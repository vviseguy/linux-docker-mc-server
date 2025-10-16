from __future__ import annotations
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from pathlib import Path
from .settings import settings
from .state import runtime


_scheduler: BackgroundScheduler | None = None


def _autosave_job():
    # Git disabled; no autosave
    return


def start_scheduler():
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    cfg = settings.config
    sched = BackgroundScheduler(timezone="UTC")
    # Keep a no-op job to exercise scheduler if needed, but it's effectively disabled
    sched.add_job(_autosave_job, "interval", seconds=cfg.sync_interval_seconds, id="autosave", replace_existing=True)
    sched.start()
    _scheduler = sched
    return sched


def shutdown_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
