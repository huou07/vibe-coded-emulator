# Contributing to Vibe Coded Emulator

Thanks for helping. This project is licensed under `GPL-3.0-or-later`; by
contributing you agree your contribution is licensed under the same terms.

## Ground rules

- Keep the existing copyright and license notices; add your own copyright line
  to files you create.
- Write code comments and documentation in English.
- Do not commit ROMs, BIOS files, firmware, `prod.keys`/`title.keys`, save
  files, or any other copyrighted or personal content.
- Do not commit secrets, tokens, credentials, or private infrastructure
  details. Use `.env.example` for documented placeholders.
- Keep changes focused; avoid unrelated rewrites.

## Development

```bash
python3 -m unittest discover -s tests   # run the test suite
python3 app.py                          # run the web app locally
node --check static/player.js           # syntax check for player changes
```

Native apps (desktop and Android) build from `native-offline/`. See
`docs/building.md` for the per-platform commands and prerequisites.

## Player changes

Changes to the web player touch a guarded surface. Before and after editing
`static/player.js`, `static/nds-touch.js`, `static/site.css` or
`static/renderer-worker.js`, run:

```bash
python3 -m unittest \
  tests.test_regression_invariants \
  tests.test_web_nds_touch_behavior \
  tests.test_native_regression_guards \
  tests.test_shared_player_ui
node tests/web_nds_touch_behavior.test.js
node tests/web_renderer_behavior.test.js
```

If a behaviour can only be confirmed interactively, say so in the pull request
rather than claiming it is fixed from a passing build.

## Pull requests

- Describe what changed and how you verified it (build + runtime evidence).
- Note anything you could not verify.
- Keep the dark-violet design language for shared UI.
