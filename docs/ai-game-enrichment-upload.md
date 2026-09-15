# Quy trình AI cập nhật thông tin game bằng proposal

Tài liệu này hướng dẫn tạo một script Python để đưa nội dung do AI chuẩn bị vào **luồng đề xuất chờ duyệt** của AN3 Arcade.

Mục tiêu là tạo/cập nhật metadata và media cho game hiện có mà không đụng tới ROM. Script chỉ tạo proposal `pending`; admin phải tự xem và nhấn **Duyệt** trong Dashboard để thông tin xuất hiện trên trang công khai.

## Luồng xử lý

1. AI đọc tên file ROM và xác định đúng tựa game/phiên bản.
2. AI nghiên cứu nguồn đáng tin cậy, sau đó chuẩn bị:
   - tên tiếng Việt và tiếng Anh;
   - mô tả;
   - URL walkthrough;
   - URL nguồn tham khảo;
   - một cover;
   - tối thiểu ba screenshots.
3. AI lưu dữ liệu và ảnh vào thư mục cục bộ.
4. Script Python đăng nhập bằng tài khoản admin, lấy CSRF token, tạo proposal và upload ảnh.
5. Dashboard hiển thị bản xem trước. Admin kiểm tra và nhấn **Duyệt** hoặc **Từ chối**.

## Điều kiện duyệt

Proposal chỉ đủ điều kiện duyệt khi có:

- 1 cover;
- ít nhất 3 screenshots;
- walkthrough URL;
- tiêu đề và mô tả.

Khi duyệt, hệ thống thay tên, mô tả, cover và thêm screenshots vào game công khai. ROM/game file không bị thay đổi hay xóa.

## Cấu trúc thư mục đề nghị

```text
ai-content/
  pmd-eos/
    proposal.json
    cover.webp
    screen-1.webp
    screen-2.webp
    screen-3.webp
tools/
  upload_ai_proposals.py
```

Mỗi thư mục con bên trong `ai-content/` tương ứng một game.

## File `proposal.json`

`game_id` là ID nội bộ của game trên Dashboard/API, không phải slug. Có thể tìm ID trong URL trang sửa game hoặc danh sách game admin.

```json
{
  "game_id": 12,
  "title_vi": "Pokémon Mystery Dungeon: Explorers of Sky",
  "title_en": "Pokémon Mystery Dungeon: Explorers of Sky",
  "description_vi": "Mô tả game bằng tiếng Việt.",
  "description_en": "Game description in English.",
  "walkthrough_url": "https://example.org/walkthrough",
  "sources": [
    "https://en.wikipedia.org/wiki/Pok%C3%A9mon_Mystery_Dungeon:_Explorers_of_Sky"
  ],
  "cover": "cover.webp",
  "screenshots": [
    "screen-1.webp",
    "screen-2.webp",
    "screen-3.webp"
  ]
}
```

Ảnh đề xuất phải là PNG, JPEG hoặc WebP. Đừng dùng thumbnail YouTube thay cho cover hoặc screenshot.

## Script `tools/upload_ai_proposals.py`

Script dưới đây dùng thư viện `requests`. Nó không gọi endpoint duyệt proposal.

```python
#!/usr/bin/env python3
import json
import os
from pathlib import Path
from urllib.parse import quote

import requests


BASE_URL = os.environ["AN3_BASE_URL"].rstrip("/")
ADMIN_NAME = os.environ["AN3_ADMIN_NAME"]
ADMIN_PASSWORD = os.environ["AN3_ADMIN_PASSWORD"]
CONTENT_ROOT = Path("ai-content")

session = requests.Session()


def require_ok(response):
    if response.ok:
        return
    try:
        detail = response.json()
    except ValueError:
        detail = response.text
    raise RuntimeError(f"HTTP {response.status_code}: {detail}")


def login_and_get_csrf():
    response = session.post(
        f"{BASE_URL}/api/login",
        json={"name": ADMIN_NAME, "password": ADMIN_PASSWORD, "next": "/admin"},
        timeout=30,
    )
    require_ok(response)

    admin = session.get(f"{BASE_URL}/admin", timeout=30)
    require_ok(admin)
    marker = 'name="csrf-token" content="'
    start = admin.text.find(marker)
    if start < 0:
        raise RuntimeError("Không lấy được CSRF token từ Dashboard.")
    start += len(marker)
    end = admin.text.find('"', start)
    return admin.text[start:end]


def post_json(path, payload, csrf):
    response = session.post(
        f"{BASE_URL}{path}",
        json=payload,
        headers={"X-CSRF-Token": csrf},
        timeout=60,
    )
    require_ok(response)
    return response.json()


def upload(path, file_path, csrf):
    file_path = Path(file_path)
    if not file_path.is_file():
        raise FileNotFoundError(file_path)
    response = session.post(
        f"{BASE_URL}{path}?name={quote(file_path.name)}",
        data=file_path.read_bytes(),
        headers={
            "X-CSRF-Token": csrf,
            "Content-Type": "application/octet-stream",
        },
        timeout=120,
    )
    require_ok(response)
    return response.json()


def upload_proposal(folder, csrf):
    data = json.loads((folder / "proposal.json").read_text(encoding="utf-8"))
    screenshots = data["screenshots"]
    if len(screenshots) < 3:
        raise RuntimeError(f"{folder}: phải có ít nhất 3 screenshots")

    proposal = post_json(
        f"/admin/api/games/{data['game_id']}/enrichment-proposal",
        {
            "title_vi": data["title_vi"],
            "title_en": data.get("title_en", data["title_vi"]),
            "description_vi": data["description_vi"],
            "description_en": data.get("description_en", data["description_vi"]),
            "walkthrough_url": data["walkthrough_url"],
            "sources": data.get("sources", []),
        },
        csrf,
    )

    proposal_id = proposal["id"]
    upload(f"/admin/api/enrichment-proposals/{proposal_id}/cover", folder / data["cover"], csrf)
    for screenshot in screenshots:
        upload(
            f"/admin/api/enrichment-proposals/{proposal_id}/screenshot",
            folder / screenshot,
            csrf,
        )
    print(f"Pending proposal created: game={data['game_id']} proposal={proposal_id}")


def main():
    csrf = login_and_get_csrf()
    for folder in sorted(CONTENT_ROOT.iterdir()):
        if folder.is_dir() and (folder / "proposal.json").is_file():
            upload_proposal(folder, csrf)


if __name__ == "__main__":
    main()
```

## Cài đặt và chạy

```bash
python3 -m pip install requests

export AN3_BASE_URL="https://an3tocom.space"
export AN3_ADMIN_NAME="ten-admin"
export AN3_ADMIN_PASSWORD="mat-khau-admin"

python3 tools/upload_ai_proposals.py
```

Không ghi mật khẩu vào `proposal.json`, source code, Git hoặc log terminal. Dùng biến môi trường, password manager, hoặc cách nạp secret phù hợp với máy vận hành.

## API được sử dụng

```text
POST /api/login
GET  /admin
POST /admin/api/games/{game_id}/enrichment-proposal
POST /admin/api/enrichment-proposals/{proposal_id}/cover
POST /admin/api/enrichment-proposals/{proposal_id}/screenshot
```

Nút **Duyệt** trong Dashboard mới gọi endpoint duyệt. Không thêm endpoint này vào script upload nếu bạn muốn duy trì bước review thủ công.

## Quy trình vận hành nhanh

1. Chuẩn bị 5–10 thư mục game mỗi đợt.
2. Kiểm tra mỗi `proposal.json` có walkthrough, cover và ít nhất 3 screenshots.
3. Chạy script một lần để tạo các proposal `pending`.
4. Vào Dashboard → **Đề xuất AI chờ duyệt**.
5. Kiểm tra tên đúng phiên bản ROM, ảnh không nhầm game, nguồn và walkthrough hợp lệ.
6. Nhấn **Duyệt** cho proposal đạt yêu cầu; nhấn **Từ chối** cho proposal sai/thiếu.

