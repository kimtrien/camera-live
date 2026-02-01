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

1. Đã cài đặt Docker và Docker Compose
2. Camera RTSP có thể truy cập từ máy chủ
3. Tài khoản Google Cloud với YouTube Data API v3 đã bật
4. Thông tin xác thực OAuth 2.0

## Hướng dẫn cài đặt

### Bước 1: Cấu hình file .env

```bash
cd camera-live
cp .env.example .env
```

Mở file `.env` và chỉnh sửa các thông số:

```env
# URL camera RTSP của bạn
RTSP_URL=rtsp://admin:matkhau@192.168.1.100:554/cam/realmonitor?channel=1&subtype=0

# Thông tin OAuth từ Google Cloud Console
YOUTUBE_CLIENT_ID=your_client_id
YOUTUBE_CLIENT_SECRET=your_client_secret

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

### Bước 2: Tạo OAuth Credentials trên Google Cloud

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
   - Ở phần Scopes, nhấn "Add or Remove Scopes"
   - Tìm và thêm: `https://www.googleapis.com/auth/youtube`
   - Nhấn "Save and Continue"
   - Ở phần Test users, nhấn "Add Users"
   - Thêm email Google của bạn
   - Nhấn "Save and Continue"

5. **Tạo OAuth Client ID**:
   - Vào "APIs & Services" → "Credentials"
   - Click "+ Create Credentials" → "OAuth client ID"
   - Application type: chọn **Desktop app**
   - Name: `Camera Live Desktop`
   - Click "Create"
   - **Lưu lại Client ID và Client Secret**

### Bước 3: Lấy Refresh Token

Chạy lệnh sau để xác thực và lấy refresh token:

```bash
docker compose run --rm camera-live python /app/src/oauth_setup.py
```

**Lưu ý**: Nếu chưa build image, hãy build trước:

```bash
docker compose build
```

Khi chạy lệnh, hệ thống sẽ:

1. Hiển thị một URL
2. Mở URL đó trong trình duyệt
3. Đăng nhập bằng tài khoản Google đã thêm vào Test Users
4. Cấp quyền cho ứng dụng
5. Token sẽ được lưu tự động vào thư mục `data/`

Nếu muốn dùng refresh token trong `.env`, copy token hiển thị trên màn hình vào biến `YOUTUBE_REFRESH_TOKEN`.

### Bước 4: Chạy hệ thống

```bash
docker compose up -d
```

Xong! Hệ thống sẽ:

1. Tạo một livestream mới trên YouTube
2. Bắt đầu stream từ camera RTSP
3. Tự động xoay sang stream mới sau 10 giờ
4. Tiếp tục vô hạn cho đến khi bạn dừng

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

## Cấu hình chi tiết

### Các biến môi trường

| Biến                    | Mô tả                       | Mặc định                 |
| ----------------------- | --------------------------- | ------------------------ |
| `RTSP_URL`              | URL camera RTSP             | Bắt buộc                 |
| `YOUTUBE_CLIENT_ID`     | OAuth Client ID             | Bắt buộc                 |
| `YOUTUBE_CLIENT_SECRET` | OAuth Client Secret         | Bắt buộc                 |
| `YOUTUBE_REFRESH_TOKEN` | OAuth Refresh Token         | Từ setup                 |
| `STREAM_DURATION_HOURS` | Thời lượng mỗi stream (giờ) | 10                       |
| `STREAM_TITLE_TEMPLATE` | Mẫu tiêu đề                 | Camera Live - {datetime} |
| `STREAM_DESCRIPTION`    | Mô tả stream                | 24/7 Camera Livestream   |
| `PRIVACY_STATUS`        | Chế độ riêng tư             | public                   |
| `TIMEZONE`              | Múi giờ                     | UTC                      |
| `LOG_LEVEL`             | Mức log                     | INFO                     |

### Các placeholder cho tiêu đề

- `{date}` - Ngày hiện tại (YYYY-MM-DD)
- `{time}` - Giờ hiện tại (HH:MM)
- `{datetime}` - Ngày và giờ
- `{timestamp}` - Timestamp đầy đủ
- `{stream_number}` - Số thứ tự stream

### Ví dụ mẫu tiêu đề

```env
# Ví dụ 1: Tiêu đề đơn giản
STREAM_TITLE_TEMPLATE=Camera Nhà - {date}
# Kết quả: Camera Nhà - 2026-02-01

# Ví dụ 2: Tiêu đề chi tiết
STREAM_TITLE_TEMPLATE=Phòng Khách Live #{stream_number} - {datetime}
# Kết quả: Phòng Khách Live #1 - 2026-02-01 16:30

# Ví dụ 3: Tiêu đề tiếng Việt
STREAM_TITLE_TEMPLATE=Giám sát 24/7 - Bắt đầu lúc {time}
# Kết quả: Giám sát 24/7 - Bắt đầu lúc 16:30
```

## Xử lý sự cố

### Stream không khởi động

1. **Kiểm tra URL RTSP**:

   ```bash
   # Thử phát RTSP bằng VLC hoặc ffplay
   ffplay "rtsp://admin:password@192.168.1.100:554/cam/realmonitor?channel=1&subtype=0"
   ```

2. **Kiểm tra logs**:

   ```bash
   docker compose logs -f
   ```

3. **Kiểm tra token OAuth**:
   - Xóa file `data/token.json`
   - Chạy lại bước lấy refresh token

### Lỗi API quota

- YouTube API có giới hạn 10,000 đơn vị/ngày
- Mỗi lần tạo stream tiêu tốn khoảng 100 đơn vị
- Nếu hết quota, phải đợi đến 0:00 giờ Pacific Time

### FFmpeg liên tục crash

1. Kiểm tra kết nối mạng đến camera
2. Kiểm tra camera có đang hoạt động
3. Thử giảm chất lượng stream (dùng subtype khác)

### Container không chạy

```bash
# Kiểm tra logs chi tiết
docker compose logs camera-live

# Kiểm tra container đang chạy
docker ps -a

# Khởi động lại container
docker compose restart
```

## Cấu trúc thư mục

```
camera-live/
├── src/
│   ├── main.py          # Bộ điều phối chính
│   ├── youtube_api.py   # Client YouTube API
│   ├── ffmpeg_runner.py # Quản lý FFmpeg
│   ├── scheduler.py     # Lập lịch xoay stream
│   └── oauth_setup.py   # Script setup OAuth
├── data/                # Lưu trữ token (tự động tạo)
├── logs/                # File log (tự động tạo)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .env                 # File cấu hình của bạn
├── README.md            # Tài liệu tiếng Anh
└── README.vi.md         # Tài liệu tiếng Việt
```

## Ghi chú quan trọng

1. **YouTube giới hạn livestream 12 giờ liên tục** - Hệ thống tự động xoay trước thời hạn này

2. **Chất lượng stream phụ thuộc camera** - Sử dụng stream copy, không nâng/hạ chất lượng

3. **Cần kết nối internet ổn định** - Nếu mất kết nối, stream sẽ dừng và tự khởi động lại

4. **Kiểm tra YouTube Studio** để xem stream đang hoạt động: https://studio.youtube.com/channel/UC.../livestreaming

## Hỗ trợ

Nếu gặp vấn đề:

1. Kiểm tra logs: `docker compose logs -f`
2. Đọc phần Xử lý sự cố ở trên
3. Kiểm tra kết nối camera và internet

## License

MIT License
