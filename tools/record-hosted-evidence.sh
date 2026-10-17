#!/usr/bin/env bash
# Record a hosted CI run at the current revision as gate-report evidence.
#
# Copy this into a project as `tools/record-hosted-evidence.sh` and run it from
# the project root:
#
#   bash tools/record-hosted-evidence.sh ci.yml
#   bash tools/record-hosted-evidence.sh release.yml 'Package lifecycle, audit and Lintian'
#
# Why this exists: AEH is offline by design — it reads Git and local evidence and
# never calls GitHub. A quality contract that says `hosted_ci: "required"` can
# therefore only be satisfied if the project records the hosted result locally.
# Without this step, `hub.py release-check` reports BLOCKED with "no hosted-runner
# evidence recorded for this revision", which is true but useless.
#
# It writes `.hub/hosted-evidence.json`, a separate file from the gate report so
# the project's own gate can rewrite its coverage on every run without erasing
# this. `hub.py verify` merges the two, and only when `head` equals the revision
# being verified.
#
# It records only what it can prove:
#   * the run must have conclusion `success` for the exact current commit;
#   * a workflow or job that GitHub reports as skipped/neutral is not recorded as
#     success;
#   * nothing is published, deployed or written outside `.hub/`.
#
# Exit codes: 0 recorded; 3 no successful hosted run exists for this commit
# (BLOCKED, not a lie); 2 usage/tooling error.
set -euo pipefail

if ! command -v gh >/dev/null 2>&1; then
  echo "record-hosted-evidence: gh is not installed" >&2
  exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "record-hosted-evidence: python3 is not installed" >&2
  exit 2
fi
if [[ $# -lt 1 ]]; then
  echo "usage: bash tools/record-hosted-evidence.sh <workflow-file-or-name> [job-name...]" >&2
  exit 2
fi

WORKFLOW="$1"; shift || true
JOBS=("$@")

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "record-hosted-evidence: not inside a Git repository" >&2
  exit 2
fi

REPO_SLUG="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
SHA="$(git rev-parse HEAD)"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"

echo "commit  : $SHA"
echo "branch  : $BRANCH"
echo "repo    : $REPO_SLUG"
echo "workflow: $WORKFLOW"

RUN="$(gh run list --repo "$REPO_SLUG" --workflow "$WORKFLOW" --commit "$SHA" \
        --status success --limit 1 \
        --json databaseId,headSha,url,conclusion,workflowName,event 2>/dev/null || echo '[]')"

if [[ "$RUN" == "[]" || -z "$RUN" ]]; then
  echo "record-hosted-evidence: no successful '$WORKFLOW' run exists for $SHA" >&2
  echo "                        this is BLOCKED, not verified — push the revision and" >&2
  echo "                        re-run after hosted CI covers it." >&2
  exit 3
fi

mkdir -p .hub
WORKFLOW_NAME="$WORKFLOW" JOBS_JSON="$(printf '%s\n' "${JOBS[@]-}" | python3 -c 'import json,sys; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))')" \
RUN_JSON="$RUN" SHA="$SHA" BRANCH="$BRANCH" REPO_SLUG="$REPO_SLUG" python3 - <<'PY'
import json, os
from pathlib import Path

run = json.loads(os.environ["RUN_JSON"])[0]
jobs = json.loads(os.environ["JOBS_JSON"])

# Its own file, not a merge into the gate report: the project's gate rewrites
# that report on every run and would erase this. `hub.py verify` merges the two,
# and only when `head` equals the revision being verified.
evidence = {
    "head": os.environ["SHA"],
    "repo": os.environ["REPO_SLUG"],
    "branch": os.environ["BRANCH"],
    "workflow": os.environ["WORKFLOW_NAME"],
    "conclusion": run.get("conclusion"),
    "recorded_at": __import__("datetime").datetime.now(
        __import__("datetime").UTC).isoformat(timespec="seconds"),
    "runner": {
        "kind": "hosted",
        "os": "github-actions",
        "arch": None,
        "label": run.get("workflowName") or os.environ["WORKFLOW_NAME"],
        "run_url": run.get("url"),
        "run_id": str(run.get("databaseId")),
        "job": ", ".join(jobs) if jobs else None,
        "head_sha": run.get("headSha"),
        "event": run.get("event"),
    },
}
path = Path(".hub/hosted-evidence.json")
path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"recorded: {path} runner={evidence['runner']['kind']} run={evidence['runner']['run_id']}")
print(f"revision: {evidence['head']}")
print("note    : this proves the environment and the run id for this exact commit;")
print("          it does not replace the project's own acceptance record for behaviour.")
print("next    : python3 /path/to/hub.py verify <slug> --gate acceptance")
PY
