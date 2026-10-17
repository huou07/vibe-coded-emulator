#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pin the accessible-tree inspection that tools/inspect-ui.py performs.

These tests cover the inspection logic itself, so a page that merely happens
to be clean cannot stand in for a working check. The rendered pages of this
project are exercised separately by tests/test_rendered_ui_accessibility.py.
"""

from __future__ import annotations

import importlib.util
import pathlib
import unittest
from pathlib import Path


ROOT = pathlib.Path(__file__).resolve().parents[1]
INSPECTOR = ROOT / "tools" / "inspect-ui.py"


def load_inspector():
    spec = importlib.util.spec_from_file_location("inspect_ui", INSPECTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


inspect_ui = load_inspector()


def roles(markup: str) -> list[str]:
    tree = inspect_ui.TreeBuilder()
    tree.feed(markup)
    tree.resolve()
    return [node.describe() for node in inspect_ui.walk(tree.root)]


def names(markup: str) -> dict[str, str]:
    tree = inspect_ui.TreeBuilder()
    tree.feed(markup)
    tree.resolve()
    return {
        node.attrs["id"]: node.accessible_name()
        for node in inspect_ui.walk(tree.root)
        if node.attrs.get("id")
    }


class AccessibleNameTests(unittest.TestCase):
    def test_aria_label_outranks_content(self):
        described = roles(
            '<button id="a" aria-label="Save changes">Save</button>',
        )
        self.assertIn('button "Save changes" #a focusable', described)

    def test_button_names_itself_from_wrapped_text(self):
        self.assertIn(
            'button "Menu" #a focusable',
            roles('<button id="a"><span aria-hidden="true">i</span><span>Menu</span></button>'),
        )

    def test_icon_only_link_is_named_by_image_alt(self):
        self.assertIn(
            'link "Settings" #a focusable',
            roles('<a id="a" href="/s"><img src="/i.png" alt="Settings"></a>'),
        )

    def test_aria_hidden_icon_does_not_become_the_name(self):
        # Two aria-hidden glyphs and no real label: the control is silent, and
        # reporting the glyphs as its name would hide a real defect.
        described = roles(
            '<button id="a"><span aria-hidden="true">x</span>'
            '<span aria-hidden="true">y</span></button>',
        )
        self.assertIn("button [NO ACCESSIBLE NAME] #a focusable", described)

    def test_label_for_names_its_control(self):
        self.assertEqual(
            names('<label for="q">Search games</label><input id="q">'),
            {"q": "Search games"},
        )

    def test_wrapping_label_names_a_control_without_an_id(self):
        # The login form labels its fields this way, so the implicit
        # association has to be honoured or every field reads as unnamed.
        self.assertEqual(
            names(
                '<label class="auth-field"><span>Password</span>'
                '<span class="auth-control"><input name="password" type="password">'
                "</span></label>",
            ),
            {},
        )
        tree = inspect_ui.TreeBuilder()
        tree.feed(
            '<label class="auth-field"><span>Password</span>'
            '<span class="auth-control"><input name="password" type="password">'
            "</span></label>",
        )
        tree.resolve()
        fields = [n for n in inspect_ui.walk(tree.root) if n.role == "textbox"]
        self.assertEqual(len(fields), 1)
        self.assertEqual(fields[0].accessible_name(), "Password")

    def test_wrapping_label_does_not_absorb_a_neighbouring_button(self):
        # The library toolbar wraps its search field and its clear button in one
        # label. Naming the field "Search games Clear" would be wrong.
        tree = inspect_ui.TreeBuilder()
        tree.feed(
            '<label for="gameSearch"><span>Search games</span>'
            '<span><input id="gameSearch" type="search">'
            '<button id="clearSearch">Clear</button></span></label>',
        )
        tree.resolve()
        resolved = {n.attrs["id"]: n.accessible_name() for n in inspect_ui.walk(tree.root)}
        self.assertEqual(resolved["gameSearch"], "Search games")
        self.assertEqual(resolved["clearSearch"], "Clear")

    def test_placeholder_is_not_an_accessible_name(self):
        described = roles('<input id="q" type="search" placeholder="Search">')
        self.assertIn("searchbox [NO ACCESSIBLE NAME] #q focusable", described)

    def test_landmark_takes_a_name_only_from_the_author(self):
        # A landmark named by its whole subtree makes the tree unreadable and
        # does not match what a browser exposes.
        self.assertIn("main", roles("<main>Some page copy</main>"))
        self.assertIn(
            'region "Find and filter games"',
            roles('<section aria-label="Find and filter games">copy</section>'),
        )

    def test_nested_header_is_not_a_second_banner(self):
        described = roles("<body><header>Site</header><main><header>Page</header></main></body>")
        self.assertEqual(described.count("banner"), 1)


class RoleTests(unittest.TestCase):
    def test_input_types_map_to_their_roles(self):
        described = roles(
            '<input type="checkbox" id="c" aria-label="Enabled">'
            '<input type="radio" id="r" aria-label="One">'
            '<input type="search" id="s" aria-label="Find">'
            '<select id="d" aria-label="Sort"></select>',
        )
        self.assertIn('checkbox "Enabled" #c focusable', described)
        self.assertIn('radio "One" #r focusable', described)
        self.assertIn('searchbox "Find" #s focusable', described)
        self.assertIn('combobox "Sort" #d focusable', described)

    def test_hidden_input_is_absent_from_the_tree(self):
        self.assertEqual(roles('<input type="hidden" name="next" value="x">'), [])

    def test_anchor_without_href_is_not_focusable(self):
        described = roles('<a id="a" aria-label="Placeholder">x</a>')
        self.assertIn('link "Placeholder" #a', described)
        self.assertNotIn("focusable", described[0])

    def test_disabled_control_is_reported_but_not_focusable(self):
        described = roles('<button id="b" disabled>Coming soon</button>')
        self.assertIn('button "Coming soon" [disabled] #b', described)

    def test_aria_hidden_subtree_is_not_reported(self):
        self.assertEqual(
            roles('<div aria-hidden="true"><button>Hidden</button></div>'),
            [],
        )

    def test_state_attributes_are_reported(self):
        described = roles(
            '<button id="b" aria-expanded="false" aria-pressed="true">Menu</button>',
        )
        self.assertIn("[expanded=false pressed=true]", described[0])

    def test_unbalanced_markup_does_not_crash_the_inspector(self):
        # A reporter that crashes on a broken page is useless on the page you
        # most need to inspect.
        described = roles("<div><button id='b'>Unclosed<section>")
        self.assertTrue(any("button" in entry for entry in described))


class CheckTests(unittest.TestCase):
    def _check(self, markup: str) -> int:
        import contextlib
        import io

        tree = inspect_ui.TreeBuilder()
        tree.feed(markup)
        tree.resolve()
        with contextlib.redirect_stderr(io.StringIO()):
            failures, _unverified = inspect_ui.check(inspect_ui.walk(tree.root))
        return failures

    def test_silent_controls_are_reported(self):
        self.assertEqual(self._check('<button id="b"></button>'), 1)
        self.assertEqual(self._check('<div role="button" tabindex="0"></div>'), 1)

    def test_named_controls_pass(self):
        self.assertEqual(self._check('<button aria-label="Save">Save</button>'), 0)

    def test_disabled_control_is_not_a_defect(self):
        # An unavailable control still needs a name, but a disabled one is not
        # an unreachable affordance, so it is not what this check hunts.
        self.assertEqual(self._check('<button disabled>Coming soon</button>'), 0)


if __name__ == "__main__":
    unittest.main()
