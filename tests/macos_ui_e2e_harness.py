# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared harness for packaged macOS UI E2E tests.

Drives the **real packaged application** through `an3ctl ui --target macos`,
which dispatches real DOM events on the app's own `data-testid` controls — the
same frontend handlers a user clicks. No test calls a Tauri command directly and
none uses screenshots or coordinates.

The distribution ``VibeCodedEmulator.app`` deliberately does not compile the
test-only ``ui-control`` bridge, so these E2E tests drive the separate automation
bundle produced by ``native-offline/scripts/build-macos-automation.sh``
(``npm run build:macos-automation``). Every test runs a throwaway copy of that
bundle with a unique bundle identifier and an isolated ``HOME``, so the owner's
library, saves and settings are never touched.
"""

from pathlib import Path
import itertools
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
AN3CTL = ROOT / "tools/an3ctl/bin/an3ctl"
BUNDLE_DIR = ROOT / "native-offline/src-tauri/target/release/bundle/macos"
AUTOMATION_APP = Path(
    os.environ.get("AN3_MACOS_AUTOMATION_APP", str(BUNDLE_DIR / "VibeCodedEmulatorAutomation.app"))
)
# The capability grants WebView IPC only to this loopback origin, so no other
# runtime port can serve the bridge; skip rather than fail when it is occupied.
RUNTIME_PORT = 38471

_instances = itertools.count(1)


def runtime_port_free():
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        probe.bind(("127.0.0.1", RUNTIME_PORT))
    except OSError:
        return False
    finally:
        probe.close()
    return True


def wait_runtime_port_free(timeout=15.0):
    """Wait for the fixed runtime port to be released by the previous test's app.

    A packaged instance killed by the previous test can hold the port briefly
    while it exits, so an immediate check would skip the next test. A genuinely
    foreign occupant (another worktree) still fails after the timeout.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if runtime_port_free():
            return True
        time.sleep(0.5)
    return runtime_port_free()


class MacosPackagedUiHarness(unittest.TestCase):
    """Bootstraps one throwaway automation bundle per test.

    Subclasses override :attr:`bundle_app_name` and :meth:`preflight` (for extra
    resource/fixture skips that must happen before the bundle copy), then use the
    ``an3ctl``/``wait_ui``/``ui_*``/``app_*`` helpers.
    """

    bundle_app_name = "AN3PackagedUITest.app"

    def setUp(self):
        if not AUTOMATION_APP.exists():
            self.skipTest(
                "the macOS automation app has not been built (npm run build:macos-automation)"
            )
        binary = AUTOMATION_APP / "Contents/MacOS/an3-offline-native"
        if not binary.exists() or b"AN3_UI_CONTROL_FILE" not in binary.read_bytes():
            self.skipTest("the automation app was not built with --features ui-control")
        self.preflight()
        if shutil.which("node") is None:
            self.skipTest("node is required to drive an3ctl")
        if not wait_runtime_port_free():
            self.skipTest(
                f"runtime port {RUNTIME_PORT} is already in use; "
                "close any running Vibe Coded Emulator instance first"
            )

        self.tmp = Path(tempfile.mkdtemp(prefix="an3-ui-e2e-"))
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.control = self.tmp / "ui-control.json"
        self.install = self.tmp / "install"
        self.install.mkdir()
        self.app = self.install / self.bundle_app_name
        shutil.copytree(AUTOMATION_APP, self.app, symlinks=True)
        # Unique per test so the throwaway copy gets its own WebKit data store and
        # can never collide with the owner's library (keyed by the bundle id) or
        # with another UI E2E class in the same discovery run.
        bundle_id = f"space.an3tocom.offline.uitest{os.getpid()}x{next(_instances)}"
        subprocess.run(
            ["/usr/libexec/PlistBuddy", "-c", f"Set :CFBundleIdentifier {bundle_id}",
             str(self.app / "Contents/Info.plist")],
            check=True,
        )
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(self.app)],
                       check=True, capture_output=True)
        self.addCleanup(self._teardown)

    def preflight(self):
        """Subclass hook for fixture/resource skips before the bundle copy."""

    def _teardown(self):
        # Scope to this throwaway bundle: other AN3 worktrees run the same
        # companion binary on this host, and killing globally would break them.
        subprocess.run(["pkill", "-f", str(self.app)], capture_output=True)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def an3ctl(self, *args, check=True):
        result = subprocess.run(
            ["bash", str(AN3CTL), *args, "--json"],
            capture_output=True, text=True, cwd=ROOT,
        )
        try:
            payload = json.loads(result.stdout.strip().splitlines()[-1]) if result.stdout.strip() else {}
        except json.JSONDecodeError:
            payload = {"ok": False, "raw": result.stdout, "stderr": result.stderr}
        if check and not payload.get("ok"):
            self.fail(f"an3ctl {' '.join(args)} failed: {payload} (stderr: {result.stderr[-300:]})")
        return payload

    def wait_ui(self, testid, state=None, timeout=90):
        args = ["ui", "wait", "--target", "macos", "--testid", testid,
                "--control-file", str(self.control), "--timeout", str(timeout * 1000)]
        if state:
            args += ["--state", state]
        return self.an3ctl(*args, check=False)

    def ui_query(self, testid):
        return self.an3ctl("ui", "query", "--target", "macos", "--testid", testid,
                           "--control-file", str(self.control))

    def ui_click(self, testid):
        return self.an3ctl("ui", "click", "--target", "macos", "--testid", testid,
                           "--control-file", str(self.control))

    def ui_native(self):
        """Native-runtime diagnostics from the running packaged app."""
        return self.an3ctl("ui", "native", "--target", "macos",
                           "--control-file", str(self.control))

    def app_start(self, rom=None):
        args = ["app", "start", "--target", "macos", "--app", str(self.app),
                "--home", str(self.home), "--control-file", str(self.control)]
        if rom is not None:
            args += ["--rom", str(rom)]
        return self.an3ctl(*args)

    def app_stop(self):
        return self.an3ctl("app", "stop", "--target", "macos", "--app", str(self.app))


def fixture_path(env_name, suffixes):
    """Resolve a legal homebrew fixture path from an environment override.

    Returns ``(path, None)`` or ``(None, reason)`` so a test can ``skipTest``
    with a precise reason instead of failing when no legal image is present.
    """
    if isinstance(suffixes, str):
        suffixes = (suffixes,)
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        return None, f"no legal homebrew fixture (set {env_name})"
    path = Path(raw).expanduser()
    if not path.exists():
        return None, f"{env_name} does not exist: {path}"
    if path.suffix.lower() not in suffixes:
        return None, f"{env_name} must point at a {'/'.join(suffixes)} image"
    return path, None


def run_native_gameplay(case, label):
    """Import, launch and sustain a native game through the packaged app.

    Requires ``case.fixture`` to be set by ``preflight``. Proves the card, the
    enabled launch control, a sustained ``running`` status and an advancing
    presented-frame counter; ``case`` is the :class:`MacosPackagedUiHarness`
    instance under test.
    """
    fixture = case.fixture
    started = case.app_start(fixture)
    case.assertTrue(started["data"]["port"] > 0)

    # The library UI is present and the capability was detected.
    case.assertTrue(case.wait_ui("game-grid")["ok"])

    # Import through the real picker control (pre-answered only in ui-control
    # builds via AN3_UI_TEST_ROM, so the real import handler still runs).
    case.ui_click("choose-rom")
    card_ok = case.wait_ui("game-card", timeout=180)
    case.assertTrue(card_ok["ok"], f"the {label} card did not appear after importing {fixture.name}")

    card = case.ui_query("game-card")
    case.assertIn(label, card["data"]["node"]["text"])

    # Native integration must have enabled the card's own launch control.
    launch = case.ui_query("game-launch")
    case.assertFalse(launch["data"]["node"]["disabled"], f"the {label} launch control is disabled")

    # Launch through the card's own control (not a direct command).
    case.ui_click("game-launch")
    running = case.wait_ui("native-status", state="running", timeout=180)
    case.assertTrue(running["ok"], f"the UI never reported native {label} as running")
    # A rejected/unsupported image also flips through `running` before failing,
    # and a stalled renderer keeps the DOM string at `running` forever. Require
    # the state to hold AND the Rust host's presented-frame counter to advance;
    # that is rendered emulation output, not a status claim.
    started = time.time()
    frames = []
    while time.time() - started < 3:
        node = case.ui_query("native-status")["data"]["node"]
        case.assertEqual(
            node.get("state"), "running", f"native {label} did not stay running: {node}"
        )
        native = case.ui_native()["data"]
        case.assertTrue(native["running"], f"the native {label} host stopped: {native}")
        frames.append(int(native["presentedFrames"]))
        time.sleep(0.5)

    case.assertTrue(frames, f"native {label} never reported a presented-frame counter")
    case.assertGreater(
        max(frames),
        min(frames),
        f"native {label} presented no frame (counter stayed at {frames[0]})",
    )

    case.app_stop()
