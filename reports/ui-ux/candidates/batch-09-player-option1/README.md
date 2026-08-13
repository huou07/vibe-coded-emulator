# Batch 09 — Gameplay Option 1 + Touch overlay

## Scope

- Applied the selected Option 1 shell: compact local-icon toolbar, dominant game region, explicit runtime/save status rail, and simplified options panels.
- Applied the user's follow-up delta: virtual controls overlay the game again; a persistent `Touch` toolbar button toggles the overlay; each control can be resized independently.
- Renamed the product-facing brand to `Ăn 3 Tô Cơm` in runtime HTML, manifest, offline player title, README, and tests.
- Preserved EmulatorJS boot, NDS touchscreen mapping, input indices, fullscreen binding, core storage, ROM delivery, save-slot storage, and offline player script order.

`BLOCKED_FOR_SEPARATE_TOUCH_TASK` was not triggered: this batch does not change the NDS touch bridge or button input mapping. It changes only controller visibility, placement, and presentation settings. Physical-device touch validation remains a staging/QA gate.

## Visual truth and normalization

- Selected shell direction: `reference-option1-700x1010.png` (700 × 1010 PNG).
- Overlay behavior reference: `reference-original-overlay-700x1010.png` (700 × 1010 PNG including 39 px browser chrome).
- Normalized overlay reference: `reference-original-overlay-content-700x971.png` (browser chrome cropped; 700 × 971).
- Normalized candidate: `candidate-touch-final-700x971.png` (700 CSS px × 971 CSS px, density 1).
- Side-by-side evidence: `reference-overlay-content-vs-candidate-touch-final.png` (1400 × 971).

![Normalized overlay reference beside final candidate](reference-overlay-content-vs-candidate-touch-final.png)

The local fixture has no ROM, so the honest same-state comparison is the existing 92% network-error state. No gameplay framebuffer or production ROM was fabricated or copied into local data.

## Responsive evidence

- `candidate-touch-final-700x1010.png`
- `candidate-touch-final-390x844.png`
- `candidate-touch-final-360x800.png`
- `candidate-touch-final-landscape-844x390.png`
- `candidate-touch-off-700x1010.png`
- `candidate-touch-settings-final-700x1010.png`

At 700 × 1010, 390 × 844, 360 × 800, and 844 × 390:

- document `scrollWidth` equals viewport width;
- the virtual-controller root matches the game rectangle and excludes the status rail;
- the controller root has `pointer-events:none`, while each control retains `pointer-events:auto`;
- no two virtual-control rectangles intersect in the default layout;
- the `Touch` button remains inside the toolbar and visible when the controller is hidden.

## Interaction evidence

- `Touch` off: `aria-pressed=false`, controller `display:none`, toolbar button remains 56–64 px wide and visible.
- `Touch` on: `aria-pressed=true`, controller `display:block`.
- Visibility persists after navigation/reload.
- Choosing `A` and setting 130% produced `--control-scale:1.3` only for A; B remained `1`; the per-control size persisted after reload.
- Per-control range is 70–140%, preventing the supported defaults from clipping at required mobile widths.
- More panel opens with focus on `#closePad`; Escape closes and restores focus to `#playerControls`.
- Save-slot panel opens with focus on `#closeSlots`; Escape closes and restores focus to `#slotMenu`.

## Regression and syntax gates

- `python3 -m unittest discover -s tests -v`: 10/10 passed.
- `python3 -m py_compile app.py`: passed using a workspace-local bytecode cache.
- `node --check`: `site.js`, `player.js`, `offline.js`, and `service-worker.js` passed.
- `bash -n`: deploy, staging deploy, and backup scripts passed.
- `git diff --check`: passed.

## Performance observations

- No runtime LCP, CLS, or INP numbers were available from the local browser workflow; none are claimed.
- Raw/gzip deltas versus the batch starting commit:
  - `site.css`: 56,569 → 64,758 B raw; 11,198 → 12,845 B gzip.
  - `player.js`: 44,945 → 48,879 B raw; 11,767 → 12,661 B gzip.
  - `offline.js`: 30,671 → 31,632 B raw; 9,584 → 9,956 B gzip.
  - `service-worker.js`: 2,756 → 2,985 B raw; 988 → 1,067 B gzip.
- Eight local Lucide SVG assets add 1,993 B raw and eight cold requests; they are included in the v19 app shell and cached for subsequent use. No external font, icon CDN, framework, or runtime dependency was added.

## Evidence hashes (SHA-256)

```text
a70aaea92c3baefd0ed0fb0957e32501b0a27dc47496034414bb7f2bcbd8c134  reference-option1-700x1010.png
de53f8da739fe493d2771d66364c6ecf4e4c5a0c1e37d1d9212d8c95ec1ba307  reference-original-overlay-content-700x971.png
f8bc649ad8f70712efe2f44b0b5826c0e6614574603e7cb10f0ad72b81148d55  candidate-touch-final-700x971.png
055d9ffdb64b3d0b47ed4e4d4579226e3aa2e4c76fe47cf349e9fa62bea88cf0  reference-overlay-content-vs-candidate-touch-final.png
81735f5cddb7bc508926c3a493bf329c46d2e724c49f9fda4b1c4058c8fda78c  candidate-touch-final-390x844.png
d0e21da17805867e2984f67be502395b992b490be0a926f3e5be63d42adead3b  candidate-touch-final-360x800.png
11a5e58509064ad3f37c9129306afd0ca28efeab32a51a5fdeb35a8a9789297d  candidate-touch-final-landscape-844x390.png
94ba9e13053f0ee6a0f111e3b7be5b954bb4a71f1bb300dd7315fd8083152491  candidate-touch-off-700x1010.png
b60d20036b4698ae32686b3ffa891417954cb8f1570a41f8c5634b181b75f83a  candidate-touch-settings-final-700x1010.png
```

## Remaining gates

- Ready-state NDS/GBA framebuffer, fullscreen, portrait/landscape rotation, and physical multi-touch must be verified on staging with representative ROM/core data.
- HTTPS/PWA restart-offline behavior requires a secure staging origin.
- No production deployment was performed.
