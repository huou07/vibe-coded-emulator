# Final design-QA capture manifest

Captured 2026-08-13 on `ui/production-ux-refresh` from the candidate working tree based on `f7d27eca360dab7dc95b9d0d7cb4930f6fa70a7a`.

## Application state

- origin: isolated local preview at `127.0.0.1:18793`
- runtime asset version: `a4c3ba803036`
- browser: Codex in-app browser
- device pixel ratio: 1
- locale: Vietnamese
- authentication: signed-in non-admin fixture, display name `QA Player`
- dataset: 8 published local fixture games; 4 are repeated in the recommended section, so 12 card instances are present in the DOM
- storage/network: normal local online preview; this is not installed-PWA or offline-restart evidence
- source artwork state: real optimized fallback cover repeated because the local fixture has no representative uploaded covers

## Accepted files

| File | Purpose | Actual pixels | MIME | SHA-256 |
| --- | --- | ---: | --- | --- |
| `reference-option1-390x843.png` | selected visual target normalized to the required viewport | 390 × 843 | image/png | `67bb0fb20ae38565ddc7a279157ea127a9e2be0fe712abbc16a11286b07c525c` |
| `home-vi-css390x843-pass3.png` | accepted implementation at 390 CSS px | 390 × 843 | image/png | `7e73b186825e769fdd7d0d2842cc82a0074f271fbc641bfed4ea3ba1748e513d` |
| `home-vi-css360x840-pass3.png` | accepted narrow implementation at 360 CSS px | 360 × 840 | image/png | `662d1383302af26586dbd7d356fb1ad78cc7be85caddb6d3d6b38aa1c3e93ce0` |
| `reference-vs-implementation-pass3.png` | same-viewport full comparison | 780 × 843 | image/png | `754e78e29adf098ff827f5217dfe728f1520d6c29187cf280d6cea8caed38543` |
| `reference-vs-implementation-pass3-header.png` | header/search/filter focus comparison | 780 × 230 | image/png | `5d0128d70aba45ed41135ce0ca37e93ffa7d1b1851e2a4647429307aadc08357` |
| `reference-vs-implementation-pass3-cards.png` | artwork/card focus comparison | 780 × 600 | image/png | `83a3aad0bd2321a335d2e375ccdfa3141456d8a973bcb25601f725a438a65344` |

## Earlier iterations

| File | Actual pixels | SHA-256 |
| --- | ---: | --- |
| `home-css390x843.png` | 390 × 843 | `09431ce20bd07598c0cf8db85ddb45f4d95da84ccbb7058ed44459c164e08cf6` |
| `home-vi-css390x843-pass2.png` | 390 × 843 | `90dd8d1360da521f8cd5e132a0d42f6fb919c0d1c1429bc6f48d8bac38e0f541` |
| `reference-vs-implementation-pass1.png` | 780 × 843 | `85f49dd77b2cd27ebd7204ffd498f2094f4f74abd48e823e65ada2213a1131e0` |
| `reference-vs-implementation-pass2.png` | 780 × 843 | `4720eed8d1fe194ec1143c08bd6ab128d679371be3229fe50062ee491f27aade` |

All implementation screenshots were captured from the live application DOM, converted to lossless PNG, inspected at original resolution, and paired with the reference in the same comparison input. No production screenshots or data were substituted.
