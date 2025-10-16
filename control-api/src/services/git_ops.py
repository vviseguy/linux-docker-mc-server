from __future__ import annotations
from pathlib import Path
from datetime import datetime
from git import Repo
import os


class GitManager:
    def __init__(
        self,
        workdir: Path,
        repo_url: str,
        main_branch: str = "main",
        sessions_prefix: str = "sessions",
        username: str | None = None,
        token: str | None = None,
    ):
        self.workdir = Path(workdir)
        self.repo_url = repo_url
        self.main_branch = main_branch
        self.sessions_prefix = sessions_prefix
        self.repo: Repo | None = None
        self.username = username
        self.token = token

    def ensure_clone(self) -> Repo:
        if (self.workdir / ".git").exists():
            self.repo = Repo(self.workdir)
        else:
            self.workdir.parent.mkdir(parents=True, exist_ok=True)
            url = self.repo_url
            if self.token and self.username and url.startswith("https://"):
                # inject basic auth into HTTPS URL
                url = url.replace("https://", f"https://{self.username}:{self.token}@")
            self.repo = Repo.clone_from(url, self.workdir)
        return self.repo

    def pull_main(self):
        assert self.repo
        self.repo.git.fetch("origin")
        self.repo.git.checkout(self.main_branch)
        self.repo.git.pull("origin", self.main_branch)

    def create_session_branch(self) -> str:
        assert self.repo
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        name = f"{self.sessions_prefix}/{ts}"
        self.repo.git.checkout("-b", name)
        return name

    def commit_all(self, message: str):
        assert self.repo
        # ensure server.properties is ignored
        gi = self.workdir / ".gitignore"
        line = "server.properties\n"
        if gi.exists():
            txt = gi.read_text(encoding="utf-8")
            if "server.properties" not in txt:
                with gi.open("a", encoding="utf-8") as f:
                    f.write(line)
        else:
            gi.write_text(line, encoding="utf-8")

        self.repo.git.add(all=True)
        # Avoid committing uninitialized repos (no changes)
        if self.repo.is_dirty(untracked_files=True):
            self.repo.index.commit(message)

    def push(self, branch: str | None = None):
        assert self.repo
        current = branch or self.repo.active_branch.name
        self.repo.git.push("origin", current)

    def merge_to_main_overwrite_current(self, session_branch: str):
        assert self.repo
        self.repo.git.checkout(self.main_branch)
        try:
            # prefer "theirs" (session) on conflicts while on main
            self.repo.git.merge("-X", "theirs", session_branch)
        except Exception:
            # fallback: force main to session's commit
            self.repo.git.reset("--hard", session_branch)
        self.push(self.main_branch)
