# P2.15 visual and responsive acceptance

Date: 2026-08-23 (Asia/Ho_Chi_Minh)

## Public-page responsive evidence

Homepage, login, and offline were loaded at 360, 390, 768, 1280, 1440, and 1920px widths. At every observed width:

- `documentElement.scrollWidth` did not exceed the viewport width;
- headers stayed within the document bounds;
- public controls remained discoverable and focusable;
- no document-level horizontal overflow was observed;
- staging identity remained visible and the expected title/route rendered.

The homepage's deliberately horizontal card presentation produces off-viewport cards inside its own contained layout at some widths, but it does not create document-level horizontal overflow.

Login and offline screens showed no horizontal control outliers at any required width. Responsive checks also covered the long fixture titles and normal search/filter restoration on the homepage.

## Authenticated dashboard evidence

The staging-only administrator dashboard was checked at 360, 390, 768, 1280, 1440 and 1920px. At every width, `documentElement.scrollWidth` equalled the client width: no document-level horizontal overflow occurred.

- At 360/390, monitor cards are a readable single column; at 768 they form two columns; from 1280 they form four columns. All observed cards stayed within the document bounds.
- Charts, daily values, top-games list and the long admin task navigation remained usable. The mobile task navigation scrolls inside its own control rather than creating page overflow.
- The real-time monitor rendered live values and a visibly distinct unavailable-power card (`Không khả dụng`); no card overlap, clipped metric or unreadable text was observed.
- English dashboard monitor layout was checked at 390px. It remained in bounds, including the longer `Real-time monitoring` heading and `Unavailable` power state.

**Visual and responsive acceptance: PASS** for the approved pages and widths. The separate physical NDS cold-start blocker is recorded in `03-physical-nds.md`; it is not a dashboard visual defect.
