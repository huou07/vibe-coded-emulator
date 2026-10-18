# NEXT-VCE — continue under the quality system

Authority for this work: [./AGENT-AUTHORITY.md](./AGENT-AUTHORITY.md). This prompt
is an owner instruction from 2026-10-17 and grants nothing that file forbids. It
explicitly authorises the changes listed below, including the ones that touch
protected control-plane files; that authorisation is the only reason they are in
scope.

## What changed before you start

A reorganization ran while your session was paused. Read these first:

- [../docs/QUALITY.md](../docs/QUALITY.md) — VCE's definition of good and its
  known gaps.
- `~/AEH/docs/quality-system.md` — the process this repository now follows.

Two gates now exist and mean different things:

| Gate | Command | Proves |
|---|---|---|
| verify | `bash tools/verify-project.sh` | docs refs, Python and JS tests, native source checks, whitespace |
| acceptance | `bash tools/acceptance.sh` | the above, plus the fail-closed publication gate when a candidate snapshot exists |

`docs/AGENT-AUTHORITY.md` and `docs/prompts/FINISH-VCE.md` are now mode 644 and
readable by the owner; the standing-authority sentences in `FINISH-VCE.md` and the
duplicate mandate in `.agents/skills.md` are superseded by `AGENT-AUTHORITY.md`.
`docs/AGENT-AUTHORITY.md` is now listed in the documentation index.

## Do these, in order

1. **Make the published workflow real or delete it.**
   The published `native-build.yml` (under `tools/publication/.github/workflows/`)
   called
   `tools/release-train.sh` five times, but `tools/build-public-snapshot.sh` never
   copies that script into the candidate, and its `paths:` filters reference a
   `tools/testrom/**` that does not exist. Either copy the release train and a real
   fixture directory into the snapshot and make `publication-check.sh` assert that
   every `run:` script path exists in the candidate, or remove the workflow and
   stop advertising cross-platform CI. Add the workflow↔script presence assertion
   to `test_publication_workflows.py` so it cannot regress.
2. **Close the sanitizer hole.** Add `^/home/[^/]+/` and `~/` to
   `PROJECT_PATTERNS` and to the survivor grep; extend `check-docs-refs.py` to
   scan source and test files for absolute host paths (today it scans `*.md`
   only); add `docs/prompts/`, `docs/AGENT-AUTHORITY.md`,
   `AGENT_INTERACTION_CAPABILITY_AUDIT.md` and `.codegraph` to the forbidden-path
   list. `tests/an3ctl.test.mjs` has already carried an absolute home-directory path.
3. **Turn skips into evidence gaps.** Make the fixture-dependent emulator lane
   fail loudly when it claims an emulator lane and no fixture exists, and print a
   machine-readable skip manifest from `verify-project.sh` so a green run cannot
   hide 20 skipped tests.
4. **Fix the wrong path and the false claim.** `docs/AGENT-AUTHORITY.md` and
   `docs/development-workflows.md` point at the staging build script by its bare
   relative name whose real location is `native-offline/scripts/`;
   `tools/publication/docs/building.md`
   says cores are not vendored as binaries while 318 vendored files are tracked.
   Fix both, and make the doc-reference checker validate a bare `scripts/<>` token
   instead of ignoring unknown roots.
5. **Add the missing gates.** One automated performance budget (frame-time p95 or
   audio underruns from `--status-json`) and one browser test asserting the
   `docs/design-system.md` and `docs/ui-page-contract.md` invariants (360 px
   no-overflow, control height, token values), or record in `../QUALITY.md` why
   neither exists yet.
6. **Delete or archive what lies.** The orphaned one-shot scratch-audit script is
   referenced by nothing; the roadmap document (later archived as
   `docs/archive/vibe-coded-roadmap-2026-10.md`) is absent from the index;
   `AGENT_INTERACTION_CAPABILITY_AUDIT.md` exists only in the index. Move stale
   documents to `docs/archive/` with a one-line reason, and document the
   sparse-checkout in `docs/development-workflows.md` so `git status` hiding 768
   paths is not a surprise.

## Rules

- Work on the current branch. Do not force-push, rewrite published history, deploy
  to production, or infer publication authority from a green gate.
- `tools/publication-check.sh` fails closed: if a scanner cannot run, publication
  is blocked, not waved through.
- One coherent change per commit, with the gate result in the message.
- Never weaken an assertion, scanner or environment boundary to obtain PASS.
- Record evidence with the exact SHA in the project's existing evidence location.
- Report `IMPLEMENTED`, `VERIFIED_*`, `ACCEPTED` and `BLOCKED/UNVERIFIED`
  separately, and name what you did not run.

## Stop when

Every item is done with recorded evidence or reported as blocked with the exact
missing capability. Then hand off: branch, HEAD, gate result, unverified items,
next action.
