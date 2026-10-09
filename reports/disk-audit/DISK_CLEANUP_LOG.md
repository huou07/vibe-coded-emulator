# Disk Cleanup Log — AN3 archive + development-history-preserving cleanup

- Date: 2026-09-22
- Scope: macOS local startup disk (user `meomeo`).
- Order followed: inventory → extract history → write history docs → validate →
  delete → measure.
- History documents (created and validated BEFORE any deletion):
  - `docs/history/AN3_LEGACY_WORKSPACE_ARCHIVE.md`
  - `docs/history/AN3_DEVELOPMENT_HISTORY.md`
- Baseline preserved: AN3 3.2.0, runtime source
  `bde744076c0a1b0667658231991ec735119995e1`, catalog `644206b`, live staging
  `staging-ccbf2f4f985fa550`.

## Phase 1 — BEFORE state (measured 2026-09-22)

### Startup disk
- `df -h /System/Volumes/Data`: **460Gi size / 415Gi used / 19Gi avail / 96%**.
- APFS container 494.3 GB; Data volume 445.4 GB used; no local TM snapshots.

### AN3 repository / worktrees
- Primary repo: `/Users/meomeo/Documents/edit an3tocom apps&web`
  (`feature/phone-controller-cross-platform` @ `a1a6e3c`).
- 48 registered worktrees (`git worktree list`).
- `~/Documents/an3-*` + main worktree ≈ **67 GB**.
- `~/Documents/Codex` ≈ **80 GB** (legacy AN3 workspaces).
- OpenCode temp roots `/private/var/folders/0z/…/T/opencode` ≈ **38 GB**.
- Git objects: 58.80 MiB loose + 210.50 MiB pack (no gc/prune performed).

### Chrome anomaly
- `/private/var/folders/0z/w0f005297l7g2_z1_9zzw6km0000gn/X/com.google.Chrome.code_sign_clone`
  = **220 GB**, 160 `code_sign_clone.*` entries (~1.4 GB each), dated
  2026-09-15 → 2026-09-21.

### Ollama
- `~/.ollama` = **21 GB** (model blobs incl. 6.1 GB, 3.1 GB, 1.2 GB, 1.1 GB).

### Android
- `~/Library/Android/sdk` = 11 GB (NDK 5.7 GB: `26.3.11579264`, `28.2.13676358`;
  system-images 3.8 GB; emulator 1.1 GB).
- AVDs: `codex-nds-api35.avd` 13 GB; `an3qa-api35.avd` 8.1 GB.
- Active emulator `emulator-5554` = **an3qa-api35**.
- `~/.gradle` 3 GB; `/opt/homebrew/share/android-commandlinetools` 5.3 GB.

### Other (kept)
- `~/.rustup` 1.1 GB, `~/.cargo` 0.46 GB, `~/.npm` 1.8 GB,
  `~/Library/Caches/Homebrew` 1.5 GB, `~/.local/share/opencode` 4.3 GB,
  `~/.codex` 2.9 GB, `~/Library/Application Support/Codex` 10 GB.

### Protected user data (never removed)
- 262 CAD files (`*.FCStd`, `*.step`, `*.stp`, `*.3mf`), ≈ 281 MB.

## Planned removals (approved)
1. Chrome `code_sign_clone` (Phase 14).
2. Ollama model data (Phase 16).
3. Stale OpenCode temp build worktrees (Phase 13).
4. Obsolete AN3 worktrees with no unique commits and no real source changes (Phase 10).
5. Old Codex workspaces with no unique uncommitted source (Phase 12).
6. `codex-nds-api35` AVD if unreferenced (Phase 15).
7. Old build outputs (`target/`, build trees) in retained worktrees (Phase 11).

## Retained (not removed)
- Main worktree, `an3-320-integration` (3.2.0 release source),
  `an3-final-wt` (rollback line), any worktree with real source changes,
  `an3-staging-lan-probe` (unique commit), `an3qa-api35`, current SDK/NDK,
  Rust toolchains, `opencode.db`, `~/.codex` sessions, protected CAD files.

## AFTER state (measured 2026-09-22, end of run)

- `df -h /System/Volumes/Data`: **460Gi size / 242Gi used / 191Gi avail / 56%**
  (BEFORE: 415Gi used / 19Gi avail / 96%).
- **Reclaimed: ~173 GiB (~186 GB).**

### Reclaimed by category (approx.)
| Category | Reclaimed | Note |
| --- | --- | --- |
| Chrome `code_sign_clone` | ~1 GB | **Correction:** the 220 GB `du` figure was APFS clone-inflated; only ~1 GB was physical. |
| Ollama models (`~/.ollama/models`) | ~21 GB | identity key + cache kept |
| Stale OpenCode temp worktrees (8) + `/private/tmp/an3-pre-eden2` | ~25 GB | git worktree remove |
| Codex (`vibe-coded-emulator`, an3-arcade `target`/`release-train`/tarballs) | ~69 GB | dirty an3-arcade source + reports kept |
| Obsolete AN3 worktrees (27) | ~33 GB | branches retained in Git |
| Main + an3-final-wt Rust `target/` | ~25 GB | rebuildable |

### Remaining AN3 worktrees (8)
- `edit an3tocom apps&web` (`feature/phone-controller-cross-platform` @ a1a6e3c) — active
- `an3-320-integration` (`integration/phone-controller-3.2.0` @ 644206b) — 3.2.0 release source
- `an3-final-wt` (`integration/final-program` @ 8dd5f52) — 3.1.0 rollback line
- `an3-session-release` (`session/release-security`) — dirty source
- `an3-session-macos-product`, `an3-wt-macos-build` — dirty vendor/generated binaries
- `an3-staging-lan-probe` (`/private/tmp`) — unique commit `4192565`
- Codex `an3-arcade` (`ui/production-ux-refresh`) — dirty source + early reports

### Post-cleanup verification
- Protected CAD files: **262 files / 280.7 MB — unchanged**.
- History docs present: `docs/history/AN3_LEGACY_WORKSPACE_ARCHIVE.md`,
  `docs/history/AN3_DEVELOPMENT_HISTORY.md`.
- 3.2.0 source intact (`644206b`); `verify-release-catalog.py` = PASS (6 installers).
- Main branch/HEAD unchanged (`a1a6e3c`); no production/staging changes made.
- Chrome clone directory absent; `~/.ollama` = 12 KB; `~/Documents/Codex` = 11 GB;
  opencode temp = 8.9 GB; AVDs = 21 GB (both kept).

### Retained on purpose (dirty / unique / owner data / uncertain)
- Both Android AVDs — `codex-nds-api35` is recorded as containing the owner's
  test ROMs/saves (do not disturb), so it was **not** removed.
- Both NDKs (`26.3.11579264` referenced by build scripts; `28.2.13676358`
  unreferenced but a toolchain → kept).
- Codex `an3-arcade` (dirty source + only copy of early reports).
- `session/release-security`, `session/macos-product`, `agent/macos-build` (dirty).
- `an3-staging-lan-probe` (unique commit).
- `~/.codex` sessions, `~/.local/share/opencode/opencode.db`, current SDK/NDK,
  Rust toolchains, `~/Library/Application Support/Codex`, protected CAD files.
