# Ăn 3 Tô Cơm

Web game riêng cho `an3tocom.space`, chạy backend nhẹ trên TV Box và render game bằng WebAssembly/canvas trên trình duyệt máy khách.

## Chức năng

- Thư viện song ngữ Việt/Anh, tìm kiếm nhanh, trang riêng cho từng game.
- Tài khoản dùng tên đăng nhập cố định và nickname hiển thị có thể đổi; mật khẩu tối thiểu 10 ký tự, hash mới dùng scrypt với salt riêng. PBKDF2 chỉ còn để đọc hash cũ và làm fallback trên Python không có scrypt.
- Mọi người có thể chơi hoặc tải tất cả game, gồm Draft, Testing và Release, không cần đăng nhập; đánh giá, bình luận, báo lỗi và yêu thích yêu cầu đăng nhập.
- Mỗi tài khoản đánh giá 1-5 sao một lần cho mỗi game và có thể cập nhật lại; danh sách yêu thích nằm ở trang tài khoản.
- Chỉ tài khoản quản trị đã đăng nhập được thấy Dashboard, upload ROM/cover, sửa mô tả, xóa game lỗi và thay đổi trạng thái Draft/Testing/Release.
- Dashboard cho phép tạo thêm quản trị viên, đổi nickname hiển thị, xử lý báo lỗi, chỉnh liên hệ maintainer và xem tổng lượt truy cập, khách riêng biệt, người chơi, game được mở nhiều cùng biểu đồ 14 ngày.
- Upload mặc định tự nhận diện hệ máy theo định dạng/tên file; file ZIP được đọc danh sách nội dung để chọn core hoặc nhận game HTML5. ROM lớn tự chuyển sang upload chia nhỏ 8 MB để tránh giới hạn request của proxy.
- Trang chủ tự chia game thành từng khu vực GBA, NDS, 3DS… và có bộ lọc theo hệ máy. Các bản GBA Release không Testing được ưu tiên trong mục Recommended.
- Bình luận và báo lỗi yêu cầu đăng nhập; quản trị viên có thể xóa bình luận và đóng báo lỗi.
- Player có tiến độ tải ROM, fullscreen, tải/nạp save state và TVPad kéo thả cho GB/GBA/NDS.
- Mỗi game có năm save slot cục bộ trên thiết bị, screenshot và lịch sử cập nhật do quản trị viên ghi.
- Chỉnh vị trí, kích thước, độ mờ hoặc ẩn phím ảo không reload game; layout được lưu theo hệ máy và hướng màn hình.
- NDS dùng nút riêng A/B/X/Y/L/R/Start/Select, không che màn hình cảm ứng và cho phép kéo thả như các hệ máy cầm tay khác. Canvas NDS được giám sát liên tục để gỡ lớp chặn pointer và có cầu nối touch-to-mouse cho trình duyệt điện thoại.
- NDS dùng core `melonds` với `EJS_startOnLoaded=true`; không dùng DeSmuME, nút **Vào game** hoặc flow start thủ công. Touch bridge theo dõi canvas, gỡ lớp chặn pointer và chuyển touch thành mouse events cho màn hình DS. Với ZIP NDS, luồng Chơi giữ ZIP gốc để melonDS xử lý phía trình duyệt; nút Tải xuống vẫn giữ nguyên archive gốc.
- Core offline được ghi và xác minh trong IndexedDB `EmulatorJS-core`/store `core` theo contract của EmulatorJS, đồng thời dùng cache bền vững `an3-arcade-cores-v1`, không bị xóa khi nâng phiên bản app shell. Trang Kho ngoại tuyến đọc/xóa cả IndexedDB và Cache Storage; marker hiện tại là `an3-offline-core-v7`.
- Thư viện tự kiểm tra game/đánh giá mới mỗi 15 giây và tài nguyên CSS/JS tự đổi phiên bản khi cập nhật, không cần xóa cache trình duyệt.
- PWA cho phép cài Ăn 3 Tô Cơm, chuyển nhanh giữa Online/Offline, đưa ROM vào kho offline riêng trên trình duyệt và chơi không cần kết nối; kho này không đồng bộ tài khoản, thư viện chung, đánh giá hay bình luận.
- PWA shell v17 cache giao diện ngay khi cài đặt. Nút tải trước core đọc report trước, chọn đúng binary theo report/capability, rồi lưu và xác minh runtime, extractor và core binary qua proxy cùng nguồn; chỉ báo sẵn sàng sau khi IndexedDB EmulatorJS và cache đã được kiểm tra.
- Trang Offline có nút tải và verify core theo từng hệ máy, nhận diện ROM/ZIP cục bộ, tự chia kho ROM theo hệ máy và giữ nguyên menu player, save slot, fullscreen, save/import state và phím ảo.
- Tài nguyên EmulatorJS đi qua proxy/cache cùng origin `/emulatorjs/<channel>/data/...`; TVBox chỉ tải một lần từ CDN, còn trình duyệt không phụ thuộc trực tiếp vào CDN có thể bị ad-blocker hoặc chính sách cross-origin chặn.
- Lần truy cập đầu tiên có hướng dẫn tự đóng sau 5 giây; nút hướng dẫn trên trang chủ luôn có thể mở lại. Khi mở menu của player, chú giải nút điều khiển hiển thị mờ trong 3 giây.
- 3DS dùng core Azahar trên kênh EmulatorJS `latest` và được gắn nhãn thử nghiệm.
- Game tự làm hỗ trợ `.zip` có `index.html` hoặc một file `.html`, chạy trong iframe sandbox.
- ROM lớn được stream và hỗ trợ HTTP Range; backend không render game.

Trên HTTP LAN, trình duyệt vẫn lưu core vào IndexedDB nhưng không có Service Worker/Cache Storage bền vững; trải nghiệm đóng/mở hoàn toàn offline yêu cầu HTTPS/PWA.

## Thư mục trên TV Box

- Ứng dụng: `/opt/an3-arcade`
- Dữ liệu/SQLite/ROM/cover: `/srv/an3-arcade`
- Cấu hình bí mật: `/etc/an3-arcade.env`
- Dịch vụ: `an3-arcade.service`
- Cổng LAN: `8091`
- URL LAN: `http://192.168.1.11:8091`

## Biến môi trường

```text
AN3_APP_DIR=/opt/an3-arcade
AN3_DATA_DIR=/srv/an3-arcade
AN3_PORT=8091
AN3_BASE_URL=http://192.168.1.11:8091
AN3_ADMIN_NAME=admin
AN3_ADMIN_PASSWORD=<mật khẩu mạnh>
AN3_COOKIE_SECURE=0
```

Khi chạy qua HTTPS trên tên miền, đổi `AN3_BASE_URL=https://an3tocom.space` và `AN3_COOKIE_SECURE=1`.

## Bảo mật

- Cài đặt mặc định dùng cookie `HttpOnly`, `SameSite=Lax`, `Secure` khi chạy HTTPS, token CSRF và session có hạn.
- Tài khoản chỉ dùng tên đăng nhập, mật khẩu và nickname hiển thị. API đăng ký, đăng nhập, đánh giá, yêu thích và upload đều có giới hạn tốc độ; upload có giới hạn kích thước, phiên upload hết hạn sau 24 giờ và kiểm tra tên/đường dẫn.
- Bình luận/báo lỗi có honeypot, chống lặp, khoảng nghỉ bắt buộc, quota theo tài khoản/IP và lọc mẫu spam cơ bản.
- HTTP header gồm CSP, HSTS khi HTTPS, `nosniff`, Referrer Policy, Permissions Policy, COOP/CORP và chặn nhúng trang từ origin khác.
- Chỉ admin mới có endpoint upload, quản lý tài khoản và cấu hình liên hệ. Không chia sẻ mật khẩu router, SSH hoặc admin trong bình luận hay ticket.
- Trên Cloudflare, bật WAF Managed Rules, Bot Fight Mode và giới hạn tốc độ cho `/api/login`, `/api/register`, `/admin/api/*`; sao lưu định kỳ `/srv/an3-arcade` trước khi nâng cấp.

## Quy trình staging

Mỗi lần cập nhật, triển khai và thử trước tại `http://192.168.1.11:8092`. Staging dùng ứng dụng, SQLite, ROM và cookie riêng, không đụng vào production. Unit là `an3-arcade-staging.service`; script `deploy-stage.sh` phát hành source sang release tách thư mục, health-check rồi tự quay về release staging trước nếu khởi động thất bại.

Tệp `/etc/an3-arcade-staging.env` cần dùng `AN3_APP_DIR=/opt/an3-arcade-staging/current`, `AN3_DATA_DIR=/srv/an3-arcade-staging`, `AN3_PORT=8092`, `AN3_ENVIRONMENT=staging`, `AN3_COOKIE_SECURE=0` và một `AN3_AUTH_PEPPER` ngẫu nhiên. Chỉ deploy production sau khi staging test đạt.

## Kích hoạt tên miền

`an3tocom.space` đang hoạt động qua Cloudflare Tunnel tới `http://127.0.0.1:8091`; không phụ thuộc IP WAN và không cần DMZ/port forward. Production phải giữ cookie secure.

Mẫu ingress nằm tại `deploy/cloudflared-config.yml.example`. Sau khi tunnel hoạt động, đổi `AN3_BASE_URL` thành `https://an3tocom.space`, đặt `AN3_COOKIE_SECURE=1` và restart `an3-arcade.service`. ROM lớn nên được upload từ Dashboard qua URL LAN để tránh giới hạn kích thước request của proxy công cộng.

## Nguồn công cụ

Footer của website ghi và liên kết tới EmulatorJS, RetroArch, mGBA, melonDS, Azahar, Python và SQLite. Quản trị viên chỉ nên upload các game/ROM mà mình có quyền phân phối.
