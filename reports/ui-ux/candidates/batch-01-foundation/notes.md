# Batch 01 — scoped foundation

Captured: 2026-08-13 against isolated local fixture `work/ui-baseline-data` on source asset `6f8484897b66` plus the uncommitted foundation layer.

## Scope

- Added consumer/admin-only color, type, spacing, radius, focus, input, button, header, page, and footer rules.
- Reused the established player root tokens by scoping every new rule to `body:not(.player-page)`.
- Removed the consumer grid/gradient background and changed public typography from global monospace to system sans; technical labels remain monospace.
- Fixed the idle auth progress CSS leak and stopped its keyframe under reduced motion.

No player DOM, `player.js`, offline storage, PWA, authentication, route, data, or deployment behavior changed.

## Verification

- Unit/integration/invariant tests: 6/6 pass (0.55s real outside the restricted listener sandbox).
- `app.py` AST: pass.
- JavaScript syntax: pass for all four frontend scripts.
- `git diff --check`: pass.
- Captured full-page 1440, 1280, 768, 390, and 360 candidates plus a 390 viewport image. All accepted files are real PNG after container conversion.

## Visual comparison

- Typography and primary lime hierarchy now align more closely with the selected artwork-deck concept.
- Interactive borders and focus styling are materially clearer than baseline.
- The selected concept is not yet reached: the old header structure, intro block, filters, cards, and duplicate Recommended layout remain.
- Page-level mobile overflow remains (379px document against 375px client at the requested 390 viewport). This is a known P0 implementation gate assigned to the next shared-header/home batch; this batch is not handoff-ready.

## Evidence

- `home-1440.png`
- `home-1280.png`
- `home-768.png`
- `home-390.png`
- `home-390-viewport.png`
- `home-360.png`
