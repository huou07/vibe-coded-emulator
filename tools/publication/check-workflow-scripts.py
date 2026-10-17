#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fail when a published workflow calls a script the candidate does not contain.

The public snapshot once shipped a `native-build.yml` whose jobs ran
`bash tools/release-train.sh` five times while `build-public-snapshot.sh` copied
neither that script nor a fixture directory, so every published native job could
only fail. This checker makes that class of defect impossible to publish: every
`bash|sh|node|python3 <path>` reference in the candidate's workflows must resolve
inside the candidate.

Usage: tools/publication/check-workflow-scripts.py CANDIDATE_DIR
Exit status: 0 all references resolve, 1 a script is missing, 2 the check could
not run (fail closed).
"""

from __future__ import annotations

import pathlib
import re
import sys

# A workflow command that runs a repository script. Deliberately narrow: the
# token must look like a path and carry an executable extension, so `python3 -m
# module`, `node --test`, `cargo test --manifest-path x/Cargo.toml` and heredoc
# bodies do not match.
SCRIPT_CALL = re.compile(
    r"(?<![\w.-])(?:bash|sh|node|python3?)\s+"
    r"((?:\./)?[A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:sh|bash|py|mjs|cjs|js))"
)
WORKFLOW_GLOBS = (".github/workflows/*.yml", ".github/workflows/*.yaml")


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: check-workflow-scripts.py CANDIDATE_DIR", file=sys.stderr)
        return 2
    candidate = pathlib.Path(argv[0])
    if not candidate.is_dir():
        print(f"candidate directory is missing: {candidate}", file=sys.stderr)
        return 2

    try:
        workflows = sorted(
            {path for pattern in WORKFLOW_GLOBS for path in candidate.glob(pattern)}
        )
    except OSError as exc:
        print(f"cannot list published workflows: {exc}", file=sys.stderr)
        return 2

    missing: list[str] = []
    references = 0
    for workflow in workflows:
        try:
            text = workflow.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"cannot read {workflow}: {exc}", file=sys.stderr)
            return 2
        for token in SCRIPT_CALL.findall(text):
            references += 1
            target = token[2:] if token.startswith("./") else token
            if not (candidate / target).is_file():
                missing.append(f"{workflow.relative_to(candidate)}: {token}")

    if missing:
        print(
            "published workflow calls a script the candidate does not contain:",
            file=sys.stderr,
        )
        for entry in missing:
            print(f"  - {entry}", file=sys.stderr)
        print(
            "  Copy the script into the snapshot, or remove the job that needs it.",
            file=sys.stderr,
        )
        return 1

    print(
        f"published workflow script references: {len(workflows)} workflow(s), "
        f"{references} reference(s), all present"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
