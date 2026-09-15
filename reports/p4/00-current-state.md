# P4 current-state verification

Date: 2026-08-23 (Asia/Ho_Chi_Minh)  
Scope: read-only production and staging verification before P4 deployment work.

## Local workspace

| Field | Result |
| --- | --- |
| Branch / committed HEAD | `ui/production-ux-refresh` / `542ef985ddd22435cad00695b065dda1be4f80d3` |
| Worktree | Intentional P3 dirty state retained; no reset or clean was run. |
| Local baseline | 22 tests, Python compile, JavaScript syntax checks, deployment-shell syntax checks, package inspection, and `git diff --check` passed. |

## Direct server check

| Check | Result |
| --- | --- |
| Direct verified-key SSH | PASS (`huou07@192.168.1.8`) |
| Direct sudo | PASS through an owner-authorized direct interactive SSH session; no credential was written to a file, report, or repository. |
| `an3-arcade.service` | active |
| `an3-arcade-staging.service` | active |
| `cloudflared.service` | active |
| `an3-arcade-backup.timer` | active and enabled |
| Production `/health` | `environment=production`, asset `46a5125abb00` |
| Staging `/health` | `environment=staging`, asset `46a5125abb00`; current release `20260823-154343-46a5125abb00` |

Production was read only and remains unchanged.
