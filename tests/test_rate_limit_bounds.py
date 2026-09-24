# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded key space for the in-process rate limiters.

``app.RATE_LIMIT`` is keyed by ``(hashed source address, action, subject)`` and
``rate_allowed`` historically pruned only the requested key, so distinct source
addresses and subjects accumulated entries for the life of the process. These
tests pin the bounded sweep: once the configured cap is exceeded, buckets whose
newest timestamp is older than the largest window in use are dropped, then the
least-recently-seen buckets are evicted, while the key being checked is always
preserved and per-key limiting is otherwise unchanged.
"""

import os
import tempfile
import time
import unittest
from unittest.mock import patch

import app


class RateLimitBoundsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="an3-rate-limit-test-")
        root = self.temp.name
        self.patches = [
            patch.object(app, "ENVIRONMENT", "staging"),
            patch.object(app, "DB_PATH", os.path.join(root, "arcade.db")),
            patch.object(app, "ROM_DIR", os.path.join(root, "roms")),
            patch.object(app, "COVER_DIR", os.path.join(root, "covers")),
            patch.object(app, "SCREENSHOT_DIR", os.path.join(root, "screenshots")),
            patch.object(app, "CUSTOM_DIR", os.path.join(root, "custom")),
            patch.object(app, "UPLOAD_DIR", os.path.join(root, "uploads")),
            patch.object(app, "EMULATOR_CACHE_DIR", os.path.join(root, "emulatorjs-cache")),
            patch.object(app, "PREPARED_ROM_DIR", os.path.join(root, "prepared-roms")),
        ]
        for active in self.patches:
            active.start()
        app.RATE_LIMIT.clear()
        app.RATE_LIMIT_MAX_KEYS = 3
        app.RATE_LIMIT_MAX_WINDOW = 600

    def tearDown(self):
        app.RATE_LIMIT.clear()
        app.RATE_LIMIT_MAX_KEYS = 4096
        app.RATE_LIMIT_MAX_WINDOW = 600
        for active in self.patches:
            active.stop()
        self.temp.cleanup()

    def seed(self, ip, age, action="probe"):
        key = (app.auth_hash(ip), action, "")
        app.RATE_LIMIT[key] = [time.time() - age]
        return key

    def test_fully_expired_keys_are_evicted_once_the_cap_is_reached(self):
        stale = [self.seed(f"192.0.2.{n}", app.RATE_LIMIT_MAX_WINDOW + 10) for n in range(3)]
        self.assertTrue(app.rate_allowed("198.51.100.1", "probe", 5, 600))
        for key in stale:
            self.assertNotIn(key, app.RATE_LIMIT)
        self.assertEqual(len(app.RATE_LIMIT), 1)
        self.assertIn((app.auth_hash("198.51.100.1"), "probe", ""), app.RATE_LIMIT)

    def test_least_recently_seen_key_is_evicted_when_nothing_has_expired(self):
        oldest = self.seed("192.0.2.1", 300)
        self.seed("192.0.2.2", 200)
        self.seed("192.0.2.3", 100)
        self.assertTrue(app.rate_allowed("198.51.100.1", "probe", 5, 600))
        self.assertNotIn(oldest, app.RATE_LIMIT)
        self.assertLessEqual(len(app.RATE_LIMIT), app.RATE_LIMIT_MAX_KEYS)
        self.assertIn((app.auth_hash("198.51.100.1"), "probe", ""), app.RATE_LIMIT)

    def test_the_key_being_checked_survives_its_own_sweep(self):
        self.seed("192.0.2.1", 1)
        target = (app.auth_hash("198.51.100.1"), "probe", "")
        self.assertTrue(app.rate_allowed("198.51.100.1", "probe", 5, 600))
        self.assertIn(target, app.RATE_LIMIT)
        self.assertLessEqual(len(app.RATE_LIMIT), app.RATE_LIMIT_MAX_KEYS)

    def test_limiting_below_the_cap_is_unchanged(self):
        app.RATE_LIMIT_MAX_KEYS = 4096
        self.assertTrue(app.rate_allowed("198.51.100.1", "login", 2, 900))
        self.assertTrue(app.rate_allowed("198.51.100.1", "login", 2, 900))
        self.assertFalse(app.rate_allowed("198.51.100.1", "login", 2, 900))
        # A different source address and a different subject remain independent.
        self.assertTrue(app.rate_allowed("198.51.100.2", "login", 2, 900))
        self.assertTrue(app.rate_allowed("198.51.100.1", "login", 2, 900, subject="7"))
        self.assertEqual(len(app.RATE_LIMIT), 3)

    def test_windows_larger_than_the_default_raise_the_expiry_horizon(self):
        app.RATE_LIMIT_MAX_WINDOW = 600
        app.rate_allowed("203.0.113.9", "register", 5, 3600)
        self.assertGreaterEqual(app.RATE_LIMIT_MAX_WINDOW, 3600)


if __name__ == "__main__":
    unittest.main()
