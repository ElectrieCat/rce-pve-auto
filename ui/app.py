"""Thin web UI over the existing CLI.

Architecture: the browser talks to these endpoints, the endpoints run
`python main.py <args>` in the repo root via subprocess and return the
captured output. No core logic is duplicated or rewritten here — the CLI
remains the single source of truth (see python/cli.py).

Security rules (local-only tool):
  * Bind to 127.0.0.1, never 0.0.0.0.
  * Only allowlisted subcommands; free-form `terraform-run` and interactive
    `change-password` are NOT exposed (terminal only).
  * deploy-users/deploy-lab/destroy-lab run ONLY with --plan (preview).
    The final apply happens in the terminal after reviewing the plan.
  * UI_READONLY=1 disables POST /api/run entirely (status dashboard mode).
  * Passwords/CSVs are never returned — the UI shows where the CSV lives.
"""
import os
import subprocess
import sys

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
READ_ONLY = os.environ.get("UI_READONLY", "0") == "1"
TIMEOUT_S = int(os.environ.get("UI_CMD_TIMEOUT", "600"))

# subcommand -> kind.
# 'ro'   = safe to run, output only.
# 'plan' = mutating command, exposed ONLY with --plan (preview). The final
#          apply runs in the terminal, where interactive prompts
#          (type 'destroy', yes/no) work. This keeps the UI hang-free.
# change-password is NOT exposed: it is interactive (input yes/no) and
# handles plaintext passwords — terminal only.
ALLOWLIST = {
    "status": "ro",
    "parse-test": "ro",
    "backup": "ro",
    "deploy-users": "plan",
    "deploy-lab": "plan",
    "destroy-lab": "plan",
}

app = FastAPI(title="rce-pve-auto UI")


class RunRequest(BaseModel):
    # e.g. ["deploy-lab", "minimal-lab", "--plan"]
    cmd: list


def _run_cli(args: list) -> dict:
    """Runs `python main.py ...` in REPO_ROOT, captures output."""
    if not args or args[0] not in ALLOWLIST:
        raise HTTPException(status_code=400, detail=f"Command not allowed: {args[:1]}")
    try:
        proc = subprocess.run(
            [sys.executable, "main.py", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="CLI command timed out")
    return {"rc": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}


@app.get("/")
def index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))


@app.get("/api/commands")
def commands():
    """Allowlisted commands + read-only flag (drives button state in the UI)."""
    return {"read_only": READ_ONLY, "allowlist": ALLOWLIST}


@app.get("/api/status")
def api_status(group: str = None, lab: str = None):
    args = ["status"]
    if group:
        args += ["--group", group]
    if lab:
        args += ["--lab", lab]
    return _run_cli(args)


@app.post("/api/run")
def api_run(req: RunRequest):
    if READ_ONLY:
        raise HTTPException(status_code=403, detail="UI is in read-only mode")
    if not req.cmd:
        raise HTTPException(status_code=400, detail="Empty command")
    sub, rest = req.cmd[0], req.cmd[1:]
    kind = ALLOWLIST.get(sub)
    if kind is None:
        raise HTTPException(status_code=400, detail=f"Command not allowed: {sub}")
    if kind == "plan" and "--plan" not in rest:
        raise HTTPException(
            status_code=400,
            detail="UI runs previews only — add --plan. "
            "Apply from the terminal after reviewing the plan.",
        )
    return _run_cli(req.cmd)
