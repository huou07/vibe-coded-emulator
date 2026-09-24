# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Keep-alive request framing: a rejected request must not desync the socket.

An HTTP/1.1 connection parses the next request from the same byte stream, so a
request whose declared body is never read leaves those bytes to be mistaken for
the next request line. Before ``Handler.drain_unread_body`` existed, a rejected
authenticated ``POST`` (or an unknown API path) corrupted the following request
on the same connection and the server answered with a protocol error. These
tests pin the corrected framing behavior through a real socket.
"""

import http.client
import json
import os
import socket
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import app


class RequestBodyKeepAliveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="an3-keepalive-test-")
        root = self.temp.name
        self.patches = [
            patch.object(app, "ENVIRONMENT", "staging"),
            patch.object(app, "BUG_REPORT_ENABLED", True),
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
        app.init_db()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        for active in self.patches:
            active.stop()
        self.temp.cleanup()

    def connection(self):
        return http.client.HTTPConnection(*self.server.server_address, timeout=5)

    def send(self, connection, method, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode()
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, response.read()

    def send_get_with_body(self, connection, path, body=b"BBBBBBBBBB"):
        connection.request("GET", path, body=body)
        response = connection.getresponse()
        return response.status, response.read()

    def assert_health_after_get_with_body(self, path, expected_status):
        connection = self.connection()
        try:
            status, _ = self.send_get_with_body(connection, path)
            self.assertEqual(status, expected_status)
            # The same connection must still frame the next request at its true
            # start even though the previous GET carried an unread body.
            status, body = self.send(connection, "GET", "/health")
            self.assertEqual(status, 200, body)
            self.assertTrue(json.loads(body)["ok"])
        finally:
            connection.close()

    def assert_health_after(self, method, path, payload, expected_status):
        connection = self.connection()
        try:
            status, _ = self.send(connection, method, path, payload)
            self.assertEqual(status, expected_status)
            # The same connection must frame the next request at its true start.
            status, body = self.send(connection, "GET", "/health")
            self.assertEqual(status, 200, body)
            self.assertTrue(json.loads(body)["ok"])
        finally:
            connection.close()

    @staticmethod
    def read_raw_response(sock, deadline=3.0):
        """Read one HTTP/1.1 response from a raw socket.

        Returns ``(status_line, headers, body)``. Headers are lower-cased for
        lookup; the body is read up to the declared ``Content-Length``.
        """
        sock.settimeout(deadline)
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        head, _, body = buf.partition(b"\r\n\r\n")
        lines = head.split(b"\r\n")
        status_line = lines[0].decode("latin-1")
        headers = {}
        for line in lines[1:]:
            if b":" in line:
                key, value = line.split(b":", 1)
                headers[key.strip().lower()] = value.strip()
        length = int(headers.get(b"content-length", b"0") or 0)
        while len(body) < length:
            chunk = sock.recv(4096)
            if not chunk:
                break
            body += chunk
        return status_line, headers, body

    def test_expect_100_continue_keepalive_is_prompt_and_framed(self):
        # RFC 9110 10.1.1: an HTTP/1.1 client that sends Expect: 100-continue
        # waits for the interim response before transmitting its body. The
        # end_headers drain must not run for that interim 1xx response, or the
        # server blocks in rfile.read() and the client deadlocks. The body is
        # then drained on the terminal response so the next request still frames.
        sock = socket.create_connection(self.server.server_address, timeout=5)
        try:
            sock.sendall(
                b"POST /api/logout HTTP/1.1\r\n"
                b"Host: 127.0.0.1\r\n"
                b"Content-Type: application/json\r\n"
                b"Content-Length: 10\r\n"
                b"Expect: 100-continue\r\n"
                b"\r\n"
            )
            try:
                status_line, _, _ = self.read_raw_response(sock, deadline=2.0)
            except socket.timeout:
                self.fail(
                    "no interim 100 Continue arrived before the body was sent; "
                    "an Expect: 100-continue client would deadlock"
                )
            self.assertEqual(status_line, "HTTP/1.1 100 Continue", status_line)
            # The client is now allowed to send the body; the terminal 401 follows.
            sock.sendall(b"A" * 10)
            status_line, _, terminal_body = self.read_raw_response(sock, deadline=3.0)
            self.assertIn("401", status_line, terminal_body)
            # The unread body must have been drained by the terminal response,
            # so the next request on the same connection frames correctly.
            sock.sendall(b"GET /health HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
            status_line, _, health_body = self.read_raw_response(sock, deadline=3.0)
            self.assertIn("200", status_line, health_body)
            self.assertTrue(json.loads(health_body)["ok"], health_body)
        finally:
            sock.close()

    def test_unauthenticated_post_body_does_not_desync_keepalive(self):
        self.assert_health_after("POST", "/api/games/1/rating", {"value": 5}, 401)

    def test_unknown_api_post_body_does_not_desync_keepalive(self):
        self.assert_health_after("POST", "/api/does-not-exist", {"value": 5}, 404)

    def test_unauthenticated_delete_body_does_not_desync_keepalive(self):
        self.assert_health_after("DELETE", "/admin/api/games/1", {"confirm": True}, 401)

    def test_rejected_csrf_post_body_does_not_desync_keepalive(self):
        # A body attached to a same-origin GET-style rejection is still drained.
        self.assert_health_after("POST", "/api/logout", {"unused": True}, 401)

    def test_static_success_with_body_does_not_desync_keepalive(self):
        # serve_static writes its own response (not through send_bytes); a
        # GET body on that path used to be left in the socket.
        self.assert_health_after_get_with_body("/static/site.css", 200)

    def test_redirect_with_body_does_not_desync_keepalive(self):
        # redirect() also writes its own response; /offline-app exercises it.
        self.assert_health_after_get_with_body("/offline-app", 303)


if __name__ == "__main__":
    unittest.main()
