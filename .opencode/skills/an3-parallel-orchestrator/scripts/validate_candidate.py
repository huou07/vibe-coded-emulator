#!/usr/bin/env python3
"""Deterministic candidate/run checks for the AN3 orchestrator (fail-closed).

Every check returns PASS / FAIL / WARN / UNVERIFIED / N/A with findings. Use
`scan` to run them all. Logical-conflict checks are base-relative when a base SHA
is supplied, so pre-existing repo debt is reported but not blamed on the candidate.

Usage:
  validate_candidate.py scan [--run-id ID] [--candidate SHA] [--base SHA] [--repo P] [--fast]
  validate_candidate.py <check> [--base SHA] [--repo P] [--status-file FILE]
  checks: tauri-commands duplicate-rg versions manifest-hash stale-release-filenames
          distribution-strings model-policy validate-manifest status
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import orchestrator_lib as lib  # noqa: E402

RELEASES = os.path.join("native-offline", "releases")
CATALOG = os.path.join(RELEASES, "catalog.json")
RG_FILE = os.path.join("docs", "REGRESSION_GUARDS.md")
TAURI_SRC = os.path.join("native-offline", "src-tauri")
AGENT_DIRS = [os.path.join(".opencode", "agent"), os.path.join(".opencode", "agents")]

# Test-only control-plane signatures that must never ship in a distribution
# artifact (RG-121 / release-gates.md).
FORBIDDEN_DISTRIBUTION_STRINGS = [
    b"AN3_UI_CONTROL_FILE",
    b"ui_control_result",
    b"AN3_UI_TEST_ROM",
]
DISTRIBUTION_EXTS = (".dmg", ".apk", ".deb", ".flatpak", ".exe", ".AppImage")

TAURI_CMD_RE = re.compile(
    r"#\[tauri::command[^\]]*\]\s*(?:#\[[^\]]*\]\s*)*(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.DOTALL,
)
RG_DEF_RE = re.compile(r"^-\s*(RG-[A-Za-z0-9-]+)\s*:", re.MULTILINE)


def result(check, status, findings=None, **extra):
    payload = {"check": check, "status": status, "findings": findings or []}
    payload.update(extra)
    return payload


def _bracket_content(text, start_index):
    """Return the content of the first [...] starting at/after start_index."""
    open_index = text.find("[", start_index)
    if open_index < 0:
        return "", start_index
    depth = 0
    for i in range(open_index, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                return text[open_index + 1:i], i
    return text[open_index + 1:], len(text)


def git_show(repo, base, relpath):
    if not base:
        return None
    proc = lib.run_git(repo, ["show", "%s:%s" % (base, relpath)], check=False)
    return proc.stdout if proc.returncode == 0 else None


def check_tauri_commands(repo, _base=None):
    src_dir = os.path.join(repo, TAURI_SRC, "src")
    if not os.path.isdir(src_dir):
        return result("tauri-commands", "N/A", ["no native-offline/src-tauri/src"])
    defined = []
    for root, _dirs, files in os.walk(src_dir):
        for name in files:
            if not name.endswith(".rs"):
                continue
            with open(os.path.join(root, name), "r", encoding="utf-8", errors="replace") as handle:
                source = handle.read()
            for match in TAURI_CMD_RE.finditer(source):
                defined.append(match.group(1))
    lib_file = os.path.join(src_dir, "lib.rs")
    handler_entries = []
    text = ""
    if os.path.exists(lib_file):
        with open(lib_file, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        index = text.find("generate_handler!")
        content, _ = _bracket_content(text, index if index >= 0 else 0)
        content = re.sub(r"//[^\n]*", "", content)
        for token in content.split(","):
            token = token.strip()
            if not token:
                continue
            token = re.sub(r"#\[[^\]]*\]", "", token).strip()
            token = token.split("::")[-1].strip()
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token):
                handler_entries.append(token)
    build_file = os.path.join(repo, TAURI_SRC, "build.rs")
    build_entries = []
    if os.path.exists(build_file):
        with open(build_file, "r", encoding="utf-8", errors="replace") as handle:
            build_text = handle.read()
        cmds_index = build_text.find("commands(")
        content, _ = _bracket_content(build_text, cmds_index if cmds_index >= 0 else 0)
        build_entries = re.findall(r'"([A-Za-z_][A-Za-z0-9_]*)"', content)
    findings = []
    dups_handler = sorted({n for n in handler_entries if handler_entries.count(n) > 1})
    if dups_handler:
        findings.append("duplicate generate_handler entries: %s" % ", ".join(dups_handler))
    defined_set, handler_set, build_set = set(defined), set(handler_entries), set(build_entries)
    for name in sorted(defined_set - handler_set):
        findings.append("command defined but not registered in generate_handler: %s" % name)
    for name in sorted(handler_set - defined_set):
        findings.append("generate_handler entry has no #[tauri::command] definition: %s" % name)
    for name in sorted(handler_set - build_set):
        findings.append("command missing from build.rs AppManifest commands(): %s" % name)
    for name in sorted(build_set - handler_set):
        findings.append("build.rs lists a command not in generate_handler: %s" % name)
    if "cfg" in text:
        findings.append("advisory: cfg attributes present near command registration; verify per-target registration")
    status = "FAIL" if any(not f.startswith("advisory") for f in findings) else "PASS"
    return result("tauri-commands", status, findings,
                  counts={"defined": len(defined), "handler": len(handler_entries), "build": len(build_entries)})


def _dup_ids(ids):
    return sorted({i for i in ids if ids.count(i) > 1})


def check_duplicate_rg(repo, base=None):
    path = os.path.join(repo, RG_FILE)
    if not os.path.exists(path):
        return result("duplicate-rg", "N/A", ["no %s" % RG_FILE])
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        current_ids = RG_DEF_RE.findall(handle.read())
    current_dups = _dup_ids(current_ids)
    base_ids = RG_DEF_RE.findall(git_show(repo, base, RG_FILE) or "") if base else []
    base_dups = _dup_ids(base_ids)
    new_dups = sorted(set(current_dups) - set(base_dups)) if base else []
    findings = []
    if current_dups and base:
        findings.append("pre-existing duplicate guard ids: %s" % ", ".join(current_dups))
    if current_dups and not base:
        findings.append("duplicate guard ids present (no --base to attribute): %s" % ", ".join(current_dups))
    if new_dups:
        findings.append("candidate introduces duplicate guard ids: %s" % ", ".join(new_dups))
    if base:
        status = "FAIL" if new_dups else "PASS"
    else:
        status = "WARN" if current_dups else "PASS"
    return result("duplicate-rg", status, findings,
                  total_definitions=len(current_ids), newDuplicates=new_dups)


def _read_json_file(repo, relpath):
    path = os.path.join(repo, relpath)
    if not os.path.exists(path):
        return None
    try:
        return lib.read_json(path)
    except ValueError as exc:
        return {"__parse_error__": str(exc)}


def check_versions(repo, base=None):
    findings = []
    desktop = {}
    package = _read_json_file(repo, os.path.join("native-offline", "package.json"))
    if isinstance(package, dict) and package.get("version"):
        desktop["package.json"] = package["version"]
    tauri = _read_json_file(repo, os.path.join(TAURI_SRC, "tauri.conf.json"))
    if isinstance(tauri, dict) and tauri.get("version"):
        desktop["tauri.conf.json"] = tauri["version"]
    cargo_path = os.path.join(repo, TAURI_SRC, "Cargo.toml")
    if os.path.exists(cargo_path):
        with open(cargo_path, "r", encoding="utf-8", errors="replace") as handle:
            match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', handle.read())
            if match:
                desktop["Cargo.toml"] = match.group(1)
    android = _read_json_file(repo, os.path.join(TAURI_SRC, "tauri.android.conf.json"))
    android_version = android.get("version") if isinstance(android, dict) else None
    desktop_values = sorted(set(desktop.values()))
    if len(desktop_values) > 1:
        findings.append("desktop version fields disagree: %s" % json.dumps(desktop, sort_keys=True))
    if base and desktop_values:
        base_desktop = {}
        for relpath, key in (("native-offline/package.json", "package.json"),
                             (os.path.join(TAURI_SRC, "tauri.conf.json"), "tauri.conf.json")):
            content = git_show(repo, base, relpath)
            if content:
                try:
                    base_desktop[key] = json.loads(content).get("version")
                except ValueError:
                    pass
        if base_desktop:
            changed = {k: v for k, v in desktop.items() if k in base_desktop and base_desktop[k] != v}
            if changed and len({v for v in changed.values()}) > 1:
                findings.append("changed desktop version fields disagree: %s" % json.dumps(changed))
    catalog = _read_json_file(repo, CATALOG)
    if isinstance(catalog, dict) and "__parse_error__" not in catalog:
        for artifact in catalog.get("artifacts", []):
            version = str(artifact.get("version", ""))
            filename = str(artifact.get("filename", ""))
            if version and version not in filename:
                findings.append("catalog version %s not present in filename %s" % (version, filename))
    status = "FAIL" if findings else "PASS"
    return result("versions", status, findings, desktop=desktop, android=android_version)


def _sha256(path, chunk=1024 * 1024):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def check_manifest_hash(repo, _base=None):
    catalog = _read_json_file(repo, CATALOG)
    if not isinstance(catalog, dict) or "__parse_error__" in (catalog or {}):
        return result("manifest-hash", "N/A", ["no readable %s" % CATALOG])
    findings, checked, missing = [], 0, []
    for artifact in catalog.get("artifacts", []):
        filename = str(artifact.get("filename", ""))
        path = os.path.join(repo, RELEASES, filename)
        if not filename or not os.path.exists(path):
            missing.append(filename)
            continue
        checked += 1
        size = os.path.getsize(path)
        if artifact.get("size") and int(artifact["size"]) != size:
            findings.append("size mismatch for %s: catalog %s, bytes %s" % (filename, artifact.get("size"), size))
        expected = str(artifact.get("sha256", "")).lower()
        if expected:
            actual = _sha256(path)
            if actual != expected:
                findings.append("sha256 mismatch for %s: catalog %s, bytes %s" % (filename, expected, actual))
    status = "FAIL" if findings else ("PASS" if checked else "UNVERIFIED")
    if not checked:
        findings.append("no catalog artifacts present locally; run tools/verify-release-catalog.py on the builder")
    return result("manifest-hash", status, findings, checked=checked, missing=missing)


VERSIONED_FILENAME_RE = re.compile(
    r"(?i)(vibecodedemulator|an3-offline|VibeCodedEmulator)[-_][0-9]+\.[0-9]+\.[0-9]+"
)
SCRIPT_GLOBS = ["tools", os.path.join("native-offline", "scripts")]


def _iter_scripts(repo):
    for base in SCRIPT_GLOBS:
        root = os.path.join(repo, base)
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                if name.endswith((".sh", ".ps1")):
                    yield os.path.join(dirpath, name)


def check_stale_release_filenames(repo, base=None):
    findings, new_hits = [], []
    for path in _iter_scripts(repo):
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        hits = sorted(set(m.group(0) for m in VERSIONED_FILENAME_RE.finditer(text)))
        if not hits:
            continue
        rel = os.path.relpath(path, repo)
        if base:
            base_text = git_show(repo, base, rel) or ""
            base_hits = set(m.group(0) for m in VERSIONED_FILENAME_RE.finditer(base_text))
            introduced = sorted(set(hits) - base_hits)
            if introduced:
                new_hits.append("%s: %s" % (rel, ", ".join(introduced)))
        else:
            findings.append("%s hard-codes %s" % (rel, ", ".join(hits)))
    if base:
        status = "FAIL" if new_hits else "PASS"
        findings = new_hits
    else:
        status = "WARN" if findings else "PASS"
    return result("stale-release-filenames", status, findings, baseRelative=bool(base))


def check_distribution_strings(repo, _base=None):
    releases = os.path.join(repo, RELEASES)
    if not os.path.isdir(releases):
        return result("distribution-strings", "N/A", ["no releases directory"])
    artifacts = [os.path.join(releases, n) for n in sorted(os.listdir(releases))
                 if n.endswith(DISTRIBUTION_EXTS)]
    if not artifacts:
        return result("distribution-strings", "UNVERIFIED",
                      ["no distribution artifacts present; scan on the builder before release"])
    findings, scanned = [], 0
    for path in artifacts:
        scanned += 1
        size = os.path.getsize(path)
        overlap = 64
        with open(path, "rb") as handle:
            offset = 0
            carry = b""
            while True:
                block = handle.read(8 * 1024 * 1024)
                if not block:
                    break
                data = carry + block
                for needle in FORBIDDEN_DISTRIBUTION_STRINGS:
                    position = data.find(needle)
                    if position >= 0:
                        findings.append("%s contains forbidden test-only string %r near offset %d"
                                        % (os.path.basename(path), needle.decode(), offset + position))
                carry = data[-overlap:]
                offset += len(block)
    status = "FAIL" if findings else "PASS"
    return result("distribution-strings", status, findings, scanned=scanned,
                  artifacts=[os.path.basename(p) for p in artifacts])


def check_model_policy(repo, _base=None):
    findings, agents = [], []
    found_dir = None
    for candidate in AGENT_DIRS:
        if os.path.isdir(os.path.join(repo, candidate)):
            found_dir = os.path.join(repo, candidate)
            break
    if found_dir:
        for name in sorted(os.listdir(found_dir)):
            if name.startswith("an3-") and name.endswith(".md"):
                fm = lib.parse_frontmatter(os.path.join(found_dir, name))
                model = fm.get("model")
                agents.append({"agent": name[:-3], "model": model})
                if model != lib.CANONICAL_MODEL:
                    findings.append("%s pins %r, expected %r" % (name, model, lib.CANONICAL_MODEL))
    config = _read_json_file(repo, os.path.join(".opencode", "opencode.json"))
    if isinstance(config, dict) and config.get("model") and config["model"] != lib.CANONICAL_MODEL:
        findings.append(".opencode/opencode.json model %r != %r" % (config["model"], lib.CANONICAL_MODEL))
    if not agents:
        findings.append("no an3-* agents found")
    status = "FAIL" if findings else "PASS"
    return result("model-policy", status, findings, model=lib.CANONICAL_MODEL, agents=agents)


def check_validate_manifest(repo, _base=None, run_id=None):
    if not run_id:
        return result("validate-manifest", "N/A", ["no --run-id supplied"])
    rdir = lib.run_dir(repo, run_id)
    path = os.path.join(rdir, "manifest.json")
    if not os.path.exists(path):
        return result("validate-manifest", "FAIL", ["manifest.json missing for run %s" % run_id])
    manifest = lib.read_json(path)
    problems = []
    for key in ("runId", "baseSha", "model", "statuses", "manifestSchemaVersion", "repoRoot"):
        if key not in manifest or manifest[key] in (None, "", {}, []):
            problems.append("manifest.%s missing or empty" % key)
    if manifest.get("model") != lib.CANONICAL_MODEL:
        problems.append("manifest model %r != %r" % (manifest.get("model"), lib.CANONICAL_MODEL))
    schema = manifest.get("manifestSchemaVersion")
    if schema != lib.MANIFEST_SCHEMA_VERSION:
        problems.append("manifest schema %s != supported %s" % (schema, lib.MANIFEST_SCHEMA_VERSION))
    status = "FAIL" if problems else "PASS"
    return result("validate-manifest", status, problems, runId=run_id)


VALID_WORKER_STATUS = set(lib.load_config()["statuses"]["worker"])


def check_status(repo, _base=None, status_file=None):
    if not status_file:
        return result("status", "N/A", ["no --status-file supplied"])
    with open(status_file, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    problems = []
    for key in ("runId", "domain", "status", "branch", "head"):
        if key not in data:
            problems.append("missing field %s" % key)
    if data.get("status") not in VALID_WORKER_STATUS:
        problems.append("status %r not in %s" % (data.get("status"), sorted(VALID_WORKER_STATUS)))
    status = "FAIL" if problems else "PASS"
    return result("status", status, problems, parsed=data)


CHECKS = {
    "tauri-commands": check_tauri_commands,
    "duplicate-rg": check_duplicate_rg,
    "versions": check_versions,
    "manifest-hash": check_manifest_hash,
    "stale-release-filenames": check_stale_release_filenames,
    "distribution-strings": check_distribution_strings,
    "model-policy": check_model_policy,
    "validate-manifest": check_validate_manifest,
    "status": check_status,
}


def run_check(name, repo, base, run_id=None, status_file=None, fast=False):
    if fast and name in ("manifest-hash", "distribution-strings"):
        return result(name, "SKIPPED", ["--fast"])
    try:
        if name in ("validate-manifest",):
            return CHECKS[name](repo, base, run_id=run_id)
        if name in ("status",):
            return CHECKS[name](repo, base, status_file=status_file)
        return CHECKS[name](repo, base)
    except Exception as exc:  # noqa: BLE001 - fail closed, never crash the scan
        return result(name, "FAIL", ["check raised %s: %s" % (type(exc).__name__, exc)])


def cmd_scan(args):
    repo = lib.find_repo_root(args.repo)
    base = args.base
    run_id = args.run_id
    if run_id and not base:
        manifest_path = os.path.join(lib.run_dir(repo, run_id), "manifest.json")
        if os.path.exists(manifest_path):
            base = lib.read_json(manifest_path).get("baseSha")
    if args.candidate:
        lib.require_commit(repo, args.candidate, "candidate")
    order = ["model-policy", "validate-manifest", "duplicate-rg", "tauri-commands", "versions",
             "stale-release-filenames", "manifest-hash", "distribution-strings", "status"]
    results = [run_check(name, repo, base, run_id=run_id, status_file=args.status_file, fast=args.fast)
               for name in order]
    failed = [r["check"] for r in results if r["status"] == "FAIL"]
    payload = {"ok": not failed, "repo": repo, "baseSha": base, "candidate": args.candidate,
               "runId": run_id, "failed": failed, "results": results}
    lib.emit(payload, exit_code=0 if not failed else 1)


def build_parser():
    parser = argparse.ArgumentParser(description="AN3 orchestrator deterministic checks")
    parser.add_argument("--repo", default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("scan")
    p.add_argument("--run-id")
    p.add_argument("--candidate")
    p.add_argument("--base")
    p.add_argument("--status-file")
    p.add_argument("--fast", action="store_true")
    p.set_defaults(func=cmd_scan)
    for name in CHECKS:
        cp = sub.add_parser(name)
        cp.add_argument("--base")
        cp.add_argument("--run-id")
        cp.add_argument("--status-file")
        cp.set_defaults(func=lambda a, _n=name: _single(a, _n))
    return parser


def _single(args, name):
    repo = lib.find_repo_root(args.repo)
    outcome = run_check(name, repo, getattr(args, "base", None),
                        run_id=getattr(args, "run_id", None),
                        status_file=getattr(args, "status_file", None))
    lib.emit({"ok": outcome["status"] != "FAIL", **outcome},
             exit_code=0 if outcome["status"] != "FAIL" else 1)


def main():
    args = build_parser().parse_args()
    try:
        args.func(args)
    except lib.OrchestratorError as exc:
        lib.fail(exc.message, code=exc.code, **exc.detail)


if __name__ == "__main__":
    main()
