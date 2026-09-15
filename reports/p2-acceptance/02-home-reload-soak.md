# P2.15 homepage unsolicited-reload soak

Date: 2026-08-23 (Asia/Ho_Chi_Minh)

## Desktop result

**PASS** — the staging homepage was exercised for more than 15 minutes at a 1440px desktop viewport. The run included repeated search entry/clear, GBA and NDS filter switching, opening and closing the guide, scrolling, idle intervals, and restoring the full library.

Observed throughout:

- URL remained `http://192.168.1.8:8092/` except for intentional direct test navigation outside the soak.
- document readiness remained `complete`;
- no unsolicited reload or service-worker-forced navigation occurred;
- the full 12-card library returned after clearing filters/search;
- ordinary browsing preserved the observed scroll position (`scrollY=72` through repeated idle intervals).

The guide interaction returned focus to the header and therefore is not used as scroll-preservation evidence; the preserved ordinary library scroll intervals are the acceptance evidence.

## Mobile result

**PASS** — a real Android touchscreen running Chrome Android held the staging homepage from 10:30:48 to 10:41:01 ICT (10 minutes 13 seconds).

The run entered `Pokemon` in search, selected the NDS filter, reached the no-results state, and scrolled the page. Periodic physical screenshots through the end of the soak showed the same query, NDS filter, no-results state and scroll position. No unsolicited reload, forced service-worker refresh, reset of the filter, or reset of the search state was observed.

This supplements, rather than replaces, the successful desktop soak above.
