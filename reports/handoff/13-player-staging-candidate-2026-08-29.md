# Player staging candidate — 2026-08-29

## Kết quả phiên

- **Production:** không SSH, không restart, không chạy updater, không thay đổi
  file hay dịch vụ production. `deploy-stage.sh` chỉ tạo matching production
  candidate tại `/tmp` của **staging host** theo flow có sẵn; nó không được
  thực thi. Production package đã kiểm tra không chứa staging-only netplay
  helper.
- **Staging:** PASS tại `http://192.168.1.8:8092`, release
  `/opt/an3-arcade-staging/releases/20260829-145107-586bd9fe28a1`.
  `/health` trả `environment: staging` và asset `586bd9fe28a1`.
- **Artifact staging:** package PASS, SHA-256
  `d913a38e8a6c43b3102e6221e88de493993a54031ca2880f7221f358318b5a4e`.

## Thay đổi player đã chuẩn bị

1. Giữ nguyên thứ tự interaction: toolbar/menu, virtual pad, NDS/3DS canvas
   touch, rồi keyboard vật lý của EmulatorJS. Virtual pad vẫn pointer-transparent
   ngoài chính các nút.
2. Luồng sắp xếp virtual pad được làm rõ: `Kéo thả / Move`, kéo các nút, mở
   lại menu player, rồi `Xong / Done`. Vị trí lưu khi thả nút và khi bấm Done,
   kể cả khi pointer capture bị mất.
3. Coalesce các mutation của canvas bridge vào một animation frame, tránh query
   DOM lặp lại trong burst khởi động core.
4. Sửa đường preload 3DS Azahar: report core dùng `requiresWebgl2`; trước đây
   logic chỉ đọc `defaultWebGL2` nên yêu cầu sai binary
   `azahar-thread-legacy-wasm.data`. Bundle staging hiện có là
   `azahar-thread-wasm.data` và report/header đã được kiểm tra read-only.
5. NDS chọn `melonds_screen_layout=Left/Right` và 3DS Azahar chọn
   `citra_layout_option=side_by_side` khi bắt đầu trên màn hình ngang
   (portrait giữ Top/Bottom/default). Xoay sau khi game đang chạy chỉ hiện
   thông báo restart để không đổi core geometry giữa frame.
6. Nút TV tự theo dõi **availability** receiver cùng mạng qua Remote Playback
   API, nhưng không liệt kê tên hay tự chọn TV: browser luôn mở picker/permission
   để người dùng chọn receiver. Khi receiver đã kết nối, game surface local ẩn
   nhưng tiếp tục render vào remote stream; toolbar, keyboard, touch hit-area
   và virtual pad giữ local để máy tính/điện thoại thành console controller.
   Virtual pad được hiện tạm thời mà không ghi đè setting Touch đã lưu.
7. Thêm cấu hình netplay staging-only (`AN3_NETPLAY_ORIGIN`) cho native
   EmulatorJS Netplay. Origin phải là HTTP(S) origin sạch, chỉ được chấp nhận ở
   staging/development; production luôn tắt và CSP không mở thêm origin.
   Đã thêm Docker staging-only cho Rust EmulatorJS-netplay relay ở
   `Dockerfile.rust-netplay` và `compose.rust-netplay.staging.yml`, pin upstream
   commit và không mount dữ liệu AN3. Không tuyên bố cable link cho core không
   hỗ trợ network emulation, đặc biệt Azahar WebAssembly hiện tại.

## Netplay Rust — staging-only đã bật

- Relay official EmulatorJS Netplay Rust commit
  `4090ca7bda795a8b7a7596f4d41a4605b515d9c5` build thành công, chạy healthy
  non-root/read-only và không có volume/mount dữ liệu AN3.
- Relay chỉ publish `192.168.1.8:8094`; UFW chỉ cho
  `192.168.1.0/24 → 192.168.1.8:8094`. Probe từ một peer LAN trả `200 {}`.
- Staging có `AN3_NETPLAY_ORIGIN=http://192.168.1.8:8094`; `/offline` CSP
  chứa origin này. Production reject cấu hình đó và packaging loại helper
  kích hoạt relay.
- Browser cùng LAN cần mở **cùng game** để native EmulatorJS host/join room
  flow dùng stable game/system ID. NDS LAN vẫn phụ thuộc melonDS/độ trễ thấp;
  không quảng cáo 3DS cable/link vì Azahar WASM chưa có network path được xác
  nhận.

## Kiểm tra đã chạy

```text
PYTHONPYCACHEPREFIX=/private/tmp/an3-pycache-player-rust \
  python3 -m unittest discover -s tests -v
# 37 tests PASS

node --check static/player.js static/offline.js static/site.js static/service-worker.js
python3 -m py_compile app.py
git diff --check
bash -n deploy-stage.sh deploy/package-staging.sh deploy/package-production.sh \
  deploy/enable-staging-netplay.sh
# 37/37 PASS; syntax/package/Compose PASS

GET staging /health                     # PASS
GET staging /offline CSP netplay origin # PASS
GET LAN staging :8094/games             # 200 {}
container netplay                       # healthy
production netplay packaging exclusion  # PASS
```

`cargo`/`rustc` không có trên máy cục bộ này, nên build thực hiện trên staging
Docker và đã PASS từ upstream commit pin. Không có thay đổi nào vào source Rust
gateway đang shadow; relay mới dùng upstream Rust thay vì thay thế Python
application.

## Acceptance còn lại

Thực hiện trên staging với ROM được cấp phép và thiết bị/browser thật: GBA,
NDS portrait + landscape, chỉnh Move/Done và touch bridge, 3DS có WebGL2/SAB,
hai peer LAN host/join cùng ROM, và TV receiver. Không kết luận FPS/gameplay
thực tế hoặc 3DS link support trước khi các test đó hoàn thành; chỉ sau
acceptance mới cân nhắc một phiên production riêng.

**Trạng thái hiện tại:** staging chưa có ROM 3DS hợp lệ/thiết bị receiver TV
trong phiên này, nên core 3DS và TV console mode mới được smoke-test qua asset,
capability/config, health và relay — chưa phải gameplay/cast acceptance.

Tài liệu cập nhật: `docs/player-layering.md`, `docs/netplay-staging.md`.
