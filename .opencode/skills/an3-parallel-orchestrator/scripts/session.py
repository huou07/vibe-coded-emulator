#!/usr/bin/env python3
"""Deterministic OpenCode session launcher for the AN3 orchestrator.

Wraps `opencode run` so the orchestrator gets a recorded session id, a log file
under the run state, and a machine-readable result instead of hand-rolled shell.

Usage:
  session.py start --run-id ID --domain D --worktree PATH --prompt-file FILE [--agent an3-worker] [--repo P]
  session.py send  --session-id ID --prompt-file FILE [--repo P] [--timeout S]
  session.py status --run-id ID [--repo P]

`start` launches the session detached and returns as soon as the session id is
known, so several workers can run concurrently. The model is always the canonical
DeepSeek V4.1 Flash; there is no fallback.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import orchestrator_lib as lib  # noqa: E402

CFG = lib.load_config()


def _opencode() -> str:
    return CFG["sessions"]["binary"]


def _base_cmd(agent, model):
    return [_opencode(), "run", "--format", "json", "--agent", agent, "--model", model]


def _read_prompt(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def cmd_start(args):
    repo = lib.find_repo_root(args.repo)
    lib.validate_run_id(args.run_id)
    lib.validate_domain(args.domain)
    agent = args.agent or CFG["sessions"]["defaultAgent"]
    model = args.model or lib.CANONICAL_MODEL
    if model != lib.CANONICAL_MODEL:
        lib.fail("model must be %s" % lib.CANONICAL_MODEL, code=64)
    if not os.path.isdir(args.worktree):
        lib.fail("worktree does not exist: %s" % args.worktree, code=4)
    sessions_dir = os.path.join(lib.run_dir(repo, args.run_id), "sessions")
    os.makedirs(sessions_dir, exist_ok=True)
    log_path = os.path.join(sessions_dir, "%s.ndjson" % args.domain)
    err_path = os.path.join(sessions_dir, "%s.err" % args.domain)
    prompt = _read_prompt(args.prompt_file)
    cmd = _base_cmd(agent, model) + ["--dir", args.worktree,
                                     "--title", "%s-%s" % (args.run_id, args.domain), prompt]
    log_handle = open(log_path, "w", encoding="utf-8")
    err_handle = open(err_path, "w", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=log_handle, stderr=err_handle,
                            start_new_session=True)
    session_id = None
    deadline = time.time() + args.wait
    while time.time() < deadline:
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if event.get("sessionID"):
                        session_id = event["sessionID"]
                        break
        if session_id:
            break
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    # record in run state
    state_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "orchestrator_state.py")
    record = [sys.executable, state_script, "--repo", repo, "add-session",
              "--run-id", args.run_id, "--domain", args.domain,
              "--session-id", session_id or "UNKNOWN", "--worktree", args.worktree,
              "--branch", args.branch or "UNKNOWN", "--pid", str(proc.pid),
              "--model", model]
    subprocess.run(record, capture_output=True, text=True)
    if not session_id and proc.poll() is not None:
        lib.emit({"ok": False, "started": False, "rc": proc.returncode,
                  "log": log_path, "errorLog": err_path,
                  "error": "session exited before producing an id"}, exit_code=1)
    lib.emit({"ok": True, "started": True, "domain": args.domain, "sessionId": session_id,
              "pid": proc.pid, "log": log_path, "errorLog": err_path,
              "agent": agent, "model": model,
              "sessionIdPending": session_id is None})


def cmd_send(args):
    model = lib.CANONICAL_MODEL
    prompt = _read_prompt(args.prompt_file)
    cmd = _base_cmd(args.agent or CFG["sessions"]["defaultAgent"], model)
    cmd += ["--session", args.session_id, prompt]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=args.timeout)
    except subprocess.TimeoutExpired:
        lib.emit({"ok": False, "sent": False, "error": "timeout"}, exit_code=1)
    lib.emit({"ok": proc.returncode == 0, "sent": True, "rc": proc.returncode,
              "stdoutTail": proc.stdout[-2000:], "stderrTail": proc.stderr[-1000:]})


def cmd_status(args):
    repo = lib.find_repo_root(args.repo)
    rdir = lib.run_dir(repo, args.run_id)
    sessions_path = os.path.join(rdir, "sessions.json")
    sessions = lib.read_json(sessions_path) if os.path.exists(sessions_path) else {}
    out = []
    for domain, session in sessions.items():
        log_path = os.path.join(rdir, "sessions", "%s.ndjson" % domain)
        last_type, tail = None, ""
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    try:
                        event = json.loads(line)
                        last_type = event.get("type", last_type)
                    except ValueError:
                        continue
            tail = last_type or ""
        out.append({"domain": domain, "pidAlive": lib.is_pid_alive(session.get("pid")),
                    "sessionId": session.get("sessionId"), "lastEvent": tail})
    lib.emit({"ok": True, "runId": args.run_id, "sessions": out})


def build_parser():
    parser = argparse.ArgumentParser(description="AN3 orchestrator sessions")
    parser.add_argument("--repo", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("start")
    p.add_argument("--run-id", required=True)
    p.add_argument("--domain", required=True)
    p.add_argument("--worktree", required=True)
    p.add_argument("--prompt-file", required=True)
    p.add_argument("--branch")
    p.add_argument("--agent")
    p.add_argument("--model")
    p.add_argument("--wait", type=float, default=30.0)
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("send")
    p.add_argument("--session-id", required=True)
    p.add_argument("--prompt-file", required=True)
    p.add_argument("--agent")
    p.add_argument("--timeout", type=float, default=900.0)
    p.set_defaults(func=cmd_send)

    p = sub.add_parser("status")
    p.add_argument("--run-id", required=True)
    p.set_defaults(func=cmd_status)
    return parser


def main():
    args = build_parser().parse_args()
    try:
        args.func(args)
    except lib.OrchestratorError as exc:
        lib.fail(exc.message, code=exc.code, **exc.detail)


if __name__ == "__main__":
    main()
