# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The vendored QR encoder and the controller pairing-SVG renderer.

The pairing QR is rendered server-side as a standalone SVG so it stays inside
the strict Content-Security-Policy (``img-src 'self'``) with no external
scripts, fonts, or CDNs. These tests pin the vendored encoder, the host-header
validation, and the SVG shape.
"""

import hashlib
import pathlib
import re
import unittest

import app
import qrcodegen


ROOT = pathlib.Path(__file__).resolve().parents[1]
# Pinned digest of the vendored Project Nayuki encoder (MIT). Update this value
# deliberately, together with the license header, if the vendored file changes.
VENDORED_QRCODEGEN_SHA256 = "9f4ed1dd201dcb92b1bc0d6e14f46c754bcff0ce48580c5d7e8ace8f6926c8ef"


class VendoredEncoderTests(unittest.TestCase):
    def test_vendored_encoder_is_unmodified(self):
        digest = hashlib.sha256((ROOT / "qrcodegen.py").read_bytes()).hexdigest()
        self.assertEqual(digest, VENDORED_QRCODEGEN_SHA256)

    def test_vendored_encoder_keeps_its_mit_license_header(self):
        source = (ROOT / "qrcodegen.py").read_text(encoding="utf-8")
        self.assertIn("MIT License", source)
        self.assertIn("Project Nayuki", source)


class ControllerJoinUrlTests(unittest.TestCase):
    def test_builds_an_absolute_join_url(self):
        self.assertEqual(
            app.controller_join_url("http", "192.0.2.8:8092", "AB12CD"),
            "http://192.0.2.8:8092/controller/join?code=AB12CD",
        )
        self.assertEqual(
            app.controller_join_url("https", "vibe.example", "AB12CD"),
            "https://vibe.example/controller/join?code=AB12CD",
        )

    def test_rejects_hosts_that_are_not_a_plain_host_or_host_port(self):
        for host in ("", " ", "http://evil.example", "evil.example/path", "evil.example;rm", "a b", "host:99 9"):
            with self.subTest(host=host):
                self.assertEqual(app.controller_join_url("http", host, "AB12CD"), "")


class ControllerQrSvgTests(unittest.TestCase):
    def _render(self, text):
        return app.controller_qr_svg(text)

    def test_viewbox_matches_the_encoder_size_plus_border(self):
        text = "http://192.0.2.8:8092/controller/join?code=AB12CD"
        qr = qrcodegen.QrCode.encode_text(text, qrcodegen.QrCode.Ecc.MEDIUM)
        span = qr.get_size() + 4 * 2
        svg = self._render(text)
        self.assertIn(f'viewBox="0 0 {span} {span}"', svg)
        # Explicit width/height give the SVG an intrinsic size so an <img> can
        # report a non-zero naturalWidth and scale through CSS.
        self.assertIn(f'width="{span}" height="{span}"', svg)

    def test_svg_is_self_contained_and_script_free(self):
        svg = self._render("http://192.0.2.8:8092/controller/join?code=AB12CD")
        self.assertTrue(svg.startswith("<svg "))
        self.assertIn("<path d=\"", svg)
        self.assertNotIn("<script", svg)
        self.assertNotIn("onload", svg)
        self.assertNotIn("xlink:href", svg)
        self.assertNotIn("<image", svg)
        # Only the SVG namespace is a URL; nothing is fetched.
        self.assertEqual(re.findall(r"https?://[^\"']+", svg), ["http://www.w3.org/2000/svg"])

    def test_path_uses_only_valid_command_characters(self):
        svg = self._render("http://192.0.2.8:8092/controller/join?code=AB12CD")
        path = re.search(r'<path d="([^"]*)"', svg).group(1)
        self.assertTrue(path)
        self.assertRegex(path, r"^[Mh vz0-9\-]+$")

    def test_rendering_is_deterministic(self):
        text = "http://192.0.2.8:8092/controller/join?code=AB12CD"
        self.assertEqual(self._render(text), self._render(text))

    def test_rejects_empty_and_oversized_payloads(self):
        with self.assertRaises(ValueError):
            self._render("")
        with self.assertRaises(ValueError):
            self._render("x" * (app.CONTROLLER_QR_MAX_TEXT + 1))


if __name__ == "__main__":
    unittest.main()
