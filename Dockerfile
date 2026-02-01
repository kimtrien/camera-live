# Camera Live Stream to YouTube
# Production Dockerfile

FROM python:3.11-slim

LABEL maintainer="Camera Live Streaming System"
LABEL description="RTSP to YouTube Live streaming with automatic rotation"

# Install FFmpeg and system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create app directory
WORKDIR /app

# Create necessary directories
RUN mkdir -p /app/data /app/logs /app/src

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ /app/src/

# Set Python path
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD pgrep -f "python.*main.py" > /dev/null && pgrep -f ffmpeg > /dev/null || exit 1

# Run the application
CMD ["python", "/app/src/main.py"]
