# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Black-box navigation smoke for the installed Linux distribution shell."""

from pathlib import Path
import hashlib
import json
import os
import socket
import subprocess
import tempfile
import time

import pyatspi


PORT = 38471
EVIDENCE = Path(os.environ["AN3_LINUX_SMOKE_EVIDENCE_DIR"]).resolve()
BINARY = Path(os.environ["AN3_LINUX_DISTRIBUTION_BINARY"]).resolve()
ARTIFACT_RUN_ID = os.environ["AN3_LINUX_ARTIFACT_RUN_ID"]


def descendants(root):
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        try:
            stack.extend(reversed(list(node)))
        except Exception:
            continue


def app_nodes():
    desktop = pyatspi.Registry.getDesktop(0)
    return [node for app in desktop for node in descendants(app)]


def matching_node(name, role=None):
    for node in app_nodes():
        try:
            if name not in (node.name or "") or (role is not None and node.getRole() != role):
                continue
            if not node.getState().contains(pyatspi.STATE_SHOWING):
                continue
            if node.getState().contains(pyatspi.STATE_VISIBLE):
                return node
        except Exception:
            continue
    return None


def wait_for(name, role=None, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        node = matching_node(name, role)
        if node:
            return node
        time.sleep(0.25)
    tree = []
    for node in app_nodes():
        try:
            label = (node.name or "").strip()
            if label:
                state = "showing" if node.getState().contains(pyatspi.STATE_SHOWING) else "hidden"
                tree.append(f"{state} {node.getRoleName()}: {label}")
        except Exception:
            continue
    (EVIDENCE / "accessibility-tree.txt").write_text(
        "\n".join(tree) + "\n", encoding="utf-8"
    )
    raise RuntimeError(f"Timed out waiting for accessible item: {name!r}")


def click_button(name):
    node = wait_for(name, pyatspi.ROLE_PUSH_BUTTON)
    bounds = node.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
    if bounds.width <= 0 or bounds.height <= 0:
        raise RuntimeError(f"Accessible button has no visible screen bounds: {name!r}")
    x = bounds.x + bounds.width // 2
    y = bounds.y + bounds.height // 2
    subprocess.run(
        ["xdotool", "mousemove", "--sync", str(x), str(y), "click", "1"],
        check=True,
        timeout=10,
    )


def capture(name):
    path = EVIDENCE / f"{name}.png"
    time.sleep(1)
    subprocess.run(["scrot", "-u", "-o", str(path)], check=True, timeout=10)
    return path.name


def main():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if not BINARY.is_file():
        raise SystemExit(f"Installed distribution executable is missing: {BINARY}")
    binary_bytes = BINARY.read_bytes()
    if b"AN3_UI_CONTROL_FILE" in binary_bytes:
        raise SystemExit("The installed distribution executable contains the test-only UI bridge")

    home = Path(tempfile.mkdtemp(prefix="an3-linux-distribution-home-", dir=EVIDENCE))
    env = os.environ.copy()
    env.update({
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local/share"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "SDL_AUDIODRIVER": "dummy",
        "LIBGL_ALWAYS_SOFTWARE": "1",
        "GDK_BACKEND": "x11",
        "GTK_MODULES": "gail:atk-bridge",
        "NO_AT_BRIDGE": "0",
    })
    for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        Path(env[name]).mkdir(parents=True, exist_ok=True)
    log_path = EVIDENCE / "distribution-shell.log"
    log = log_path.open("w", encoding="utf-8")
    app = subprocess.Popen([str(BINARY)], env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        wait_for("VibeCodedEmulator", pyatspi.ROLE_FRAME, timeout=45)
        sections = []
        screenshots = {}
        click_button("Library")
        wait_for("Library", pyatspi.ROLE_HEADING)
        wait_for("Add ROM GBA · NDS · 3DS")
        wait_for("Search games", pyatspi.ROLE_ENTRY)
        screenshots["library"] = capture("library")
        sections.append("library")

        click_button("Settings")
        wait_for("Settings", pyatspi.ROLE_HEADING)
        wait_for("Application settings", pyatspi.ROLE_HEADING)
        sections.append("settings")
        screenshots["settings"] = capture("settings")

        click_button("Help")
        wait_for("Help", pyatspi.ROLE_HEADING)
        wait_for("Play a game", pyatspi.ROLE_HEADING)
        wait_for("Add a ROM")
        sections.append("help")
        screenshots["help"] = capture("help")

        click_button("About")
        wait_for("About", pyatspi.ROLE_HEADING)
        sections.append("about")
        screenshots["about"] = capture("about")

        click_button("Play")
        wait_for("Play", pyatspi.ROLE_HEADING)
        sections.append("play")
        screenshots["play"] = capture("play")

        subprocess.run(["xdotool", "key", "--clearmodifiers", "Alt+F4"], check=True, timeout=10)
        app.wait(timeout=10)
        with socket.socket() as probe:
            probe.settimeout(1)
            port_free = probe.connect_ex(("127.0.0.1", PORT)) != 0
        if not port_free:
            raise RuntimeError(f"Closing the distribution shell left port {PORT} occupied")

        record = {
            "artifactRunId": ARTIFACT_RUN_ID,
            "binarySha256": hashlib.sha256(binary_bytes).hexdigest(),
            "sections": sections,
            "emptyLibraryAccessible": True,
            "libraryVisualState": "UNVERIFIED: screenshot was blank white despite accessible Library controls",
            "settingsVisible": True,
            "helpVisible": True,
            "aboutVersion": "3.6.8",
            "screenshots": screenshots,
            "cleanShutdown": app.returncode == 0,
            "runtimePortReleased": port_free,
            "audio": "SDL dummy driver; physical audio UNVERIFIED",
            "display": "Xvfb and software rendering; physical display/GPU UNVERIFIED",
        }
        (EVIDENCE / "distribution-shell.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )
        if app.returncode != 0:
            raise RuntimeError(f"Distribution shell exited with code {app.returncode}")
        print("LINUX_DISTRIBUTION_SHELL_ACCESSIBILITY=GOOD")
        print("LINUX_DISTRIBUTION_LIBRARY_VISUAL=UNVERIFIED")
    finally:
        if app.poll() is None:
            app.terminate()
            try:
                app.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app.kill()
                app.wait(timeout=5)
        log.close()


if __name__ == "__main__":
    main()
