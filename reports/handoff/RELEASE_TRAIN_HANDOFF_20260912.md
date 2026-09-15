# VibeCodedEmulator — Release Train Handoff

**Ngày:** 2026-09-12 (Asia/Ho_Chi_Minh)  
**Run:** `2026-09-08-multimodel-release-train`  
**Trạng thái tổng thể:** `COMPLETE_WITH_KNOWN_LIMITATIONS`  
**Môi trường:** chỉ **staging** — production không được truy cập, đóng gói, cập nhật hay khởi động lại.

## Cập nhật authoritative — 2026-09-12

Phần này thay thế các nhận định cũ trong tài liệu về APK/DMG, Linux blocked, audio “unverified”, artifact manifest và asset staging. Các phần lịch sử bên dưới được giữ lại để truy vết, không phải trạng thái hiện tại.

- Đã publish staging asset `df14d4aa2d9a` tại `/opt/an3-arcade-staging/releases/20260912-164924-df14d4aa2d9a`; rollback target vẫn là `/opt/an3-arcade-staging/releases/20260911-230833-bef86865b122`.
- Release Center hiện công bố bốn installer native đã kiểm chứng. Manifest staging và HTTP stream download đối chiếu đúng size/SHA-256 với local cho toàn bộ bốn artifact. Windows EXE vẫn `blocked`, không có URL.
- OWNER-VERIFIED (quan sát owner, không phải automated evidence): GBA/NDS trên DMG macOS hiện tại chạy mượt; GBA/NDS trên APK Android hiện tại chạy mượt; âm thanh thực sự nghe được trên cả hai đều mượt. Điều này thay thế trạng thái cũ “audibility unverified”.
- Android 3DS đã có portable Azahar/libretro Vulkan hardware path: legal homebrew boot, hình ảnh tiến triển, input, layout persist, Vulkan presentation và save state đều hoạt động. Tuy vậy các homebrew đã thử không có qualifying audio samples, do đó Android 3DS vẫn không quảng cáo/không accepted.
- Debian authorized builder đã build và smoke native `.deb`/Flatpak: GBA chạy Vulkan, NDS chạy desktop OpenGL fallback, SDL audio được khởi tạo. Không có browser-only package.
- HTTP staging là insecure context nên `navigator.gpu` không có; `requested=webgpu` đúng khi fallback `effective=webgl2` tại `requestAdapter`. Khi adapter/device thật sự thành công, contract vẫn bắt buộc `effective=webgpu`.

| Artifact | Size | SHA-256 | HTTP staging |
| --- | ---: | --- | --- |
| macOS DMG | 42,282,073 | `762f1e8122c0b3455ed4a43509c001eb9a12adb252a398b5310c4ac9f8cb90f3` | PASS |
| Android APK | 87,703,074 | `128780ed3f21cbf2ac4b158fcd02fc60bd97e92c9b9ded90918f52ad7a3faa24` | PASS |
| Linux DEB | 1,812,216 | `7b8672db446a73c8dcf78220b77feb1501d9a0ae6958623fa74ba9319a3a7b49` | PASS |
| Linux Flatpak | 1,805,368 | `65f72ed64935cd958d1e977dcbbb3a2e3ecad5e29d8c6746be76c9916a525a50` | PASS |

Verification completed: 119 explicit Python tests PASS; 30 Release Center/package tests PASS; package syntax, four local SHA sidecars, staging archive contents, staging health, and HTTP byte/hash parity PASS. The Android AVD still needs shutdown after final local test completion.

## Tóm tắt bàn giao

P5 Android native đã hoàn thành với giới hạn được ghi nhận rõ ràng. Kiến trúc native dùng portable libretro host chung cho GBA/NDS; Android là adapter mỏng với `SurfaceView`/ANativeWindow, Vulkan ưu tiên và GLES3 fallback rõ ràng. Hợp đồng renderer và Core Options ABI đã được đưa vào `native-offline/native-runtime/core/` để macOS/Android dùng chung, thay vì sao chép triển khai theo từng nền tảng.

Menu native macOS đã được làm gọn nhưng giữ nguyên chín mục và toàn bộ chức năng. Android tuân theo cùng mô hình menu, draft Save Settings, 10 Quick Save slots, Auto Save độc lập, import/export state và layout/input NDS. Android 3DS bị chặn có chủ ý và không được quảng cáo, vì chưa có native support đủ bằng chứng.

## Trạng thái theo nền tảng

| Nền tảng | Trạng thái | Bằng chứng hiện tại |
| --- | --- | --- |
| Web | PARTIAL | Staging đang chạy asset `bef86865b122`; contract WebGPU ưu tiên → WebGL2 fallback, touch NDS và renderer suite đã qua. Chưa reaccept toàn bộ browser gameplay matrix mới trong lượt này. |
| macOS DMG | PARTIAL | GBA/NDS chạy 59–60 FPS qua Vulkan → MoltenVK → Metal. Menu chín mục, draft discard bằng Escape, slots và Auto Save controls đã được quan sát. Chưa có fresh 3DS long-run và chưa xác nhận nghe được âm thanh. |
| Android APK | PARTIAL | Native NDS chạy Vulkan và explicit GLES3; portrait/landscape, Top/Bottom, Side-by-Side, tap/drag/release, draft cancel/save, slots 1/10, Auto Save, import/export và restart persistence đều đã test trên ARM64 AVD. Chưa xác nhận nghe được âm thanh; Android 3DS intentionally unavailable. |
| Linux DEB | BLOCKED | Debian builder từ chối tạo browser-only package; portable desktop surface/audio/OpenGL adapter và package integration chưa có. |
| Linux Flatpak | BLOCKED | Cùng native-host blocker; không có DEB verified để đóng gói Flatpak. |
| Windows EXE | BLOCKED | PowerShell build path deterministic đã có, nhưng thiếu Windows Vulkan build/signing/runtime host thực; không có `.exe` và không publish. |

## Artifact staging đã publish

Staging asset: `bef86865b122`  
Release path: `/opt/an3-arcade-staging/releases/20260911-230833-bef86865b122`  
Rollback target: `/opt/an3-arcade-staging/releases/20260909-195906-8ecb7b06ad8c`

| Artifact | Local path | Size | SHA-256 |
| --- | --- | ---: | --- |
| macOS DMG | `native-offline/releases/vibecodedemulator-0.4.4-macos-aarch64.dmg` | 42,976,820 | `b63b3e61708c532c899b1a8e7283af5d200c648a9465deef1f3d54f1d5fb2870` |
| Android APK | `native-offline/releases/vibecodedemulator-0.4.4-android-arm64-staging.apk` | 74,229,651 | `cd98c834d5730f532b6e68a373072231c2519780822db9c6c30ff65e00086ff6` |

Health endpoint, Release Center manifest và HTTP downloads đã được đối chiếu: kích thước và SHA-256 staging khớp chính xác artifact local cho cả DMG và APK. Linux/Windows hiện `blocked` và không có download URL.

## Kiểm thử đã hoàn thành

- `tools/release-train.sh --staging verify all`: 110 Python tests PASS, NDS touch behavior PASS, 11 web renderer cases PASS, native JavaScript syntax PASS.
- `git diff --check`: PASS.
- macOS: DMG `codesign --verify` và `hdiutil verify` PASS; GBA/NDS fresh runtime quan sát được.
- Android: APK exact hash, signature v2 debug staging, NDS runtime matrix Vulkan/GLES3 và persistence/state/layout/input hoàn thành như bảng trên.
- Linux: native build entrypoint cho DEB và Flatpak đều exit 3 đúng chủ đích thay vì tạo package browser-only.
- Windows: canonical entrypoint báo BLOCKED trên host không phải Windows; không tuyên bố artifact không tồn tại.

## Giới hạn cần giữ nguyên

1. Không coi PCM/AAudio counters là bằng chứng audio nghe được. macOS và Android vẫn chưa đạt audio-PASS.
2. Không quảng cáo Android 3DS cho đến khi native core/render path thật sự được hỗ trợ và runtime-test.
3. Không đổi Linux thành browser renderer để “pass” build; cần native desktop adapter dùng chung trước.
4. Không tạo hoặc publish Windows `.exe` nếu chưa có Windows builder/runtime thật.
5. Native và web giữ hai renderer family tách biệt: native dùng Vulkan → native OpenGL fallback; web dùng WebGPU → WebGL2 fallback.

## Việc tiếp theo đề xuất

1. Trên Debian builder, triển khai portable native desktop surface/audio/OpenGL adapter dùng chung rồi mới build/verify `.deb` và Flatpak.
2. Trên máy Windows thật, chạy `native-offline/scripts/build-windows-staging.ps1`, ký/kiểm tra `.exe`, runtime-test Vulkan và OpenGL fallback, sau đó mới thêm manifest/download entry.
3. Thực hiện fresh macOS 3DS long-run và speaker audibility; thực hiện Android speaker audibility trên môi trường có thể nghe được.
4. Khi có artifact mới đã verify, cập nhật Release Center qua staging-only deploy và đối chiếu HTTP size/SHA-256 trước khi ghi PASS.

## Vệ sinh và working tree

AVD, test app, browser test tab và temporary Linux builder payload đã được đóng/xóa. Staging service cần thiết vẫn chạy. Working tree vẫn intentionally dirty (`17` modified, `102` untracked ở lần kiểm tra cuối); không có reset, clean hay revert diện rộng nào được thực hiện.

## Tài liệu liên quan

- `reports/handoff/RELEASE_TRAIN_STATE.md`
- `reports/handoff/SYSTEM_INSPECTION_HANDOFF.md`
- `reports/handoff/RELEASE_TRAIN_P5_NATIVE_MIGRATION_20260910.md`
- `docs/REGRESSION_GUARDS.md`
