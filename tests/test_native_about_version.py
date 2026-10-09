# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The packaged About panel must show the real build version, never a hardcoded
literal.

The tracked native shell keeps a ``__AN3_VERSION__`` token. ``prepare-web.mjs``
injects the canonical version into the generated assets; the Android build
passes its own ``tauri.android.conf.json`` value because that file overrides
``package.json``. These checks fail if a stale version literal is reintroduced
in the source or if the committed Android asset drifts from the package version.
"""

from __future__ import annotations

import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB_INDEX = ROOT / "native-offline" / "web" / "index.html"
PREPARE_WEB = ROOT / "native-offline" / "scripts" / "prepare-web.mjs"
BUILD_ANDROID = ROOT / "native-offline" / "scripts" / "build-android-staging.sh"
ANDROID_CONF = ROOT / "native-offline" / "src-tauri" / "tauri.android.conf.json"
ANDROID_INDEX = (
    ROOT / "native-offline" / "src-tauri" / "gen" / "android" / "app" / "src" / "main" / "assets" / "index.html"
)


def source(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


class NativeAboutVersionTests(unittest.TestCase):
    def test_source_shell_keeps_the_version_token_not_a_literal(self):
        html = source(WEB_INDEX)
        self.assertIn('data-app-version="__AN3_VERSION__"', html)
        self.assertIn("?v=__AN3_VERSION__", html)
        self.assertNotRegex(html, r"\?v=\d+\.\d+\.\d+")
        self.assertNotRegex(html, r"<span>Version</span><strong>\d+\.\d+\.\d+</strong>")

    def test_prepare_web_injects_the_canonical_version(self):
        script = source(PREPARE_WEB)
        self.assertIn("__AN3_VERSION__", script)
        self.assertIn("AN3_APP_VERSION", script)
        self.assertIn("package.json", script)

    def test_android_build_passes_the_package_version(self):
        script = source(BUILD_ANDROID)
        self.assertIn("AN3_APP_VERSION", script)
        self.assertIn("tauri.android.conf.json", script)

    def test_generated_android_about_matches_the_package_version(self):
        version = json.loads(source(ANDROID_CONF))["version"]
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        html = source(ANDROID_INDEX)
        self.assertIn(f'data-app-version="{version}"', html)
        self.assertIn(f"?v={version}", html)
        self.assertNotIn("__AN3_VERSION__", html)
        self.assertNotIn("2.3.0", html)


if __name__ == "__main__":
    unittest.main()
