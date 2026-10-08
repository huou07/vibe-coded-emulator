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
        env.update({"AN3_DATA_DIR": os.path.join(cls.temp, "data"), "AN3_PORT": str(PORT)})
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

    def test_account_backed_metrics_endpoint_is_retired(self):
        self.assertEqual(Client().request("GET", "/api/admin/system-metrics")[0], 404)

    def test_login_and_registration_stay_retired(self):
        client = Client()
        self.assertEqual(client.request("POST", "/api/register", {"name": "normal-user"})[0], 404)
        self.assertEqual(client.request("POST", "/api/login", {"name": "normal-user"})[0], 404)
        self.assertEqual(client.request("GET", "/api/admin/system-metrics")[0], 404)





    def test_reliability_paths_do_not_auto_reload_or_cache_api_responses(self):
        with open(os.path.join(ROOT, "static", "site.js"), encoding="utf-8") as handle:
            site_js = handle.read()
        with open(os.path.join(ROOT, "static", "service-worker.js"), encoding="utf-8") as handle:
            worker_js = handle.read()
        self.assertNotIn("data.version !== currentVersion) location.reload()", site_js)
        self.assertIn('refresh.textContent = english ? "Refresh when ready"', site_js)
        self.assertIn('url.pathname.startsWith("/api/")', worker_js)
        self.assertIn('fetch(event.request, {cache: "no-store"})', worker_js)
        self.assertNotIn("adminMonitoring", site_js)
        self.assertNotIn("/api/admin/system-metrics", site_js)



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




if __name__ == "__main__":
    unittest.main()
