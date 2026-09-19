#!/usr/bin/env python3
"""Deterministic self-tests for the 'parallelism' skill (v1.2). No LLM workers.

Spawn is exercised with a mock launcher (PARALLELISM_LAUNCHER); tests never call
a real provider.
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


def main():
    tmp = tempfile.mkdtemp(prefix="parallelism-selftest-")
    support = tempfile.mkdtemp(prefix="parallelism-support-")
    genv = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "init", "-q", tmp], check=True)

    def gitc(*args):
        return subprocess.run(["git", "-C", tmp, *args], capture_output=True, text=True, env=genv)

    def commit(msg):
        gitc("add", "-A")
        gitc("commit", "-q", "--allow-empty", "-m", msg)
        return gitc("rev-parse", "HEAD").stdout.strip()

    c0 = commit("base")
    with open(os.path.join(tmp, "mod.py"), "w") as fh:
        fh.write("x=1\n")
    c1 = commit("mod")
    with open(os.path.join(tmp, "app.py"), "w") as fh:
        fh.write("y=1\n")
    c2 = commit("app")
    os.makedirs(os.path.join(tmp, "weird"))
    with open(os.path.join(tmp, "weird", "thing.py"), "w") as fh:
        fh.write("z=1\n")
    c3 = commit("weird")

    testmap = os.path.join(support, "map.json")
    with open(testmap, "w") as fh:
        json.dump({"full": ["full-suite"], "shared": ["app.py"],
                   "rules": [{"match": "mod.py", "tests": ["unit mod"]}]}, fh)

    slow = os.path.join(support, "slow.sh")
    quick = os.path.join(support, "quick.sh")
    for path, body in ((slow, "#!/bin/sh\nsleep 120\n"), (quick, "#!/bin/sh\nexit 0\n")):
        with open(path, "w") as fh:
            fh.write(body)
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)

    def t(args, env=None):
        return run(["--repo", tmp, *args], env=env)

    def launcher(path):
        return {**os.environ, "PARALLELISM_LAUNCHER": path}

    # ---- v1.1 regression coverage (preserved) -----------------------------
    results["A_zero_helpers"] = "PASS" if json.loads(t(["status"]).stdout)["count"] == 0 else "FAIL"
    par = json.loads(t(["decide", "--tasks", "3", "--independence", "high", "--overlap", "low",
                        "--init-cost", "low", "--integration-cost", "low"]).stdout)
    seq = json.loads(t(["decide", "--tasks", "1", "--independence", "high", "--overlap", "low",
                        "--init-cost", "low", "--integration-cost", "low"]).stdout)
    results["B_parallelization_decision"] = "PASS" if par["recommendation"] == "parallel" and seq["recommendation"] == "sequential" else "FAIL"
    r = t(["spawn", "--name", "x", "--assignment", "/nonexistent"])
    results["C_no_model_no_spawn"] = "PASS" if r.returncode != 0 and "model" in (r.stdout + r.stderr).lower() else "FAIL"

    s1 = json.loads(t(["spawn", "--name", "w1", "--id", "w1", "--model", "provA/m1",
                       "--objective", "impl", "--owns", "src/a.py", "--group", "g1",
                       "--accept", "a", "--tests", "unit"], env=launcher(slow)).stdout)
    dup = t(["spawn", "--name", "w1", "--id", "w1", "--model", "provA/m1", "--objective", "impl",
             "--owns", "src/a.py"], env=launcher(slow))
    conflict = t(["spawn", "--name", "w2", "--id", "w2", "--model", "provA/m1", "--objective", "impl",
                  "--owns", "src/a.py"], env=launcher(slow))
    results["D_stable_worker_id"] = "PASS" if json.loads(t(["status"]).stdout)["helpers"][0]["id"] == "w1" else "FAIL"
    results["E_duplicate_dispatch_prevented"] = "PASS" if dup.returncode != 0 and "already running" in dup.stdout else "FAIL"
    results["F_ownership_conflict_rejected"] = "PASS" if conflict.returncode != 0 and "ownership conflict" in conflict.stdout else "FAIL"

    os.kill(int(s1["pid"]), signal.SIGKILL)
    time.sleep(0.3)
    noresume = t(["spawn", "--name", "w1", "--id", "w1", "--model", "provA/m1", "--objective", "impl"],
                 env=launcher(slow))
    resume = t(["spawn", "--name", "w1", "--id", "w1", "--model", "provA/m1", "--objective", "impl",
                "--resume"], env=launcher(slow))
    s1b = json.loads(resume.stdout) if resume.returncode == 0 else {}
    results["G_recovery_reconcile"] = "PASS" if noresume.returncode != 0 and "interrupted" in noresume.stdout and s1b.get("pid") else "FAIL"
    if s1b.get("pid"):
        os.kill(int(s1b["pid"]), signal.SIGKILL)

    json.dumps(t(["spawn", "--name", "wq", "--id", "wq", "--model", "provA/m1", "--objective", "quick"],
                 env=launcher(quick)).stdout)
    start = time.time()
    w = t(["wait", "--name", "wq", "--timeout", "10"])
    results["H_event_driven_wait"] = "PASS" if w.returncode == 0 and time.time() - start < 8 else "FAIL"

    resfile = os.path.join(support, "result.json")
    with open(resfile, "w") as fh:
        json.dump({"status": "BLOCKED", "commit": "none", "tests": "unverified",
                   "acceptance": "n/a", "blockers": ["missing fixture"]}, fh)
    rr = json.loads(t(["result", "--name", "wq", "--file", resfile]).stdout)
    results["I_worker_result_ingested"] = "PASS" if rr["status"] == "BLOCKED" and rr["result"]["blockers"] == ["missing fixture"] else "FAIL"

    a = json.loads(t(["resolve-model", "--model", "provA/model-1"]).stdout)["model"]
    b = json.loads(t(["resolve-model", "--model", "provB/model-2"]).stdout)["model"]
    results["J_model_switch"] = "PASS" if (a, b) == ("provA/model-1", "provB/model-2") else "FAIL"

    t(["checkpoint", "--name", "stuck", "--status", "WORKING", "--commit", "abc"])
    for _ in range(3):
        last = json.loads(t(["progress", "--name", "stuck", "--limit", "2"]).stdout)
    results["K_no_progress_parks"] = "PASS" if last["action"] == "park" and last["status"] == "BLOCKED" and last["redispatch"] is False else "FAIL"

    t(["checkpoint", "--name", "dup", "--status", "WORKING"])
    t(["checkpoint", "--name", "dup", "--status", "VALIDATING"])
    st = json.loads(t(["status"]).stdout)
    results["L_no_duplicate_records"] = "PASS" if [h["name"] for h in st["helpers"]].count("dup") == 1 else "FAIL"

    me = os.getpid()
    first = json.loads(t(["lock", "acquire", "--name", "integration", "--pid", str(me)]).stdout)
    second = t(["lock", "acquire", "--name", "integration", "--pid", str(me)])
    nomerge = t(["premerge", "--candidate", "HEAD", "--tests", "unit fail"])
    okmerge = t(["premerge", "--candidate", "HEAD", "--tests", "unit pass"])
    rel = json.loads(t(["lock", "release", "--name", "integration", "--pid", str(me)]).stdout)
    results["M_exclusive_writer"] = "PASS" if first.get("acquired") and second.returncode != 0 else "FAIL"
    results["N_no_unvalidated_merge"] = "PASS" if nomerge.returncode != 0 and okmerge.returncode == 0 and rel.get("released") else "FAIL"

    # ---- v1.2 additions ----------------------------------------------------
    sel = json.loads(t(["select-tests", "--map", testmap, "--base", c0, "--head", c1]).stdout)
    results["P_affected_test_selection"] = "PASS" if sel["commands"] == ["unit mod"] and not sel["full"] else "FAIL"

    shared = json.loads(t(["select-tests", "--map", testmap, "--base", c1, "--head", c2]).stdout)
    results["Q_shared_dependency_broad"] = "PASS" if shared["full"] and shared["commands"] == ["full-suite"] else "FAIL"

    unknown = json.loads(t(["select-tests", "--map", testmap, "--base", c2, "--head", c3]).stdout)
    results["R_unknown_change_fallback"] = "PASS" if unknown["full"] and "weird/thing.py" in unknown["unclassified"] else "FAIL"

    passed = json.loads(t(["run-tests", "--cmd", "python3 -c \"print('Ran 3 tests'); print('OK (skipped=1)')\""]).stdout)
    failed = json.loads(t(["run-tests", "--cmd", "python3 -c \"print('Ran 2 tests'); print('FAILED (failures=1, skipped=1)'); print('FAIL: t (m.T)')\"; exit 1"]).stdout)
    timed = json.loads(t(["run-tests", "--cmd", "sleep 5", "--timeout", "1"]).stdout)
    results["S_structured_result_parse"] = "PASS" if passed["ok"] and passed["counts"]["total"] == 3 and passed["counts"]["skipped"] == 1 else "FAIL"
    results["T_failed_skipped_timeout"] = "PASS" if (not failed["ok"] and failed["failed"] == ["t (m.T)"]
                                                       and timed["counts"].get("timedOut") and not timed["ok"]) else "FAIL"

    # merge conflict detection (branch vs main edits the same file)
    base = gitc("rev-parse", "HEAD").stdout.strip()
    default_branch = gitc("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    gitc("checkout", "-q", "-b", "feat")
    with open(os.path.join(tmp, "shared.txt"), "w") as fh:
        fh.write("feat\n")
    feat = commit("feat change")
    gitc("checkout", "-q", default_branch)
    with open(os.path.join(tmp, "shared.txt"), "w") as fh:
        fh.write("main\n")
    main_sha = commit("main change")
    t(["lock", "acquire", "--name", "integration", "--pid", str(me)])
    conflicted = t(["premerge", "--candidate", feat, "--base", base, "--target", main_sha,
                    "--tests", "unit pass"])
    stale = t(["premerge", "--candidate", "HEAD", "--tests", "unit pass", "--expect-head", base,
               "--integration-branch", "HEAD"])
    results["U_merge_conflict_detection"] = "PASS" if conflicted.returncode != 0 and "conflict" in conflicted.stdout.lower() else "FAIL"
    results["V_stale_integration_head_rejected"] = "PASS" if stale.returncode != 0 and "stale" in stale.stdout.lower() else "FAIL"
    t(["lock", "release", "--name", "integration", "--pid", str(me)])

    # multi-worker completion by group (event-driven, no LLM)
    sp1 = json.loads(t(["spawn", "--name", "m1", "--id", "m1", "--model", "provA/m1", "--objective", "a",
                        "--group", "batch", "--owns", "s/a"], env=launcher(quick)).stdout)
    sp2 = json.loads(t(["spawn", "--name", "m2", "--id", "m2", "--model", "provA/m1", "--objective", "b",
                        "--group", "batch", "--owns", "s/b"], env=launcher(quick)).stdout)
    wg = t(["wait", "--group", "batch", "--timeout", "10"])
    col = json.loads(t(["collect", "--group", "batch"]).stdout)
    ids = {w["id"] for w in col["workers"]}
    results["W_multi_worker_completion"] = (
        "PASS" if sp1.get("ok") and sp2.get("ok") and wg.returncode == 0
        and col["count"] == 2 and len(ids) == 2
        else "FAIL sp1=%s sp2=%s wg=%s col=%s" % (sp1.get("error"), sp2.get("error"), wg.returncode, col.get("count")))
    results["X_duplicate_completion_prevented"] = "PASS" if col["count"] == 2 else "FAIL"

    sid = os.environ.get("PARALLELISM_TEST_SESSION")
    if sid:
        r = run(["verify-model", "--session", sid, "--expect",
                 os.environ.get("PARALLELISM_TEST_MODEL", "opencode-go/deepseek-v4.1-flash")])
        results["O_model_inheritance_verified"] = "PASS" if r.returncode == 0 else "FAIL"
    else:
        results["O_model_inheritance_verified"] = "SKIP (set PARALLELISM_TEST_SESSION)"

    print(json.dumps(results, indent=2, sort_keys=True))
    failed_tests = [k for k, v in results.items() if str(v).startswith("FAIL")]
    sys.exit(1 if failed_tests else 0)


if __name__ == "__main__":
    main()
