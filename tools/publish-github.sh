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

usage() {
  cat <<'USAGE'
Usage: tools/publish-github.sh --confirm [--repo OWNER/NAME] [--snapshot DIR]

  --confirm        required; acknowledge that this publishes publicly
  --adopt-remote   merge an existing remote main into the snapshot (no force-push)
  --repo OWNER/NAME  default: huou07/vibe-coded-emulator
  --snapshot DIR     default: work/public-snapshot
  -h, --help       show this help

Environment: AN3_PUBLIC_AUTHOR_NAME, AN3_PUBLIC_AUTHOR_EMAIL
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --confirm) CONFIRMED=1; shift ;;
    --adopt-remote) ADOPT_REMOTE=1; shift ;;
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

[[ "$CONFIRMED" -eq 1 ]] || die "refusing to publish without --confirm (this is intentional)"
command -v git >/dev/null || die "git is required"
command -v python3 >/dev/null || die "python3 is required"

OWNER="${REPO%%/*}"
NAME="${REPO##*/}"
AUTHOR_NAME="${AN3_PUBLIC_AUTHOR_NAME:-$OWNER}"
AUTHOR_EMAIL="${AN3_PUBLIC_AUTHOR_EMAIL:-${OWNER}@users.noreply.github.com}"

step "1/7 build the sanitized snapshot"
"$ROOT/tools/build-public-snapshot.sh" "$SNAPSHOT" >/dev/null

step "2/7 security gate (fail closed)"
AN3_PUBLICATION_CANDIDATE="$SNAPSHOT" "$ROOT/tools/publication-check.sh" "$SNAPSHOT"

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
  gh repo create "$REPO" --public --description \
    "Open-source, cross-platform emulator with native apps, offline play, and local game libraries." \
    >/dev/null
  note "created: $REPO"
fi
gh repo edit "$REPO" \
  --description "Open-source, cross-platform emulator with native apps, offline play, and local game libraries." \
  --add-topic emulator --add-topic gba --add-topic nds --add-topic nintendo-3ds \
  --add-topic tauri --add-topic rust --add-topic python --add-topic vulkan \
  --add-topic webassembly --add-topic gplv3 >/dev/null 2>&1 || note "topics/description: partially applied"

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
