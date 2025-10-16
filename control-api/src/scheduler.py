from __future__ import annotations
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from pathlib import Path
from .settings import settings
from .state import runtime
from .services.git_ops import GitManager


_scheduler: BackgroundScheduler | None = None


def _autosave_job():
    cfg = settings.config
    if not runtime.session_branch:
        return
    from .settings import settings as _settings

    workdir = _settings.root / cfg.repo.path
    gm = GitManager(
        workdir=workdir,
        repo_url=cfg.repo.url,
        main_branch=cfg.repo.branch,
        sessions_prefix=cfg.repo.session_branch_prefix,
    )
    try:
        gm.ensure_clone()
        gm.commit_all("Autosave")
        gm.push(runtime.session_branch)
    except Exception:
        # Best-effort autosave; we can log to file later
        pass


def start_scheduler():
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    cfg = settings.config
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(_autosave_job, "interval", seconds=cfg.sync_interval_seconds, id="autosave", replace_existing=True)
    sched.start()
    _scheduler = sched
    return sched


def shutdown_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
