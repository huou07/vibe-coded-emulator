#!/usr/bin/env python3
"""Fail when the documentation points at something the repository does not have.

Two failure classes, both real:

1. A path reference that does not resolve in the tracked tree. This is how a
   document ends up citing a per-run report that only ever existed on one
   machine, or an absolute path from a retired workstation.
2. An absolute path into somebody's home directory. Those never resolve on a
   different host and they leak a person's directory layout into a public
   snapshot.

Existence is decided against ``git ls-files``, so a sparse checkout does not
make a tracked file look missing and an untracked scratch file does not make a
tracked file look present.

``docs/archive/`` is skipped on purpose: archived documents are historical
records that are deliberately not maintained. Rewriting them would destroy the
only record of why a decision was taken.

Exit status: 0 clean, 1 findings, 2 the check could not run (fail closed).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_PREFIX = "docs/archive/"

# Documentation roots. Anything else in the tree is product source, not prose.
DOC_GLOBS = ("*.md", "docs/**/*.md", "tools/**/*.md", "deploy/**/*.md",
             "native-offline/**/*.md", "rust-gateway/**/*.md", "native/**/*.md")

# Source and test files are checked for absolute host paths too. A path that
# names a home directory resolves on one machine and leaks that machine's layout;
# tests/an3ctl.test.mjs already carried one. Prose documents are covered by the
# token scan above, and retained private evidence under docs/evidence is not
# source and is never published, so neither is rescanned here.
CODE_GLOBS = ("*.py", "tools/**/*.py", "tools/**/*.mjs", "tools/**/*.js",
              "tests/**/*.py", "tests/**/*.js", "tests/**/*.mjs",
              "static/**/*.js", "static/**/*.mjs")

# A home directory with a real user segment: /home/<name>/... or /Users/<name>/...
# The trailing slash matters: a test fixture that asserts on the bare prefix
# ``"/home/"`` is a detector, not a leaked path.
ABSOLUTE_HOST_PATH = re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+/")

# Files that must contain the patterns themselves, and vendored or generated
# third-party content whose bytes are not ours to rewrite.
HOST_PATH_EXEMPT = (
    "tools/check-docs-refs.py",
    "tools/build-public-snapshot.sh",
    "tools/publication-check.sh",
    "native-offline/vendor/",
    "native-offline/native-runtime/core/vendor/",
    "native-offline/src-tauri/gen/",
    "native-offline/patches/",
    "static/fonts/",
)

# A backticked token is treated as a path reference when it looks like one.
PATH_TOKEN = re.compile(
    r"`([^`\n]+?)`",
)
PATHISH = re.compile(
    r"^[A-Za-z0-9_./@+-]+$",            # no spaces or shell metacharacters
)
PLACEHOLDER = re.compile(r"[*?${}<>|]")
MD_LINK = re.compile(r"\]\(([^)\s]+)")
# Directories at the top of a path reference, to avoid matching bare words like
# `core` or a code identifier that happens to contain a slash-free name.
KNOWN_ROOTS = frozenset("""
AGENTS.md LICENSE README.md THIRD_PARTY_NOTICES.md LICENSE.txt
app.py netcode.py qrcodegen.py sync_engine.py
data deploy docs native native-offline reports rust-gateway static tests tools work
""".split())


def tracked_files() -> set[str]:
    """Tracked files plus every tracked directory prefix.

    A document may legitimately name a directory (``native-offline/scripts/``).
    Git lists files, not directories, so the directory prefixes are derived here
    so that naming a directory is not reported as a missing path.
    """
    try:
        out = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, check=True,
            capture_output=True, text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"check-docs-refs: cannot list tracked files: {exc}", file=sys.stderr)
        raise SystemExit(2)
    files = {line.strip() for line in out.splitlines() if line.strip()}
    prefixes: set[str] = set()
    for name in files:
        parts = name.split("/")
        for depth in range(1, len(parts)):
            prefixes.add("/".join(parts[:depth]))
    return files | prefixes


def ignored_paths() -> list[str]:
    """Paths deliberately excluded by Git, whether or not they exist locally.

    ``git status --ignored`` reports only materialized paths. A clean CI checkout
    may not contain runtime state such as ``data/``, even though ``.gitignore``
    intentionally excludes it. Check the documented root paths against ignore
    rules as well as collecting any currently materialized ignored paths.
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--ignored=matching"],
            cwd=ROOT, capture_output=True, text=True,
        )
    except OSError:
        return []
    ignored: set[str] = set()
    for line in result.stdout.splitlines():
        if "!!" in line:
            ignored.add(line.split("!!", 1)[1].strip().rstrip("/"))

    candidates = sorted(
        path for root in KNOWN_ROOTS for path in (root, f"{root}/")
    )
    try:
        configured = subprocess.run(
            ["git", "check-ignore", "--no-index", "--stdin"],
            cwd=ROOT, input="\n".join(candidates) + "\n",
            capture_output=True, text=True,
        )
    except OSError as exc:
        print(f"check-docs-refs: cannot check ignore rules: {exc}", file=sys.stderr)
        raise SystemExit(2)
    if configured.returncode not in (0, 1):
        print("check-docs-refs: cannot check ignore rules", file=sys.stderr)
        raise SystemExit(2)
    ignored.update(line.strip().rstrip("/") for line in configured.stdout.splitlines())
    return sorted(ignored)


def doc_files() -> list[Path]:
    seen: dict[Path, None] = {}
    for pattern in DOC_GLOBS:
        for path in ROOT.glob(pattern):
            if path.is_file():
                seen.setdefault(path.relative_to(ROOT).as_posix(), None)
    return sorted(ROOT / p for p in seen)


def code_files() -> list[Path]:
    seen: dict[Path, None] = {}
    for pattern in CODE_GLOBS:
        for path in ROOT.glob(pattern):
            rel = path.relative_to(ROOT).as_posix()
            if path.is_file() and not any(rel.startswith(p) or rel == p for p in HOST_PATH_EXEMPT):
                seen.setdefault(rel, None)
    return sorted(ROOT / p for p in seen)


def scan_host_paths(path: Path) -> list[str]:
    """Absolute host paths in source or test files.

    ``docs/archive/`` is exempt because it keeps the historical record verbatim,
    and the bookkeeping files above are exempt because they define the scan.
    """
    rel = path.relative_to(ROOT).as_posix()
    if rel.startswith(ARCHIVE_PREFIX):
        return []
    findings: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    for line_no, line in enumerate(text.splitlines(), 1):
        for match in ABSOLUTE_HOST_PATH.finditer(line):
            findings.append(
                f"{rel}:{line_no}: absolute host path {match.group(0)!r} — use a "
                f"repository-relative path or a named environment variable"
            )
    return findings


def top_segment(token: str) -> str:
    return token.split("/", 1)[0]


def check_absolute(line_no: int, doc: str, token: str, findings: list[str]) -> None:
    if token.startswith("/Users/") or token.startswith("/home/") or token.startswith("~"):
        findings.append(
            f"{doc}:{line_no}: absolute personal path {token!r} — use a "
            f"repository-relative path or a named environment variable"
        )


def check_repo_relative(line_no: int, doc: str, token: str,
                        tracked: set[str], ignored: set[str],
                        findings: list[str]) -> None:
    if token.startswith(("http://", "https://", "mailto:", "#")):
        return
    target = token.split("#", 1)[0].split("?", 1)[0].rstrip("/")
    if not target or PLACEHOLDER.search(target):
        return
    # A bare word, a filename we do not own, or something outside the repo.
    head = top_segment(target)
    if head not in KNOWN_ROOTS:
        return
    candidates = {target, target.lstrip("./")}
    doc_dir = str(Path(doc).parent)
    if doc_dir not in (".", ""):
        candidates.add(f"{doc_dir}/{target}")
    if any(c in tracked for c in candidates):
        return
    # A deliberately unversioned path is still a real path. Ignore rules for
    # a directory also apply to any documented child, even when absent locally.
    if any(
        candidate == path or candidate.startswith(path + "/")
        for candidate in candidates
        for path in ignored
    ):
        return
    findings.append(
        f"{doc}:{line_no}: {token!r} is not a path in this repository"
    )


def scan(doc: Path, tracked: set[str], ignored: set[str]) -> list[str]:
    rel = doc.relative_to(ROOT).as_posix()
    if rel.startswith(ARCHIVE_PREFIX):
        return []
    findings: list[str] = []
    for line_no, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith("```"):
            continue
        targets = [m.group(1) for m in MD_LINK.finditer(line)]
        targets += [m.group(1) for m in PATH_TOKEN.finditer(line)]
        for raw in targets:
            token = raw.strip()
            if not PATHISH.match(token):
                continue
            check_absolute(line_no, rel, token, findings)
            check_repo_relative(line_no, rel, token, tracked, ignored, findings)
    return findings


def main() -> int:
    tracked = tracked_files()
    ignored = set(ignored_paths())
    docs = doc_files()
    sources = code_files()
    findings: list[str] = []
    for doc in docs:
        findings.extend(scan(doc, tracked, ignored))
    for source in sources:
        findings.extend(scan_host_paths(source))
    if findings:
        print("Documentation reference check FAILED:\n", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        print(
            f"\n{len(findings)} finding(s) across {len(docs)} document(s) and "
            f"{len(sources)} source file(s).\n"
            "Fix the reference, or move a superseded document to docs/archive/ "
            "with a reason. Do not silence the check.",
            file=sys.stderr,
        )
        return 1
    print(f"Documentation reference check: clean ({len(docs)} documents, "
          f"{len(sources)} source files, {len(tracked)} tracked paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
