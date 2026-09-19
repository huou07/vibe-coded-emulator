# Git worktree and branch policy

Every top-level **write** session gets its own branch and worktree. Writers never
share a worktree. Use `scripts/worktree.py`; do not hand-roll the commands.

## Names

- Run ID: `<YYYYMMDD>-<HHMM>` (UTC or local, recorded in the manifest).
- Worker branch: `agent/<run-id>/<domain>`
- QA/verify branch: `agent/<run-id>/<domain>` (for example `qa`)
- Integration branch: `integration/<run-id>`
- Promotion (optional): `promotion/<run-id>`
- Worktree: `<repo-parent>/an3-wt-<run-id>-<domain>` (default `..`; override only
  when the parent is unavailable).

Domains are lowercase `[a-z0-9-]+`, no slashes, no spaces.

## Creation rules

- Record the committed base SHA in the manifest before creating anything.
- Start independent workers from the **same** recorded base SHA unless a DAG
  dependency requires a later one.
- Creation is idempotent and failure-safe: an existing correct worktree/branch is
  reported `EXISTING`; a mismatched or locked path fails closed.
- Never create a worktree over a dirty path or an existing unrelated branch.

## Hard prohibitions

Never automatically, and never without explicit instructions for a specific SHA:

- `git reset --hard` (especially on user work), `git clean`, force checkout
- `git push --force`, rewriting another worker's branch
- `git checkout`/`stash`/`reset` inside a worktree you do not own
- editing the main checkout or another session's checkout

## Baseline discipline

Before a shared-subsystem edit: identify its guards, run the matching tests on the
base, then run the same tests after the change. A worker that crashes keeps its
worktree and commits; it is never discarded automatically.

## Cleanup

`cleanup_run.py` removes worktrees only when they are clean and their commits are
integrated (or the caller passes an explicit override), removes branches only when
merged, and never touches the main worktree. Prefer `--dry-run` first. Evidence
stays under the Git common dir, not in the product tree.
