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
STAGING = (ROOT / "deploy/package-staging.sh").read_text(encoding="utf-8")
PRODUCTION = (ROOT / "deploy/package-production.sh").read_text(encoding="utf-8")
UPDATE_PRODUCTION = (ROOT / "deploy/update-production.sh").read_text(encoding="utf-8")


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
        self.assertIn("sync_engine", modules)

    def test_every_local_app_import_is_packaged_for_staging_and_production(self):
        for module in sorted(local_modules()):
            self.assertIn(f"{module}.py", STAGING, f"package-staging.sh omits {module}.py")
            self.assertIn(f"{module}.py", PRODUCTION, f"package-production.sh omits {module}.py")

    def test_production_updater_installs_every_local_module(self):
        for module in sorted(local_modules()):
            self.assertRegex(
                UPDATE_PRODUCTION,
                rf'install[^\n]*"\$TMP/{module}\.py"',
                f"update-production.sh does not install {module}.py",
            )


if __name__ == "__main__":
    unittest.main()
