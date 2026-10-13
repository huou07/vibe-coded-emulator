# Home scratch cleanup — 2026-10-13

Branch `feature/phone-controller-cross-platform`, HEAD `deade56`.

## Problem

`/home/huou07` held 52G of VCE/an3 build scratch directly in `$HOME`: ten flat
copies of the project plus three acceptance-run trees. Nothing referenced them,
but each carried a full `target/`, Gradle and dependency cache.

Verified before touching anything:

- Live services run from `/opt/an3-arcade` and
  `/opt/an3-arcade-staging/current` (user `tvshare`). No process had a working
  directory or open file under the scratch roots.
- No path under `app.py`, `docs/`, `tools/` or `deploy/` referenced a scratch
  root.
- Only `~/eden` was a Git repository; every other root was a plain copy with no
  history to lose.
- `/opt/an3-arcade-backups` already held 38 deployment snapshots.

## Result

`/home/huou07`: **52G → 17G**.

| Stage | Action | Reclaimed |
| --- | --- | --- |
| Tier 1 | Removed regenerable build caches (`target/`, `node_modules/`, Gradle `build/`, `.cache`, `.gradle`, `.cxx`, `.externalNativeBuild`, flatpak checkouts) plus the Cargo cache root `an3-release-cache` | ~26G |
| Tier 2 | Curated acceptance evidence into `docs/evidence/linux-runtime-2026-10/`, archived the full run trees, emptied them | ~2.2G |
| Tier 3 | Archived the source-only copies to zstd tarballs, then emptied them | ~7G net |

## Archive

11.8G of source compressed to 4.9G. Every tarball was verified with
`tar --zstd -tf` before any original was emptied.

`/home/agents-worker/vce-scratch-archive/`

| Tarball | Entries | Size |
| --- | --- | --- |
| `an3-parity-build.tar.zst` | 58417 | 3.0G |
| `an3-verify.tar.zst` | 1471 | 775M |
| `an3-rt.tar.zst` | 1596 | 513M |
| `an3-product-5de0a64.tar.zst` | 1290 | 218M |
| `eden.tar.zst` | 33882 | 71M |
| `huou07-release-7c3a06d.tar.zst` | 70 | 116K |

`evidence/` additionally holds `vce-342-linux-ui-acceptance.tar.zst`,
`vce-342-statecheck-2026-10-08.tar.zst` and
`vce-352-linux-runtime-20261009.tar.zst`.

Restore with `tar --zstd -xf <tarball> -C /home/huou07`.

## Safety notes

- `src-tauri/gen` was deliberately **not** treated as cache. VCE tracks source
  under `native-offline/src-tauri/gen/{android,schemas}` (177 tracked files), so
  pruning by that directory name would have destroyed tracked content. Gradle
  output inside it is reached through `build/` instead.
- The tool only matched `target`, `node_modules`, `build`, `.cache`, `.gradle`,
  `.cxx`, `.externalNativeBuild` and `flatpak-checkout-*`. Every `build` match
  was listed and reviewed before deletion; all were Cargo, Gradle or CPM output.

## Owner actions still required

The `agents-worker` identity can empty these roots but cannot unlink the
directory entries themselves, and cannot delete files owned by another user.

1. `~/an3-migration-final` and `~/an3-migration-initial` — never readable by
   `agents-worker`; not inspected, not touched. Owner should review and remove.
2. ~433M of residue the worker could not remove:
   - `~/eden/.cache` (~360M, CPM dependency cache)
   - `~/an3-parity-build` (~367M, Eden build trees)
3. Root-owned Mesa shader caches inside the emptied `vce-352-*` run tree
   parents; harmless, but they block full removal of those directories.
4. The `opencut-v2-*` / `or-*` group (~15G) belongs to a separate project and
   was intentionally left untouched. It needs its own retention decision.
5. The archive lives under `/home/agents-worker/`. Move it somewhere durable
   before that account is reset.

## Prevention

Use `tools/home-scratch-audit.sh` to re-inventory. It is read-only by default
and only prunes the reviewed cache list with `--apply-cache`; it never touches
source trees, evidence or packages.

Going forward, put build scratch under a single disposable root instead of
`$HOME` — that is what produced roughly a hundred loose `.py`/`.sh` files
alongside these directories.

## Follow-up

The broader engineering mission is tracked separately. This cleanup changes no
product code and no runtime behaviour; `docs/evidence/` is documentation only.
