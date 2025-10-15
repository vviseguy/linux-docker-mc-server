from __future__ import annotations

import os
import subprocess
import time
from typing import Optional

from .config import settings

DATA_DIR = "/data"

class GitSync:
    def __init__(self, repo_url: Optional[str] = None, branch: Optional[str] = None):
        self.repo_url = repo_url or settings.git_repo
        self.branch = branch or settings.git_branch
        self.workdir = DATA_DIR

    def configured(self) -> bool:
        return bool(self.repo_url)

    def _run(self, *args: str, cwd: Optional[str] = None, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(args, cwd=cwd, check=check, capture_output=True, text=True)

    def ensure_repo(self) -> None:
        if not self.configured():
            return
        git_dir = os.path.join(self.workdir, ".git")
        if os.path.isdir(git_dir):
            return
        os.makedirs(self.workdir, exist_ok=True)
        # If folder is empty, clone; if not empty, init+remote+fetch+reset
        is_empty = not any(os.scandir(self.workdir))
        if is_empty:
            self._run("git", "clone", "--branch", self.branch, self.repo_url, self.workdir)
        else:
            self._run("git", "init" , cwd=self.workdir)
            self._run("git", "remote", "remove", "origin", cwd=self.workdir, check=False)
            self._run("git", "remote", "add", "origin", self.repo_url, cwd=self.workdir)
            self._run("git", "fetch", "origin", self.branch, cwd=self.workdir)
            self._run("git", "checkout", "-B", self.branch, cwd=self.workdir)
            self._run("git", "reset", "--hard", f"origin/{self.branch}", cwd=self.workdir)

    def pull(self) -> str:
        if not self.configured():
            return "git disabled"
        self.ensure_repo()
        cp = self._run("git", "pull", "--rebase", "origin", self.branch, cwd=self.workdir)
        return cp.stdout + cp.stderr

    def commit_and_push(self, message: str) -> str:
        if not self.configured() or not settings.git_auto_push:
            return "push disabled"
        # configure identity (optional)
        try:
            self._run("git", "config", "user.email", "mc-control@example" , cwd=self.workdir)
            self._run("git", "config", "user.name", "mc-control" , cwd=self.workdir)
        except Exception:
            pass
        # Add all, but optionally restore server.properties from HEAD
        self._run("git", "add", "-A", cwd=self.workdir)
        if settings.git_ignore_server_properties:
            prop = os.path.join(self.workdir, "server.properties")
            if os.path.exists(prop):
                # unstage and restore file to remote version to avoid push of local sensitive changes
                subprocess.run(["git", "restore", "--staged", "server.properties"], cwd=self.workdir)
        # Commit if there are staged changes
        cp = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=self.workdir)
        if cp.returncode != 0:
            self._run("git", "commit", "-m", message, cwd=self.workdir)
            push = self._run("git", "push", "origin", self.branch, cwd=self.workdir)
            return push.stdout + push.stderr
        return "no changes"

    def periodic_push(self, stop_event) -> None:
        # Optional background loop; not used by default
        while not stop_event.is_set():
            try:
                self.commit_and_push("Periodic save")
            except Exception:
                pass
            time.sleep(settings.git_push_interval_seconds)
