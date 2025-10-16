from __future__ import annotations
from pathlib import Path
from datetime import datetime
from git import Repo
import os
import json
import time
from uuid import uuid4


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
        def _inject_auth(url: str) -> str:
            if self.token and self.username and url.startswith("https://"):
                return url.replace("https://", f"https://{self.username}:{self.token}@")
            return url

        if (self.workdir / ".git").exists():
            self.repo = Repo(self.workdir)
            # If using HTTPS and creds provided, ensure remote URL has auth injected
            try:
                origin = self.repo.remotes.origin
                current_url = list(origin.urls)[0]
                desired_url = _inject_auth(self.repo_url)
                if desired_url != current_url and desired_url.startswith("https://"):
                    origin.set_url(desired_url)
            except Exception:
                pass
        else:
            self.workdir.parent.mkdir(parents=True, exist_ok=True)
            url = _inject_auth(self.repo_url)
            self.repo = Repo.clone_from(url, self.workdir)
        return self.repo

    # Helper to dispatch to a host-side git agent via data/.ctl when available
    def _agent_available(self) -> bool:
        ctl = self.workdir / ".ctl"
        return ctl.exists() and (ctl / "requests").exists()

    def _enqueue_request(self, action: str, args: dict | None = None, timeout: int = 30) -> dict:
        ctl = self.workdir / ".ctl"
        req_dir = ctl / "requests"
        res_dir = ctl / "responses"
        req_dir.mkdir(parents=True, exist_ok=True)
        res_dir.mkdir(parents=True, exist_ok=True)
        rid = str(uuid4())
        payload = {
            "id": rid,
            "action": action,
            "workdir": str(self.workdir),
            "args": args or {},
        }
        req_file = req_dir / f"{rid}.json"
        res_file = res_dir / f"{rid}.json"
        req_file.write_text(json.dumps(payload), encoding="utf-8")

        # Wait for response
        wait_until = time.time() + timeout
        while time.time() < wait_until:
            if res_file.exists():
                try:
                    txt = res_file.read_text(encoding="utf-8")
                    res = json.loads(txt)
                finally:
                    # cleanup
                    try:
                        res_file.unlink()
                    except Exception:
                        pass
                return res
            time.sleep(0.5)
        return {"id": rid, "ok": False, "err": "timeout waiting for agent", "rc": 252}

    def pull_main(self):
        assert self.repo
        # If host agent is available, delegate pull to it
        if self._agent_available():
            self._enqueue_request("pull", {"branch": self.main_branch})
            return
        self.repo.git.fetch("origin")
        self.repo.git.checkout(self.main_branch)
        self.repo.git.pull("origin", self.main_branch)

    def create_session_branch(self) -> str:
        assert self.repo
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        name = f"{self.sessions_prefix}/{ts}"
        if self._agent_available():
            res = self._enqueue_request("create_session_branch", {"prefix": self.sessions_prefix})
            if res.get("ok"):
                return res.get("payload", {}).get("session_branch", name)
            # fall through to local
        self.repo.git.checkout("-b", name)
        return name

    def commit_all(self, message: str):
        assert self.repo
        if self._agent_available():
            self._enqueue_request("commit_all", {"message": message})
            return
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
        if self._agent_available():
            self._enqueue_request("push", {"branch": current})
            return
        self.repo.git.push("origin", current)

    def merge_to_main_overwrite_current(self, session_branch: str):
        assert self.repo
        if self._agent_available():
            self._enqueue_request(
                "merge_to_main_overwrite_current", {"session_branch": session_branch, "main_branch": self.main_branch}
            )
            return
        self.repo.git.checkout(self.main_branch)
        try:
            # prefer "theirs" (session) on conflicts while on main
            self.repo.git.merge("-X", "theirs", session_branch)
        except Exception:
            # fallback: force main to session's commit
            self.repo.git.reset("--hard", session_branch)
        self.push(self.main_branch)
