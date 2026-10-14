#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Print the accessible structure of a rendered page as text.

This exists so an agent can review this web UI without a browser, without a
screenshot and without a vision model. It parses the same server-rendered HTML
the browser receives and reports the accessibility tree the user agent would
build: the role of each element, its accessible name, its states, its value and
its position in the focus order.

It is deliberately a reporter, not a linter. ``--check`` turns the one defect
that means a control is unreachable or silent into a non-zero exit so the
existing gate can hold it; without it the output is for reading.

Scope, stated honestly:

* It reads one HTML document at a time, from ``--url`` or ``--file``.
* It cannot run JavaScript. A control whose accessible name is assigned at
  runtime cannot be confirmed here, so ``--check`` counts those separately
  instead of passing them silently.
* It says nothing about layout, colour, spacing, focus-ring visibility or
  motion. Those need a browser or a device and are not claimed here.

Stdlib only, so it runs on a Debian workstation with no extra install.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

# Implicit ARIA roles for the HTML elements this UI actually uses. Deriving the
# role from the element is more reliable than trusting an explicit role
# attribute, because an explicit role can disagree with real behaviour.
IMPLICIT_ROLES = {
    "a": "link",
    "article": "article",
    "aside": "complementary",
    "button": "button",
    "footer": "contentinfo",
    "form": "form",
    "h1": "heading",
    "h2": "heading",
    "h3": "heading",
    "h4": "heading",
    "h5": "heading",
    "h6": "heading",
    "header": "banner",
    "img": "img",
    "li": "listitem",
    "main": "main",
    "nav": "navigation",
    "ol": "list",
    "option": "option",
    "p": "paragraph",
    "section": "region",
    "select": "combobox",
    "table": "table",
    "textarea": "textbox",
    "ul": "list",
}

# Roles a keyboard or screen-reader user must be able to reach and operate.
# A control in this set with no accessible name is a defect: it is present and
# focusable but silent.
OPERABLE_ROLES = {
    "button",
    "checkbox",
    "combobox",
    "link",
    "menuitem",
    "option",
    "radio",
    "searchbox",
    "switch",
    "tab",
    "textbox",
}

# Elements that create a sectioning scope. A header or footer inside one of
# these is generic, not a landmark.
SECTIONING = {"article", "aside", "main", "nav", "section"}

# Roles whose accessible name may come from their own content. Every other
# role takes a name only from the author: a landmark or region named by its
# entire subtree would make the tree unreadable and would not match how a
# browser exposes it.
CONTENT_NAMED_ROLES = {
    "button",
    "cell",
    "checkbox",
    "columnheader",
    "gridcell",
    "heading",
    "link",
    "menuitem",
    "menuitemcheckbox",
    "menuitemradio",
    "option",
    "radio",
    "row",
    "rowheader",
    "switch",
    "tab",
    "tooltip",
    "treeitem",
}

# Controls a <label> may name, whether by for= or by wrapping.
LABELABLE = {"button", "input", "meter", "output", "progress", "select", "textarea"}

VOID_ELEMENTS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "source",
    "track",
    "wbr",
}

# Attributes that expose a state a user can perceive.
STATE_ATTRIBUTES = (
    "aria-expanded",
    "aria-pressed",
    "aria-selected",
    "aria-checked",
    "aria-disabled",
    "aria-current",
    "aria-required",
    "aria-invalid",
    "aria-busy",
)


class Node:
    """One element in the accessible tree."""

    def __init__(
        self, tag: str, attrs: dict[str, str], ancestors: tuple[str, ...] = ()
    ) -> None:
        self.tag = tag
        self.attrs = attrs
        self.role = self._resolve_role(ancestors)
        self.name = ""
        # Raw text directly inside this element. Accessible names derived from
        # content recurse over it in _content_name.
        self.text = ""
        self.children: list[Node] = []
        # Assigned during the walk, so focus order and document order cannot
        # drift apart.
        self.order = 0

    def _resolve_role(self, ancestors: tuple[str, ...]) -> str:
        explicit = self.attrs.get("role", "").strip()
        if explicit:
            # A multi-token role attribute takes its first token.
            return explicit.split()[0]
        # header and footer are landmarks only at the top level. Inside a
        # sectioning element they are generic, and reporting them as a second
        # banner or contentinfo would overstate the page's structure.
        if self.tag in {"header", "footer"} and (
            SECTIONING & set(ancestors)
        ):
            return ""
        if self.tag == "input":
            input_type = self.attrs.get("type", "text").strip().lower()
            if input_type == "checkbox":
                return "checkbox"
            if input_type == "radio":
                return "radio"
            if input_type == "search":
                return "searchbox"
            if input_type in {"button", "submit", "reset"}:
                return "button"
            if input_type == "hidden":
                # A hidden input is not in the accessibility tree at all.
                return ""
            return "textbox"
        return IMPLICIT_ROLES.get(self.tag, "")

    @property
    def focusable(self) -> bool:
        if self.attrs.get("disabled") is not None:
            return False
        if self.attrs.get("tabindex") == "-1":
            return False
        if self.tag in {"a", "button", "input", "select", "textarea"}:
            if self.tag == "a" and "href" not in self.attrs:
                return False
            return True
        return self.attrs.get("tabindex") is not None

    @property
    def hidden(self) -> bool:
        return self.attrs.get("aria-hidden", "").strip().lower() == "true"

    def states(self) -> list[str]:
        found = []
        for attribute in STATE_ATTRIBUTES:
            value = self.attrs.get(attribute)
            if value is not None:
                found.append(f"{attribute.replace('aria-', '')}={value.strip()}")
        if self.attrs.get("disabled") is not None:
            found.append("disabled")
        if self.attrs.get("required") is not None:
            found.append("required")
        return found

    def accessible_name(self) -> str:
        """The name a screen reader would announce for this node."""
        if self.name:
            return self.name
        if self.role in CONTENT_NAMED_ROLES:
            return _content_name(self)
        return ""

    def describe(self) -> str:
        parts = [self.role or self.tag]
        name = self.accessible_name()
        if name:
            parts.append(f'"{name}"')
        elif self.role in OPERABLE_ROLES:
            parts.append("[NO ACCESSIBLE NAME]")
        states = self.states()
        if states:
            parts.append("[" + " ".join(states) + "]")
        if self.tag in {"input", "textarea"}:
            value = self.attrs.get("value", "").strip()
            if value:
                parts.append(f"value={value!r}")
        identifier = self.attrs.get("id")
        if identifier:
            parts.append(f"#{identifier}")
        if self.focusable:
            parts.append("focusable")
        return " ".join(parts)


class TreeBuilder(HTMLParser):
    """Build the accessible tree from a rendered document."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document", {})
        self.stack: list[Node] = [self.root]
        self.by_id: dict[str, list[Node]] = {}
        # (node, referenced id) pairs for aria-labelledby, resolved after the
        # tree is complete.
        self.referenced: list[tuple[Node, str]] = []
        # (target id, label node) for label[for].
        self.labelled: list[tuple[str, Node]] = []
        # (labelled control, wrapping label node) for implicit labels.
        self.wrapping_labels: list[tuple[Node, Node]] = []
        self.order = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {
            key.lower(): (value if value is not None else "")
            for key, value in attrs
        }
        ancestors = tuple(entry.tag for entry in self.stack[1:])
        node = Node(tag, attributes, ancestors)

        self.order += 1
        node.order = self.order

        self.stack[-1].children.append(node)
        # An explicit aria-label outranks any name derived from content.
        label = attributes.get("aria-label", "").strip()
        if label:
            node.name = " ".join(label.split())
        elif tag == "img":
            node.name = " ".join(attributes.get("alt", "").split())

        identifier = attributes.get("id")
        if identifier:
            self.by_id.setdefault(identifier, []).append(node)
        for reference in attributes.get("aria-labelledby", "").split():
            self.referenced.append((node, reference))
        if tag not in VOID_ELEMENTS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # A self-closing tag has no subtree, so it must not enter the stack.
        depth = len(self.stack)
        self.handle_starttag(tag, attrs)
        if len(self.stack) > depth:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        # A label that wraps its control names that control. Recorded here
        # because the association is only known once the label is closed.
        if tag == "label":
            index = next(
                (
                    position
                    for position in range(len(self.stack) - 1, 0, -1)
                    if self.stack[position].tag == "label"
                ),
                None,
            )
            if index is not None:
                label_node = self.stack[index]
                target_id = label_node.attrs.get("for", "")
                if not target_id:
                    target_id = next(
                        (
                            candidate.attrs["id"]
                            for candidate in _descendants(label_node)
                            if candidate.attrs.get("id")
                        ),
                        "",
                    )
                if target_id:
                    self.labelled.append((target_id, label_node))
                else:
                    # An implicit wrapping label names the control it wraps
                    # even when that control carries no id, which is how the
                    # login form labels its fields.
                    for candidate in _descendants(label_node):
                        if candidate.tag in LABELABLE:
                            self.wrapping_labels.append((candidate, label_node))
                            break

        # Close the nearest matching open element. Unbalanced markup must not
        # crash a reporter whose job is to describe a broken page.
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data.strip():
            node = self.stack[-1]
            node.text = " ".join(f"{node.text} {data}".split())

    def resolve(self) -> Node:
        """Compute accessible names once the tree is complete.

        The order mirrors the accessibility computation: aria-label, then
        aria-labelledby / label-for, then the element's own content. Content
        is gathered from descendants because a button rarely wraps its label
        directly, and aria-hidden subtrees are skipped because that is exactly
        what hiding an icon from assistive technology means.
        """
        for node, reference in self.referenced:
            label = " ".join(
                target.accessible_name()
                for target in self.by_id.get(reference, [])
            ).strip()
            if label and not node.name:
                node.name = label
        # A label names its control, but a label element is not itself part of
        # the accessibility tree, so the text is taken from its content.
        for target_id, label_node in self.labelled:
            label = _content_name(label_node)
            if not label:
                continue
            for target in self.by_id.get(target_id, []):
                if not target.name:
                    target.name = label
        for target, label_node in self.wrapping_labels:
            if not target.name:
                target.name = _content_name(label_node)
        return self.root


def _descendants(node: Node) -> list[Node]:
    out: list[Node] = []
    for child in node.children:
        out.append(child)
        out.extend(_descendants(child))
    return out


def _content_name(node: Node, root: bool = True) -> str:
    """Text content of a node, excluding aria-hidden subtrees.

    An image contributes its alt text, which is what makes an icon-only link
    named. A *nested* interactive control is skipped, because a label that
    wraps both its input and a neighbouring button must not absorb that
    button's name. The node itself is never skipped, so a button still names
    itself from its own text.
    """
    if node.tag == "img":
        return node.attrs.get("alt", "").strip()
    if not root and node.tag in {"input", "select", "textarea", "button", "a"}:
        return ""
    parts: list[str] = []
    if not node.hidden and node.text:
        parts.append(node.text)
    for child in node.children:
        nested = _content_name(child, root=False)
        if nested:
            parts.append(nested)
    return " ".join(" ".join(parts).split())


def walk(node: Node, hidden: bool = False) -> list[Node]:
    """Nodes worth reporting, in document order.

    aria-hidden is inherited: hiding a wrapper hides everything inside it,
    which is how an icon font is taken out of the tree without taking its
    neighbours with it.
    """
    out: list[Node] = []
    hidden = hidden or node.hidden
    if node.role and not hidden:
        out.append(node)
    for child in node.children:
        out.extend(walk(child, hidden))
    return out


def load_document(url: str | None, file_path: str | None) -> tuple[str, str]:
    if file_path:
        return Path(file_path).read_text(encoding="utf-8"), f"file:{file_path}"
    if not url:
        raise SystemExit("inspect-ui: one of --url or --file is required")
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace"), url
    except (urllib.error.URLError, OSError) as failure:
        raise SystemExit(f"inspect-ui: could not read {url}: {failure}") from failure


def check(nodes: list[Node]) -> tuple[int, int]:
    """Report silent operable controls. Returns (failures, unverified)."""
    failures = 0
    unverified = 0
    for node in nodes:
        if node.role not in OPERABLE_ROLES or node.accessible_name():
            continue
        identifier = node.attrs.get("id", "?")
        placeholder = node.attrs.get("placeholder", "").strip()
        if placeholder:
            # Placeholder text is often the only visible text, and it is not an
            # accessible name. Named explicitly so it is fixed, not guessed at.
            print(
                f"FAIL unnamed {node.role} #{identifier}: has placeholder text "
                "but no accessible name",
                file=sys.stderr,
            )
        else:
            print(f"FAIL unnamed {node.role} #{identifier}", file=sys.stderr)
        failures += 1
    return failures, unverified


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print the accessible structure of a rendered page.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="fetch this URL and inspect the response")
    source.add_argument("--file", help="inspect a local HTML file")
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero when an operable control has no accessible name",
    )
    arguments = parser.parse_args(argv)

    document, origin = load_document(arguments.url, arguments.file)
    tree = TreeBuilder()
    tree.feed(document)
    tree.resolve()

    nodes = walk(tree.root)
    focusable = [node for node in nodes if node.focusable]

    print(f"# {origin}")
    print(
        f"# {len(nodes)} nodes with an accessibility role, "
        f"{len(focusable)} in the focus order\n"
    )
    for node in nodes:
        print(node.describe())

    if arguments.check:
        failures, _unverified = check(nodes)
        if failures:
            print(f"\n# {failures} unnamed operable control(s)", file=sys.stderr)
            return 1
        print("\n# no unnamed operable controls", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
