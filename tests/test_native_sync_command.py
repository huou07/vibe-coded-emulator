import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIB_RS = ROOT / "native-offline/src-tauri/src/lib.rs"


class NativeSyncCommandTests(unittest.TestCase):
    def _command(self, name):
        source = LIB_RS.read_text(encoding="utf-8")
        command = re.search(
            rf"#\[tauri::command\]\s*async fn {name}\([^}}]+?\n}}",
            source,
        )
        self.assertIsNotNone(command, f"{name} must be an async Tauri command")
        return command.group(0)

    def test_peer_requests_run_on_the_blocking_worker(self):
        self.assertIn(
            "spawn_blocking(move || sync_peer::request(method, payload))",
            self._command("native_sync_request"),
        )

    def test_peer_discovery_runs_on_the_blocking_worker(self):
        self.assertIn(
            "spawn_blocking(sync_peer::discover_peers)",
            self._command("native_sync_discover"),
        )


if __name__ == "__main__":
    unittest.main()
