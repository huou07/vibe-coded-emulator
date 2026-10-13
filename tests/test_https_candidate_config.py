# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Invariants for the prepared direct-HTTPS candidate configuration.

The candidate in deploy/caddy-production.Caddyfile is not active yet, so nothing
at runtime would notice if it rotted. These tests pin the properties that make
the cutover safe, without needing Caddy installed.
"""
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_CADDYFILE = ROOT / "deploy/caddy-production.Caddyfile"
GENERIC_CADDYFILE = ROOT / "deploy/Caddyfile"


class ProductionCaddyfileTests(unittest.TestCase):
    def setUp(self):
        self.text = PRODUCTION_CADDYFILE.read_text(encoding="utf-8")

    def test_upstream_is_loopback(self):
        """The application backend must not be proxied from a public address."""
        self.assertIn("reverse_proxy 127.0.0.1:8091", self.text)
        self.assertNotRegex(self.text, r"reverse_proxy\s+(?!127\.0\.0\.1)")

    def test_http_redirect_port_matches_the_router_forward(self):
        """The router sends WAN 80 to 8088; Caddy must listen there."""
        self.assertIn("http_port 8088", self.text)

    def test_no_real_mailbox_is_committed(self):
        self.assertIn("YOUR_EMAIL@example.com", self.text)
        self.assertIsNone(
            re.search(r"[A-Za-z0-9._%+-]+@(gmail|outlook|yahoo|hotmail)\.", self.text),
            "a real personal mailbox must not be committed in infrastructure config",
        )

    def test_both_public_hostnames_are_covered(self):
        # Match the real site-block header, ignoring comment lines that also
        # mention the domain.
        headers = [
            line.strip()
            for line in self.text.splitlines()
            if line and not line.lstrip().startswith("#") and "an3tocom.space {" in line
        ]
        self.assertEqual(len(headers), 1, "expected exactly one site block")
        self.assertIn("www.an3tocom.space", headers[0])

    def test_websocket_upgrade_is_not_blocked(self):
        """LAN Sync and Phone Controller need WebSocket upgrades to pass through."""
        for blocker in ("flush_interval", "buffer_requests"):
            self.assertNotIn(
                blocker,
                self.text,
                "buffering directives can stall WebSocket traffic to the LAN services",
            )

    def test_no_indirective_ports_are_referenced(self):
        """Nothing here serves 18088 or 3478, so nothing may forward to them."""
        self.assertIsNone(
            re.search(r"reverse_proxy[^\n]*:(18088|3478)\b", self.text),
            "the candidate must not proxy a port that has no service behind it",
        )


class GenericTemplateTests(unittest.TestCase):
    """The shipped example must stay free of real hostnames and addresses."""

    def setUp(self):
        self.text = GENERIC_CADDYFILE.read_text(encoding="utf-8")

    def test_template_is_generic(self):
        self.assertIn("example.com", self.text)
        self.assertNotIn("an3tocom.space", self.text)
        self.assertIsNone(
            re.search(r"[A-Za-z0-9._%+-]+@(gmail|outlook|yahoo|hotmail)\.", self.text)
        )


if __name__ == "__main__":
    unittest.main()
