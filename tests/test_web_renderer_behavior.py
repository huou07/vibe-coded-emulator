# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class WebRendererBehaviorTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js is required for renderer behavior coverage')
    def test_renderer_failure_and_readiness_transitions(self):
        subprocess.run(['node', '--test', 'tests/web_renderer_behavior.test.js'], cwd=ROOT, check=True, capture_output=True, text=True)
