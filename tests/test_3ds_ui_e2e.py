# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Packaged-app 3DS gameplay E2E (macOS), gated on a legal homebrew fixture.

Drives the **real packaged application** through `an3ctl ui --target macos`,
which dispatches real DOM events on the app's own controls: the import button,
the generic `game-card` for "Nintendo 3DS", its `game-launch` control and the
`native-status` `data-state`. It never calls a Tauri command directly and uses no
screenshots or coordinates; the throwaway-copy/isolated-``HOME`` bootstrap and
the gameplay runner are shared with the GBA/NDS E2E in
``tests/macos_ui_e2e_harness.py``.

The run path requires the test-only ``ui-control`` automation bundle plus a legal
3DS homebrew image supplied through ``AN3_3DS_FIXTURE``; it skips otherwise. As
with GBA/NDS (RG-151), passing requires rendered output: while ``native-status``
holds ``running`` the test polls ``an3ctl ui native`` and asserts the host's
presented-frame counter strictly advances, so an image the Azahar core accepted
but never presents fails the gate.

``ThreeDsDomContractTests`` below still exercises the shipped DOM contract that
the gated test depends on, so the selector/label drift is caught everywhere.
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
THREE_DS_LABEL = "Nintendo 3DS"
# Azahar loads 3DSX homebrew executables and NCSD/NCCH images; accept any of the
# extensions the shipped library maps to the `3ds` system.
THREE_DS_SUFFIXES = (".3dsx", ".3ds", ".cci", ".cia", ".cxi", ".app")


class ThreeDsPackagedUiE2ETests(MacosPackagedUiHarness):
    bundle_app_name = "AN3ThreeDsUITest.app"

    def preflight(self):
        self.fixture, reason = fixture_path("AN3_3DS_FIXTURE", THREE_DS_SUFFIXES)
        if self.fixture is None:
            self.skipTest(reason)

    def test_70_packaged_3ds_gameplay(self):
        run_native_gameplay(self, THREE_DS_LABEL)


class ThreeDsDomContractTests(unittest.TestCase):
    """Fixture-independent guard for the DOM contract the gated E2E drives.

    The gameplay E2E can only run where a legal 3DS homebrew image exists, so this
    keeps the label, extension mapping and selector/state contract honest
    everywhere. It is a static drift guard, not interactive acceptance.
    """

    def test_offline_3ds_label_extensions_and_testids_match_the_e2e(self):
        self.assertIn('"3ds":{label:"Nintendo 3DS"', OFFLINE_JS)
        for suffix in THREE_DS_SUFFIXES:
            self.assertIn(f'"{suffix}":"3ds"', OFFLINE_JS)
        self.assertIn('card.dataset.testid=game.system==="switch"?"switch-game-card":"game-card"', OFFLINE_JS)
        self.assertIn('play.dataset.testid=game.system==="switch"?"switch-launch":"game-launch"', OFFLINE_JS)
        self.assertIn('note.dataset.testid=game.system==="switch"?"switch-status":"native-status"', OFFLINE_JS)
        self.assertIn('nativeStatus.dataset.state="running"', OFFLINE_JS)


if __name__ == "__main__":
    unittest.main()
