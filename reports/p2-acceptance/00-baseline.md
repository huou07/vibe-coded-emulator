# P2.15 baseline

Date: 2026-08-23 (Asia/Ho_Chi_Minh)

## Scope and safety

This acceptance run is restricted to the isolated staging service. Production was inspected only through read-only health, service, backup, and artifact checks. No production service, data, ROM, upload, Cloudflare route, tunnel, asset, or configuration was changed.

| Check | Result |
| --- | --- |
| Source branch / committed revision | `ui/production-ux-refresh` / `542ef985ddd22435cad00695b065dda1be4f80d3` |
| Working tree | Intentionally dirty; preserved without reset, clean, checkout, or history rewrite |
| Staging endpoint | `http://192.168.1.8:8092` |
| Staging health asset | `9cf7de4b8d0b` |
| Staging service | `an3-arcade-staging.service` active |
| Staging listener | `192.168.1.8:8092` only |
| Staging code/data roots | `/opt/an3-arcade-staging/current` and `/srv/an3-arcade-staging` |
| Staging write boundary | `ReadWritePaths=/srv/an3-arcade-staging` |
| Production health asset | `ef1c8a3df6b8` |
| Production service / backup timer | active / active |
| Production changed in this run | **NO** |

The active staging release resolves to `/opt/an3-arcade-staging/releases/20260823-111241-p215-nds-url`. Its unit runs as `tvshare`, has a 1 GiB memory ceiling and a 200% CPU quota, and has no write allow-list for `/srv/an3-arcade`. Its deployed `app.py` SHA-256 is `7ef4cd4f74e18d18439ba1398c2162a08ac76fcde52d680655ca775f7cd52465`; the public static asset version remains the intentional candidate `9cf7de4b8d0b`.
