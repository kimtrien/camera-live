# Camera Live Stream to YouTube

Automated RTSP camera streaming to YouTube Live with automatic stream rotation.

## Features

- **Automatic YouTube Live Creation**: Creates livestreams via YouTube Data API v3
- **Stream Rotation**: Automatically rotates streams every N hours (default: 10)
- **No Transcoding**: Uses FFmpeg stream copy for minimal CPU usage
- **OAuth2 Authentication**: Secure token-based authentication
- **Resilient**: Auto-restarts on failures, retries API calls
- **Docker Ready**: Runs entirely via Docker Compose

## Prerequisites

1. Docker and Docker Compose installed
2. RTSP camera accessible from the host
3. Google Cloud project with YouTube Data API v3 enabled
4. OAuth 2.0 credentials (Desktop app type)

---

## Quick Start

### Step 1: Create OAuth Credentials on Google Cloud

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or select existing)
3. Enable **YouTube Data API v3**
4. Go to **OAuth consent screen**:
   - Choose "External"
   - Add your email to **Test users**
5. Go to **Credentials** → **Create Credentials** → **OAuth client ID**
   - Select **Desktop app** as application type
6. Save the **Client ID** and **Client Secret**

### Step 2: Configure .env

```bash
cp .env.example .env
# Edit .env with your configuration
```

### Step 3: Get OAuth Token

> ⚠️ **IMPORTANT**: Run this directly on your computer with a browser, NOT inside Docker!

```bash
# Create virtual environment (one-time)
python3 -m venv .venv

# Activate and install dependencies
source .venv/bin/activate
pip install requests

# Run OAuth setup
python src/oauth_setup.py \
  --client-id "YOUR_CLIENT_ID" \
  --client-secret "YOUR_CLIENT_SECRET"
```

The script will:

1. Open your browser automatically
2. You sign in with Google and grant permissions
3. Token is saved to `data/token.json`

### Step 4: Build and Run

```bash
# Build Docker image
docker compose build

# Start streaming
docker compose up -d
```

That's it! The system will automatically:

- Create a YouTube livestream
- Start streaming from your RTSP camera
- Rotate to a new stream every 10 hours
- Continue indefinitely until stopped

---

## Commands

```bash
# Start in background
docker compose up -d

# View logs
docker compose logs -f

# Stop streaming
docker compose down

# Restart
docker compose restart

# Rebuild after changes
docker compose build --no-cache
docker compose up -d
```

---

## Configuration

All configuration is via the `.env` file:

| Variable                | Description              | Default                  |
| ----------------------- | ------------------------ | ------------------------ |
| `RTSP_URL`              | RTSP camera URL          | Required                 |
| `YOUTUBE_CLIENT_ID`     | OAuth client ID          | Required                 |
| `YOUTUBE_CLIENT_SECRET` | OAuth client secret      | Required                 |
| `STREAM_DURATION_HOURS` | Hours per stream         | 10                       |
| `STREAM_TITLE_TEMPLATE` | Title template           | Camera Live - {datetime} |
| `STREAM_DESCRIPTION`    | Stream description       | 24/7 Camera Livestream   |
| `PRIVACY_STATUS`        | public/unlisted/private  | public                   |
| `TIMEZONE`              | IANA timezone            | UTC                      |
| `LOG_LEVEL`             | DEBUG/INFO/WARNING/ERROR | INFO                     |

### Title Template Placeholders

- `{date}` - Current date (YYYY-MM-DD)
- `{time}` - Current time (HH:MM)
- `{datetime}` - Date and time
- `{timestamp}` - Full timestamp
- `{stream_number}` - Sequential stream number

---

## Troubleshooting

### "OOB flow has been blocked" error

Google has deprecated OOB flow. **Solution**: Run OAuth setup directly on your computer with a browser, not inside Docker.

### Stream not starting

1. Check RTSP URL is accessible: `ffplay rtsp://...`
2. Verify OAuth token exists in `data/token.json`
3. Check logs: `docker compose logs -f`

### API quota errors

- YouTube API has daily quotas (10,000 units/day)
- Each stream creation uses ~100 quota units
- Wait until Pacific Time midnight if exceeded

### FFmpeg crashes

- System automatically restarts FFmpeg
- If persistent, check camera connectivity
- Review logs in container

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Host                              │
│                                                                 │
│  ┌───────────────────────────────┐      ┌────────────────────┐  │
│  │      camera-controller        │      │camera-ffmpeg-stream│  │
│  │   (Orchestrator Container)    │      │ (Dynamic Container)│  │
│  │                               │      │                    │  │
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

The system uses a **Controller-Agent** architecture:

1. **Controller**: A Python-based container that manages YouTube API, schedules rotations, and controls the streaming container.
2. **FFmpeg Agent**: A high-performance `linuxserver/ffmpeg` container created dynamically by the controller to handle the actual stream.

---

## Files

```
camera-live/
├── src/
│   ├── main.py          # Main orchestrator (Controller)
│   ├── youtube_api.py   # YouTube API client
│   ├── ffmpeg_runner.py # Docker container manager for FFmpeg
│   ├── scheduler.py     # Stream rotation scheduler
│   └── oauth_setup.py   # OAuth setup script
├── data/
│   └── token.json       # OAuth token (auto-generated)
├── logs/                # Log files (auto-created)
├── Dockerfile           # Controller image definition
├── docker-compose.yml   # Local development setup
├── docker-compose.prod.yml # Production deployment setup
├── DEPLOY.md            # Detailed production deployment guide
├── requirements.txt
├── .env.example
├── .env                 # Your configuration
├── README.md            # English documentation
└── README.vi.md         # Vietnamese documentation
```

---

## License

MIT License
