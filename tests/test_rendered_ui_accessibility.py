#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Assert the shipped pages keep a usable accessibility tree.

This boots the real server and inspects the HTML it actually serves, so it
fails on a control that a user can focus but cannot hear. It is the
regression guard for tools/inspect-ui.py: the inspector finds problems in
hand-written markup, and this proves the product's own pages stay clean.

Deliberately narrow. It asserts that every operable control has an accessible
name and that the primary journeys keep their landmarks and focusable entry
points. It says nothing about layout, colour or motion, which need a browser
and are not claimed here.

The server is started on staging, which is the environment that serves the
library routes; a production-only run would silently skip the pages this file
exists to protect.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request


ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
INSPECTOR = ROOT / "tools" / "inspect-ui.py"
PORT = 18994


def load_inspector():
    spec = importlib.util.spec_from_file_location("inspect_ui", INSPECTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


inspect_ui = load_inspector()


def fetch(path: str) -> str:
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=15) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def accessible_nodes(path: str) -> list:
    tree = inspect_ui.TreeBuilder()
    tree.feed(fetch(path))
    tree.resolve()
    return inspect_ui.walk(tree.root)


class RenderedPageAccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.mkdtemp(prefix="an3-ui-tree-")
        env = os.environ.copy()
        env.update(
            {
                "AN3_DATA_DIR": os.path.join(cls.temp, "data"),
                "AN3_PORT": str(PORT),
                "AN3_ADMIN_NAME": "rootadmin",
                "AN3_ADMIN_PASSWORD": "admin-pass-123",
                "AN3_COOKIE_SECURE": "0",
                # Staging serves the library routes this file inspects.
                "AN3_ENVIRONMENT": "staging",
            }
        )
        cls.server = subprocess.Popen(
            [sys.executable, str(APP)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2)
                return
            except Exception:
                time.sleep(0.1)
        cls.tearDownClass()
        raise RuntimeError("test server did not start")

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "server", None) is not None:
            cls.server.terminate()
            cls.server.wait(timeout=8)
            if cls.server.stdout is not None:
                cls.server.stdout.close()
            cls.server = None
        shutil.rmtree(cls.temp, ignore_errors=True)

    def test_no_shipped_page_has_a_silent_control(self):
        # The one defect that makes a control unreachable in practice: present,
        # focusable, and silent.
        for path in ("/", "/games", "/login", "/register", "/offline"):
            with self.subTest(path=path):
                nodes = accessible_nodes(path)
                silent = [
                    f"{node.role}#{node.attrs.get('id', '?')}"
                    for node in nodes
                    if node.role in inspect_ui.OPERABLE_ROLES
                    and not node.accessible_name()
                ]
                self.assertEqual(silent, [], f"{path} has unnamed controls")

    def test_every_page_keeps_its_primary_landmarks(self):
        # A user navigating by landmark must find the same three regions on
        # every page; losing them is a regression even when nothing is broken.
        for path in ("/", "/games", "/login", "/register", "/offline"):
            with self.subTest(path=path):
                roles = {node.role for node in accessible_nodes(path)}
                self.assertIn("main", roles)
                self.assertIn("navigation", roles)
                self.assertIn("contentinfo", roles)

    def test_the_library_search_field_is_named(self):
        # The representative journey: find and filter games. Naming the field
        # is what makes that journey usable without sight.
        fields = [
            node
            for node in accessible_nodes("/games")
            if node.attrs.get("id") == "gameSearch"
        ]
        self.assertEqual(len(fields), 1)
        self.assertEqual(fields[0].role, "searchbox")
        self.assertEqual(fields[0].accessible_name(), "Search games")
        self.assertTrue(fields[0].focusable)

    def test_the_menu_toggle_reports_its_expanded_state(self):
        # A disclosure control that never announces its state is unusable with
        # a screen reader, and the state is invisible in a screenshot.
        toggles = [
            node
            for node in accessible_nodes("/")
            if node.attrs.get("id") == "navToggle"
        ]
        self.assertEqual(len(toggles), 1)
        self.assertEqual(toggles[0].role, "button")
        self.assertTrue(toggles[0].accessible_name())
        self.assertEqual(toggles[0].attrs.get("aria-expanded"), "false")
        self.assertEqual(toggles[0].attrs.get("aria-controls"), "siteNav")

    def test_every_page_offers_the_sign_in_entry_points(self):
        # Recovery matters as much as the happy path: a visitor who cannot
        # find the way in is stuck on the marketing page.
        for path in ("/", "/games", "/offline"):
            with self.subTest(path=path):
                labels = {
                    node.accessible_name()
                    for node in accessible_nodes(path)
                    if node.role == "link"
                }
                self.assertIn("Log in", labels)
                self.assertIn("Register", labels)

    def test_the_download_page_marks_unavailable_builds(self):
        # The four platform cards are the download page's whole purpose; each
        # must announce that it is unavailable rather than presenting a dead
        # control as if it worked.
        nodes = accessible_nodes("/")
        unavailable = [
            node
            for node in nodes
            if node.role == "button" and "disabled" in node.states()
        ]
        self.assertEqual(len(unavailable), 4, "expected one card per platform")
        for node in unavailable:
            self.assertTrue(node.accessible_name())

    def test_the_offline_page_offers_a_recovery_action(self):
        # An error state with no way forward is a dead end, and a screenshot of
        # it would not say whether anything can be done.
        actions = [
            node
            for node in accessible_nodes("/offline")
            if node.role in {"button", "link"} and node.accessible_name()
        ]
        self.assertTrue(actions, "the offline page must offer a way forward")

    def test_inspection_cannot_see_runtime_only_names(self):
        # Recorded as a known limit, not a defect: without this note a future
        # reader could mistake the clean result above for full coverage.
        source = INSPECTOR.read_text(encoding="utf-8")
        self.assertIn("cannot run JavaScript", source)


if __name__ == "__main__":
    unittest.main()
