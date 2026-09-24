"""Focused tests for tools/release-artifact-scan.py (release-security goal 4).

The scanner runs before publication next to the unknown-license gate. It must:

* find credentials and private data in release artifacts and the evidence
  bundle without network access or a gitleaks install,
* honour the ``.gitleaks.toml`` allowlists and inline ``[[rules]]`` so the
  config stays the single source of truth for suppressions,
* never print or persist a matched secret value, and
* exit non-zero on a finding (0 clean, 1 findings, 2 configuration error).

Fixtures are synthetic and live under a TemporaryDirectory; the real repository
files are only read for the config contract.
"""
from __future__ import annotations

import contextlib
import gzip
import importlib.util
import io
import json
import lzma
import tarfile
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "release-artifact-scan.py"
REAL_CONFIG = ROOT / "tools" / "publication" / ".gitleaks.toml"
RELEASE_TRAIN = ROOT / "tools" / "release-train.sh"

spec = importlib.util.spec_from_file_location("release_artifact_scan", TOOL)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

GITHUB_TOKEN = "ghp_" + "A" * 36


def _default_rules():
    return mod._compile_rules(mod.DEFAULT_RULES)


class ConfigTests(unittest.TestCase):
    def test_real_gitleaks_config_parses_with_its_allowlist(self):
        config = mod.parse_gitleaks_config(REAL_CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(config["warnings"], [])
        self.assertTrue(config["extend_default"])
        self.assertEqual(len(config["allowlists"]), 4)
        allowlist = config["allowlists"][0]
        self.assertEqual(allowlist["paths"], ["static/player-runtime\\.js$"])
        self.assertEqual(allowlist["regexes"], ["an3-presentation-renderer-v1"])
        account_allowlist = config["allowlists"][1]
        self.assertEqual(
            account_allowlist["paths"],
            [
                "(^|/|!)native-account\\.js$",
                "(^|/|!)tauri\\.conf\\.json$",
                "(^|/|!)liban3_offline_native\\.so$",
                "(^|/|!)an3-offline-native$",
            ],
        )
        self.assertEqual(account_allowlist["regexes"], ["an3tocom\\.space"])
        self.assertEqual(
            config["allowlists"][2]["paths"], ["(^|/|!)an3_switch_companion$"]
        )
        self.assertEqual(
            config["allowlists"][2]["regexes"], ["joseignacioechevarria@gmail\\.com"]
        )
        self.assertEqual(
            config["allowlists"][3]["paths"],
            ["(^|/|!)org\\.gnome\\.system\\.proxy\\.gschema\\.xml$"],
        )
        self.assertEqual(config["allowlists"][3]["regexes"], ["192\\.168\\.0\\.0"])
        # Every built-in rule is present; the config only adds to them.
        rule_ids = [rule[0] for rule in config["rules"]]
        self.assertIn("private-key-block", rule_ids)
        self.assertIn("an3-env-secret", rule_ids)

    def test_inline_custom_rule_is_merged(self):
        text = "[[rules]]\nid = 'canary'\nregex = '''CANARY-[0-9]{4}'''\n"
        config = mod.parse_gitleaks_config(text)
        custom = [rule for rule in config["rules"] if rule[1] == "custom"]
        self.assertEqual(custom, [("canary", "custom", b"CANARY-[0-9]{4}")])

    def test_custom_rule_without_inline_regex_is_a_warning(self):
        config = mod.parse_gitleaks_config("[[rules]]\nid = 'builtin-reference'\n")
        self.assertEqual(config["warnings"], [
            "custom rule 'builtin-reference' has no inline regex; only inline "
            "regex rules are supported and this rule was ignored"
        ])
        self.assertNotIn("builtin-reference", [rule[0] for rule in config["rules"]])

    def test_multiline_allowlist_paths_are_joined(self):
        text = "[[allowlists]]\npaths = [\n  'a\\.txt$',\n  'b\\.txt$',\n]\n"
        config = mod.parse_gitleaks_config(text)
        self.assertEqual(config["allowlists"][0]["paths"], ["a\\.txt$", "b\\.txt$"])

    def test_comments_and_blank_lines_are_ignored(self):
        config = mod.parse_gitleaks_config("# comment\n\n[extend]\nuseDefault = true\n")
        self.assertTrue(config["extend_default"])
        self.assertEqual(config["allowlists"], [])
        self.assertEqual(config["warnings"], [])


class DetectionTests(unittest.TestCase):
    SAMPLES = {
        "private-key-block": chr(10).join(("-----BEGIN " + "PRIVATE KEY-----", "not-a-real-test-key", "-----END " + "PRIVATE KEY-----")),
        "google-api-key": "AIza" + "A" * 35,
        "google-oauth-client-secret": "GOCSPX-" + "A" * 20,
        "aws-access-key-id": "AKIA" + "A" * 16,
        "github-token": GITHUB_TOKEN,
        "slack-token": "xoxb-" + "A" * 10,
        "stripe-secret-key": "sk_live_" + "A" * 20,
        "jwt": "eyJ" + "A" * 12 + "." + "B" * 12 + "." + "C" * 12,
        "an3-env-secret": "AN3_AUTH_PEPPER=" + "A" * 8,
        "an3-google-client-id": "AN3_GOOGLE_CLIENT_ID=" + "A" * 8,
        "home-directory-path": "/" + "Users/" + "meo" + "meo" + "/roms",
        "windows-home-path": "C:\\Users\\bob\\roms",
        "lan-address": "192." + "168.1.2",
        "personal-email": "test" + "@gmail.com",
        "private-infra-host": "an3tocom" + ".space",
        "developer-handle": "meo" + "meo",
        "legacy-marker": "an3" + "_codex",
    }

    def _rules_for(self, payload: bytes):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "artifact.bin"
            path.write_bytes(payload)
            result = mod.scan([str(path)], _default_rules(), [])
        return {finding["rule"] for finding in result["findings"]}

    def test_every_rule_detects_its_sample(self):
        for rule_id, sample in self.SAMPLES.items():
            with self.subTest(rule=rule_id):
                self.assertIn(rule_id, self._rules_for(sample.encode("utf-8")))

    def test_clean_payload_has_no_findings(self):
        self.assertEqual(self._rules_for(b"clean release payload\n"), set())

    def test_findings_carry_path_line_and_no_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.bin"
            path.write_bytes(b"header\n" + GITHUB_TOKEN.encode() + b"\n")
            result = mod.scan([str(path)], _default_rules(), [])
        self.assertEqual(len(result["findings"]), 1)
        finding = result["findings"][0]
        self.assertEqual(finding["rule"], "github-token")
        self.assertEqual(finding["category"], "secret")
        self.assertEqual(finding["line"], 2)
        self.assertEqual(finding["match_length"], len(GITHUB_TOKEN))
        self.assertNotIn(GITHUB_TOKEN, json.dumps(result))
        self.assertTrue(finding["path"].endswith("app.bin"))

    def test_detects_secret_inside_binary_bytes(self):
        payload = b"\x00\x01\x02" + GITHUB_TOKEN.encode() + b"\xff\xfe"
        self.assertIn("github-token", self._rules_for(payload))

    def test_personal_email_local_part_is_bounded(self):
        # A long unanchored [A-Za-z0-9._%+-] run must not trigger quadratic
        # backtracking: the local part is capped at 64 characters, so a
        # multi-MiB run completes in bounded wall-clock time instead of
        # hanging the release train.
        payload = b"a" * (4 * 1024 * 1024)
        started = time.monotonic()
        self.assertEqual(self._rules_for(payload), set())
        elapsed = time.monotonic() - started
        self.assertLess(
            elapsed,
            30.0,
            f"personal-email scan of a 4 MiB local-part run took {elapsed:.2f}s",
        )

    def test_personal_email_still_detects_a_normal_address(self):
        self.assertIn("personal-email", self._rules_for(b"test" + b"@gmail.com"))


class ChunkCarryTests(unittest.TestCase):
    """A match wholly inside the chunk carry must be reported exactly once."""

    def test_token_wholly_inside_carry_is_reported_once(self):
        token = GITHUB_TOKEN.encode()
        # Place the token so it ends exactly at the first CHUNK_BYTES boundary:
        # the whole match then lives inside the carry of the next window.
        payload = b"\x01" * (mod.CHUNK_BYTES - len(token)) + token + b"\x02" * 128
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "carry.bin"
            path.write_bytes(payload)
            result = mod.scan([str(path)], _default_rules(), [])
        findings = [f for f in result["findings"] if f["rule"] == "github-token"]
        self.assertEqual(len(findings), 1, findings)
        self.assertEqual(findings[0]["offset"], mod.CHUNK_BYTES - len(token))
        self.assertEqual(findings[0]["match_length"], len(token))


class AllowlistTests(unittest.TestCase):
    CONFIG = (
        "[[allowlists]]\n"
        "description = 'fixture'\n"
        "paths = ['allowed\\.txt$']\n"
        "regexTarget = 'match'\n"
        "regexes = ['ghp_" + "A" * 36 + "']\n"
    )

    def _run(self, payloads):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config.toml"
            config.write_text(self.CONFIG, encoding="utf-8")
            for name, payload in payloads.items():
                (root / name).write_text(payload, encoding="utf-8")
            config_data = mod.parse_gitleaks_config(config.read_text(encoding="utf-8"))
            rules = mod._compile_rules(config_data["rules"])
            result = mod.scan(
                [str(root / name) for name in payloads],
                rules,
                config_data["allowlists"],
            )
        return result

    def test_allowlisted_value_in_matching_path_is_suppressed(self):
        result = self._run({"allowed.txt": GITHUB_TOKEN})
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["suppressed"], 1)

    def test_same_value_in_other_path_is_still_reported(self):
        result = self._run({"other.txt": GITHUB_TOKEN})
        self.assertEqual([finding["rule"] for finding in result["findings"]], ["github-token"])
        self.assertEqual(result["suppressed"], 0)

    def test_real_config_allowlist_targets_the_localstorage_key(self):
        config = mod.parse_gitleaks_config(REAL_CONFIG.read_text(encoding="utf-8"))
        allowlist = config["allowlists"][0]
        self.assertTrue(
            mod._allowlist_matches(
                allowlist,
                "static/player-runtime.js",
                b'rendererStorageKey = "an3-presentation-renderer-v1"',
            )
        )
        self.assertFalse(
            mod._allowlist_matches(allowlist, "static/player.js", b"an3-presentation-renderer-v1")
        )


class MainTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _run(self, targets, *extra):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = mod.main([*extra, *[str(item) for item in targets]])
        return code, stderr.getvalue()

    def test_exit_zero_on_clean_artifact(self):
        artifact = self.root / "clean.bin"
        artifact.write_bytes(b"nothing sensitive")
        code, output = self._run([artifact])
        self.assertEqual(code, 0)
        self.assertIn("RELEASE_ARTIFACT_SCAN=CLEAN", output)

    def test_exit_one_on_finding(self):
        artifact = self.root / "leak.bin"
        artifact.write_text(GITHUB_TOKEN, encoding="utf-8")
        code, output = self._run([artifact])
        self.assertEqual(code, 1)
        self.assertIn("RELEASE_ARTIFACT_SCAN=FINDINGS", output)

    def test_missing_config_is_a_configuration_error(self):
        artifact = self.root / "clean.bin"
        artifact.write_bytes(b"clean")
        code, output = self._run([artifact], "--config", str(self.root / "nope.toml"))
        self.assertEqual(code, 2)
        self.assertIn("config not found", output)

    def test_missing_target_is_a_configuration_error(self):
        code, output = self._run([self.root / "ghost.bin"])
        self.assertEqual(code, 2)
        self.assertIn("target does not exist", output)

    def test_directory_is_walked_recursively(self):
        nested = self.root / "a" / "b"
        nested.mkdir(parents=True)
        (nested / "leak.bin").write_text(GITHUB_TOKEN, encoding="utf-8")
        report = self.root / "report.json"
        code, _ = self._run([self.root / "a"], "--json", str(report))
        self.assertEqual(code, 1)
        data = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(data["summary"]["findings"], 1)
        self.assertEqual(data["findings"][0]["rule"], "github-token")

    def test_json_report_is_written_and_never_contains_the_secret(self):
        artifact = self.root / "leak.bin"
        artifact.write_text("token=" + GITHUB_TOKEN, encoding="utf-8")
        report = self.root / "report.json"
        code, _ = self._run([artifact], "--json", str(report))
        self.assertEqual(code, 1)
        raw = report.read_text(encoding="utf-8")
        self.assertNotIn(GITHUB_TOKEN, raw)
        data = json.loads(raw)
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["tool"]["name"], "release-artifact-scan")
        finding = data["findings"][0]
        self.assertEqual(
            set(finding), {"rule", "category", "path", "offset", "line", "match_length"}
        )

    def test_oversized_file_is_skipped_and_reported(self):
        artifact = self.root / "big.bin"
        artifact.write_bytes(b"x" * 64)
        report = self.root / "report.json"
        code, output = self._run(
            [artifact], "--max-file-bytes", "16", "--json", str(report)
        )
        self.assertEqual(code, 0)
        self.assertIn("file(s) were not scanned", output)
        data = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(data["summary"]["skipped"], 1)
        self.assertEqual(data["findings"], [])

    def test_finding_limit_does_not_hide_findings(self):
        # A file that trips the per-file finding cap must still fail the scan;
        # dropping the collected findings would silently exit 0 on a real leak.
        artifact = self.root / "flood.bin"
        artifact.write_text(("meo" + "meo" + chr(10)) * 1001, encoding="utf-8")
        report = self.root / "report.json"
        code, output = self._run([artifact], "--json", str(report))
        self.assertEqual(code, 1)
        self.assertIn("RELEASE_ARTIFACT_SCAN=FINDINGS", output)
        data = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(data["summary"]["findings"], 1000)
        self.assertEqual(data["summary"]["skipped"], 1)
        self.assertEqual(data["skipped"][0]["reason"], "finding limit reached")

    def test_custom_config_rule_is_enforced(self):
        artifact = self.root / "canary.txt"
        artifact.write_text("build CANARY-1234 end", encoding="utf-8")
        config = self.root / "config.toml"
        config.write_text(
            "[[rules]]\nid = 'canary'\nregex = '''CANARY-[0-9]{4}'''\n",
            encoding="utf-8",
        )
        code, _ = self._run([artifact], "--config", str(config))
        self.assertEqual(code, 1)


def _zip_bytes(members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def _ar_member(name, payload):
    header = (
        name.ljust(16).encode("ascii")
        + b"0".ljust(12)
        + b"0".ljust(6)
        + b"0".ljust(6)
        + b"100644".ljust(8)
        + str(len(payload)).encode("ascii").ljust(10)
        + b"`\n"
    )
    assert len(header) == 60
    member = header + payload
    if len(payload) % 2:
        member += b"\n"
    return member


def _ar_bytes(members):
    return b"!<arch>\n" + b"".join(_ar_member(name, data) for name, data in members.items())


def _tar_xz_bytes(members):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:xz") as archive:
        for name, payload in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def _tar_gz_bytes(members):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, payload in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


class ArchiveExpansionTests(unittest.TestCase):
    """Compressed container members must be expanded, not raw-scanned."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _scan(self, filename, payload, max_bytes=None):
        path = self.root / filename
        path.write_bytes(payload)
        kwargs = {} if max_bytes is None else {"max_bytes": max_bytes}
        # Use a stable basename so assertions read the reported member path.
        return mod.scan_file(path, _default_rules(), [], **kwargs)

    def test_apk_zip_member_secret_is_found(self):
        payload = _zip_bytes({"assets/config.txt": GITHUB_TOKEN, "lib/app.so": b"clean"})
        findings, suppressed, skipped, _ = self._scan("app.apk", payload)
        self.assertIsNone(skipped)
        self.assertEqual([finding["rule"] for finding in findings], ["github-token"])
        self.assertTrue(findings[0]["path"].endswith("app.apk!assets/config.txt"))
        self.assertNotIn(GITHUB_TOKEN, json.dumps(findings))

    def test_tar_gz_member_secret_is_found(self):
        payload = _tar_gz_bytes({"pkg/notes.txt": GITHUB_TOKEN.encode()})
        findings, _, skipped, _ = self._scan("bundle.tar.gz", payload)
        self.assertIsNone(skipped)
        self.assertEqual([finding["rule"] for finding in findings], ["github-token"])
        self.assertTrue(findings[0]["path"].endswith("bundle.tar.gz!pkg/notes.txt"))

    def test_gzip_single_member_secret_is_found(self):
        payload = gzip.compress(GITHUB_TOKEN.encode())
        findings, _, skipped, _ = self._scan("blob.gz", payload)
        self.assertIsNone(skipped)
        self.assertEqual([finding["rule"] for finding in findings], ["github-token"])

    def test_xz_single_member_secret_is_found(self):
        payload = lzma.compress(GITHUB_TOKEN.encode())
        findings, _, skipped, _ = self._scan("blob.xz", payload)
        self.assertIsNone(skipped)
        self.assertEqual([finding["rule"] for finding in findings], ["github-token"])

    def test_nested_zip_member_secret_is_found(self):
        inner = _zip_bytes({"deep.txt": GITHUB_TOKEN})
        payload = _zip_bytes({"inner.zip": inner})
        findings, _, skipped, _ = self._scan("outer.apk", payload)
        self.assertIsNone(skipped)
        self.assertEqual([finding["rule"] for finding in findings], ["github-token"])
        self.assertTrue(findings[0]["path"].endswith("outer.apk!inner.zip!deep.txt"))

    def test_deb_ar_data_member_secret_is_found(self):
        payload = _ar_bytes(
            {
                "debian-binary": b"2.0\n",
                "control.tar.xz": lzma.compress(b""),
                "data.tar.xz": _tar_xz_bytes({"usr/share/doc/notes": GITHUB_TOKEN.encode()}),
            }
        )
        findings, _, skipped, _ = self._scan("pkg.deb", payload)
        self.assertIsNone(skipped)
        self.assertEqual([finding["rule"] for finding in findings], ["github-token"])
        self.assertTrue(
            findings[0]["path"].endswith("pkg.deb!data.tar.xz!usr/share/doc/notes")
        )

    def test_clean_archive_has_no_findings(self):
        payload = _zip_bytes({"a.txt": b"hello", "b.bin": b"\x00\x01\x02"})
        findings, _, skipped, _ = self._scan("clean.apk", payload)
        self.assertEqual(findings, [])
        self.assertIsNone(skipped)

    def test_member_larger_than_limit_is_skipped_and_reported(self):
        payload = _zip_bytes({"big.bin": b"x" * 200000})
        findings, _, skipped, _ = self._scan("big.apk", payload, max_bytes=len(payload) + 10)
        self.assertEqual(findings, [])
        self.assertIn("exceeds --max-file-bytes", skipped)
        self.assertIn("big.apk!big.bin", skipped)

    def test_oversized_member_does_not_desync_following_members(self):
        payload = _tar_gz_bytes(
            {"big.bin": b"x" * 300000, "after/secret.txt": GITHUB_TOKEN.encode()}
        )
        findings, _, skipped, _ = self._scan("b.tar.gz", payload, max_bytes=100000)
        self.assertIn("big.bin exceeds", skipped)
        self.assertEqual([finding["rule"] for finding in findings], ["github-token"])
        self.assertTrue(findings[0]["path"].endswith("b.tar.gz!after/secret.txt"))

    def test_finding_limit_inside_archive_still_fails_closed(self):
        payload = _zip_bytes({"flood.txt": (("meo" + "meo" + chr(10)) * 1001).encode()})
        findings, _, skipped, _ = self._scan("flood.apk", payload)
        self.assertEqual(len(findings), 1000)
        self.assertEqual(skipped, "finding limit reached")

    def test_invalid_compressed_member_is_reported_not_clean(self):
        payload = b"\x1f\x8b\x08\x00" + b"not really gzip"
        findings, _, skipped, _ = self._scan("broken.gz", payload)
        self.assertEqual(findings, [])
        self.assertIn("could not be expanded", skipped)

    def test_expansion_does_not_extract_to_disk(self):
        payload = _zip_bytes({"secret.txt": GITHUB_TOKEN})
        self._scan("app.apk", payload)
        self.assertEqual(sorted(item.name for item in self.root.iterdir()), ["app.apk"])

    def test_allowlist_matches_member_path(self):
        config = (
            "[[allowlists]]\n"
            "description = 'fixture'\n"
            "paths = ['allowed\\.txt$']\n"
            "regexTarget = 'match'\n"
            "regexes = ['ghp_" + "A" * 36 + "']\n"
        )
        config_data = mod.parse_gitleaks_config(config)
        rules = mod._compile_rules(config_data["rules"])
        payload = _zip_bytes({"assets/allowed.txt": GITHUB_TOKEN})
        path = self.root / "app.apk"
        path.write_bytes(payload)
        result = mod.scan([str(path)], rules, config_data["allowlists"])
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["suppressed"], 1)


class ReleaseTrainWiringTests(unittest.TestCase):
    """The scan must run in the train beside the unknown-license gate."""

    def test_bash_syntax_is_valid(self):
        import subprocess

        result = subprocess.run(
            ["bash", "-n", str(RELEASE_TRAIN)], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_train_references_the_scanner_and_gate(self):
        text = RELEASE_TRAIN.read_text(encoding="utf-8")
        self.assertIn("tools/release-artifact-scan.py", text)
        self.assertIn("tools/publication/.gitleaks.toml", text)
        self.assertIn("AN3_REQUIRE_CLEAN_ARTIFACTS", text)
        self.assertIn("SECRET_SCAN.json", text)
        self.assertIn("run_artifact_secret_scan", text)
        # The scan runs from the shared evidence helper, so freeze and the
        # coordinated build both get it.
        self.assertIn('run_artifact_secret_scan "$out" "$artifacts"', text)


if __name__ == "__main__":
    unittest.main()
