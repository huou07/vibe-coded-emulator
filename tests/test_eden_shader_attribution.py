# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SANITIZER = ROOT / "native-offline/scripts/sanitize-eden-shader-attribution.py"
COPYRIGHT = "// SPDX-FileCopyrightText: 2013 Jose I. Echevarria"


class EdenShaderAttributionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.shader = Path(self.temp.name) / "opengl_smaa.glsl"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_sanitizer(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SANITIZER), str(self.shader)],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_removes_contact_but_preserves_copyright_and_license(self) -> None:
        address = "shader.author" + "@" + "example.com"
        original = (
            "// SPDX-FileCopyrightText: 2013 Jorge Jimenez\n"
            f"{COPYRIGHT} ({address})\n"
            "// SPDX-License-Identifier: MIT\n"
            "void main() { gl_FragColor = vec4(1.0); }\n"
        )
        self.shader.write_text(original, encoding="utf-8")

        result = self.run_sanitizer()

        self.assertEqual(result.returncode, 0, result.stderr)
        sanitized = self.shader.read_text(encoding="utf-8")
        self.assertNotIn(address, sanitized)
        self.assertIn(COPYRIGHT + "\n", sanitized)
        self.assertIn("// SPDX-License-Identifier: MIT\n", sanitized)
        self.assertIn("void main() { gl_FragColor = vec4(1.0); }\n", sanitized)
        self.assertNotIn(address, result.stdout + result.stderr)

    def test_is_idempotent(self) -> None:
        address = "shader.author" + "@" + "example.com"
        self.shader.write_text(
            f"{COPYRIGHT} ({address})\n// SPDX-License-Identifier: MIT\n",
            encoding="utf-8",
        )
        self.assertEqual(self.run_sanitizer().returncode, 0)
        once = self.shader.read_text(encoding="utf-8")

        second = self.run_sanitizer()

        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("ALREADY_CLEAN", second.stdout)
        self.assertEqual(self.shader.read_text(encoding="utf-8"), once)

    def test_every_pinned_eden_build_sanitizes_shader_source(self) -> None:
        contracts = {
            "native-offline/scripts/build-linux-eden-companion.sh": "prepare-eden-source.sh",
            "native-offline/scripts/build-macos-eden-companion.sh": "prepare-eden-source.sh",
            "native-offline/scripts/prepare-eden-source.sh": "sanitize-eden-shader-attribution.py",
            "native-offline/scripts/build-android-eden.sh": "sanitize-eden-shader-attribution.py",
            "native-offline/scripts/build-windows-eden-companion.ps1": "sanitize-eden-shader-attribution.py",
        }
        for script, marker in contracts.items():
            with self.subTest(script=script):
                self.assertIn(marker, (ROOT / script).read_text(encoding="utf-8"))

    def test_fails_closed_if_pinned_attribution_changes(self) -> None:
        original = "// SPDX-FileCopyrightText: 2013 Different Author\n// SPDX-License-Identifier: MIT\n"
        self.shader.write_text(original, encoding="utf-8")

        result = self.run_sanitizer()

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.shader.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
