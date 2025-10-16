#!/usr/bin/env python3
"""
Simple host-side Git agent.

Place this script on the host and run it (systemd, screen, tmux, etc.).
It watches the repo's `data/.ctl/requests/` directory for JSON requests from the
control-api container and executes a safe subset of git operations in the
requested repository path using the host's credentials.

This avoids providing the container with host credentials. Only whitelisted
actions are allowed.

Usage:
  python host_git_agent.py --data-dir ./data

Requests are JSON files written to:
  <data-dir>/.ctl/requests/<uuid>.json

Responses are written to:
  <data-dir>/.ctl/responses/<uuid>.json

Request format:
  {
    "id": "<uuid>",
    "action": "pull" | "push" | "clone" | "create_session_branch" | "commit_all" | "merge_to_main_overwrite_current",
    "workdir": "absolute-or-relative-path-to-repo",
    "args": { ... }
  }

Response format:
  {
    "id": "<uuid>",
    "ok": true|false,
    "rc": int,
    "out": "stdout",
    "err": "stderr",
    "payload": { ... }  # optional
  }
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4


ALLOWED_ACTIONS = {
    "clone",
    "pull",
    "create_session_branch",
    "commit_all",
    "push",
    "merge_to_main_overwrite_current",
}


def run_cmd(cmd, cwd=None):
    try:
        p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:
        return 253, "", str(e)


def ensure_dirs(base: Path):
    req = base / "requests"
    res = base / "responses"
    req.mkdir(parents=True, exist_ok=True)
    res.mkdir(parents=True, exist_ok=True)
    return req, res


def handle_request(path: Path, requests_dir: Path, responses_dir: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Failed to read request {path}: {e}", file=sys.stderr)
        path.unlink(missing_ok=True)
        return

    req_id = data.get("id") or path.stem
    action = data.get("action")
    workdir = Path(data.get("workdir", ".")).resolve()
    args = data.get("args", {}) or {}

    resp = {"id": req_id, "ok": False, "rc": 255, "out": "", "err": "", "payload": {}}

    if action not in ALLOWED_ACTIONS:
        resp.update({"err": f"action not allowed: {action}", "rc": 254})
        (responses_dir / f"{req_id}.json").write_text(json.dumps(resp), encoding="utf-8")
        path.unlink(missing_ok=True)
        return

    # Restrict workdir to be inside the data folder tree
    try:
        data_root = requests_dir.parents[1].resolve()
        if not str(workdir).startswith(str(data_root)):
            resp.update({"err": f"workdir outside allowed data root: {workdir}", "rc": 252})
            (responses_dir / f"{req_id}.json").write_text(json.dumps(resp), encoding="utf-8")
            path.unlink(missing_ok=True)
            return
    except Exception:
        pass

    print(f"[agent] {datetime.utcnow().isoformat()} handling {action} for {workdir}")

    if action == "clone":
        url = args.get("url")
        if not url:
            resp.update({"err": "missing url for clone", "rc": 251})
        else:
            workdir.parent.mkdir(parents=True, exist_ok=True)
            rc, out, err = run_cmd(["git", "clone", url, str(workdir)])
            resp.update({"rc": rc, "out": out, "err": err, "ok": rc == 0})

    elif action == "pull":
        branch = args.get("branch", "main")
        rc, out, err = run_cmd(["git", "fetch", "origin"], cwd=workdir)
        if rc == 0:
            rc2, out2, err2 = run_cmd(["git", "checkout", branch], cwd=workdir)
            if rc2 == 0:
                rc3, out3, err3 = run_cmd(["git", "pull", "origin", branch], cwd=workdir)
                rc, out, err = rc3, out3, err3
            else:
                rc, out, err = rc2, out2, err2
        resp.update({"rc": rc, "out": out, "err": err, "ok": rc == 0})

    elif action == "create_session_branch":
        prefix = args.get("prefix", "sessions")
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        branch = f"{prefix}/{ts}"
        rc, out, err = run_cmd(["git", "checkout", "-b", branch], cwd=workdir)
        resp.update({"rc": rc, "out": out, "err": err, "ok": rc == 0, "payload": {"session_branch": branch}})

    elif action == "commit_all":
        message = args.get("message", "autosave")
        gi = workdir / ".gitignore"
        if not gi.exists() or "server.properties" not in gi.read_text(encoding="utf-8"):
            try:
                with gi.open("a", encoding="utf-8") as f:
                    f.write("server.properties\n")
            except Exception:
                pass

        rc1, out1, err1 = run_cmd(["git", "add", "-A"], cwd=workdir)
        rc2, out2, err2 = run_cmd(["git", "status", "--porcelain"], cwd=workdir)
        if rc2 == 0 and out2.strip():
            rc3, out3, err3 = run_cmd(["git", "commit", "-m", message], cwd=workdir)
            rc, out, err = rc3, out3, err3
        else:
            rc, out, err = 0, "no changes", ""
        resp.update({"rc": rc, "out": out, "err": err, "ok": rc == 0})

    elif action == "push":
        branch = args.get("branch")
        if not branch:
            resp.update({"err": "missing branch for push", "rc": 251})
        else:
            rc, out, err = run_cmd(["git", "push", "origin", branch], cwd=workdir)
            resp.update({"rc": rc, "out": out, "err": err, "ok": rc == 0})

    elif action == "merge_to_main_overwrite_current":
        session_branch = args.get("session_branch")
        main_branch = args.get("main_branch", "main")
        if not session_branch:
            resp.update({"err": "missing session_branch", "rc": 251})
        else:
            rc, out, err = run_cmd(["git", "checkout", main_branch], cwd=workdir)
            if rc == 0:
                rc2, out2, err2 = run_cmd(["git", "merge", "-X", "theirs", session_branch], cwd=workdir)
                if rc2 != 0:
                    rc3, out3, err3 = run_cmd(["git", "reset", "--hard", session_branch], cwd=workdir)
                    rc, out, err = rc3, out3, err3
                else:
                    rc, out, err = rc2, out2, err2
            resp.update({"rc": rc, "out": out, "err": err, "ok": rc == 0})

    # Write response and remove request
    (responses_dir / f"{req_id}.json").write_text(json.dumps(resp), encoding="utf-8")
    path.unlink(missing_ok=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", default=os.getenv("DATA_DIR", "./data"), help="Path to the repo data folder")
    args = p.parse_args()

    base = Path(args.data_dir) / ".ctl"
    req_dir, res_dir = ensure_dirs(base)

    print("Host Git Agent running. Watching:", req_dir)
    try:
        while True:
            entries = sorted(req_dir.glob("*.json"))
            for ent in entries:
                try:
                    handle_request(ent, req_dir, res_dir)
                except Exception as e:
                    print(f"Error handling {ent}: {e}", file=sys.stderr)
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("shutting down")


if __name__ == "__main__":
    main()
