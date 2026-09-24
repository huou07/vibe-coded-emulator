# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Packaged-app GBA/NDS gameplay E2E (macOS), gated on legal homebrew fixtures.

Drives the **real packaged application** through `an3ctl ui --target macos`,
which dispatches real DOM events on the app's own controls: the import button,
the generic `game-card` for "Game Boy Advance"/"Nintendo DS", its `game-launch`
control and the `native-status` `data-state`. It never calls a Tauri command
directly and uses no screenshots or coordinates.

The run path requires the test-only ``ui-control`` automation bundle plus a legal
homebrew fixture for the system under test, supplied through
``AN3_GBA_FIXTURE``/``AN3_NDS_FIXTURE``; it skips otherwise. The throwaway-copy
and isolated-``HOME`` bootstrap is shared with the Switch E2E in
``tests/macos_ui_e2e_harness.py``.

The fixture gate is an environment precondition, not a substitute for
verification: on a host without a legal GBA/NDS homebrew image these tests report
SKIP, and the gameplay path stays UNVERIFIED. ``GBANDSDomContractTests`` below
still exercises the shipped DOM contract that the gated tests depend on.

Passing the gate now requires rendered output, not just a status string: while
``native-status`` holds ``running`` the test polls ``an3ctl ui native``, which
reads the Rust host's presented-frame counter through the test-only bridge, and
asserts the counter advances. A core that accepted the image but never presents
a frame (blank/frozen output) fails the gate.
"""

from pathlib import Path
import sys
import unittest


sys.path.append(str(Path(__file__).resolve().parent))
from macos_ui_e2e_harness import (
    MacosPackagedUiHarness,
    ROOT,
    fixture_path,
    run_native_gameplay,
)


OFFLINE_JS = (ROOT / "static" / "offline.js").read_text(encoding="utf-8")
GBA_LABEL = "Game Boy Advance"
NDS_LABEL = "Nintendo DS"


class GbaPackagedUiE2ETests(MacosPackagedUiHarness):
    bundle_app_name = "AN3GbaUITest.app"

    def preflight(self):
        self.fixture, reason = fixture_path("AN3_GBA_FIXTURE", ".gba")
        if self.fixture is None:
            self.skipTest(reason)

    def test_70_packaged_gba_gameplay(self):
        run_native_gameplay(self, GBA_LABEL)


class NdsPackagedUiE2ETests(MacosPackagedUiHarness):
    bundle_app_name = "AN3NdsUITest.app"

    def preflight(self):
        self.fixture, reason = fixture_path("AN3_NDS_FIXTURE", ".nds")
        if self.fixture is None:
            self.skipTest(reason)

    def test_70_packaged_nds_gameplay(self):
        run_native_gameplay(self, NDS_LABEL)


class GBANDSDomContractTests(unittest.TestCase):
    """Fixture-independent guard for the DOM contract the gated E2E drives.

    The gameplay E2E can only run where a legal homebrew image exists, so this
    keeps the selector/state contract honest everywhere. It is a static drift
    guard, not interactive acceptance.
    """

    def test_offline_gba_nds_cards_expose_the_testids_and_states_the_e2e_waits_for(self):
        self.assertIn('gba:{label:"Game Boy Advance"', OFFLINE_JS)
        self.assertIn('nds:{label:"Nintendo DS"', OFFLINE_JS)
        self.assertIn('card.dataset.testid=game.system==="switch"?"switch-game-card":"game-card"', OFFLINE_JS)
        self.assertIn('play.dataset.testid=game.system==="switch"?"switch-launch":"game-launch"', OFFLINE_JS)
        self.assertIn('note.dataset.testid=game.system==="switch"?"switch-status":"native-status"', OFFLINE_JS)
        self.assertIn('nativeStatus.dataset.state="starting"', OFFLINE_JS)
        self.assertIn('nativeStatus.dataset.state="running"', OFFLINE_JS)


if __name__ == "__main__":
    unittest.main()
