---
name: vce-ui-ux
description: Use when changing the visual or interaction design of the VCE Web site, the shared player UI, the native shell or the Android mirror — navigation, layout, spacing, control sizing, design tokens, accessibility, or the entry point of a new feature. Triggers on "the UI looks cluttered", "redesign", "make it cleaner", "add an entry point", "touch target", "design token", "responsive". Do not use for emulation, transport or storage changes, or for a single token value that the browser lane already asserts.
---

# VCE UI/UX work

Use this procedure for a bounded visual or interaction change on one real
surface. "Cleaner" is not a result you can assert; a reviewed before/after and a
green contract lane are.

## Preconditions

- Read `docs/features/ui-shell.md`, then `docs/ARCHITECTURE.md` for the
  shared-UI rule, then `docs/design-system.md`, `docs/ui-page-contract.md` and,
  for anything over the canvas, `docs/player-layering.md`.
- Name the surface and the journey: Web site, Web player, native shell library,
  native player overlay, or Android. One at a time.
- Remember the coupling: `static/` is the browser UI **and** the native player's
  UI, and Android serves a committed mirror that no build regenerates. Re-copy
  the mirror or `tools/check-native-mirror.py` fails (RG-156).
- Keep the owner's dated reports separate from evidence: "the Linux UI is
  cluttered" is a requirement to investigate, not a finding.

## Procedure

1. Capture the before state: screenshot or rendered tree of the journey entry,
   its primary action, and the region you believe is cluttered.
2. Write down the concrete friction in observable terms — competing primary
   actions, unlabeled icons, mixed spacing scales, duplicated status text,
   controls below the touch-target tier. Vague dissatisfaction is not a defect.
3. Change the smallest set of components or tokens that removes that friction.
   Prefer the token layer (`static/theme-violet.css`, `static/site.css`) and the
   existing component patterns over a new one.
4. Keep the contracts: two-tier control heights (primary ≥42 px, compact ≥28 px),
   360 px no overflow, stable DOM IDs, layer/input order.
5. If the file is shared, mirror it to the Android asset tree and re-run the
   mirror check.
6. Run the contract lanes: the browser lane (`tests/web-runtime.test.mjs` under
   the canonical runner), `tests/test_rendered_ui_accessibility.py`, and
   `bash tools/verify-project.sh`.
7. Review the after state on the real surface. A visual judgement is a human
   review; record it as such. Automation proves contract, not taste.

## Protected behaviour

- Do not weaken the design-contract assertions to fit a component; raise the
  compact tier or document the exception as its own reviewed change.
- Do not reorder player layering or input precedence for a visual effect.
- Do not show an affordance for a surface that cannot complete the flow (Switch
  with no companion, LAN transfer with no peer transport).
- Do not restyle the whole product in one change; a UX pass is one journey.

## Stop and report

Report surface, journey, the friction removed, the before/after evidence, the
lanes run with their results, the mirrored files, and any visual judgement that
remains `UNVERIFIED` because no real surface was reviewed.

Skip this procedure for backend-only work, a token value the browser lane already
asserts, or an emulation change with no visible effect.
