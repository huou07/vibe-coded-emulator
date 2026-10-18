#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Publish the sanitized public source snapshot to GitHub.
#
# RUN THIS MANUALLY, ONLY WHEN YOU INTEND TO PUBLISH. Nothing in this repository
# publishes to GitHub automatically.
#
# Usage:
#   tools/publish-github.sh --confirm [--repo OWNER/NAME] [--snapshot DIR]
#   tools/publish-github.sh --confirm --branch codex/name [--repo OWNER/NAME] [--snapshot DIR]
#
# Environment (author identity for the single public commit):
#   AN3_PUBLIC_AUTHOR_NAME   default: GitHub username from --repo
#   AN3_PUBLIC_AUTHOR_EMAIL  default: <username>@users.noreply.github.com
#   AN3_PUBLIC_GIT_PROTOCOL  https (default) or ssh
#
# It never prints secrets and never force-pushes.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="huou07/vibe-coded-emulator"
SNAPSHOT="${AN3_PUBLICATION_CANDIDATE:-$ROOT/work/public-snapshot}"
CONFIRMED=0
ADOPT_REMOTE=0
BRANCH=""
BASE_BRANCH="main"
CREATE_PR=1
USE_PREBUILT_SNAPSHOT=0
CHECK_CANDIDATE=0
COMMIT_SUBJECT="Update clean public source snapshot"
# Empty means "not requested": --branch creates a PR with a generic title/body,
# and an existing PR is left untouched rather than having an owner-edited
# title or body overwritten.
PR_TITLE=""
PR_BODY_FILE=""

usage() {
  cat <<'USAGE'
Usage: tools/publish-github.sh --confirm [--repo OWNER/NAME] [--snapshot DIR]

  --confirm        required; acknowledge that this publishes publicly
  --check-candidate only verify that --snapshot is the core-only public product,
                 then exit (nothing is published; --confirm not required)
  --adopt-remote   merge an existing remote main into the snapshot (no force-push)
  --branch NAME    publish one clean snapshot commit on NAME
  --base NAME      base branch for a new review branch (default: main)
  --no-pr           push a review branch without opening or editing a PR
  --prebuilt        publish the already-built and scanned snapshot at --snapshot
  --message TITLE   public commit title (default: Update clean public source snapshot)
  --title TITLE     pull-request title for --branch (default: a generic snapshot title)
  --body-file FILE  pull-request body for --branch (default: a generic publication body)
  --repo OWNER/NAME  default: huou07/vibe-coded-emulator
  --snapshot DIR     default: work/public-snapshot
  -h, --help       show this help

Environment: AN3_PUBLIC_AUTHOR_NAME, AN3_PUBLIC_AUTHOR_EMAIL
USAGE
}

CHECK_CANDIDATE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --confirm) CONFIRMED=1; shift ;;
    --check-candidate) CHECK_CANDIDATE=1; shift ;;
    --adopt-remote) ADOPT_REMOTE=1; shift ;;
    --branch) [[ -n "${2:-}" ]] || { printf 'ERROR: --branch needs a name\n' >&2; exit 2; }; BRANCH="$2"; shift 2 ;;
    --base) [[ -n "${2:-}" ]] || { printf 'ERROR: --base needs a branch name\n' >&2; exit 2; }; BASE_BRANCH="$2"; shift 2 ;;
    --no-pr) CREATE_PR=0; shift ;;
    --prebuilt) USE_PREBUILT_SNAPSHOT=1; shift ;;
    --message) [[ -n "${2:-}" ]] || { printf 'ERROR: --message needs a title\n' >&2; exit 2; }; COMMIT_SUBJECT="$2"; shift 2 ;;
    --title) [[ -n "${2:-}" ]] || { printf 'ERROR: --title needs a value\n' >&2; exit 2; }; PR_TITLE="$2"; shift 2 ;;
    --body-file) [[ -n "${2:-}" ]] || { printf 'ERROR: --body-file needs a path\n' >&2; exit 2; }; PR_BODY_FILE="$2"; shift 2 ;;
    --repo) [[ -n "${2:-}" ]] || { printf 'ERROR: --repo needs OWNER/NAME\n' >&2; exit 2; }; REPO="$2"; shift 2 ;;
    --snapshot) [[ -n "${2:-}" ]] || { printf 'ERROR: --snapshot needs a directory\n' >&2; exit 2; }; SNAPSHOT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    -*) printf 'ERROR: unknown option: %s\n' "$1" >&2; exit 2 ;;
    *) SNAPSHOT="$1"; shift ;;
  esac
done

die() { printf 'PUBLISH=FAIL %s\n' "$*" >&2; exit 1; }
note() { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }

# The public repository is the core-only product. Its own contract tests require
# the account/login, CMS/analytics and phone-controller surfaces to be absent,
# and they stay on the public line when a review branch is overlaid onto it. This
# script copies app.py verbatim, so a candidate exported from the full-featured
# private development line would replace the public app.py with one that still
# defines those routes, and the hosted checks reject the pull request after the
# fact. Refuse here, before anything is pushed, and name the line to export from.
check_core_only_candidate() {
  python3 - "$1" <<'PY'
import pathlib
import sys

candidate = pathlib.Path(sys.argv[1])
app = candidate / "app.py"
if not app.is_file():
    print(f"PUBLISH=FAIL candidate has no app.py: {candidate}", file=sys.stderr)
    raise SystemExit(1)

text = app.read_text(encoding="utf-8", errors="replace")
surfaces = [
    (marker, label)
    for marker, label in (
        ('path == "/login"', "login page route"),
        ('path == "/register"', "registration page route"),
        ('path == "/account"', "account page route"),
        ('"/api/account/', "account API"),
    )
    if marker in text
]
if surfaces:
    print("PUBLISH=FAIL this candidate is not the core-only public product:", file=sys.stderr)
    for marker, label in surfaces:
        print(f"  - app.py still defines the {label} ({marker})", file=sys.stderr)
    print(
        "  Export the snapshot from the core-only line (a core-only/* branch) rather than the "
        "full-featured development branch; the public line's own contract tests require those "
        "surfaces to be absent.",
        file=sys.stderr,
    )
    raise SystemExit(1)
PY
}

if [[ "$CHECK_CANDIDATE" -eq 1 ]]; then
  check_core_only_candidate "$SNAPSHOT" || exit 1
  note "PUBLICATION_SOURCE=PASS core-only public product: $SNAPSHOT"
  exit 0
fi

[[ "$CONFIRMED" -eq 1 ]] || die "refusing to publish without --confirm (this is intentional)"
if [[ -n "$BRANCH" && ( ! "$BRANCH" =~ ^[A-Za-z0-9._/-]+$ || "$BRANCH" == *..* || "$BRANCH" == */ ) ]]; then
  die "invalid branch name"
fi
if [[ ! "$BASE_BRANCH" =~ ^[A-Za-z0-9._/-]+$ || "$BASE_BRANCH" == *..* || "$BASE_BRANCH" == */ ]]; then
  die "invalid base branch name"
fi
if [[ "$CREATE_PR" -eq 0 && -z "$BRANCH" ]]; then
  die "--no-pr requires --branch"
fi
command -v git >/dev/null || die "git is required"
command -v python3 >/dev/null || die "python3 is required"

OWNER="${REPO%%/*}"
NAME="${REPO##*/}"
AUTHOR_NAME="${AN3_PUBLIC_AUTHOR_NAME:-$OWNER}"
AUTHOR_EMAIL="${AN3_PUBLIC_AUTHOR_EMAIL:-${OWNER}@users.noreply.github.com}"

step "1/7 build the sanitized snapshot"
if [[ "$USE_PREBUILT_SNAPSHOT" -eq 0 ]]; then
  "$ROOT/tools/build-public-snapshot.sh" "$SNAPSHOT" >/dev/null
else
  [[ -d "$SNAPSHOT" ]] || die "prebuilt snapshot is missing: $SNAPSHOT"
  note "using prebuilt snapshot: $SNAPSHOT"
fi

step "2/7 security gate (fail closed)"
AN3_PUBLICATION_CANDIDATE="$SNAPSHOT" "$ROOT/tools/publication-check.sh" "$SNAPSHOT"

step "2b/7 the candidate must be the core-only public product"
check_core_only_candidate "$SNAPSHOT" || exit 1
note "PUBLICATION_SOURCE=PASS core-only public product"

step "3/7 create a fresh single-commit repository (no development history)"
find "$SNAPSHOT" -name '.git' -maxdepth 2 -prune -exec rm -rf {} + 2>/dev/null || true
git -C "$SNAPSHOT" init -q -b main
git -C "$SNAPSHOT" add -A
git -C "$SNAPSHOT" \
  -c user.name="$AUTHOR_NAME" -c user.email="$AUTHOR_EMAIL" \
  commit -q -m "Initial public release: Vibe Coded Emulator

Clean source snapshot exported from the private development history.
See PROVENANCE.md. Licensed GPL-3.0-or-later."
note "commit: $(git -C "$SNAPSHOT" log -1 --format='%h %an <%ae>')"

if ! command -v gh >/dev/null 2>&1; then
  die "gh is required to create/configure the GitHub repository. Install it (brew install gh) and run 'gh auth login', then re-run."
fi
gh auth status >/dev/null 2>&1 || die "gh is not authenticated. Run 'gh auth login' first."

step "4/7 create or reuse the repository"
SCOPES="$(gh auth status 2>&1 | sed -n 's/.*Token scopes: //p' | head -1)"
if [[ -d "$SNAPSHOT/.github/workflows" && "$SCOPES" != *"'workflow'"* ]]; then
  die "your GitHub token lacks the 'workflow' scope, required to publish .github/workflows/. Fix it with:  gh auth refresh -h github.com -s workflow   (or remove .github/workflows/ from the snapshot)."
fi
if gh repo view "$REPO" >/dev/null 2>&1; then
  note "repository exists: $REPO"
else
  [[ -z "$BRANCH" ]] || die "review-branch publication requires the existing repository $REPO"
  gh repo create "$REPO" --public --description \
    "Open-source, cross-platform emulator with native apps, offline play, and local game libraries." \
    >/dev/null
  note "created: $REPO"
fi
if [[ -z "$BRANCH" ]]; then
  gh repo edit "$REPO" \
    --description "Open-source, cross-platform emulator with native apps, offline play, and local game libraries." \
    --add-topic emulator --add-topic gba --add-topic nds --add-topic nintendo-3ds \
    --add-topic tauri --add-topic rust --add-topic python --add-topic vulkan \
    --add-topic webassembly --add-topic gplv3 >/dev/null 2>&1 || note "topics/description: partially applied"
else
  note "repository description, topics, and settings left unchanged for review-branch publication"
fi

step "5/7 push main (no force)"
git -C "$SNAPSHOT" remote remove origin 2>/dev/null || true
# `gh auth login` grants an HTTPS token, so HTTPS + gh's credential helper is
# the reliable default. SSH is used only when explicitly requested and a key is
# actually registered with GitHub.
gh auth setup-git >/dev/null 2>&1 || true
PROTOCOL="${AN3_PUBLIC_GIT_PROTOCOL:-https}"
if [[ "$PROTOCOL" == "ssh" ]]; then
  REMOTE="git@github.com:$REPO.git"
  note "using SSH; this requires a key registered at https://github.com/settings/keys"
else
  REMOTE="https://github.com/$REPO.git"
fi
note "remote: $REMOTE"
git -C "$SNAPSHOT" remote add origin "$REMOTE"

if [[ -n "$BRANCH" ]]; then
  SNAPSHOT_COMMIT="$(git -C "$SNAPSHOT" rev-parse HEAD)"
  git -C "$SNAPSHOT" fetch -q origin \
    "refs/heads/$BASE_BRANCH:refs/remotes/origin/$BASE_BRANCH" \
    || die "could not fetch origin/$BASE_BRANCH for the review branch"
  if git -C "$SNAPSHOT" ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
    git -C "$SNAPSHOT" fetch -q origin \
      "refs/heads/$BRANCH:refs/remotes/origin/$BRANCH" \
      || die "could not fetch the existing review branch"
    git -C "$SNAPSHOT" checkout -q -b "$BRANCH" "origin/$BRANCH"
    git -C "$SNAPSHOT" merge-base --is-ancestor "origin/$BASE_BRANCH" "origin/$BRANCH" \
      || die "existing review branch is not based on origin/$BASE_BRANCH"
  else
    git -C "$SNAPSHOT" checkout -q -b "$BRANCH" "origin/$BASE_BRANCH"
  fi
  # Overlay the clean candidate on current public source. Files omitted by the
  # curated snapshot remain intact on main; the development history is never
  # added to this branch.
  git -C "$SNAPSHOT" checkout "$SNAPSHOT_COMMIT" -- .
  git -C "$SNAPSHOT" add -A
  if git -C "$SNAPSHOT" diff --cached --quiet; then
    die "the snapshot has no changes relative to origin/main"
  fi
  git -C "$SNAPSHOT" \
    -c user.name="$AUTHOR_NAME" -c user.email="$AUTHOR_EMAIL" \
    commit -q -m "$COMMIT_SUBJECT" \
    -m "Curated source snapshot exported without private development history. See PROVENANCE.md."
  git -C "$SNAPSHOT" push -u origin "$BRANCH"
  if [[ "$CREATE_PR" -eq 0 ]]; then
    step "7/7 review branch pushed"
    note "branch: $BRANCH"
    note "base: $BASE_BRANCH"
    exit 0
  fi
  # The pull-request text must describe the publication that actually happened.
  # A hard-coded title/body from an earlier publication read as a different
  # change; pass --title/--body-file to be specific, or use the generic text
  # below, which claims only what this script actually verifies.
  pr_body="$(mktemp -t an3-pr-body.XXXXXX)"
  trap 'rm -f "${pr_body:-}"' EXIT
  if [[ -n "$PR_BODY_FILE" ]]; then
    [[ -f "$PR_BODY_FILE" && ! -L "$PR_BODY_FILE" ]] || die "PR body file is not a regular file: $PR_BODY_FILE"
    cp -- "$PR_BODY_FILE" "$pr_body"
  else
    cat > "$pr_body" <<'BODY'
## Summary

Curated public source snapshot exported from the private development history
without that history. See `PROVENANCE.md`.

## Validation

- The fail-closed publication gate ran before this branch was pushed: snapshot
  secret, personal-data and private-infrastructure scans reported no findings.
- Source verification, packaging and device acceptance remain the authority of
  the exact-SHA CI runs and the dedicated platform builders. This pull request
  publishes source, not build artifacts, and does not claim a packaged or
  gameplay result.
BODY
  fi
  if PR_URL="$(gh pr view --repo "$REPO" "$BRANCH" --json url --jq .url 2>/dev/null)"; then
    # An existing pull request is only rewritten for the fields the caller
    # explicitly asked to set; an owner-edited title or body is never clobbered.
    if [[ -n "$PR_TITLE" && -n "$PR_BODY_FILE" ]]; then
      gh pr edit --repo "$REPO" "$PR_URL" --title "$PR_TITLE" --body-file "$pr_body" \
        || die "branch was pushed, but pull request update failed"
    elif [[ -n "$PR_TITLE" ]]; then
      gh pr edit --repo "$REPO" "$PR_URL" --title "$PR_TITLE" \
        || die "branch was pushed, but pull request title update failed"
    elif [[ -n "$PR_BODY_FILE" ]]; then
      gh pr edit --repo "$REPO" "$PR_URL" --body-file "$pr_body" \
        || die "branch was pushed, but pull request update failed"
    else
      note "existing pull request left unchanged (pass --title/--body-file to update it)"
    fi
  else
    PR_URL="$(gh pr create --repo "$REPO" --base "$BASE_BRANCH" --head "$BRANCH" \
      --title "${PR_TITLE:-Update clean public source snapshot}" --body-file "$pr_body")" \
      || die "branch was pushed, but pull request creation failed"
  fi
  rm -f "$pr_body"
  trap - EXIT
  step "7/7 review requested"
  note "pull request: $PR_URL"
  note "branch: $BRANCH"
  exit 0
fi

# A repository created without --source may already contain an initial commit
# (for example a README). Detect it and merge non-destructively when asked:
# no force-push, no history rewrite, and the snapshot's files win.
if git -C "$SNAPSHOT" fetch -q origin main 2>/dev/null; then
  if [[ "$ADOPT_REMOTE" -eq 1 ]]; then
    note "remote main exists; merging it with the snapshot (snapshot files win, no force)"
    git -C "$SNAPSHOT" \
      -c user.name="$AUTHOR_NAME" -c user.email="$AUTHOR_EMAIL" \
      merge -q --allow-unrelated-histories -X ours \
      -m "Merge the existing remote commit into the initial public release" origin/main \
      || die "merge failed; resolve manually in $SNAPSHOT"
  else
    die "the remote repository already has a 'main' branch. Re-run with --adopt-remote to merge it into the snapshot (snapshot files win, no force-push), or delete the repository and re-run."
  fi
fi

if ! git -C "$SNAPSHOT" push -u origin main 2>/tmp/an3-push.err; then
  cat /tmp/an3-push.err >&2
  if grep -q "workflow" /tmp/an3-push.err; then
    die "GitHub rejected the workflow file. Grant the scope and re-run:  gh auth refresh -h github.com -s workflow  &&  tools/publish-github.sh --confirm --adopt-remote"
  fi
  die "push failed (see the message above). Check 'gh auth status'; for SSH errors add a key to GitHub or re-run with AN3_PUBLIC_GIT_PROTOCOL=https."
fi

step "6/7 security settings (best effort; reported individually)"
set +e
gh api -X PATCH "repos/$REPO" \
  -f 'security_and_analysis[secret_scanning][status]=enabled' \
  -f 'security_and_analysis[secret_scanning_push_protection][status]=enabled' >/dev/null 2>&1 \
  && note "secret scanning + push protection: enabled" || note "secret scanning + push protection: NOT applied (plan/permission)"
gh api -X PUT "repos/$REPO/vulnerability-alerts" >/dev/null 2>&1 \
  && note "Dependabot alerts: enabled" || note "Dependabot alerts: NOT applied"
gh api -X PUT "repos/$REPO/automated-security-fixes" >/dev/null 2>&1 \
  && note "Dependabot security updates: enabled" || note "Dependabot security updates: NOT applied"
gh api -X PUT "repos/$REPO/private-vulnerability-reporting" >/dev/null 2>&1 \
  && note "private vulnerability reporting: enabled" || note "private vulnerability reporting: NOT applied"
gh api -X PUT "repos/$REPO/branches/main/protection" --input - >/dev/null 2>&1 <<'JSON' \
  && note "branch protection (require PR + CI): enabled" || note "branch protection: NOT applied"
{
  "required_status_checks": {"strict": true, "contexts": ["test"]},
  "enforce_admins": false,
  "required_pull_request_reviews": {"required_approving_review_count": 0},
  "restrictions": null
}
JSON
set -e

step "7/7 done"
note "repository: https://github.com/$REPO"
note "reminder: keep this repository free of private infrastructure data; run the gate before every future publication."
