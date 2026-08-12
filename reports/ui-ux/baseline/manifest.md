# Screenshot baseline manifest

Captured: 2026-08-12 with the Codex in-app browser before UI source changes.

Repository: `ui/production-ux-refresh` at `c6a5273837bea31db5d768315f2c8d1fc18e1234`.

Sources:

- staging: `http://192.168.1.11:8092`, asset `def955887c68`, sparse smoke fixture (one GBA, one NDS), Vietnamese, guest;
- isolated local: `http://127.0.0.1:18793`, current-source asset `6f8484897b66`, ignored fixture under `work/ui-baseline-data`, English, guest or isolated local admin as noted.

All accepted files are real `image/png` after lossless container conversion. When a page has a vertical scrollbar, the screenshot captures the drawable client area and is 15px narrower than the requested CSS viewport. Candidate captures must use the same page state/capture method or normalize scrollbar occupancy before pixel-level comparison.

| File | Requested viewport | Bitmap | Source / route / state | SHA-256 |
| --- | --- | --- | --- | --- |
| `01-home-staging-1440.png` | 1440×900 | 1425×891 | staging `/`, guest, populated | `ab4acc105dddd7c99ff2a8b1f973850fbe60a15059bbde38c3e7983decb67f99` |
| `01-home-staging-1280.png` | 1280×800 | 1265×791 | staging `/`, guest, populated | `075f0e48fca3663e955dc2271badac066838c617f3b43bddd03e3e48df4f5e01` |
| `01-home-staging-768.png` | 768×1024 | 753×1004 | staging `/`, guest, populated | `d6c349f7112d5970923f5b781332d4519dfd2aed8e5f8fce31e9ceae11d99381` |
| `01-home-staging-390.png` | 390×844 | 375×812 | staging `/`, guest, populated | `2e0a13bb8a19e21bff20119ba6dfe338ff79646a7e65cd8347b5e2cf1ccd583d` |
| `01-home-staging-360.png` | 360×800 | 345×767 | staging `/`, guest, populated | `124a8c21734a90c466aadff20e62aa801269b6b7d2f9a03de489d69f43c2b02d` |
| `02-login-idle-staging-1280.png` | 1280×720 | 1265×720 | staging `/login`, guest, idle | `1e4b4730efabcc2dc5db93206d18163d2e311e3d41a04f3d981cdcc56371c933` |
| `03-game-detail-pmd-1280.png` | 1280×800 | 1265×791 | staging `/game/pmd-eos`, guest, sparse detail | `67152c38bb0c71405b2d62686bc3855d2cff80425e3f980aed98873a87cc1e3d` |
| `03-game-detail-pmd-390.png` | 390×844 | 375×812 | staging `/game/pmd-eos`, guest, sparse detail | `320a837415d9ffdb1202c0451e3337bc28066b38a6104307d1af510a6ec2c6cd` |
| `04-player-pmd-1280.png` | 1280×720 | 1280×720 | staging `/play/pmd-eos`, loading at 92% | `f27e12f12112e8cd7160ccdbc65156e45f681ed8fb9374b2b70c33373b7e2690` |
| `04-player-pmd-390.png` | 390×844 | 390×844 | staging `/play/pmd-eos`, loading at 92% | `1da0d32680fa3b6cf532b5a3f544aac00050a74829b1c61cb275b2ccc317e7cb` |
| `05-home-empty-local-1280.png` | 1280×800 | 1280×800 | local `/`, guest, empty library | `f625bf97baa41cb03e29fd41733eb81b437cbcc768795a2a7be285f494c553db` |
| `05-home-empty-local-390.png` | 390×844 | 390×844 | local `/`, guest, empty library | `ed3c83b3d73b05fe2a88b9ff1aa6cd6953fe9d1a95d058a2624b8f11728294e0` |
| `06-game-404-local-1280.png` | 1280×800 | 1280×800 | local `/game/not-a-real-game`, guest, 404 | `3be72fb666dcadadf3b326029e8fc8424e9ecdc402d5f49a4a26181fdeadccc2` |
| `07-register-local-390.png` | 390×844 | 375×812 | local `/register`, guest, idle | `ad8f80405919f990506a18cc9775c5050a7780627f821b9410a9803e325c2690` |
| `08-offline-mixed-local-1280.png` | 1280×800 | 1265×791 | local `/offline`, prior browser-local GBA/core fixture | `99d9651063d3609065d43af757dd9b16d4769c9db76a6c9f0f226a737efaa37d` |
| `08-offline-mixed-local-390.png` | 390×844 | 375×812 | local `/offline`, prior browser-local GBA/core fixture | `fdded2a7de7cfbf3d3803325fc4ce2b5117538eebf0ec702626bdf66ffc3b1d6` |
| `09-admin-empty-local-1280.png` | 1280×800 | 1265×791 | local `/admin`, isolated admin, empty library | `9542d65139cd7795d19d604a7d1c87b26f49194b1120a9c479e2be7c3d55758b` |
| `09-admin-empty-local-390.png` | 390×844 | 375×812 | local `/admin`, isolated admin, empty library | `f0cf836f4d36c6be1fc9ba0d5d9b9dd199968506abba83edab9238dda43199e4` |
| `10-guide-modal-local-390.png` | 390×844 | 390×844 | local `/`, isolated admin, guide open | `34bfafc1b3ceda1d6998d11004d1a139572eb00c4c459369469b03cbff7fdf19` |
| `11-search-no-results-staging-1280.png` | 1280×720 | 1280×720 | staging `/`, guest, query `zzzz-no-match` | `dca5a516c70d9de24fbae9b72f5536d0297b595f6f5729891fe71ef3e30095de` |
| `11-search-no-results-staging-390.png` | 390×844 | 375×812 | staging `/`, guest, query `zzzz-no-match` | `489b1a4419de8715029c258dee32775d5913a87c40dec98b746263d32914e68e` |
| `12-account-empty-local-1280.png` | 1280×800 | 1280×800 | local `/account`, isolated admin, no favorites | `2b931ce958b756bc60c3148f7961b313f7fcf2d29f4f97c2ac2009951ffbb793` |
| `12-account-empty-local-390.png` | 390×844 | 375×812 | local `/account`, isolated admin, no favorites | `634e6b5f32310b06c3a3fb502541a2ce5d7315f6843f8f5bf4738424ae69e83e` |

## Baseline limits / required recaptures

- Player captures are accepted only as loading-shell evidence, not stable visual-regression goldens. Before any player-shell batch, capture ready GBA and NDS at desktop/mobile, EmulatorJS menu, save slots, pad panel, portrait/landscape, and fullscreen. Runtime success must include core start and save-state evidence because accelerated canvas capture can be blank.
- The staging asset predates the current production player's touch-default promotion. Non-player static assets match the current UI baseline, but player comparison must use the current candidate on staging.
- HTTPS/PWA restart-after-network-loss cannot be proven on LAN HTTP staging. It needs an HTTPS staging/secure test origin plus physical or installed-PWA QA; production is not the review environment.
- Production-density artwork, long titles, populated screenshots/updates/comments, and non-admin authenticated mobile navigation still need representative staging fixtures before their implementation batches.
