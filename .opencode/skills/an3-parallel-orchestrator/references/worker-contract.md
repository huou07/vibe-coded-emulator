# Worker contract

A worker is a **top-level session** (`opencode run`) running the `an3-worker` agent
in its own worktree. Render its prompt from `templates/worker-prompt.md`.

## The worker receives

`runId`, `baseSha`, `worktree`, `branch`, `domain`, `goals`, `nonGoals`,
`dependencies`, `sharedApiContracts`, `ownedFiles`, `resourceRules`, `expectedTests`,
`modelPolicy`, `commitPolicy`, and the applicable reference files only (load
platform guidance only for affected platforms).

## Worker rules

- Stay inside the declared domain and owned files; make the smallest coherent change.
- No unrelated refactors, renames, or formatting.
- Do not merge another worker; do not rebase an active worker branch.
- Do not deploy staging or production; do not push unless explicitly authorized.
- Commit coherent, reviewable milestones (avoid giant uncommitted changes).
- Inspect `git diff` before every commit; remove accidental changes.
- Run the expected tests before handoff; report failures honestly.
- Report dependencies, shared interfaces, and shared files touched.
- If blocked, record `BLOCKED` with exact evidence; never fake or mock real behavior.
- Python is 3.9-compatible. Load `an3-codegraph-first` before exploring code.
- Obey `AGENTS.md` and the regression guards.

## Model

Only `opencode-go/deepseek-v4.1-flash`. The worker may spawn at most 3 concurrent
subagents (read-only roles only). The worker must not create top-level sessions.

## Machine-readable status

End every milestone report with exactly:

```
WORKER_STATUS_BEGIN
{ ...templates/worker-status.json shape... }
WORKER_STATUS_END
```

Validate parsed status with `validate_candidate.py status` where practical. Do not
depend on prose alone. The worker commits its branch and reports `READY_FOR_REVIEW`
for the orchestrator; it does not integrate.
