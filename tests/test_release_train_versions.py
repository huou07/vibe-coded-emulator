"""Regression: the coordinated release train must derive artifact names from
version metadata, never from a hard-coded version literal.

Historical failure: `tools/release-train.sh --coordinated` carried stale
`0.4.5` artifact filenames long after the app moved on, so a bump could copy a
leftover file under the wrong name.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_TRAIN = ROOT / "tools" / "release-train.sh"

# Any artifact-like name carrying a literal semver (vibecodedemulator-1.2.3-...).
HARDCODED_ARTIFACT = re.compile(
    r"(?i)(vibecodedemulator|an3-offline)[-_][0-9]+\.[0-9]+\.[0-9]+"
)


class ReleaseTrainVersionDerivationTests(unittest.TestCase):
    def test_no_hardcoded_artifact_version_literals(self):
        text = RELEASE_TRAIN.read_text(encoding="utf-8")
        hits = sorted(set(HARDCODED_ARTIFACT.findall(text)))
        self.assertEqual(
            hits, [],
            "release-train.sh hard-codes artifact version literals; derive them "
            "from tauri.conf.json / tauri.android.conf.json instead: %s" % hits,
        )

    def test_derives_versions_from_metadata(self):
        text = RELEASE_TRAIN.read_text(encoding="utf-8")
        self.assertIn("tauri.conf.json", text)
        self.assertIn("tauri.android.conf.json", text)
        self.assertIn("desktop_version", text)
        self.assertIn("android_version", text)


if __name__ == "__main__":
    unittest.main()
