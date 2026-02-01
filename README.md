# Camera Live Stream to YouTube

Automated RTSP camera streaming to YouTube Live with automatic stream rotation.

## Features

- **Automatic YouTube Live Creation**: Creates new livestreams via YouTube Data API v3
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

## Quick Start

### 1. Clone and Configure

```bash
cd camera-live
cp .env.example .env
# Edit .env with your configuration
```

### 2. Get YouTube OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or select existing)
3. Enable **YouTube Data API v3**
4. Go to **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID**
5. Select **Desktop app** as application type
6. Download or copy the Client ID and Client Secret
7. Add your email to **Test users** if app is in testing mode

### 3. Generate OAuth Token

Run the OAuth setup script to get your refresh token:

```bash
# Using Docker
docker compose run --rm camera-live python /app/src/oauth_setup.py

# Or locally with Python
pip install -r requirements.txt
python src/oauth_setup.py --client-id YOUR_ID --client-secret YOUR_SECRET
```

Follow the browser prompts to authorize. Save the refresh token to your `.env` file.

### 4. Start Streaming

```bash
docker compose up -d
```

That's it! The system will:

1. Create a YouTube livestream
2. Start streaming from your RTSP camera
3. Automatically rotate to a new stream every 10 hours
4. Continue indefinitely until stopped

## Configuration

All configuration is via the `.env` file:

| Variable                | Description              | Default                  |
| ----------------------- | ------------------------ | ------------------------ |
| `RTSP_URL`              | RTSP camera URL          | Required                 |
| `YOUTUBE_CLIENT_ID`     | OAuth client ID          | Required                 |
| `YOUTUBE_CLIENT_SECRET` | OAuth client secret      | Required                 |
| `YOUTUBE_REFRESH_TOKEN` | OAuth refresh token      | From setup               |
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

## Commands

```bash
# Start in background
docker compose up -d

# View logs
docker compose logs -f

# Stop streaming
docker compose down

# Rebuild after changes
docker compose build --no-cache
docker compose up -d
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Container                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ │
│  │   main.py   │  │ youtube_api │  │    scheduler    │ │
│  │ Orchestrator│──│   API v3    │──│  Timer/Rotation │ │
│  └──────┬──────┘  └─────────────┘  └─────────────────┘ │
│         │                                               │
│  ┌──────▼──────┐                                       │
│  │ffmpeg_runner│                                       │
│  │  RTSP→RTMP  │                                       │
│  └──────┬──────┘                                       │
└─────────┼───────────────────────────────────────────────┘
          │
    ┌─────▼─────┐        ┌──────────────┐
    │   RTSP    │        │   YouTube    │
    │  Camera   │        │    Live      │
    └───────────┘        └──────────────┘
```

## Troubleshooting

### Stream not starting

- Check RTSP URL is accessible: `ffplay rtsp://...`
- Verify OAuth token is valid
- Check logs: `docker compose logs -f`

### API quota errors

- YouTube API has daily quotas
- Each stream creation uses ~100 quota units
- Default quota is 10,000 units/day

### FFmpeg crashes

- System automatically restarts FFmpeg
- If persistent, check camera connectivity
- Review FFmpeg logs in `/app/logs/`

## Files

```
camera-live/
├── src/
│   ├── main.py          # Main orchestrator
│   ├── youtube_api.py   # YouTube API client
│   ├── ffmpeg_runner.py # FFmpeg process manager
│   ├── scheduler.py     # Stream rotation scheduler
│   └── oauth_setup.py   # OAuth setup script
├── data/                # Token storage (auto-created)
├── logs/                # Log files (auto-created)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

## License

MIT License
