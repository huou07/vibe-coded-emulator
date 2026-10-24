# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Every local module app.py imports must ship in the staged/production payloads.

A missing module is not a build error: the archive simply excludes it and the
running service fails at import time, which the staging health check catches
only after the release switch. This pins the invariant.
"""

import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
STAGING_PATH = ROOT / "deploy/package-staging.sh"
PRODUCTION_PATH = ROOT / "deploy/package-production.sh"
UPDATE_PRODUCTION_PATH = ROOT / "deploy/update-production.sh"
STAGING = STAGING_PATH.read_text(encoding="utf-8") if STAGING_PATH.is_file() else None
PRODUCTION = PRODUCTION_PATH.read_text(encoding="utf-8") if PRODUCTION_PATH.is_file() else None
UPDATE_PRODUCTION = UPDATE_PRODUCTION_PATH.read_text(encoding="utf-8") if UPDATE_PRODUCTION_PATH.is_file() else None


def _imports(source):
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module.split(".")[0]


def local_modules():
    """Local .py modules reachable from app.py, including transitive imports."""

    seen, queue = set(), list(_imports(APP))
    while queue:
        name = queue.pop()
        if name in seen or not (ROOT / f"{name}.py").is_file():
            continue
        seen.add(name)
        queue.extend(_imports((ROOT / f"{name}.py").read_text(encoding="utf-8")))
    return seen


class PackagingImportTests(unittest.TestCase):
    def test_local_imports_are_detected(self):
        modules = local_modules()
        self.assertIn("netcode", modules)
        self.assertNotIn("sync_engine", modules)
        self.assertNotIn("google_sync", modules)

    def test_every_local_app_import_is_packaged_for_staging_and_production(self):
        if STAGING is None or PRODUCTION is None:
            self.skipTest("public source snapshot omits private deployment scripts")
        for module in sorted(local_modules()):
            self.assertIn(f"{module}.py", STAGING, f"package-staging.sh omits {module}.py")
            self.assertIn(f"{module}.py", PRODUCTION, f"package-production.sh omits {module}.py")

    def test_production_updater_installs_every_local_module(self):
        if UPDATE_PRODUCTION is None:
            self.skipTest("public source snapshot omits private deployment scripts")
        for module in sorted(local_modules()):
            self.assertRegex(
                UPDATE_PRODUCTION,
                rf'install[^\n]*"\$TMP/{module}\.py"',
                f"update-production.sh does not install {module}.py",
            )


if __name__ == "__main__":
    unittest.main()
