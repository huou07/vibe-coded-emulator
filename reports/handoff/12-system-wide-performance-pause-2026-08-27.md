# Handoff toàn hệ thống — phiên tối ưu hiệu năng đã dừng

**Ngày chốt:** 2026-08-27
**Quyết định:** Chủ sở hữu yêu cầu dừng phiên polish. Không chạy thêm Android/PWA test, không sửa thêm code, và không deploy production trong phiên này.

## 1. Trạng thái chốt

| Khu vực | Trạng thái | Bằng chứng / giới hạn |
| --- | --- | --- |
| Local source | Dừng ở trạng thái đã kiểm thử tĩnh và unit/integration | `HEAD=542ef985ddd22435cad00695b065dda1be4f80d3`; worktree vốn đã dirty và được giữ nguyên, không clean/reset. |
| Backup local trước phiên | PASS, được giữ lại | Archive 201 MiB, SHA-256 `1abae82339d5cb5a727dd8ecdbf3bdd7fd61e1005cb5f3e3d305719610a97e51`; kiểm tra `tar -tzf` PASS. |
| Staging | Đã deploy và đang chạy | Service `an3-arcade-staging.service=active`; health ở `http://192.168.1.8:8092/health` trả `environment=staging`, asset `cc015f4d64dd`. |
| Production | Không thay đổi trong phiên này | Service `an3-arcade.service=active`; health trả asset đang live `107d77c36767`. Không có database, ROM, save, code/static production nào được thay đổi bởi phiên này. |
| Candidate production tạm thời | Không còn sẵn sàng để chạy | Hai file trong `/tmp` đã được kiểm tra lại và hiện không còn tồn tại. Không được dùng đường dẫn `/tmp` cũ để deploy. |
| Android / gameplay thật | Chưa chạy, theo yêu cầu dừng | Không có kết luận mới về GBA, NDS, 3DS, Switch, virtual pad, shortcut hoặc offline install trên thiết bị thật. |

## 2. Bản đồ hệ thống hiện tại

1. **Ứng dụng chính:** Python trong `app.py` phục vụ trang chính, `/offline`, game/player, API và file/ROM có kiểm soát range request. SQLite vẫn là nguồn dữ liệu chính; dữ liệu runtime nằm riêng dưới `/srv/an3-arcade` hoặc `/srv/an3-arcade-staging`.
2. **Client/player:** `static/site.js`, `static/offline.js`, `static/player.js` và service worker xử lý thư viện, offline/PWA, core preload, IndexedDB và EmulatorJS trong trình duyệt. Luồng NDS touch, canvas mapping, virtual pad geometry và cho phép phím chồng lên nhau không bị thay đổi trong phiên này.
3. **Emulation:** GBA/NDS stable player hiện hữu vẫn là đường chạy chính. Core 3DS/Switch không được thay đổi hoặc kiểm thử trong phiên polish này; không được suy diễn rằng chúng đã pass từ các kiểm tra dưới đây.
4. **Rust/Redis/Docker:** Thành phần Rust gateway, Redis và Docker đang là shadow/staging-only từ các phiên trước. Chúng chưa thay thế Python/SQLite ở production và không được đặt vào đường tải ROM/core hoặc gameplay trong phiên này.
5. **Môi trường:** Production chạy tại port 8091 và staging tại port 8092. Staging dùng layout release có symlink `current`; production hiện dùng application root `/opt/an3-arcade/current`.

## 3. Thay đổi đã có trong candidate staging `cc015f4d64dd`

Các thay đổi dưới đây nhằm giảm work lặp lại, I/O SQLite và cache overhead mà không đổi phong cách UI hay core gameplay.

### Server và static delivery

- `app.py` tạo asset fingerprint bằng toàn bộ cây `static/`, gồm cả asset lồng nhau như font. Các script deploy dùng đúng cùng quy tắc, tránh browser nhận bundle stale khi một file nested thay đổi.
- HTTP handler hỗ trợ HTTP/1.1; redirect và range `416` trả `Content-Length: 0` rõ ràng.
- Query string được parse một lần; các đường dẫn public (`/static/`, `/emulatorjs/`, `/cover/`, `/screenshot/`, `/download/`, `/game-file/`, `/custom/`, `/service-worker.js`, `/health`) không còn mở SQLite session chỉ để xác định user.
- Static file đã version bằng fingerprint nhận cache header immutable một năm. File chưa version vẫn chỉ cache ngắn để không phá luồng cũ.
- SQLite `journal_mode=WAL` chỉ được thiết lập ở luồng khởi tạo thay vì lặp lại mỗi lần mở kết nối. Kết nối vẫn bật foreign keys và busy timeout.
- Query play count ở trang chủ dùng aggregate join thay cho correlated count theo từng game. Không có migration, index, xoá hoặc chỉnh sửa database.

### Browser và PWA

- `static/site.js` cache text/card/section để tìm kiếm client-side không liên tục lower-case và quét DOM không cần thiết. Filter khi gõ được gộp qua `requestAnimationFrame`.
- Poll thư viện nền chuyển từ interval cố định 15 giây sang timeout 60 giây có nhận biết tab visibility. Trạng thái search/filter, nút refresh và banner update vẫn được giữ.
- `static/player.js` dọn cả hai bootstrap timers khi player thành công, lỗi hoặc `pagehide`; việc này chặn timer tiếp tục chạy sau lỗi load core.
- Cùng file giảm fan-out IndexedDB khi đọc save slots từ nhiều transaction xuống một readonly transaction. Không thay code NDS touch bridge, mouse mapping, canvas observer hoặc toạ độ virtual controls.
- `static/offline.js` quét core inventory bằng một lần mở IndexedDB và Cache Storage cho mỗi lần render panel; không còn đọc toàn bộ body core bằng `arrayBuffer()` chỉ để hiện dung lượng.
- Service worker nâng cache namespace lên `an3-arcade-pwa-v29`, bỏ qua `/download/` và `/game-file/` để không nhân bản ROM vào Cache Storage. `ignoreSearch` chỉ dùng cho static asset cùng origin, không áp dụng cho EmulatorJS.
- Offline registration lấy fingerprint từ manifest để service worker và bundle version cùng nhau.

### Release engineering

- Thêm `deploy/backup-production-current.sh`: chỉ root chạy, không nhận argument, từ chối ghi đè backup, copy đầy đủ app hiện tại và tạo SQLite Online Backup WAL-aware, chạy `PRAGMA integrity_check`, in SHA-256.
- `deploy/update-production.sh` gọi backup helper trước khi thay release và cài helper `an3-arcade-backup-current`.
- `deploy/rollback-production.sh` cài lại rollback/backup helper nếu snapshot có chúng. Rollback này có chủ đích chỉ rollback code/static; database, ROM và save không bị động tới.
- Đồng bộ fingerprint recursive trong `deploy-stage.sh`, `deploy/update-staging.sh` và `deploy/update-production.sh`.

## 4. Kiểm thử đã hoàn tất

Đã PASS tại local, trước khi người dùng yêu cầu dừng:

```text
PYTHONPYCACHEPREFIX=/private/tmp/an3-pycache-polish python3 -m unittest discover -s tests -v
# 35 tests, PASS (0.817s)

git diff --check
python3 -m py_compile app.py
node --check static/site.js static/offline.js static/player.js static/service-worker.js
bash -n deploy-stage.sh deploy/update-staging.sh deploy/update-production.sh \
  deploy/backup-production-current.sh deploy/rollback-production.sh \
  deploy/package-staging.sh deploy/package-production.sh
```

Browser smoke test trên staging (trước khi dừng) đã xác nhận:

- Trang chính tải `site.js` và `site.css` với fingerprint `cc015f4d64dd`.
- Tìm `Pokemon Emerald` trả đúng một card; clear search và lọc NDS trả sáu card NDS.
- `/offline` có `offlineShortcut`, `coreManager` và form game offline; `offline.js`, `player.js` và manifest cùng fingerprint staging.

Đây là smoke test UI/data-binding, **không** phải xác nhận gameplay hay PWA offline end-to-end.

## 5. Staging: lịch sử deploy và trạng thái hiện tại

Lần deploy staging đầu tiên phát hiện sai lệch fingerprint:

- App mới tính hash recursive, còn helper root-owned cũ ở staging chỉ tính file static cấp một.
- Vì vậy release check mong asset `788abcfe2ad5` trong khi app xuất asset `cc015f4d64dd`.
- Deploy đầu tiên đã tự rollback về release cũ; candidate lỗi vẫn được giữ để kiểm tra, không xoá backup/release.

Sau đó chỉ helper root-owned staging được đồng bộ với quy tắc recursive (checksum sau cài: `73cfcc36b4d19fad1fb5dd9f19d33253b6d1a97e2d6238698af55922b73beafd`). Deploy lặp lại PASS:

```text
STAGING_RELEASE=PASS
STAGING_ASSET=cc015f4d64dd
STAGING_RELEASE_PATH=/opt/an3-arcade-staging/releases/20260826-173355-cc015f4d64dd
STAGING_ROLLBACK_TARGET=/opt/an3-arcade-staging/releases/20260825-093916-107d77c36767
```

Xác nhận đọc-only cuối phiên ngày 2026-08-27:

```text
an3-arcade-staging.service=active
GET http://192.168.1.8:8092/health
{"ok": true, "environment": "staging", "asset_version": "cc015f4d64dd", ...}
```

Lưu ý vận hành: service staging hiện bind `192.168.1.8:8092`, không bind loopback. Vì thế `curl http://127.0.0.1:8092/health` trên host staging sẽ bị từ chối dù service và health LAN vẫn tốt. Dùng địa chỉ LAN trên khi xác minh staging, trừ khi unit được thay đổi có chủ đích trong một phiên khác.

## 6. Production: trạng thái, backup và rollback

Xác nhận đọc-only cuối phiên:

```text
an3-arcade.service=active
GET http://127.0.0.1:8091/health
{"ok": true, "environment": "production", "asset_version": "107d77c36767", ...}
```

Production **không** chạy candidate `cc015f4d64dd`. Không có deploy, migration, thay database/ROM/save hoặc khởi động lại production nào trong phiên này.

Backup local trước khi làm việc được giữ nguyên tại:

```text
/Users/meomeo/Documents/Codex/2026-08-24/users-meomeo-documents-codex-2026-08-3/outputs/an3-arcade-backups/an3-arcade-pre-performance-polish-20260826-171333.tar.gz
SHA-256: 1abae82339d5cb5a727dd8ecdbf3bdd7fd61e1005cb5f3e3d305719610a97e51
Integrity: PASS
```

Khi và chỉ khi một phiên sau được chủ sở hữu cho phép chuẩn bị deploy lại, `backup-production-current.sh` sẽ tạo:

```text
/opt/an3-arcade-backups/YYYYMMDD-HHMMSS
/srv/an3-arcade/backups/arcade-predeploy-YYYYMMDD-HHMMSS.db
```

Helper từ chối overwrite. Backup database dùng SQLite Online Backup, kiểm tra integrity và in SHA-256. Không được xoá các backup này.

Sau một production deploy thành công có backup stamp, rollback code/static tương ứng là:

```text
sudo /usr/local/sbin/an3-arcade-rollback-production \
  /opt/an3-arcade-backups/YYYYMMDD-HHMMSS
```

Rollback yêu cầu root, validate snapshot trước khi dừng service, giữ failed release tại `/opt/an3-arcade-failed-releases/`, và để nguyên database/ROM/save. Không chạy lệnh rollback này trong phiên hiện tại.

### Cảnh báo candidate production

Trước khi dừng, package production tạm đã từng pass prepare ở `/tmp/an3-arcade-production-20260826-173353.tgz` và `/tmp/deploy-an3-production-20260826-173353.sh`. Kiểm tra cuối phiên cho thấy **cả hai hiện đã mất**. `/tmp` không phải nơi lưu artifact release bền vững. Do đó:

- Không được chạy lại command deploy cũ.
- Không được coi candidate cũ là sẵn sàng production.
- Một phiên được duyệt sau này phải package lại từ source đã review, kiểm thử lại và tạo script deploy mới trước khi owner cân nhắc production.

`update-production.sh` hiện có xoá các static bundle legacy `offline-app.*` trong lúc release; đây là hành vi hợp nhất `/offline-app` vào `/offline` đã có từ scope trước, không phải database hoặc dữ liệu người dùng. App snapshot trước deploy làm phần code/static đó có thể rollback. Khi duyệt production lại, người vận hành phải xác nhận đây vẫn là hành vi mong muốn.

## 7. Hạng mục cố ý không làm / chưa xác nhận

- Không rewrite application production sang Rust, không cut over Redis/Docker shadow và không cache ROM/core qua Redis.
- Không thêm hoặc cập nhật core giả lập 3DS/Nintendo Switch.
- Không thay player GBA/NDS stable, NDS touch bridge, virtual keyboard drag/drop, free overlap, input mapping hoặc UI design.
- Không thay database schema, không thêm index và không chạy migration.
- Không benchmark FPS, memory hoặc RUM; cải thiện ở đây là giảm work lặp lại đã được code/test, không phải con số FPS được đo trên game thật.
- Không chạy Android regression harness dù thiết bị Android đã được chủ sở hữu cho phép sử dụng.
- Không test lại shortcut/PWA install và offline end-to-end; kết quả PASS do người dùng xác nhận từ phiên trước được giữ là ngữ cảnh, không phải kết quả test mới.
- Không test gameplay GBA/NDS/3DS/Switch, hoặc toàn bộ button UI bằng thiết bị thật sau candidate này.

Các giới hạn này phải được giữ nguyên trong mọi quyết định release tiếp theo; không được suy ra "PASS" từ test tĩnh hay browser smoke test.

## 8. Hướng tiếp nhận an toàn nếu mở lại công việc

1. Đọc lại `AGENTS.md`, `.codex/invariants.md`, `.codex/session-state.md`, `docs/player-layering.md`, `docs/android-regression.md` và `tools/android/README.md` trước khi sửa player/deploy.
2. Giữ nguyên worktree dirty; không dùng `git reset --hard`, `git clean`, broad checkout hoặc lệnh xoá backup. Phân biệt các untracked change của các phiên trước với phần performance candidate.
3. Xác minh staging trước: `GET http://192.168.1.8:8092/health` phải có `asset_version=cc015f4d64dd`, rồi chạy Android regression harness riêng cho player/mobile. Nếu cần PWA offline thật, dùng secure localhost tunnel theo README thay vì kết luận từ HTTP staging thông thường.
4. Chỉ sau khi gameplay/UI/PWA được acceptance rõ ràng, package production mới từ source đã review. Không tự deploy production; owner phải chạy script production mới tạo ra và kiểm tra output `PRODUCTION_BACKUP=PASS`, đường dẫn app backup, database backup, integrity và SHA-256.
5. Nếu production deploy thất bại sau khi backup, dùng đúng backup stamp do script vừa in. Không phục hồi database trừ khi có sự cho phép migration/data-recovery riêng; code rollback mặc định cố ý không đụng database/ROM/save.

## 9. Tệp liên quan để tiếp tục

- Application: `app.py`, `static/site.js`, `static/offline.js`, `static/player.js`, `static/service-worker.js`.
- Deploy/rollback: `deploy-stage.sh`, `deploy/update-staging.sh`, `deploy/update-production.sh`, `deploy/backup-production-current.sh`, `deploy/rollback-production.sh`.
- Quy trình: `AGENTS.md`, `.codex/invariants.md`, `.codex/session-state.md`, `docs/operations.md`, `docs/android-regression.md`, `tools/android/README.md`.
- Handoff trước: `reports/handoff/10-rust-gateway-offline-pwa-staging-2026-08-24.md` và `reports/handoff/11-offline-pwa-production-2026-08-24.md`.

## 10. Tính toàn vẹn workspace

Repository có nhiều thay đổi tracked/untracked từ các phiên trước (Rust shadow, Docker, reports, fonts/assets, deploy tooling và UI work). Chúng đã tồn tại trong worktree dirty và được giữ nguyên. Không có thao tác reset, clean hay delete repository/backup nào được thực hiện trong phiên này.

Handoff này là mốc dừng: staging đang chạy candidate hiệu năng; production vẫn là `107d77c36767`; production artifact tạm đã hết hạn/mất; mọi release và test mobile tiếp theo cần được mở thành một phiên có scope/acceptance riêng.
