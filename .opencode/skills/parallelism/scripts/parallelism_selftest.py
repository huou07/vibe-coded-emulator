#!/usr/bin/env python3
"""Deterministic self-tests for the 'parallelism' skill (v1.1). No LLM workers.

Spawn is exercised with a mock launcher (PARALLELISM_LAUNCHER) so no real
provider/model calls are made.
"""
from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "parallelism.py")
results = {}


def run(args, cwd=None, env=None):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True,
                          cwd=cwd, env=env)


def alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def main():
    tmp = tempfile.mkdtemp(prefix="parallelism-selftest-")
    subprocess.run(["git", "init", "-q", tmp], check=True)
    genv = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "-C", tmp, "commit", "-q", "--allow-empty", "-m", "base"],
                   check=True, env=genv)

    slow = os.path.join(tmp, "slow.sh")
    quick = os.path.join(tmp, "quick.sh")
    for path, body in ((slow, "#!/bin/sh\nsleep 120\n"), (quick, "#!/bin/sh\nexit 0\n")):
        with open(path, "w") as fh:
            fh.write(body)
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)

    def t(args, env=None):
        return run(["--repo", tmp, *args], env=env)

    def env_launcher(path):
        return {**os.environ, "PARALLELISM_LAUNCHER": path}

    # 1: default is zero helpers
    results["A_zero_helpers"] = "PASS" if json.loads(t(["status"]).stdout)["count"] == 0 else "FAIL"

    # 2: parallelization decision is deterministic, no LLM
    par = json.loads(t(["decide", "--tasks", "3", "--independence", "high", "--overlap", "low",
                        "--init-cost", "low", "--integration-cost", "low"]).stdout)
    seq = json.loads(t(["decide", "--tasks", "1", "--independence", "high", "--overlap", "low",
                        "--init-cost", "low", "--integration-cost", "low"]).stdout)
    results["B_parallelization_decision"] = (
        "PASS" if par["recommendation"] == "parallel" and seq["recommendation"] == "sequential" else "FAIL")

    # 3: spawn refuses without a resolvable model
    r = t(["spawn", "--name", "x", "--assignment", "/nonexistent"])
    results["C_no_model_no_spawn"] = "PASS" if r.returncode != 0 and "model" in (r.stdout + r.stderr).lower() else "FAIL"

    # 3-6: spawn with mock launcher -> stable id, duplicate prevention, ownership conflict
    s1 = json.loads(t(["spawn", "--name", "w1", "--id", "w1", "--model", "provA/m1",
                       "--objective", "impl a", "--owns", "src/a.py", "--accept", "a works",
                       "--tests", "unit"], env=env_launcher(slow)).stdout)
    dup = t(["spawn", "--name", "w1", "--id", "w1", "--model", "provA/m1",
             "--objective", "impl a", "--owns", "src/a.py"], env=env_launcher(slow))
    conflict = t(["spawn", "--name", "w2", "--id", "w2", "--model", "provA/m1",
                  "--objective", "impl b", "--owns", "src/a.py"], env=env_launcher(slow))
    st = json.loads(t(["status"]).stdout)
    results["D_stable_worker_id"] = "PASS" if st["helpers"][0]["id"] == "w1" else "FAIL"
    results["E_duplicate_dispatch_prevented"] = "PASS" if dup.returncode != 0 and "already running" in dup.stdout else "FAIL"
    results["F_ownership_conflict_rejected"] = "PASS" if conflict.returncode != 0 and "ownership conflict" in conflict.stdout else "FAIL"

    # 7: recovery after an interrupted Master (worker pid died)
    os.kill(int(s1["pid"]), signal.SIGKILL)
    time.sleep(0.3)
    noresume = t(["spawn", "--name", "w1", "--id", "w1", "--model", "provA/m1",
                  "--objective", "impl a"], env=env_launcher(slow))
    resume = t(["spawn", "--name", "w1", "--id", "w1", "--model", "provA/m1",
                "--objective", "impl a", "--resume"], env=env_launcher(slow))
    s1b = json.loads(resume.stdout) if resume.returncode == 0 else {}
    results["G_recovery_reconcile"] = (
        "PASS" if noresume.returncode != 0 and "interrupted" in noresume.stdout
        and resume.returncode == 0 and s1b.get("pid") else "FAIL")
    if s1b.get("pid"):
        os.kill(int(s1b["pid"]), signal.SIGKILL)

    # 4: event-driven wait returns on process exit (mock launcher, no LLM)
    q = json.loads(t(["spawn", "--name", "wq", "--id", "wq", "--model", "provA/m1",
                      "--objective", "quick"], env=env_launcher(quick)).stdout)
    start = time.time()
    w = t(["wait", "--name", "wq", "--timeout", "10"])
    results["H_event_driven_wait"] = (
        "PASS" if w.returncode == 0 and time.time() - start < 8 else "FAIL")

    # 6: worker completion + blocker via compact result
    resfile = os.path.join(tmp, "result.json")
    with open(resfile, "w") as fh:
        json.dump({"status": "BLOCKED", "commit": "none", "tests": "unverified",
                   "acceptance": "n/a", "blockers": ["missing fixture"]}, fh)
    rr = json.loads(t(["result", "--name", "wq", "--file", resfile]).stdout)
    results["I_worker_result_ingested"] = (
        "PASS" if rr["status"] == "BLOCKED" and rr["result"]["blockers"] == ["missing fixture"] else "FAIL")

    # 4/9: model resolution + switching with no code change
    a = json.loads(t(["resolve-model", "--model", "provA/model-1"]).stdout)["model"]
    b = json.loads(t(["resolve-model", "--model", "provB/model-2"]).stdout)["model"]
    results["J_model_switch"] = "PASS" if (a, b) == ("provA/model-1", "provB/model-2") else "FAIL"

    # 11: no-progress parking
    t(["checkpoint", "--name", "stuck", "--status", "WORKING", "--commit", "abc"])
    for _ in range(3):
        last = json.loads(t(["progress", "--name", "stuck", "--limit", "2"]).stdout)
    results["K_no_progress_parks"] = (
        "PASS" if last["action"] == "park" and last["status"] == "BLOCKED" and last["redispatch"] is False else "FAIL")

    # 9/10: no duplicate checkpoints
    t(["checkpoint", "--name", "dup", "--status", "WORKING"])
    t(["checkpoint", "--name", "dup", "--status", "VALIDATING"])
    st = json.loads(t(["status"]).stdout)
    results["L_no_duplicate_records"] = (
        "PASS" if [h["name"] for h in st["helpers"]].count("dup") == 1 else "FAIL")

    # 7/11: exclusive integration writer + no auto-merge of unvalidated commits
    me = os.getpid()
    first = json.loads(t(["lock", "acquire", "--name", "integration", "--pid", str(me)]).stdout)
    second = t(["lock", "acquire", "--name", "integration", "--pid", str(me)])
    nomerge = t(["premerge", "--candidate", "HEAD", "--tests", "unit fail"])
    okmerge = t(["premerge", "--candidate", "HEAD", "--tests", "unit pass"])
    rel = json.loads(t(["lock", "release", "--name", "integration", "--pid", str(me)]).stdout)
    results["M_exclusive_writer"] = "PASS" if first.get("acquired") and second.returncode != 0 else "FAIL"
    results["N_no_unvalidated_merge"] = (
        "PASS" if nomerge.returncode != 0 and okmerge.returncode == 0 and rel.get("released") else "FAIL")

    # 12: real session model verification (no LLM call) when a session is provided
    sid = os.environ.get("PARALLELISM_TEST_SESSION")
    if sid:
        expected = os.environ.get("PARALLELISM_TEST_MODEL", "opencode-go/deepseek-v4.1-flash")
        r = run(["verify-model", "--session", sid, "--expect", expected])
        results["O_model_inheritance_verified"] = "PASS" if r.returncode == 0 else "FAIL"
    else:
        results["O_model_inheritance_verified"] = "SKIP (set PARALLELISM_TEST_SESSION)"

    print(json.dumps(results, indent=2, sort_keys=True))
    failed = [k for k, v in results.items() if str(v).startswith("FAIL")]
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
