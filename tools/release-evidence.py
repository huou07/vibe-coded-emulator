#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Deterministic release evidence: license inventory, CycloneDX SBOM, SHA256SUMS.

No external SBOM tool (syft/cdxgen/cyclonedx) is required. Every component is
derived from an input that is already committed to the repository:

* ``THIRD_PARTY_NOTICES.md`` tables -> bundled components and their licenses,
* ``native-offline/package-lock.json`` -> npm dependencies incl. their SPDX license,
* ``native-offline/src-tauri/Cargo.lock`` and ``rust-gateway/Cargo.lock`` -> crates.

The SBOM deliberately omits a generation timestamp so identical inputs always
produce byte-identical evidence; pass ``--timestamp`` to record one explicitly
(ISO-8601 date-time, e.g. ``2026-09-19T00:00:00Z``).

Usage:
    python3 tools/release-evidence.py --out build/evidence \\
        [--root .] [--artifacts native-offline/releases] [--timestamp 2026-09-19T00:00:00Z]

Outputs written into ``--out``:
    LICENSE_INVENTORY.json  machine-readable license/dependency inventory
    sbom.cdx.json           CycloneDX 1.5 JSON SBOM
    SHA256SUMS              GNU sha256sum lines for every regular artifact

Publication gate:
    --fail-on-unknown  fail closed (exit 3) when any component still has no
                       license, so a release cannot be published until the
                       inventory is reconciled against docs/licensing/license-audit.md.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import re
import sys
from pathlib import Path

TOOL_NAME = "release-evidence"
TOOL_VERSION = "1"
SPDX_APP = "GPL-3.0-or-later"

# A handful of notice strings are names, not SPDX expressions, and must not be
# guessed into an expression form (CycloneDX expressions must be valid SPDX).
NAME_ONLY_LICENSES = {"public domain", "bsd family"}
LICENSE_ALIASES = {"sil ofl 1.1": "OFL-1.1"}

# Files that are evidence *about* artifacts rather than release artifacts.
CHECKSUM_EXCLUDED_SUFFIXES = (".sha256", ".sha512", ".sig", ".asc", ".json")
CHECKSUM_EXCLUDED_NAMES = {"SHA256SUMS", "catalog.json"}

_SPDX_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+\-]*$")

# CycloneDX ``metadata.timestamp`` is an RFC 3339 / ISO-8601 date-time. A build
# id or a directory stamp is not a valid timestamp, so reject it here rather
# than emit an SBOM a consumer cannot validate.
_ISO_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clean_cell(value: str) -> str:
    value = value.replace("`", "").strip()
    value = re.sub(r"\*\*(.+?)\*\*", r"\1", value)
    return value.strip()


def _license_field(text: str):
    """Return a CycloneDX ``licenses`` entry for a notice-table license string."""
    text = _clean_cell(text)
    if not text:
        return None
    lowered = text.lower()
    if lowered in NAME_ONLY_LICENSES:
        return {"license": {"name": text}}
    alias = LICENSE_ALIASES.get(lowered)
    if alias:
        return {"license": {"id": alias}}
    tokens = text.split()
    if tokens and all(
        _SPDX_TOKEN.match(token) or token in {"AND", "OR", "WITH"} for token in tokens
    ):
        return {"expression": text}
    return {"license": {"name": text}}


def parse_notices(path: Path):
    """Parse every markdown pipe table that has ``Component`` and ``License``."""
    if not path.is_file():
        return []
    components = []
    header = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            header = None
            continue
        cells = [_clean_cell(cell) for cell in line.strip("|").split("|")]
        if all(set(cell) <= {"-", ":"} and cell for cell in cells):
            continue  # separator row
        if "Component" in cells and "License" in cells:
            header = {
                "component": cells.index("Component"),
                "license": cells.index("License"),
                "version": _index_or_none(cells, "Version / revision", "Version"),
                "copyright": _index_or_none(cells, "Copyright"),
                "source": _index_or_none(cells, "Corresponding source"),
            }
            continue
        if header is None or len(cells) <= header["license"]:
            continue
        name = cells[header["component"]]
        if not name or name.lower() == "component":
            continue
        components.append(
            {
                "name": name,
                "version": _cell_at(cells, header["version"]),
                "license": cells[header["license"]],
                "copyright": _cell_at(cells, header["copyright"]),
                "source": _cell_at(cells, header["source"]),
                "ecosystem": "bundled-notices",
            }
        )
    return components


def _index_or_none(cells, *names):
    for name in names:
        if name in cells:
            return cells.index(name)
    return None


def _cell_at(cells, index):
    if index is None or index >= len(cells):
        return None
    value = cells[index]
    return value or None


def _hash_from_integrity(integrity: str):
    if not integrity or "-" not in integrity:
        return None
    algorithm, _, encoded = integrity.partition("-")
    try:
        digest = base64.b64decode(encoded).hex()
    except (ValueError, binascii.Error):
        return None
    return {"alg": "SHA-" + algorithm[3:].upper(), "content": digest}


def parse_npm_lock(path: Path):
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    components = []
    for key, entry in data.get("packages", {}).items():
        if not key:
            continue  # the root project, represented by the SBOM metadata component
        name = entry.get("name") or key.rsplit("node_modules/", 1)[-1]
        component = {
            "name": name,
            "version": entry.get("version"),
            "license": entry.get("license"),
            "source": entry.get("resolved"),
            "copyright": None,
            "ecosystem": "npm",
            "dev": bool(entry.get("dev")),
        }
        digest = _hash_from_integrity(entry.get("integrity", ""))
        if digest:
            component["hashes"] = [digest]
        components.append(component)
    return components


_CARGO_FIELD = re.compile(r'^(name|version|source|checksum)\s*=\s*"([^"]*)"$')


def parse_cargo_lock(path: Path):
    if not path.is_file():
        return []
    components = []
    current = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line == "[[package]]":
            current = {}
            components.append(current)
            continue
        if current is None:
            continue
        if line.startswith("[") and line != "[[package]]":
            current = None
            continue
        match = _CARGO_FIELD.match(line)
        if match:
            current[match.group(1)] = match.group(2)
    parsed = []
    for entry in components:
        if not entry.get("name"):
            continue
        component = {
            "name": entry["name"],
            "version": entry.get("version"),
            "license": None,
            "source": entry.get("source"),
            "copyright": None,
            "ecosystem": "cargo",
        }
        checksum = entry.get("checksum")
        if checksum and re.fullmatch(r"[0-9a-f]{64}", checksum):
            component["hashes"] = [{"alg": "SHA-256", "content": checksum}]
        parsed.append(component)
    return parsed


def collect_components(root: Path):
    """Merge every machine-readable input into one sorted component list."""
    components = []
    components.extend(parse_notices(root / "THIRD_PARTY_NOTICES.md"))
    components.extend(parse_npm_lock(root / "native-offline" / "package-lock.json"))
    components.extend(
        parse_cargo_lock(root / "native-offline" / "src-tauri" / "Cargo.lock")
    )
    components.extend(parse_cargo_lock(root / "rust-gateway" / "Cargo.lock"))

    unique = {}
    for component in components:
        key = (
            component["ecosystem"],
            component["name"].lower(),
            component.get("version") or "",
            component.get("license") or "",
            component.get("source") or "",
        )
        unique.setdefault(key, component)
    return sorted(
        unique.values(),
        key=lambda item: (item["ecosystem"], item["name"].lower(), item.get("version") or ""),
    )


def purl_npm(name: str, version):
    if name.startswith("@"):
        scope, _, package = name.partition("/")
        path = f"%40{scope[1:]}/{package}"
    else:
        path = name
    return f"pkg:npm/{path}@{version}" if version else f"pkg:npm/{path}"


def purl_cargo(name: str, version):
    return f"pkg:cargo/{name}@{version}" if version else f"pkg:cargo/{name}"


def _component_purl(component):
    version = component.get("version")
    ecosystem = component["ecosystem"]
    if ecosystem == "npm":
        return purl_npm(component["name"], version)
    if ecosystem == "cargo":
        return purl_cargo(component["name"], version)
    return None


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "component"


def _to_cdx(component, index: int):
    purl = _component_purl(component)
    entry = {
        "type": "library",
        "bom-ref": purl or f"urn:an3:notice:{_slug(component['name'])}-{index}",
        "name": component["name"],
        "properties": [{"name": "an3:ecosystem", "value": component["ecosystem"]}],
    }
    if component.get("version"):
        entry["version"] = component["version"]
    if purl:
        entry["purl"] = purl
    license_field = _license_field(component["license"]) if component.get("license") else None
    if license_field:
        entry["licenses"] = [license_field]
    if component.get("hashes"):
        entry["hashes"] = component["hashes"]
    for name, value in (
        ("an3:source", component.get("source")),
        ("an3:copyright", component.get("copyright")),
        ("an3:npmScope", "development" if component.get("dev") else None),
    ):
        if value:
            entry["properties"].append({"name": name, "value": value})
    return entry


def _app_versions(root: Path):
    def version_of(relative):
        path = root / relative
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8")).get("version")

    return (
        version_of("native-offline/src-tauri/tauri.conf.json"),
        version_of("native-offline/src-tauri/tauri.android.conf.json"),
    )


def build_sbom(root: Path, components, timestamp=None):
    desktop_version, android_version = _app_versions(root)
    metadata = {
        "tools": [
            {
                "vendor": "Vibe Coded Emulator",
                "name": TOOL_NAME,
                "version": TOOL_VERSION,
            }
        ],
        "component": {
            "type": "application",
            "bom-ref": "pkg:generic/vibe-coded-emulator"
            + (f"@{desktop_version}" if desktop_version else ""),
            "name": "vibe-coded-emulator",
            "licenses": [{"expression": SPDX_APP}],
            "properties": [
                {"name": "an3:licenseAudit", "value": "docs/licensing/license-audit.md"},
            ],
        },
    }
    if desktop_version:
        metadata["component"]["version"] = desktop_version
    if android_version:
        metadata["component"]["properties"].append(
            {"name": "an3:androidVersion", "value": android_version}
        )
    if timestamp:
        metadata["timestamp"] = timestamp
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": metadata,
        "components": [_to_cdx(component, index) for index, component in enumerate(components)],
    }


def build_license_inventory(components):
    rows = []
    by_license = {}
    unknown_by_ecosystem = {}
    for component in components:
        license_text = component.get("license") or None
        rows.append(
            {
                "name": component["name"],
                "version": component.get("version") or None,
                "license": license_text,
                "ecosystem": component["ecosystem"],
                "source": component.get("source") or None,
                "copyright": component.get("copyright") or None,
            }
        )
        if license_text is None:
            ecosystem = component["ecosystem"]
            unknown_by_ecosystem[ecosystem] = unknown_by_ecosystem.get(ecosystem, 0) + 1
        key = license_text or "UNKNOWN"
        by_license[key] = by_license.get(key, 0) + 1
    return {
        "schema_version": 1,
        "components": rows,
        "summary": {
            "total": len(rows),
            "with_license": len(rows) - by_license.get("UNKNOWN", 0),
            "unknown_license": by_license.get("UNKNOWN", 0),
            "unknown_by_ecosystem": dict(sorted(unknown_by_ecosystem.items())),
            "by_license": dict(sorted(by_license.items())),
        },
    }


def write_sha256sums(artifacts_dir: Path, destination: Path):
    """Write GNU ``sha256sum`` lines for every regular artifact in the directory."""
    names = []
    for path in sorted(artifacts_dir.iterdir(), key=lambda item: item.name):
        if not path.is_file() or path.is_symlink():
            continue
        if path.name.startswith(".") or path.name in CHECKSUM_EXCLUDED_NAMES:
            continue
        if path.name.endswith(CHECKSUM_EXCLUDED_SUFFIXES):
            continue
        names.append(path.name)
    if not names:
        raise ValueError(f"No regular release artifacts found in {artifacts_dir}")
    lines = [f"{sha256_file(artifacts_dir / name)}  {name}" for name in names]
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return names


def generate(root: Path, out: Path, artifacts=None, timestamp=None):
    out.mkdir(parents=True, exist_ok=True)
    components = collect_components(root)
    inventory = build_license_inventory(components)
    (out / "LICENSE_INVENTORY.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    sbom = build_sbom(root, components, timestamp=timestamp)
    (out / "sbom.cdx.json").write_text(
        json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    checksummed = []
    if artifacts is not None:
        checksummed = write_sha256sums(artifacts, out / "SHA256SUMS")
    return inventory, sbom, checksummed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--out", required=True, help="Evidence output directory (created).")
    parser.add_argument("--artifacts", default=None, help="Directory of release artifacts to checksum.")
    parser.add_argument("--timestamp", default=None, help="Optional fixed SBOM timestamp.")
    parser.add_argument(
        "--fail-on-unknown",
        action="store_true",
        help="Publication gate: exit 3 when any component still has no license.",
    )
    args = parser.parse_args(argv)
    if args.timestamp and not _ISO_TIMESTAMP.match(args.timestamp):
        parser.error(
            "--timestamp must be an ISO-8601 date-time "
            "(example: 2026-09-19T00:00:00Z)"
        )

    root = Path(args.root).resolve()
    out = Path(args.out).resolve()
    inventory, _, checksummed = generate(
        root,
        out,
        artifacts=Path(args.artifacts).resolve() if args.artifacts else None,
        timestamp=args.timestamp,
    )
    summary = inventory["summary"]
    print(
        f"RELEASE_EVIDENCE=wrote {summary['total']} components "
        f"({summary['with_license']} with license, {summary['unknown_license']} unknown) "
        f"to {out}"
    )
    if checksummed:
        print(f"SHA256SUMS={len(checksummed)} artifacts")
    if args.fail_on_unknown and summary["unknown_license"]:
        ecosystems = ", ".join(
            f"{name}={count}"
            for name, count in summary["unknown_by_ecosystem"].items()
        ) or "ecosystems=unknown"
        print(
            "RELEASE_EVIDENCE_GATE=FAIL "
            f"{summary['unknown_license']} component(s) without a license ({ecosystems}); "
            "reconcile docs/licensing/license-audit.md before publication",
            file=sys.stderr,
        )
        return 3
    if args.fail_on_unknown:
        print("RELEASE_EVIDENCE_GATE=PASS every component carries a license")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
