#!/usr/bin/env bash
set -euo pipefail

data_dir="${AN3_DATA_DIR:-/srv/an3-arcade}"
backup_dir="${AN3_BACKUP_DIR:-$data_dir/backups}"
db_path="$data_dir/arcade.db"
stamp="$(date +%Y%m%d-%H%M%S)"
test -f "$db_path"
install -d -m 0750 "$backup_dir"
tmp_dir="$(mktemp -d "$backup_dir/.an3-backup.XXXXXX")"
trap 'rm -rf "$tmp_dir"' EXIT

python3 - "$db_path" "$tmp_dir/arcade-$stamp.db" <<'PY'
import sqlite3
import sys

source = sqlite3.connect(sys.argv[1])
target = sqlite3.connect(sys.argv[2])
try:
    source.backup(target)
    result = target.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise SystemExit(f"backup integrity check failed: {result}")
finally:
    target.close()
    source.close()
PY

python3 - "$data_dir" "$tmp_dir/rom-manifest-$stamp.tsv" <<'PY'
import os
import sys

root, output = sys.argv[1:]
roots = ("roms", "covers", "screenshots")
entries = []
for child in roots:
    base = os.path.join(root, child)
    if not os.path.isdir(base):
        continue
    for directory, _, filenames in os.walk(base):
        for filename in filenames:
            path = os.path.join(directory, filename)
            entries.append((os.path.relpath(path, root), os.path.getsize(path)))
with open(output, "w", encoding="utf-8") as handle:
    for relative, size in sorted(entries):
        handle.write(f"{relative}\t{size}\n")
PY

chmod 0600 "$tmp_dir/arcade-$stamp.db" "$tmp_dir/rom-manifest-$stamp.tsv"
mv "$tmp_dir/arcade-$stamp.db" "$backup_dir/"
mv "$tmp_dir/rom-manifest-$stamp.tsv" "$backup_dir/"
echo "created $backup_dir/arcade-$stamp.db"
echo "created $backup_dir/rom-manifest-$stamp.tsv"
