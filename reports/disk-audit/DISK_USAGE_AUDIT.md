# Disk Usage Audit

- Date: 2026-09-22
- Host: macOS (Apple Silicon), user `meomeo`
- Scope: local startup disk only. No network mounts, external drives or remote
  filesystems were traversed. Symlinks were not followed into other volumes.
- Method: read-only metadata inspection (`df`, `diskutil`, `tmutil`, `du -shx`,
  `find -xdev`, `ls`, `git worktree list`, `git count-objects`). No contents of
  personal documents were read.

**NO FILES WERE DELETED OR MODIFIED. No cleanup, cache purge, prune, snapshot
deletion, uninstall, move, compression or Git mutation was performed.**

---

## 1. Executive summary

The startup disk is an APFS container of 494.3 GB. The Data volume holds
~445 GB (96% used); only ~20 GB is free.

One issue dominates everything else:

- **`/private/var/folders/0z/w0f005297l7g2_z1_9zzw6km0000gn/X/com.google.Chrome.code_sign_clone`
  = 220 GB** — 160 abandoned Chrome "code-sign clone" temp copies (~1.4 GB
  each), dated 2026-09-15 → 2026-09-21. This single directory is ~49% of all
  used space and is the primary reason the disk is nearly full.

After that, the largest consumers are the AN3 project and its build ecosystem
(~185 GB combined across `~/Documents`, `Codex`, temp build roots and emulators),
Ollama models (21 GB), the Android SDK + AVDs (~40 GB), and application data.

No local Time Machine/APFS snapshots exist, so "purgeable/snapshot" storage is
**not** a meaningful contributor here.

---

## 2. Startup disk capacity

| Item | Value |
| --- | --- |
| Startup volume | `Macintosh HD` (`/dev/disk3s1s1`, sealed system snapshot) |
| File system | APFS |
| Container ceiling | 494.3 GB (494,332,366,848 B) |
| Data volume (`disk3s5`) used | 445.4 GB (445,374,140,416 B) — 96% |
| Free / not allocated | ~20.0 GB |
| System volume used | 12.6 GB |
| Preboot | 9.1 GB |
| Recovery | 1.6 GB |
| VM volume | 5.4 GB |
| FileVault | "No (Encrypted at rest)" |
| `df` capacity (Data) | 460Gi size / 415Gi used / 19Gi avail / 96% |

Note: a `VibeCodedEmulator` disk image (144.5 MB) is mounted as `disk6s1`
(leftover from packaged-DMG verification). It was not unmounted.

---

## 3. Top 20 directories

| # | Path | Size | Category | Explanation |
| --- | --- | --- | --- | --- |
| 1 | `/private/var/folders/0z/…/X/com.google.Chrome.code_sign_clone` | 220 GB | D CACHE (generated) | Abandoned Chrome code-sign temp clones |
| 2 | `~/Documents/Codex` | 80 GB | C/E | Legacy Codex workspaces; `2026-08-12` alone = 79 GB |
| 3 | `/private/var/folders/0z/…/T/opencode` | 38 GB | C | Temp build worktrees from recent sessions |
| 4 | `~/Documents/an3-final-wt` | 26 GB | B | AN3 staging integration worktree |
| 5 | `/Applications` | 26 GB | B/G | Installed apps (incl. FreeCAD, CapCut, iMovie) |
| 6 | `~/Documents/edit an3tocom apps&web` | 22 GB | B | AN3 primary worktree |
| 7 | `~/.ollama` | 21 GB | C/D | Local LLM model blobs |
| 8 | `~/.android/avd` | 21 GB | B/E | Two Android AVDs (13 GB + 8 GB userdata) |
| 9 | `~/Library/Android/sdk` | 11 GB | B | Android SDK (NDK 5.7, sysimg 3.8, emulator 1.1) |
| 10 | `~/Library/Application Support/Codex` | 10 GB | C | Codex desktop browser profile/indexeddb |
| 11 | `/opt/homebrew` | 10 GB | B | Homebrew prefix (incl. 5.3 GB commandlinetools) |
| 12 | `~/Library/Application Support` | 30 GB | B/C/G | Parent: Codex 10G, Firefox 7G, Steam 5.3G, Google 2G, Zalo 1.3G |
| 13 | `~/Library/Caches` | 5.5 GB | D | App caches (Homebrew 1.5G, Google 1.3G, Codex 0.6G…) |
| 14 | `/Library` | 4.4 GB | B/G | System-wide support files |
| 15 | `~/.local/share/opencode` | 4.3 GB | C | OpenCode session DB (`opencode.db` 4.1 GB) |
| 16 | `~/.gradle` | 3.0 GB | D | Gradle caches (Android builds) |
| 17 | `~/.codex` | 2.9 GB | C | Codex CLI sessions (1.7G), thread history, plugins |
| 18 | `~/.npm` | 1.8 GB | D | npm cache |
| 19 | `~/.rustup` | 1.1 GB | B | Rust toolchains + Android std (required by AN3) |
| 20 | `~/Library/pnpm` + `~/.cargo` | 0.5 + 0.5 GB | D/B | pnpm store; cargo registry |

(`~/Documents/Codex/2026-08-12/…/an3-arcade/work/release-train` alone is 24 GB of
historical release-train build output.)

---

## 4. Top 20 files

| # | Path | Size | Type | Category |
| --- | --- | --- | --- | --- |
| 1 | `~/.android/avd/codex-nds-api35.avd/userdata-qemu.img.qcow2` | 13 GB | AVD image | B/E |
| 2 | `~/.android/avd/an3qa-api35.avd/userdata-qemu.img.qcow2` | 8.0 GB | AVD image | B/E |
| 3 | `~/.ollama/models/blobs/sha256-dec52a44…` | 6.1 GB | model blob | C/D |
| 4 | `~/.local/share/opencode/opencode.db` | 4.1 GB | sqlite | C |
| 5 | `~/Library/Android/sdk/system-images/android-35/…/system.img` | 3.6 GB | sysimg | B |
| 6 | `/opt/homebrew/share/android-commandlinetools/system-images/…/system.img` | 3.6 GB | sysimg (dupe) | E/F |
| 7 | `~/.ollama/models/blobs/sha256-9c60bdd6…` | 3.1 GB | model blob | C/D |
| 8 | `~/Library/Application Support/Codex/Default/Partitions/codex-browser-app/File System/001/t/00/00000001` | 2.0 GB | browser cache | C |
| 9 | `~/Library/Application Support/Codex/Default/Partitions/…/File System/001/t/00/00000003` | 1.7 GB | browser cache | C |
| 10 | `~/Library/Application Support/Codex/Default/Partitions/…/IndexedDB/http_192.168.1.8_8092.indexeddb.blob/1/00/2` | 2.0 GB | indexeddb | C |
| 11 | `~/Library/Application Support/Codex/Default/Partitions/…/IndexedDB/https_an3tocom.space_0.indexeddb.blob/2/00/2` | 2.0 GB | indexeddb | C |
| 12 | `~/Library/Application Support/Firefox/…/storage/default/https+++an3tocom.space/idb/…/1` | 2.0 GB | indexeddb | C |
| 13 | `~/Library/Application Support/Firefox/…/storage/default/https+++an3tocom.space/idb/…/1` | 2.0 GB | indexeddb | C |
| 14 | `~/Downloads/test 3ds file decrypted Pokemon X (Europe)…/Pokemon X ….3ds` | 2.0 GB | ROM fixture | G (locally created) |
| 15 | `~/.ollama/models/blobs/sha256-fcc29a2e…` | 1.2 GB | model blob | C/D |
| 16 | `/Applications/CapCut.app/Contents/Frameworks/libVECreator.dylib` | 1.1 GB | app lib | B |
| 17 | `~/.ollama/models/blobs/sha256-daec91ff…` | 1.1 GB | model blob | C/D |
| 18 | `~/Library/Containers/com.docker.docker/Data/vms/0/data/Docker.raw` | 539 MB | VM disk | B/E |
| 19 | `~/Downloads/New Folder With Items` | 1.4 GB | folder | G |
| 20 | `~/Documents/3mf` | 128 MB | folder (CAD) | **A PROTECTED** |

(No individual CAD file exceeds 1 GB; see §13.)

---

## 5. AN3 project / worktree breakdown

`git worktree list` reports **48 worktrees**. The AN3 checkout is
`~/Documents/edit an3tocom apps&web` (shared `.git`). Sizes:

| Worktree / path | Size | Generated dirs (largest) |
| --- | --- | --- |
| `~/Documents/an3-final-wt` | 26 GB | `src-tauri/target` 12 GB, `releases` 0.6 GB |
| `~/Documents/edit an3tocom apps&web` | 22 GB | `src-tauri/target` 18 GB (debug 8.7 / release 3.2 / aarch64-linux-android 4.2), `releases` 3.2 GB, `vendor` 0.34 GB |
| `an3-wt-20260917-1326-integration` | 6.6 GB | target/releases |
| `an3-session-android-qa` | 4.4 GB | target |
| `an3-session-eden` | 4.2 GB | Eden build |
| `an3-wt-20260918-0037-release-hardening` | 4.1 GB | target |
| `an3-wt-parallel-integration` | 3.8 GB | target |
| `an3-session-macos-product` | 2.2 GB | target |
| `an3-wt-20260918-0037-controller-switch` | 1.9 GB | target |
| `an3-wt-macos-build` | 1.8 GB | target |
| `an3-wt-parallel-desktop-controller` | 1.7 GB | target |
| `an3-wt-20260917-1326-promo` | 0.68 GB | |
| ~35 remaining worktrees (`an3-session-*`, `an3-wt-*`, `agent/*`) | ~0.4–0.53 GB each | mostly target/node_modules |

Aggregate: `~/Documents/an3-*` + `edit an3tocom apps&web` = **67 GB**.

Related AN3 storage outside `~/Documents`:
- `/private/var/folders/0z/…/T/opencode` = **38 GB** (session build roots:
  `an3-320-integration` 8.4 GB, `an3-emulation-694e240` 6.2 GB,
  `an3-settings-770227e` 6.2 GB, six ~2.2 GB worktrees, misc).
- `~/Documents/Codex/2026-08-12/…/an3-arcade` = **79 GB**
  (`work/release-train` 24 GB, `native-offline` 21 GB, `work` misc, `reports`).
- `~/Library/Android` 11 GB + `~/.android/avd` 21 GB + `~/.gradle` 3 GB (AN3
  Android builds/emulators).

**Total AN3-attributable ≈ 67 + 38 + 79 + ~35 ≈ 219 GB** (including shared
toolchains it reuses).

Git internals (read-only): each worktree's `.git` is a 4 KB pointer file; the
shared object store lives in the primary repo. `.git/worktrees/` metadata is
negligible; the dominant Git cost is checked-out working trees and their build
outputs, not loose objects. No `git gc`/prune was run.

Dirty state: `~/Documents/an3-final-wt` shows `M AGENTS.md` + `?? docs/handoff/`
(pre-existing). The main worktree is clean of tracked changes. **No worktree is
proposed for removal; several are dirty and require review.**

---

## 6. Android / Gradle / AVD breakdown

| Component | Size |
| --- | --- |
| `~/Library/Android/sdk` | 11 GB |
| ├─ `ndk` (26.3.11579264, 28.2.13676358) | 5.7 GB |
| ├─ `system-images/android-35` | 3.8 GB |
| ├─ `emulator` | 1.1 GB |
| ├─ `build-tools` (28.2, 35.0.0) | 186 MB |
| ├─ `platforms/android-36` | 134 MB |
| ├─ `cmake` | 114 MB |
| └─ `platform-tools` | 37 MB |
| `/opt/homebrew/share/android-commandlinetools` | 5.3 GB (overlaps the SDK; Homebrew-installed copy) |
| `~/.gradle` | 3.0 GB |
| AVD `codex-nds-api35.avd` | 13 GB (`userdata-qemu.img.qcow2`) |
| AVD `an3qa-api35.avd` | 8.1 GB (`userdata-qemu.img.qcow2`) |

- **AVDs:** `codex-nds-api35` (13 GB) and `an3qa-api35` (8.1 GB). The AN3
  regression harness and the current emulator session (`emulator-5554`,
  `codex-nds-api35`) depend on these. **Do not remove without review.**
- **NDK versions:** AN3's Android build currently references NDK
  `26.3.11579264` (`build-android-staging.sh` default, `NDK_HOME`), and
  `28.2.13676358` is also installed. The older/extra NDK is
  **POSSIBLE REVIEW CANDIDATE**, not safe-to-delete — confirm which version the
  build uses before removing either.
- `system-images` is duplicated between `~/Library/Android/sdk` and
  `/opt/homebrew/share/android-commandlinetools` (two 3.6 GB `system.img`).

---

## 7. Rust / Cargo breakdown

| Component | Size | Notes |
| --- | --- | --- |
| `~/.rustup` | 1.1 GB | toolchains incl. Android std targets required by AN3 |
| `~/.cargo` (registry) | 0.46 GB | crate sources/cache |
| AN3 `src-tauri/target` (main worktree) | 18 GB | debug 8.7, release 3.2, `aarch64-linux-android` 4.2 |
| `an3-final-wt` `target` | 12 GB | |
| Other worktree `target` dirs | ~20–25 GB combined | many `agent/*`/`session/*` worktrees |

Rust build outputs across worktrees are the largest AN3 **generated** category.
`~/.rustup` is **ACTIVE/REQUIRED** (Android builds need rustup's Android std) —
not a cleanup candidate. `target/` trees are rebuildable but are active build
state for each worktree.

---

## 8. Node / Python / Homebrew breakdown

| Component | Size | Category |
| --- | --- | --- |
| `/opt/homebrew` | 10 GB | B (Homebrew prefix + 5.3 GB commandlinetools) |
| `~/Library/Caches/Homebrew` | 1.5 GB | D (downloaded bottles) |
| `~/.npm` | 1.8 GB | D (npm cache) |
| `~/Library/pnpm` | 0.5 GB | D (pnpm store) |
| `~/Library/Caches/pnpm` | 0.11 GB | D |
| `~/Library/Caches/pip` | 0.20 GB | D |
| `~/Library/Caches/com.apple.python` | 0.07 GB | D |
| `~/Library/Python` | 0.04 GB | B |

No project-level Python virtualenvs (`.venv`) were found in the AN3 worktrees.
No CMake/Ninja trees outside the worktree build roots were found.

---

## 9. OpenCode / Codex / CodeGraph breakdown

| Component | Size | Category |
| --- | --- | --- |
| `~/Library/Application Support/Codex` | 10 GB | C (browser profile/indexeddb) |
| `~/.codex` | 2.9 GB | C (`sessions` 1.7G, `thread_history_1.sqlite` 0.46G, `plugins` 0.34G, `logs_2.sqlite` 96M) |
| `~/.local/share/opencode` | 4.3 GB | C (`opencode.db` 4.1 GB session history) |
| `~/Library/Application Support/ai.opencode.desktop` | 0.45 GB | C |
| `~/Library/Caches/Codex` | 0.64 GB | D |
| `~/.config/opencode` | 61 MB | B (config; keep) |
| `~/.agents` | 0.43 MB | B (skills; keep) |
| `.codegraph` (main worktree) | 39 MB | C (regenerable index) |

Agent history/skills/config were not deleted and are not proposed for removal.
The large items are generated session/browser caches.

---

## 10. macOS Library / application data

| Path | Size | Category |
| --- | --- | --- |
| `~/Library/Application Support` | 30 GB | B/C/G |
| ├─ Codex | 10 GB | C |
| ├─ Firefox | 7.0 GB | B/G |
| ├─ Steam | 5.3 GB | B/G |
| ├─ Google | 2.0 GB | B |
| ├─ ZaloData | 1.3 GB | B/G |
| ├─ Code | 1.0 GB | B |
| ├─ dsh-desktop | 0.70 GB | B |
| ├─ minecraft | 0.60 GB | B |
| ├─ ai.opencode.desktop | 0.45 GB | C |
| ├─ BambuStudio(+Beta) | 0.49 GB | B (CAD/3D printing — protected context) |
| `~/Library/Android` | 11 GB | B |
| `~/Library/Caches` | 5.5 GB | D |
| `~/Library/Containers` | 0.89 GB | B/G (Docker 0.56 GB) |
| `~/Library/pnpm` | 0.53 GB | D |
| `~/Library/Arduino15` | 0.38 GB | B |
| `~/Library/Logs` | 41 MB | C |

Application containers were identified by vendor and **not** marked safe to
delete merely for size.

---

## 11. APFS / Time Machine snapshots

- `tmutil listlocalsnapshots /` → **none**.
- The System volume is a sealed APFS snapshot (`disk3s1s1`, snapshot
  `7290E727-…`), which is normal macOS system sealing, not a user snapshot.
- **Conclusion:** local snapshots are **not** contributing to the apparent disk
  usage. The "System Data" pressure is explained by the measured directories
  above (chiefly the 220 GB Chrome clone directory on the Data volume).

---

## 12. Duplicate generated artifacts

Byte-identical / same-name generated data found more than once:

| Duplicate set | Locations | Approx. duplicate size |
| --- | --- | --- |
| 3.2.0 six-artifact release | `…/an3-320-integration/native-offline/releases/*` **and** `…/work/release-train/build-…/artifacts/*` | ~336 MB (one extra copy) |
| Android `system.img` (android-35) | `~/Library/Android/sdk/...` and `/opt/homebrew/share/android-commandlinetools/...` | ~3.6 GB (one extra copy) |
| Historical release tarballs | `~/Documents/Codex/2026-08-12/.../work/*.tgz` (~0.46 GB each) | ~1.4 GB+ |
| Release-train build roots | `…/work/release-train` (24 GB, Codex) and temp build roots | overlapping generated output |

Additionally, release artifacts are stored per-worktree
(`~/Documents/edit an3tocom apps&web/native-offline/releases` = 3.2 GB,
`an3-final-wt/.../releases` = 0.64 GB, etc.). These are generated/re-downloadable
but their provenance differs (different builds); hashing was not performed
exhaustively. **No CAD/design file is included in this duplicate analysis.**

---

## 13. Protected user data

**Category A — PROTECTED USER DATA. Never remove or propose removal.**

CAD / design / manufacturing files found under `~/Documents` (and elsewhere):

| Extension group | Count | Aggregate size |
| --- | --- | --- |
| `*.FCStd`, `*.FCStd1`, `*.fcstd`, `*.fcstd1` (FreeCAD) | | |
| `*.step`, `*.STEP`, `*.stp`, `*.STP` (STEP) | | |
| `*.3mf`, `*.3MF` (3MF) | | |
| **Combined** | **262 files** | **~281 MB** |

These include parts, assemblies and 3D-print models (camera mounts, holders,
gears, risers, `~/Documents/3mf` = 128 MB, `.FCBak` backups, etc.). They are
small relative to the disk but are **permanently protected**:

- They are NOT marked reclaimable.
- No duplicate-removal, `rm`, archival or dedup is recommended for them.
- `.FCBak` FreeCAD backup files are treated as **protected user data** too.

Other conservatively-protected/unknown items: personal documents, photos,
`~/Downloads` ROM/homebrew fixtures (locally created), `~/Documents/Klei`,
`~/Documents/dsh`, Arduino sketches, and any unknown user-created document.
These are classified REVIEW/PROTECTED, not safe-to-delete.

---

## 14. Potential reclaimable space

Estimates only. **Nothing will be deleted without explicit approval.**

| Group | Path / component | Current size | Est. reclaimable | Why it exists | Consequence if removed | Rebuildable? | Confidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LOW RISK (after approval) | Chrome `X/com.google.Chrome.code_sign_clone` | 220 GB | ~220 GB | Abandoned Chrome code-sign temp clones | None for user data; Chrome may recreate clones on next update | Regenerated automatically | High |
| LOW RISK | Temp build roots `/private/var/folders/…/T/opencode` | 38 GB | ~38 GB | Session build worktrees | Build outputs lost; reproducible from source | Yes (rebuild) | High |
| REQUIRES REVIEW | `~/Documents/Codex` (legacy workspaces) | 80 GB | up to ~79 GB | Historical Codex work incl. `release-train` 24 GB | Historical evidence/builds lost | Partly | Medium |
| REQUIRES REVIEW | AN3 worktrees (`an3-*`), incl. `target/` trees | ~67 GB (Documents) | large subset | Parallel/agent/session worktrees | Losing a worktree loses uncommitted work | Git-recoverable if committed | Medium |
| REQUIRES REVIEW | Android AVDs | 21 GB | 0–21 GB | Emulators | Current emulator session depends on one | Recreated | Medium |
| REQUIRES REVIEW | Extra NDK / Homebrew commandlinetools | 5.7 GB NDK + 5.3 GB | ~5.3 GB dupe | Toolchains | Builds break if the referenced version is removed | Redownloadable | Medium |
| REQUIRES REVIEW | Ollama models | 21 GB | 0–21 GB | Local LLMs | Re-download needed | Yes | Medium |
| CACHE (regenerable) | `~/.npm`, `~/Library/Caches/Homebrew`, pip/pnpm caches, `~/Library/Caches` | ~8 GB | ~6 GB | Package/app caches | Slower next install | Yes | Medium |
| REVIEW | Codex app profile + `~/.codex` sessions + `opencode.db` | ~17 GB | large subset | Session history/browser cache | History lost | No (history) | Low–Medium |
| DO NOT TOUCH | CAD/design files, `~/Library/Application Support` app data, toolchains, `.git` | — | 0 | User data / active | Data loss | No | High |

**Conservative headline estimate:** the single Chrome clone directory alone is
~220 GB and is the safest large reclaim candidate. Combined LOW-RISK (Chrome
clones + temp build roots) ≈ **258 GB**. Additional REQUIRES-REVIEW material
(legacy Codex workspaces, old worktrees, AVDs, Ollama, caches) could add tens of
GB more but needs your decision.

---

## 15. Recommended cleanup candidates — approval required

Ranked for your review. **No commands are provided and nothing was executed.**

1. **Chrome `code_sign_clone` directory (220 GB)** — highest impact, lowest risk.
   Generated temp clones, not user data. Recommend investigating why Chrome is
   leaving them (Chrome update interruption) before removing.
2. **OpenCode/Codex temp build roots `/private/var/folders/…/T/opencode`
   (38 GB)** — reproducible build outputs from recent sessions.
3. **Legacy Codex workspaces `~/Documents/Codex/2026-08-12` (79 GB)** — includes
   24 GB of historical `release-train` output; review which are still needed.
4. **Redundant AN3 worktrees** — review each for committed status; ~35 small
   worktrees plus large `target/` trees. Keep dirty worktrees.
5. **Android AVDs (21 GB) and duplicate Homebrew commandlinetools (5.3 GB)** —
   review emulator needs and toolchain references first.
6. **Ollama models (21 GB)** — remove only unused models.
7. **Developer caches (~6 GB)** — npm/Homebrew/pip/pnpm caches.

---

## 16. Unknown / review-required items

| Item | Size | Why unknown |
| --- | --- | --- |
| `~/Documents/Klei` | 44 MB | Game data; user content — REVIEW |
| `~/Documents/dsh`, `dsh-desktop` | 26 MB / 703 MB | Unknown app — REVIEW |
| `~/Documents/3mf` and CAD files | 128 MB / 281 MB total | **PROTECTED USER DATA** |
| `~/Downloads/New Folder With Items`, ROM fixtures | ~3.4 GB | Possibly user-managed content — REVIEW |
| `~/Library/Application Support/{Firefox,Steam,Google,ZaloData,minecraft}` | ~16 GB | App data; user state — REVIEW |
| `~/Documents/Codex` older dated folders | ~1.4 GB | Unknown historical evidence — REVIEW |
| `~/Library/Arduino15` | 378 MB | Toolchain — REVIEW |

---

## Appendix — methodology & safety

- Commands used were read-only: `df`, `diskutil info/apfs list`,
  `tmutil listlocalsnapshots`, `du -shx`, `find -xdev`, `ls`, `git worktree
  list`, `git count-objects`, `docker system df` (daemon was down, so skipped).
- `-xdev` kept traversal on the local startup filesystem; symlinks were not
  followed into other volumes; network mounts were not touched.
- No `sudo` was used. No privileged location was accessed.
- No file contents of personal documents were read.
- No cleanup, deletion, move, compression, uninstall, prune, snapshot deletion
  or Git mutation was performed.

**NO FILES WERE DELETED OR MODIFIED.**

---

## Follow-up snapshot — 2026-10-09

This is a read-only resnapshot after the previously recorded cleanup. `du`
figures below are logical directory footprints and may overcount APFS clones;
`df` is the filesystem-level capacity measurement.

- Startup Data volume: 460 GiB size, 295 GiB used, 135 GiB available (69% used).
- `git worktree list` reports 16 registered worktrees, about 36 GiB total by
  `du -sh`. Twelve have modified or untracked files. All remain preserved.
- Active checkout: `/Users/meomeo/Documents/edit an3tocom apps&web`, branch
  `feature/phone-controller-cross-platform`, HEAD
  `ce84bdc6e88b85ca2a8944d9fc3bb375bdc3fef2` at the start of this follow-up.
  Its 8.0 GiB footprint includes `native-offline/releases` 3.3 GiB,
  `src-tauri/gen` 2.0 GiB, `src-tauri/target` 1.9 GiB, and `vendor` 339 MiB.
- The read-only legacy Codex worktree is 9.4 GiB: `native-offline` 3.7 GiB and
  `work` 5.1 GiB. Within `work`, timestamped production-deploy artifact roots
  occupy 2.3 GiB. It was not modified during this follow-up.
- `an3-330-integration` is 6.9 GiB, including `work` 4.9 GiB and
  `native-offline` 1.8 GiB. `work/release-train` is 3.3 GiB and contains
  repeated timestamped source-freeze/build roots.
- `an3-final-wt` is 5.8 GiB, including `work` 4.3 GiB and
  `native-offline` 1.3 GiB. Its release-train scratch is 3.6 GiB, again split
  across repeated frozen-source and build-attempt directories.
- `/private/tmp/an3-vce-3313-assets` is 1.4 GiB, almost all its
  `native-offline/src-tauri/target` (1.3 GiB); it has untracked and modified
  work and was preserved.

The strongest causal evidence is the combination of (1) the September 22
inventory of 48 worktrees with independent Rust/Android/native build outputs,
(2) repeated release-train roots of 140 MiB to 1.6 GiB each in the retained
integration worktrees, and (3) the release script's timestamped unique output
paths with no successful local scratch cleanup. A full extracted macOS source
tree and its build outputs stayed beside every successful artifact set. The
other 2026-09-22 major causes and actual cleanup are recorded in
`DISK_CLEANUP_LOG.md`: about 173 GiB was reclaimed, primarily from old Codex
workspaces, temporary OpenCode worktrees, obsolete AN3 worktrees/targets, and
Ollama models. The apparent 220 GiB Chrome clone directory was APFS clone
inflation; deleting it reclaimed about 1 GiB physical, not 220 GiB.

At this follow-up snapshot, no local cargo/rustc, Gradle, Android emulator,
package builder, or test loop was active. An idle `adb` server remained. No
existing worktree, artifact, cache, AVD, report, or other user data was deleted
in this follow-up; the surviving worktrees with dirty or uncertain state need
source/evidence review before any further removal.

Prevention now includes the existing non-destructive 40 GiB warning / 25 GiB
stop preflight on package builds, plus this follow-up's checks before release
source freezing and coordinated builds. On successful coordinated builds, the
script now retains the exact artifacts and source manifest and removes only
the run's exact extracted macOS build copy; failed roots remain for diagnosis.
The targeted disk-preflight/release-train suite passed 16 tests and the script
passed `bash -n`. The public storage-preflight PR #9 is still open; its required
CI tests pass, the duplicate native matrix is canceled, and it remains subject
to user review before merge. No push, release, or deployment occurred.
