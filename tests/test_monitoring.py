# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import http.client
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.py")
PORT = 18792


class Client:
    def __init__(self):
        self.cookie = ""

    def request(self, method, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode()
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.cookie:
            headers["Cookie"] = self.cookie
        connection = http.client.HTTPConnection("127.0.0.1", PORT, timeout=10)
        connection.request(method, path, body, headers)
        response = connection.getresponse()
        raw = response.read()
        cookie = response.getheader("Set-Cookie")
        if cookie and "an3_session=" in cookie:
            self.cookie = cookie.split(";", 1)[0]
        connection.close()
        return response.status, dict(response.getheaders()), raw


class MonitoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.mkdtemp(prefix="an3-monitoring-")
        env = os.environ.copy()
        env.update({"AN3_DATA_DIR": os.path.join(cls.temp, "data"), "AN3_PORT": str(PORT), "AN3_ADMIN_NAME": "monitor-admin", "AN3_ADMIN_PASSWORD": "monitor-admin-pass-123"})
        cls.server = subprocess.Popen([sys.executable, APP], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        deadline = time.time() + 12
        while time.time() < deadline:
            try:
                if Client().request("GET", "/health")[0] == 200:
                    return
            except OSError:
                time.sleep(.1)
        raise RuntimeError("monitoring test server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.server.terminate()
        cls.server.wait(timeout=8)
        import shutil
        shutil.rmtree(cls.temp)

    def test_admin_allowed_and_schema_has_safe_values(self):
        client = Client()
        self.assertEqual(client.request("POST", "/api/login", {"name": "monitor-admin", "password": "monitor-admin-pass-123"})[0], 200)
        status, headers, raw = client.request("GET", "/api/admin/system-metrics")
        payload = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Cache-Control"), "no-store")
        self.assertIn("cpu", payload)
        self.assertIn("ram", payload)
        self.assertIn("disk", payload)
        self.assertIn("uptime_seconds", payload)
        self.assertIn("app", payload)
        if payload["cpu"].get("used_percent") is not None:
            self.assertTrue(0 <= payload["cpu"]["used_percent"] <= 100)
        if payload["ram"].get("used_percent") is not None:
            self.assertTrue(0 <= payload["ram"]["used_percent"] <= 100)
            self.assertTrue(payload["ram"]["used_bytes"] <= payload["ram"]["total_bytes"])
        self.assertTrue(0 <= payload["disk"]["used_percent"] <= 100)
        serialized = json.dumps(payload).lower()
        for secret in ("password", "token", "ssh", "cloudflare", "environment"):
            self.assertNotIn(secret, serialized)

    def test_guest_and_normal_user_denied(self):
        self.assertEqual(Client().request("GET", "/api/admin/system-metrics")[0], 401)
        normal = Client()
        self.assertEqual(normal.request("POST", "/api/register", {"name": "normal-user", "display_name": "Normal User", "password": "normal-user-pass-123", "confirm": "normal-user-pass-123"})[0], 201)
        self.assertEqual(normal.request("GET", "/api/admin/system-metrics")[0], 403)

    def test_unavailable_sensor_values_are_explicit(self):
        import app
        with mock.patch.object(app, "_temperature", return_value=None), mock.patch.object(app, "_power_watts", return_value=None):
            payload = app.system_metrics()
        self.assertEqual(payload["temperature"], {"celsius": None, "status": "unavailable"})
        self.assertEqual(payload["power"], {"watts": None, "status": "unavailable"})

    def test_power_uses_the_fixed_turbostat_helper(self):
        import app
        completed = subprocess.CompletedProcess(["sudo"], 0, stdout="12.345\n", stderr="")
        with mock.patch.object(app.subprocess, "run", return_value=completed) as run:
            self.assertEqual(app._power_watts(), 12.35)
        run.assert_called_once_with(
            ["/usr/bin/sudo", "-n", app.TURBOSTAT_HELPER],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )

    def test_power_rejects_invalid_turbostat_output(self):
        import app
        completed = subprocess.CompletedProcess(["sudo"], 0, stdout="not-a-number\n", stderr="")
        with mock.patch.object(app.subprocess, "run", return_value=completed):
            self.assertIsNone(app._power_watts())

    def test_temperature_prefers_x86_cpu_package_over_first_zone(self):
        import app
        with tempfile.TemporaryDirectory(prefix="an3-temperature-") as root:
            thermal_root = os.path.join(root, "thermal")
            hwmon_root = os.path.join(root, "hwmon")
            os.makedirs(os.path.join(thermal_root, "thermal_zone0"))
            os.makedirs(os.path.join(thermal_root, "thermal_zone4"))
            os.makedirs(os.path.join(hwmon_root, "hwmon0"))
            fixtures = {
                os.path.join(thermal_root, "thermal_zone0", "type"): "INT3400 Thermal",
                os.path.join(thermal_root, "thermal_zone0", "temp"): "20000",
                os.path.join(thermal_root, "thermal_zone4", "type"): "x86_pkg_temp",
                os.path.join(thermal_root, "thermal_zone4", "temp"): "33000",
                os.path.join(hwmon_root, "hwmon0", "name"): "coretemp",
                os.path.join(hwmon_root, "hwmon0", "temp1_label"): "Package id 0",
                os.path.join(hwmon_root, "hwmon0", "temp1_input"): "32000",
            }
            for path, value in fixtures.items():
                with open(path, "w", encoding="ascii") as handle:
                    handle.write(value)
            with mock.patch.object(app, "THERMAL_ROOT", thermal_root), mock.patch.object(app, "HWMON_ROOT", hwmon_root):
                self.assertEqual(app._temperature(), 33.0)

    def test_reliability_paths_do_not_auto_reload_or_cache_api_responses(self):
        with open(os.path.join(ROOT, "static", "site.js"), encoding="utf-8") as handle:
            site_js = handle.read()
        with open(os.path.join(ROOT, "static", "service-worker.js"), encoding="utf-8") as handle:
            worker_js = handle.read()
        self.assertNotIn("data.version !== currentVersion) location.reload()", site_js)
        self.assertIn('refresh.textContent = english ? "Refresh when ready"', site_js)
        self.assertIn('url.pathname.startsWith("/api/")', worker_js)
        self.assertIn('fetch(event.request, {cache: "no-store"})', worker_js)
        self.assertIn('if (value === null || value === undefined || value === "") return null;', site_js)

    def test_cpu_sample_is_a_bounded_percent(self):
        import app
        previous = app._CPU_SAMPLE
        try:
            app._CPU_SAMPLE = None
            with mock.patch.object(app, "_read_cpu_totals", side_effect=[(100, 20), (200, 60)]):
                self.assertIsNone(app._cpu_percent())
                self.assertEqual(app._cpu_percent(), 60.0)
        finally:
            app._CPU_SAMPLE = previous

    def test_dashboard_analytics_uses_local_calendar_days_and_real_events(self):
        import app
        now = 1_725_000_000
        conn = app.sqlite3.connect(":memory:")
        conn.row_factory = app.sqlite3.Row
        conn.executescript("""
            CREATE TABLE page_views(visitor_hash TEXT, user_id INTEGER, path TEXT, created_at INTEGER);
            CREATE TABLE games(id INTEGER PRIMARY KEY, title_vi TEXT, slug TEXT);
            CREATE TABLE play_events(id INTEGER PRIMARY KEY, visitor_hash TEXT, user_id INTEGER, game_id INTEGER, created_at INTEGER);
            CREATE TABLE download_events(id INTEGER PRIMARY KEY, visitor_hash TEXT, user_id INTEGER, path TEXT, created_at INTEGER);
        """)
        conn.execute("INSERT INTO games(id,title_vi,slug) VALUES(1,'Real game','real-game')")
        today_start = int(app.datetime.combine(app.datetime.fromtimestamp(now).date(), app.datetime_time.min).timestamp())
        conn.execute("INSERT INTO page_views VALUES('a',NULL,'/',?)", (today_start + 60,))
        conn.execute("INSERT INTO page_views VALUES('a',NULL,'/game',?)", (today_start + 180,))
        conn.execute("INSERT INTO play_events(visitor_hash,user_id,game_id,created_at) VALUES('a',NULL,1,?)", (today_start + 120,))
        conn.execute("INSERT INTO play_events(visitor_hash,user_id,game_id,created_at) VALUES('a',NULL,1,?)", (today_start + 300,))
        conn.execute("INSERT INTO download_events(visitor_hash,user_id,path,created_at) VALUES('a',NULL,'/download-app/release',?)", (today_start + 120,))
        conn.execute("INSERT INTO download_events(visitor_hash,user_id,path,created_at) VALUES('old',NULL,'/download-app/release',?)", (today_start - 14 * 86400,))
        conn.execute("INSERT INTO page_views VALUES('old',NULL,'/',?)", (today_start - 14 * 86400,))
        with mock.patch.object(app.time, "time", return_value=now):
            totals, previous, series = app.dashboard_analytics(conn, 14)
        self.assertEqual(len(series), 14)
        self.assertEqual(series[-1][1:], (1, 1))
        self.assertEqual(sum(visits for _, visits, _ in series), 1)
        # Totals cover the selected window only; the equal-length window before
        # it supplies the real comparison used by the percentage change.
        self.assertEqual(totals, {"visits": 1, "downloads": 1})
        self.assertEqual(previous, {"visits": 1, "downloads": 1})
        with mock.patch.object(app.time, "time", return_value=now):
            all_totals, _, all_series = app.dashboard_analytics(conn, None)
        self.assertGreaterEqual(len(all_series), 15)
        self.assertEqual(all_totals, {"visits": 2, "downloads": 2})

    def test_staging_release_path_is_strictly_staging_only(self):
        release_path = os.path.join(ROOT, "deploy-stage.sh")
        if not os.path.isfile(release_path):
            self.skipTest("sanitized public source omits the private staging deploy entrypoint")
        with open(release_path, encoding="utf-8") as handle:
            release = handle.read()
        self.assertIn('source "$ROOT/tools/ssh/staging-common.sh"', release)
        self.assertIn('"$ROOT/tools/ssh/check-staging-key.sh"', release)
        self.assertIn('"$ROOT/deploy/package-staging.sh" "$ARCHIVE"', release)
        self.assertIn('REMOTE_RELEASE_HELPER="/usr/local/sbin/an3-arcade-staging-release"', release)
        self.assertIn("sudo -n", release)
        self.assertIn("STAGING_DEPLOY=PASS", release)
        self.assertNotIn("package-production.sh", release)
        self.assertNotIn("update-production.sh", release)
        self.assertNotIn("PRODUCTION_RELEASE", release)
        self.assertNotIn("an3-production-release", release)

    def test_production_update_keeps_database_backup_and_rollback(self):
        with open(os.path.join(ROOT, "deploy", "update-production.sh"), encoding="utf-8") as handle:
            production_update = handle.read()
        self.assertIn('"$TMP/deploy/rollback-production.sh"', production_update)
        self.assertIn("an3-arcade-rollback-production", production_update)
        self.assertIn('"$TMP/deploy/backup-production-current.sh"', production_update)
        self.assertIn("an3-arcade-backup-current", production_update)
        self.assertIn('"$TMP/deploy/seed-azahar-core.sh"', production_update)
        self.assertIn("an3-arcade-seed-azahar-core", production_update)
        self.assertIn("offline-app-service-worker.js", production_update)
        with open(os.path.join(ROOT, "deploy", "seed-azahar-core.sh"), encoding="utf-8") as handle:
            seed = handle.read()
        self.assertIn('report.get("core", report.get("name"))', seed)
        self.assertIn('options.get("requireThreads") is not True', seed)
        self.assertIn('options.get("requiresWebgl2") is not True', seed)
        with open(os.path.join(ROOT, "deploy", "backup-production-current.sh"), encoding="utf-8") as handle:
            production_backup = handle.read()
        self.assertIn("source.backup(target)", production_backup)
        self.assertIn("PRAGMA integrity_check", production_backup)
        self.assertIn("PRODUCTION_DATABASE_SHA256", production_backup)
        self.assertIn("Refusing to overwrite", production_backup)

    def test_staging_package_allows_only_current_verified_native_installers(self):
        with open(os.path.join(ROOT, "deploy", "package-staging.sh"), encoding="utf-8") as handle:
            package = handle.read()
        self.assertIn("NATIVE_ARTIFACTS=(", package)
        self.assertIn('python3 "$ROOT/tools/verify-release-catalog.py" --print-filenames', package)
        self.assertIn('done < "$PAYLOAD/artifacts.txt"', package)
        self.assertIn('"$ROOT/native-offline/releases/catalog.json"', package)
        self.assertIn('"$ROOT/native-offline/releases/$artifact.sha256"', package)
        self.assertIn("--exclude='native-offline/releases/*'", package)
        self.assertIn("--exclude='*.DS_Store'", package)
        self.assertIn("Verified staging installer is unavailable", package)

    def test_dashboard_and_offline_reference_markup_have_no_fixed_values(self):
        with open(APP, encoding="utf-8") as handle:
            source = handle.read()
        with open(os.path.join(ROOT, "static", "site.css"), encoding="utf-8") as handle:
            stylesheet = handle.read()
        self.assertNotIn('data-series="48,40,44,60', source)
        self.assertNotIn('data-series="46,43,45,53', source)
        self.assertIn('data-series="{visit_series}"', source)
        self.assertIn('data-series2="{download_series}"', source)
        self.assertIn('top:16px;right:16px', stylesheet)

    def test_admin_task_tabs_are_horizontal_only(self):
        with open(os.path.join(ROOT, "static", "site.css"), encoding="utf-8") as handle:
            stylesheet = handle.read()
        self.assertIn('overflow-x:auto!important', stylesheet)
        self.assertIn('overflow-y:hidden!important', stylesheet)
        self.assertIn('touch-action:pan-x', stylesheet)
        self.assertIn('white-space:nowrap', stylesheet)
        self.assertIn('grid-template-columns:minmax(0,1.48fr) minmax(0,1.95fr) minmax(0,1fr) minmax(0,.92fr)', stylesheet)
        self.assertIn('height:96px', stylesheet)
        self.assertIn('align-items:center!important', stylesheet)
        self.assertIn('line-height:1', stylesheet)
        self.assertIn('padding:0!important', stylesheet)
        self.assertIn('border-radius:22px 0 0 22px!important', stylesheet)


if __name__ == "__main__":
    unittest.main()
