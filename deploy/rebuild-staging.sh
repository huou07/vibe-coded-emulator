#!/usr/bin/env bash
set -euo pipefail

# Rebuild the isolated staging data set on the current production host.
# This script changes only staging-specific paths, its service, and the exact
# LAN firewall rule for 192.0.2.8:8092. It never changes production code,
# data, services, or Cloudflare configuration.

if [[ "$#" -ne 1 ]]; then
  echo "usage: rebuild-staging.sh /path/to/source-archive.tgz" >&2
  exit 2
fi

ARCHIVE="$1"
PRODUCTION_DATA=/srv/an3-arcade
STAGING_ROOT=/opt/an3-arcade-staging
STAGING_DATA=/srv/an3-arcade-staging
STAGING_ENV=/etc/an3-arcade-staging.env
STAGING_UNIT=/etc/systemd/system/an3-arcade-staging.service
UNIT=an3-arcade-staging.service
LAN_HOST=192.0.2.8
PORT=8092
STAMP="$(date +%Y%m%d-%H%M%S)"
RELEASE="$STAGING_ROOT/releases/${STAMP}-rebuild"
CURRENT="$STAGING_ROOT/current"
NEXT="$STAGING_ROOT/current.next"
DATA_NEW="$STAGING_DATA.new"
ENV_NEW="$STAGING_ENV.new"
DATA_RETIRED="$STAGING_DATA.retired-$STAMP"
ENV_RETIRED="$STAGING_ENV.retired-$STAMP"

[[ -r "$ARCHIVE" ]] || { echo "Staging archive is not readable." >&2; exit 1; }
[[ -r "$PRODUCTION_DATA/arcade.db" ]] || { echo "Production database is not readable." >&2; exit 1; }
[[ -d "$PRODUCTION_DATA/roms" ]] || { echo "Production ROM root is not readable." >&2; exit 1; }
[[ ! -e "$DATA_NEW" && ! -L "$DATA_NEW" ]] || { echo "Pending staging data path exists: $DATA_NEW" >&2; exit 1; }
[[ ! -e "$ENV_NEW" && ! -L "$ENV_NEW" ]] || { echo "Pending staging environment path exists: $ENV_NEW" >&2; exit 1; }
[[ ! -e "$NEXT" && ! -L "$NEXT" ]] || { echo "Pending staging release link exists: $NEXT" >&2; exit 1; }

install -d -m 0755 "$STAGING_ROOT/releases" "$RELEASE"
tar -xzf "$ARCHIVE" -C "$RELEASE"
[[ -f "$RELEASE/app.py" && -d "$RELEASE/static" && -f "$RELEASE/deploy/an3-arcade-staging.service" ]] || {
  echo "Staging archive has an unexpected layout." >&2
  exit 1
}
# macOS archive metadata must never become served/static files or affect the
# server-computed asset version.
find "$RELEASE" -type f -name '._*' -delete
chown -R root:root "$RELEASE"
find "$RELEASE" -type d -exec chmod 0755 {} +
find "$RELEASE" -type f -exec chmod 0644 {} +
chmod 0755 "$RELEASE/app.py"

install -d -o tvshare -g tvshare -m 0750 "$DATA_NEW"
for directory in roms prepared-roms covers screenshots proposal-covers proposal-screenshots custom uploads emulatorjs-cache cache tmp logs backups; do
  install -d -o tvshare -g tvshare -m 0750 "$DATA_NEW/$directory"
done

python3 - "$PRODUCTION_DATA/arcade.db" "$DATA_NEW/arcade.db" "$PRODUCTION_DATA/roms" "$DATA_NEW/roms" <<'PY'
import os
import shutil
import sqlite3
import sys
import time

source_db, staging_db, production_roms, staging_roms = sys.argv[1:]

source = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
source.row_factory = sqlite3.Row
target = sqlite3.connect(staging_db)
target.row_factory = sqlite3.Row
try:
    # A consistent SQLite Online Backup snapshot is the only production data
    # read. The staged copy is then aggressively minimized before activation.
    source.backup(target)

    selected = []
    for system, terms in (("gba", ("pokemon", "emerald")), ("nds", ("mystery", "dungeon", "explorers", "sky"))):
        where = " AND ".join(["lower(title_vi || ' ' || title_en) LIKE ?"] * len(terms))
        rows = target.execute(
            f"SELECT id, system, rom_path, rom_name FROM games WHERE system=? AND {where}",
            (system, *(f"%{term}%" for term in terms)),
        ).fetchall()
        if len(rows) != 1:
            raise RuntimeError(f"expected exactly one authorized {system} test game, found {len(rows)}")
        selected.append(rows[0])

    for row in selected:
        relative = row["rom_path"]
        if not relative or os.path.basename(relative) != relative or relative in {".", ".."}:
            raise RuntimeError("test ROM metadata has an unsafe path")
        source_path = os.path.join(production_roms, relative)
        destination_path = os.path.join(staging_roms, relative)
        if not os.path.isfile(source_path):
            raise RuntimeError(f"authorized test ROM is unavailable for {row['system']}")
        shutil.copy2(source_path, destination_path)

    keep_ids = tuple(int(row["id"]) for row in selected)
    now = int(time.time())
    target.execute("PRAGMA foreign_keys=ON")
    with target:
        # Remove sessions, users, account activity, moderation, settings, and
        # every production catalogue record except the two authorized ROM tests.
        for table in (
            "sessions", "ratings", "comments", "favorites", "reports", "page_views",
            "play_events", "game_screenshots", "game_updates", "game_enrichment_proposals",
            "upload_sessions", "users", "site_settings",
        ):
            target.execute(f"DELETE FROM {table}")
        target.execute(f"DELETE FROM games WHERE id NOT IN ({','.join('?' for _ in keep_ids)})", keep_ids)
        target.execute(
            f"UPDATE games SET cover_path='', description_vi='', description_en='', updated_at=? "
            f"WHERE id IN ({','.join('?' for _ in keep_ids)})",
            (now, *keep_ids),
        )

        fixtures = [
            ("an3-test-adventure", "AN3 Test Adventure", "AN3 Test Adventure", "Cuộc phiêu lưu giả lập cho kiểm thử giao diện.", "Synthetic adventure for UI testing.", "gba", 1, 0),
            ("pixel-racer-fixture", "Pixel Racer Fixture", "Pixel Racer Fixture", "Thẻ kiểm thử nhãn GBA, tìm kiếm và lưới thư viện.", "Fixture for system filters and library cards.", "gba", 1, 0),
            ("dungeon-ui-test", "Dungeon UI Test", "Dungeon UI Test", "Không có ROM; dùng để kiểm thử badge và trạng thái trống.", "No ROM; used for badge and empty-state testing.", "nds", 0, 0),
            ("retro-puzzle-demo", "Retro Puzzle Demo", "Retro Puzzle Demo", "Bản ghi giả cho bộ lọc và bố cục di động.", "Synthetic record for filters and mobile layout.", "nds", 1, 0),
            ("long-vietnamese-fixture", "Trò chơi phiêu lưu giả lập với tiêu đề tiếng Việt thật dài để kiểm thử khả năng xuống dòng trên mọi kích thước màn hình", "Long Vietnamese title fixture", "Đây là mô tả tiếng Việt cố ý dài để kiểm thử cách thẻ game, trang chi tiết, tìm kiếm, bộ lọc và bảng quản trị hiển thị nội dung nhiều dòng mà không tạo thanh cuộn ngang ngoài ý muốn.", "Long Vietnamese-description fixture.", "gba", 1, 0),
            ("long-english-fixture", "Long English Fixture", "The Exceptionally Long English Fixture Title Used to Exercise Wrapping, Search Results, and Responsive Card Geometry", "Mô tả ngắn cho bản ghi tiếng Anh.", "This intentionally verbose English description exercises long-form copy in library cards, search results, empty states, responsive layouts, and administrative tables without relying on executable game content.", "nds", 1, 0),
            ("missing-cover-fixture", "Thiếu ảnh bìa Fixture", "Missing Cover Fixture", "Không có ảnh bìa để xác nhận ảnh thay thế.", "No cover image, so the fallback artwork remains visible.", "gba", 0, 1),
            ("favorite-fixture", "Yêu thích Fixture", "Favorite State Fixture", "Bản ghi dành cho kiểm thử trạng thái yêu thích sau khi người kiểm thử đăng nhập.", "A fixture intended for favorite-state testing after a staging-only user signs in.", "nds", 1, 0),
            ("high-activity-fixture", "Hoạt động cao Fixture", "High Activity Fixture", "Bản ghi tạo mẫu dữ liệu hoạt động cho dashboard.", "Synthetic play-event data supports dashboard activity checks.", "gba", 1, 0),
            ("zero-activity-fixture", "Không hoạt động Fixture", "Zero Activity Fixture", "Bản ghi không có lượt chơi mẫu.", "This fixture deliberately has no play events.", "nds", 0, 0),
        ]
        fixture_ids = {}
        for slug, title_vi, title_en, desc_vi, desc_en, system, published, experimental in fixtures:
            cursor = target.execute(
                "INSERT INTO games(slug,title_vi,title_en,description_vi,description_en,system,rom_path,rom_name,cover_path,file_size,published,experimental,system_auto,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?, '', '', '', 0,?,?,?,?,?)",
                (slug, title_vi, title_en, desc_vi, desc_en, system, published, experimental, 0, now, now),
            )
            fixture_ids[slug] = cursor.lastrowid
        for offset in range(25):
            target.execute(
                "INSERT INTO play_events(visitor_hash,user_id,game_id,created_at) VALUES(?,?,?,?)",
                (f"staging-fixture-{offset:02d}", None, fixture_ids["high-activity-fixture"], now - offset),
            )

    target.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise RuntimeError("staging database integrity check failed")
finally:
    target.close()
    source.close()
PY
chown -R tvshare:tvshare "$DATA_NEW"
chmod 0640 "$DATA_NEW/arcade.db"

umask 077
pepper="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
{
  printf 'AN3_AUTH_PEPPER=%s\n' "$pepper"
  printf '%s\n' 'AN3_APP_DIR=/opt/an3-arcade-staging/current'
  printf '%s\n' 'AN3_DATA_DIR=/srv/an3-arcade-staging'
  printf '%s\n' 'AN3_HOST=192.0.2.8'
  printf '%s\n' 'AN3_PORT=8092'
  printf '%s\n' 'AN3_BASE_URL=http://192.0.2.8:8092'
  printf '%s\n' 'AN3_ENVIRONMENT=staging'
  printf '%s\n' 'AN3_COOKIE_SECURE=0'
} > "$ENV_NEW"
chown root:root "$ENV_NEW"
chmod 0600 "$ENV_NEW"

PREVIOUS=""
if [[ -L "$CURRENT" ]]; then
  PREVIOUS="$(readlink "$CURRENT")"
fi

rollback() {
  systemctl stop "$UNIT" || true
  if [[ -n "$PREVIOUS" ]]; then
    rm -f "$NEXT"
    ln -s "$PREVIOUS" "$NEXT"
    mv -Tf "$NEXT" "$CURRENT"
  fi
  if [[ -e "$DATA_RETIRED" ]]; then
    rm -rf -- "$STAGING_DATA"
    mv "$DATA_RETIRED" "$STAGING_DATA"
  fi
  if [[ -e "$ENV_RETIRED" ]]; then
    rm -f "$STAGING_ENV"
    mv "$ENV_RETIRED" "$STAGING_ENV"
  fi
  systemctl start "$UNIT" || true
}

systemctl stop "$UNIT"
if [[ -e "$STAGING_DATA" ]]; then mv "$STAGING_DATA" "$DATA_RETIRED"; fi
if [[ -e "$STAGING_ENV" ]]; then mv "$STAGING_ENV" "$ENV_RETIRED"; fi
mv "$DATA_NEW" "$STAGING_DATA"
mv "$ENV_NEW" "$STAGING_ENV"
install -o root -g root -m 0644 "$RELEASE/deploy/an3-arcade-staging.service" "$STAGING_UNIT"
ln -s "releases/$(basename "$RELEASE")" "$NEXT"
mv -Tf "$NEXT" "$CURRENT"
systemctl daemon-reload
ufw allow proto tcp from 192.0.2.0/24 to "$LAN_HOST" port "$PORT" comment 'AN3 Arcade staging LAN'
systemctl enable --now "$UNIT"

healthy=0
for attempt in $(seq 1 20); do
  if curl --fail --silent --show-error "http://$LAN_HOST:$PORT/health" | grep -q '"environment": "staging"'; then
    healthy=1
    break
  fi
  sleep 1
done
if [[ "$healthy" -ne 1 ]]; then
  rollback
  echo "Staging health failed; the previous staging service/data were restored." >&2
  exit 1
fi

# The obsolete staging copy contained a broad production-derived media set.
# It is removed only after the new isolated service is healthy.
rm -rf -- "$DATA_RETIRED"
rm -f -- "$ENV_RETIRED"
printf 'STAGING_REBUILD=PASS\n'
printf 'STAGING_URL=http://%s:%s\n' "$LAN_HOST" "$PORT"
