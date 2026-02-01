# Hướng dẫn Deploy Production

Hướng dẫn triển khai Camera Live Stream lên server production.

## Yêu cầu hệ thống

- **OS:** Ubuntu 20.04+ / Debian 11+ / hoặc bất kỳ Linux distribution có Docker
- **Docker:** 20.10+
- **Docker Compose:** v2.0+
- **RAM:** Tối thiểu 512MB (khuyến nghị 1GB)
- **Network:** Kết nối internet ổn định để stream lên YouTube

## Bước 1: Cài đặt Docker

```bash
# Cài đặt Docker
curl -fsSL https://get.docker.com | sh

# Thêm user vào group docker (không cần sudo)
sudo usermod -aG docker $USER

# Đăng xuất và đăng nhập lại để áp dụng
```

## Bước 2: Tạo thư mục project

```bash
# Tạo thư mục
mkdir -p ~/camera-live
cd ~/camera-live

# Tạo thư mục data và logs
mkdir -p data logs
```

## Bước 3: Tải file cấu hình

```bash
# Tải docker-compose.prod.yml
curl -o docker-compose.yml https://raw.githubusercontent.com/kimtrien/camera-live/main/docker-compose.prod.yml

# Tải file .env mẫu
curl -o .env.example https://raw.githubusercontent.com/kimtrien/camera-live/main/.env.example
cp .env.example .env
```

## Bước 4: Cấu hình .env

Chỉnh sửa file `.env`:

```bash
nano .env
```

Cập nhật các giá trị:

```env
# RTSP Camera URL
RTSP_URL=rtsp://username:password@camera-ip:554/path

# YouTube OAuth2 Credentials (từ Google Cloud Console)
YOUTUBE_CLIENT_ID=your-client-id.apps.googleusercontent.com
YOUTUBE_CLIENT_SECRET=GOCSPX-xxx

# Stream Configuration
STREAM_DURATION_HOURS=12
STREAM_TITLE_TEMPLATE=Camera Live - {date} - {time}
STREAM_DESCRIPTION=24/7 Camera Livestream
PRIVACY_STATUS=private
TIMEZONE=Asia/Ho_Chi_Minh
```

## Bước 5: Thiết lập OAuth Token

**QUAN TRỌNG:** Bước này cần thực hiện trên máy có trình duyệt web.

### Trên máy local (có trình duyệt):

```bash
# Clone repo
git clone https://github.com/kimtrien/camera-live.git
cd camera-live

# Cài đặt Python dependencies
pip install google-api-python-client google-auth-oauthlib

# Chạy script OAuth
python oauth_setup.py
```

Làm theo hướng dẫn để đăng nhập Google và cấp quyền.

### Copy token lên server:

```bash
# Trên máy local
scp token.json user@your-server:~/camera-live/data/
```

Hoặc copy nội dung file `token.json` và tạo file trên server:

```bash
# Trên server
nano ~/camera-live/data/token.json
# Paste nội dung và lưu
```

## Bước 6: Pull Docker images

```bash
cd ~/camera-live

# Pull controller image
docker pull ghcr.io/kimtrien/camera-live:latest

# Pull FFmpeg image (cần thiết cho streaming)
docker pull linuxserver/ffmpeg:latest
```

## Bước 7: Khởi động service

```bash
cd ~/camera-live

# Khởi động
docker compose up -d

# Kiểm tra logs
docker logs -f camera-controller
```

## Bước 8: Kiểm tra hoạt động

```bash
# Xem trạng thái containers
docker ps

# Xem logs controller
docker logs --tail=50 camera-controller

# Xem logs FFmpeg (khi đang stream)
docker logs --tail=50 camera-ffmpeg-stream
```

Nếu thành công, bạn sẽ thấy:

```
Stream status: active
Stream is now active!
Status - Stream #1 | FFmpeg: running | Remaining: 12.0 hours
```

## Quản lý Service

### Dừng service

```bash
docker compose down

# Dừng cả FFmpeg container
docker stop camera-ffmpeg-stream 2>/dev/null
```

### Khởi động lại

```bash
docker compose restart
```

### Cập nhật phiên bản mới

```bash
# Pull image mới
docker pull ghcr.io/kimtrien/camera-live:latest
docker pull linuxserver/ffmpeg:latest

# Khởi động lại
docker compose down
docker stop camera-ffmpeg-stream 2>/dev/null
docker compose up -d
```

### Xem logs realtime

```bash
# Controller logs
docker logs -f camera-controller

# FFmpeg logs
docker logs -f camera-ffmpeg-stream
```

## Thiết lập Auto-start

Service sẽ tự động khởi động lại khi:

- Server reboot
- Container crash

Đảm bảo Docker service được enable:

```bash
sudo systemctl enable docker
```

## Troubleshooting

### Lỗi: "Permission denied" với docker.sock

```bash
# Thêm quyền cho docker socket
sudo chmod 666 /var/run/docker.sock
```

### Lỗi: Token expired

```bash
# Chạy lại oauth_setup.py trên máy local
# Sau đó copy token.json mới lên server
```

### Lỗi: Camera không kết nối được

1. Kiểm tra RTSP URL đúng chưa
2. Kiểm tra firewall cho phép kết nối đến camera
3. Test với ffplay: `ffplay "rtsp://..."`

### Lỗi: Stream không hiển thị trên YouTube

1. Kiểm tra YouTube Studio xem có lỗi gì không
2. Đảm bảo camera output H.264 hoặc HEVC
3. Kiểm tra bandwidth internet

## Cấu trúc thư mục

```
~/camera-live/
├── docker-compose.yml    # Docker Compose config
├── .env                  # Environment variables
├── data/
│   └── token.json        # YouTube OAuth token
└── logs/                 # Log files (optional)
```

## Monitoring

### Sử dụng cron để kiểm tra định kỳ

```bash
# Thêm vào crontab
crontab -e

# Thêm dòng sau để kiểm tra mỗi 5 phút
*/5 * * * * docker ps | grep -q camera-controller || docker compose -f ~/camera-live/docker-compose.yml up -d
```

### Nhận thông báo khi stream lỗi

Có thể tích hợp với:

- Telegram Bot
- Discord Webhook
- Email alerts

(Tính năng này có thể được thêm trong phiên bản sau)

## Liên hệ hỗ trợ

- GitHub Issues: https://github.com/kimtrien/camera-live/issues
- Email: [your-email]
