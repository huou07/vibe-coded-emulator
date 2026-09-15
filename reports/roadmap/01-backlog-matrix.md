# AN3 Arcade — Backlog Matrix

Date: 2026-08-20  
Current execution boundary: P0 only. All non-P0 work is deferred deliberately.

| ID | Issue | Severity | Area | Repro | Dependency | Risk | Acceptance | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Performance fell after UI refresh on weak devices | P0 regression | Player/runtime | Reported; source/runtime audit incomplete | Like-for-like device trace | Misdiagnosed image-quality downgrade | Not materially slower than known-good; no input/save/fullscreen regression | Measurement blocker |
| 2 | NDS settings/menu covered or blocked by touch overlay | P0 regression | NDS player | Reproduced with runtime hit testing | EmulatorJS DOM/menu state | Touch bridge or pad regression | Menu has interaction priority in all layouts | Staging targeted pass |
| 3 | Desktop NDS forced virtual controls / physical keyboard unusable | P0 regression | NDS input policy | Reproduced on desktop capability profile | Capability test and EmulatorJS keyboard behavior | Breaking mobile defaults | Keyboard/remap available; pad optional; mobile default preserved | Staging partial pass |
| 4 | Speed increase/decrease controls | P1 usability | Player | Not run in P0 | Core capability policy | Core-specific behavior | Reversible speed control | Deferred |
| 5 | Adaptive performance profiles | P1 usability | Player/runtime | Not run in P0 | P0.1 measurements | Quality/performance trade-off | Low/Balanced/Quality/Custom, reversible | Deferred |
| 6 | Global and per-button virtual-pad scale | P1 usability | Player | Existing controls partly present | P0 input safety | Touch-layout regression | Persisted and usable controls | Deferred |
| 7 | Align Offline/Admin/Dashboard with Main Page | P1 usability | UI | Not run in P0 | Design inventory | Broad visual regression | Reviewed responsive parity | Deferred |
| 8 | Offline mobile install/shortcut action | P1 usability | Offline/PWA | Not run in P0 | Browser install APIs | Browser-specific UX | Supported install route works | Deferred |
| 9 | Admin-only Quick Edit on game page | P1 usability | Admin/content | Not run in P0 | Auth and audit policy | Unauthorized edit exposure | Admin-only audited edit path | Deferred |
| 10 | Desktop admin table/actions cramped | P1 usability | Admin | Not run in P0 | Responsive layout audit | Admin workflow regression | No hidden actions at desktop widths | Deferred |
| 11 | Server metrics | P1 usability | Admin/telemetry | Not run in P0 | Trusted OS/hardware metrics | Misleading operational data | Only reliable metric sources shown | Deferred |
| 12 | Content-description policy rewrite | P2 feature | Content | Not run in P0 | Editorial policy | Copyright/policy mistakes | Compliant descriptions and links | Deferred |
| 13 | Facebook and Discord links | P2 feature | Community | Not run in P0 | Owner-provided destinations | External-link mistakes | Verified links and placement | Deferred |
| 14 | Remote/vibe-code page | P2 feature | Tooling | Not run in P0 | Access/security design | Remote access exposure | Separate security review | Deferred |
| 15 | Migrate old server data | Infrastructure | Operations/data | Not run in P0 | Inventory, backups, migration plan | Data loss/downtime | Rehearsed migration and rollback | Deferred |
| 16 | Add 3DS/Switch cores | P3 R&D | Emulator platform | Not run in P0 | Per-core feasibility/licensing | Unsupported performance/legal distribution | Separate approved feasibility | Deferred |
| 17 | Separate advertising page with review policy | P2 feature | Monetization | Not run in P0 | Content policy/admin review | Ads leak into player/homepage | Isolated page and approval flow | Deferred |
| 18 | Points and ranks | P2 feature | Community | Not run in P0 | Abuse/privacy policy | Incentive abuse | Clear, auditable criteria | Deferred |
| 19 | Multiplayer/network bridge | P3 R&D | Emulator platform | Not run in P0 | Per-core networking feasibility | Save/state/network correctness | Separate core-by-core R&D approval | Deferred |

## Order of work

P0 must be completely green before this matrix advances. In particular, item 1 requires measurement evidence rather than a speculative rendering downgrade. Items 4–19 are not authorization to change code during this P0 recovery pass.
