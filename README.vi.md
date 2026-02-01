# Camera Live Stream lên YouTube

Hệ thống tự động stream camera RTSP lên YouTube Live với tính năng xoay vòng stream.

## Tính năng

- **Tự động tạo YouTube Live**: Tạo livestream mới qua YouTube Data API v3
- **Xoay vòng Stream**: Tự động tạo stream mới sau mỗi N giờ (mặc định: 10 giờ)
- **Không chuyển mã**: Sử dụng FFmpeg stream copy, tiết kiệm CPU
- **Xác thực OAuth2**: Bảo mật bằng token
- **Tự phục hồi**: Tự động khởi động lại khi gặp lỗi
- **Chạy bằng Docker**: Chỉ cần một lệnh `docker compose up -d`

## Yêu cầu

1. Docker và Docker Compose đã cài đặt
2. Camera RTSP có thể truy cập từ máy chủ
3. Tài khoản Google Cloud với YouTube Data API v3 đã bật
4. Thông tin xác thực OAuth 2.0

---

## Hướng dẫn cài đặt

### Bước 1: Tạo OAuth Credentials trên Google Cloud

1. Truy cập [Google Cloud Console](https://console.cloud.google.com)

2. **Tạo Project mới** (hoặc chọn project có sẵn):
   - Click "Select a project" → "New Project"
   - Đặt tên project và nhấn "Create"

3. **Bật YouTube Data API v3**:
   - Vào menu ☰ → "APIs & Services" → "Library"
   - Tìm kiếm "YouTube Data API v3"
   - Click vào kết quả và nhấn "Enable"

4. **Cấu hình OAuth Consent Screen**:
   - Vào "APIs & Services" → "OAuth consent screen"
   - Chọn "External" và nhấn "Create"
   - Điền các thông tin bắt buộc:
     - App name: `Camera Live`
     - User support email: email của bạn
     - Developer contact: email của bạn
   - Nhấn "Save and Continue"
   - Ở phần **Scopes**, nhấn "Add or Remove Scopes"
   - Tìm và thêm: `https://www.googleapis.com/auth/youtube`
   - Nhấn "Save and Continue"
   - Ở phần **Test users**, nhấn "Add Users"
   - **Thêm email Google của bạn** (quan trọng!)
   - Nhấn "Save and Continue"

5. **Tạo OAuth Client ID**:
   - Vào "APIs & Services" → "Credentials"
   - Click "+ Create Credentials" → "OAuth client ID"
   - Application type: chọn **Desktop app**
   - Name: `Camera Live Desktop`
   - Click "Create"
   - **Lưu lại Client ID và Client Secret**

### Bước 2: Cấu hình file .env

```bash
cd camera-live
cp .env.example .env
```

Mở file `.env` và chỉnh sửa:

```env
# URL camera RTSP của bạn
RTSP_URL=rtsp://admin:matkhau@192.168.1.100:554/cam/realmonitor?channel=1&subtype=0

# Thông tin OAuth từ Google Cloud Console
YOUTUBE_CLIENT_ID=your_client_id_here
YOUTUBE_CLIENT_SECRET=your_client_secret_here

# Thời lượng mỗi stream (giờ)
STREAM_DURATION_HOURS=10

# Mẫu tiêu đề stream
STREAM_TITLE_TEMPLATE=Camera Live - {datetime}

# Mô tả stream
STREAM_DESCRIPTION=Camera giám sát 24/7

# Chế độ riêng tư: public, unlisted, hoặc private
PRIVACY_STATUS=public

# Múi giờ
TIMEZONE=Asia/Ho_Chi_Minh
```

### Bước 3: Lấy OAuth Token

> ⚠️ **QUAN TRỌNG**: Bước này phải chạy **trực tiếp trên máy tính có trình duyệt**, KHÔNG chạy trong Docker!

```bash
# 1. Tạo virtual environment (chỉ cần làm 1 lần)
python3 -m venv .venv

# 2. Kích hoạt virtual environment
source .venv/bin/activate

# 3. Cài đặt thư viện cần thiết
pip install requests

# 4. Chạy OAuth setup
python src/oauth_setup.py \
  --client-id "YOUR_CLIENT_ID" \
  --client-secret "YOUR_CLIENT_SECRET"
```

**Hoặc** nếu đã cấu hình trong `.env`:

```bash
source .venv/bin/activate
python src/oauth_setup.py \
  --client-id "$(grep YOUTUBE_CLIENT_ID .env | cut -d= -f2)" \
  --client-secret "$(grep YOUTUBE_CLIENT_SECRET .env | cut -d= -f2)"
```

**Quy trình xác thực:**

1. Script sẽ tự động **mở trình duyệt**
2. **Đăng nhập** bằng tài khoản Google đã thêm vào Test Users
3. **Cấp quyền** cho ứng dụng
4. Tab sẽ hiển thị "Xác thực thành công!"
5. Token được lưu tự động vào `data/token.json`

### Bước 4: Build Docker Image

```bash
docker compose build
```

### Bước 5: Chạy hệ thống

```bash
docker compose up -d
```

**Xong!** Hệ thống sẽ:

1. ✅ Tạo một livestream mới trên YouTube
2. ✅ Bắt đầu stream từ camera RTSP
3. ✅ Tự động xoay sang stream mới sau 10 giờ
4. ✅ Tiếp tục vĩnh viễn cho đến khi bạn dừng

---

## Các lệnh thường dùng

```bash
# Khởi động (chạy nền)
docker compose up -d

# Xem logs theo thời gian thực
docker compose logs -f

# Xem logs 100 dòng gần nhất
docker compose logs --tail=100

# Dừng hệ thống
docker compose down

# Khởi động lại
docker compose restart

# Build lại image (sau khi sửa code)
docker compose build --no-cache
docker compose up -d

# Kiểm tra trạng thái container
docker compose ps
```

---

## Cấu hình chi tiết

### Các biến môi trường

| Biến                    | Mô tả                       | Mặc định                 |
| ----------------------- | --------------------------- | ------------------------ |
| `RTSP_URL`              | URL camera RTSP             | Bắt buộc                 |
| `YOUTUBE_CLIENT_ID`     | OAuth Client ID             | Bắt buộc                 |
| `YOUTUBE_CLIENT_SECRET` | OAuth Client Secret         | Bắt buộc                 |
| `YOUTUBE_REFRESH_TOKEN` | OAuth Refresh Token         | Từ token.json            |
| `STREAM_DURATION_HOURS` | Thời lượng mỗi stream (giờ) | 10                       |
| `STREAM_TITLE_TEMPLATE` | Mẫu tiêu đề                 | Camera Live - {datetime} |
| `STREAM_DESCRIPTION`    | Mô tả stream                | 24/7 Camera Livestream   |
| `PRIVACY_STATUS`        | Chế độ riêng tư             | public                   |
| `TIMEZONE`              | Múi giờ                     | UTC                      |
| `LOG_LEVEL`             | Mức log                     | INFO                     |

### Các placeholder cho tiêu đề

| Placeholder       | Ví dụ            | Mô tả            |
| ----------------- | ---------------- | ---------------- |
| `{date}`          | 2026-02-01       | Ngày hiện tại    |
| `{time}`          | 16:30            | Giờ hiện tại     |
| `{datetime}`      | 2026-02-01 16:30 | Ngày và giờ      |
| `{timestamp}`     | 20260201_163000  | Timestamp đầy đủ |
| `{stream_number}` | 1                | Số thứ tự stream |

### Ví dụ mẫu tiêu đề

```env
# Tiêu đề đơn giản
STREAM_TITLE_TEMPLATE=Camera Nhà - {date}
# → Camera Nhà - 2026-02-01

# Tiêu đề chi tiết
STREAM_TITLE_TEMPLATE=Phòng Khách Live #{stream_number} - {datetime}
# → Phòng Khách Live #1 - 2026-02-01 16:30

# Tiêu đề tiếng Việt
STREAM_TITLE_TEMPLATE=Giám sát 24/7 - Bắt đầu lúc {time}
# → Giám sát 24/7 - Bắt đầu lúc 16:30
```

---

## Kiến trúc

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Host                              │
│                                                                 │
│  ┌───────────────────────────────┐      ┌────────────────────┐  │
│  │      camera-controller        │      │camera-ffmpeg-stream│  │
│  │    (Container Điều khiển)     │      │ (Container Stream) │  │
│  │                               │      │    (Động)          │  │
│  │  ┌─────────┐  ┌─────────────┐ │      │   ┌────────────┐   │  │
│  │  │ main.py │  │ youtube_api │ │      │   │   FFmpeg   │   │  │
│  │  └────┬────┘  └──────┬──────┘ │      │   │ RTSP→RTMP  │   │  │
│  │       │              │        │      │   └─────┬──────┘   │  │
│  │  ┌────▼────┐         │        │      │         │          │  │
│  │  │scheduler│         │        │      │         │          │  │
│  │  └────┬────┘         │        │      │         │          │  │
│  │       │              │        │      │         │          │  │
│  │  ┌────▼────────┐     │        │      │         │          │  │
│  │  │ffmpeg_runner│─────┼────────┼──────▶         │          │  │
│  │  │(Docker Ctrl)│     │        │      │         │          │  │
│  │  └─────────────┘     │        │      │         │          │  │
│  └───────────┬──────────┴────────┘      └─────────┼──────────┘  │
└──────────────┼────────────────────────────────────┼─────────────┘
               │                                    │
         ┌─────▼─────┐                        ┌─────▼─────┐
         │  YouTube  │                        │   RTSP    │
         │   API     │                        │  Camera   │
         └───────────┘                        └───────────┘
```

Hệ thống sử dụng kiến trúc **Controller-Agent** (Điều khiển - Thực thi):

1. **Controller**: Container chạy Python quản lý YouTube API, lập lịch xoay vòng và điều khiển container stream thông qua Docker socket.
2. **FFmpeg Agent**: Container `linuxserver/ffmpeg` hiệu suất cao được tạo động bởi controller để xử lý việc truyền tải video thực tế.

---

## Xử lý sự cố

### ❌ Lỗi "OOB flow has been blocked"

Google đã chặn OOB flow. **Giải pháp**: Chạy OAuth setup trực tiếp trên máy tính có trình duyệt, không trong Docker.

```bash
source .venv/bin/activate
python src/oauth_setup.py --client-id "ID" --client-secret "SECRET"
```

### ❌ Stream không khởi động

1. **Kiểm tra URL RTSP**:

   ```bash
   # Thử phát bằng VLC hoặc ffplay
   ffplay "rtsp://admin:password@192.168.1.100:554/..."
   ```

2. **Kiểm tra logs**:

   ```bash
   docker compose logs -f
   ```

3. **Kiểm tra token OAuth**:
   - Đảm bảo file `data/token.json` tồn tại
   - Thử chạy lại OAuth setup nếu token hết hạn

### ❌ Lỗi "Access Not Configured"

- Đảm bảo đã bật YouTube Data API v3 trong Google Cloud Console
- Kiểm tra đã thêm email vào Test Users

### ❌ Lỗi API quota

- YouTube API có giới hạn 10,000 đơn vị/ngày
- Mỗi lần tạo stream tiêu tốn khoảng 100 đơn vị
- Nếu hết quota, phải đợi đến 0:00 giờ Pacific Time

### ❌ FFmpeg liên tục crash

1. Kiểm tra kết nối mạng đến camera
2. Kiểm tra camera có đang hoạt động
3. Thử dùng subtype khác trong URL RTSP

### ❌ Container không chạy

```bash
# Kiểm tra logs chi tiết
docker compose logs camera-live

# Kiểm tra container
docker ps -a

# Khởi động lại
docker compose restart
```

---

## Cấu trúc thư mục

```
camera-live/
├── src/
│   ├── main.py          # Bộ điều phối chính (Controller)
│   ├── youtube_api.py   # Client YouTube API
│   ├── ffmpeg_runner.py # Quản lý container FFmpeg
│   ├── scheduler.py     # Lập lịch xoay stream
│   └── oauth_setup.py   # Script setup OAuth
├── data/
│   └── token.json       # Token OAuth (tự động tạo)
├── logs/                # File log (tự động tạo)
├── Dockerfile           # Định nghĩa image Controller
├── docker-compose.yml   # Cấu hình chạy local
├── docker-compose.prod.yml # Cấu hình chạy production
├── DEPLOY.md            # Hướng dẫn deploy chi tiết
├── requirements.txt
├── .env.example
├── .env                 # Cấu hình của bạn
├── README.md            # Tài liệu tiếng Anh
└── README.vi.md         # Tài liệu tiếng Việt (file này)
```

---

## Ghi chú quan trọng

1. **YouTube giới hạn livestream 12 giờ** - Hệ thống tự động xoay trước thời hạn

2. **Chất lượng stream phụ thuộc camera** - Không nâng/hạ chất lượng

3. **Cần kết nối internet ổn định** - Stream sẽ tự khởi động lại nếu mất kết nối

4. **Kiểm tra YouTube Studio** để xem stream:
   https://studio.youtube.com/channel/UC.../livestreaming

5. **Token OAuth có thời hạn** - Refresh token thường có hiệu lực 6 tháng. Nếu hết hạn, chạy lại OAuth setup.

---

## Tóm tắt nhanh

```bash
# 1. Clone và cấu hình
cp .env.example .env
# Sửa .env với thông tin của bạn

# 2. Lấy OAuth token (chạy trên máy có browser)
python3 -m venv .venv
source .venv/bin/activate
pip install requests
python src/oauth_setup.py --client-id "ID" --client-secret "SECRET"

# 3. Build và chạy
docker compose build
docker compose up -d

# 4. Xem logs
docker compose logs -f
```

---

## License

MIT License
