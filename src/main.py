"""
Camera Live Stream to YouTube - Main Orchestrator

This is the main entry point for the RTSP to YouTube Live streaming system.
It coordinates the YouTube API, FFmpeg runner, and scheduler components.
"""

import os
import sys
import signal
import logging
import time
import threading
from datetime import datetime
from typing import Optional

from youtube_api import YouTubeAPI, YouTubeAPIError
from ffmpeg_runner import FFmpegRunner, FFmpegState
from scheduler import StreamScheduler, SchedulerState

# Configure logging
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/app/logs/camera-live.log")
    ]
)
logger = logging.getLogger(__name__)


class CameraLiveOrchestrator:
    """
    Main orchestrator for RTSP to YouTube Live streaming.
    
    Coordinates:
    - YouTube API for livestream creation and management
    - FFmpeg for RTSP to RTMP streaming
    - Scheduler for stream rotation timing
    """
    
    def __init__(self):
        # Load configuration from environment
        self.rtsp_url = os.getenv("RTSP_URL")
        self.client_id = os.getenv("YOUTUBE_CLIENT_ID")
        self.client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
        self.refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")
        
        self.duration_hours = float(os.getenv("STREAM_DURATION_HOURS", "10"))
        self.title_template = os.getenv("STREAM_TITLE_TEMPLATE", "Camera Live - {datetime}")
        self.description = os.getenv("STREAM_DESCRIPTION", "24/7 Camera Livestream")
        self.privacy_status = os.getenv("PRIVACY_STATUS", "public")
        self.timezone = os.getenv("TIMEZONE", "UTC")
        
        # Validate required configuration
        self._validate_config()
        
        # Initialize components
        self.youtube: Optional[YouTubeAPI] = None
        self.ffmpeg: Optional[FFmpegRunner] = None
        self.scheduler: Optional[StreamScheduler] = None
        
        # State tracking
        self.current_broadcast_id: Optional[str] = None
        self.current_stream_id: Optional[str] = None
        self.current_rtmp_url: Optional[str] = None
        
        self._shutdown_event = threading.Event()
        self._rotation_lock = threading.Lock()
        self._is_rotating = False
    
    def _validate_config(self):
        """Validate required configuration values."""
        errors = []
        
        if not self.rtsp_url:
            errors.append("RTSP_URL is required")
        if not self.client_id:
            errors.append("YOUTUBE_CLIENT_ID is required")
        if not self.client_secret:
            errors.append("YOUTUBE_CLIENT_SECRET is required")
        
        if errors:
            for error in errors:
                logger.error(error)
            raise ValueError("Missing required configuration: " + ", ".join(errors))
        
        logger.info("Configuration validated successfully")
        logger.info("RTSP URL: %s", self._mask_url(self.rtsp_url))
        logger.info("Stream duration: %.1f hours", self.duration_hours)
        logger.info("Privacy status: %s", self.privacy_status)
        logger.info("Timezone: %s", self.timezone)
    
    def _mask_url(self, url: str) -> str:
        """Mask sensitive parts of URL for logging."""
        if "@" in url:
            # Mask credentials in RTSP URL
            parts = url.split("@")
            protocol_creds = parts[0]
            rest = "@".join(parts[1:])
            protocol = protocol_creds.split("://")[0]
            return f"{protocol}://****:****@{rest}"
        return url
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            logger.info("Received signal %d, initiating shutdown...", signum)
            self._shutdown_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def _on_ffmpeg_crash(self):
        """Handle FFmpeg crash - attempt to restart."""
        logger.error("FFmpeg crashed, attempting restart...")
        
        if self._shutdown_event.is_set():
            logger.info("Shutdown in progress, not restarting FFmpeg")
            return
        
        # Brief delay before restart
        time.sleep(5)
        
        if self.current_rtmp_url and self.ffmpeg:
            success = self.ffmpeg.start(self.current_rtmp_url)
            if success:
                logger.info("FFmpeg restarted successfully")
            else:
                logger.error("FFmpeg restart failed, initiating stream rotation")
                self._rotate_stream()
    
    def _on_rotation_needed(self):
        """Handle stream rotation when duration expires."""
        logger.info("Stream rotation triggered by scheduler")
        self._rotate_stream()
    
    def _rotate_stream(self):
        """
        Rotate to a new stream.
        
        1. Stop FFmpeg
        2. Complete current broadcast
        3. Create new livestream
        4. Start FFmpeg with new RTMP URL
        5. Start new timer
        """
        with self._rotation_lock:
            if self._is_rotating:
                logger.warning("Rotation already in progress")
                return
            self._is_rotating = True
        
        try:
            logger.info("=" * 50)
            logger.info("STARTING STREAM ROTATION")
            logger.info("=" * 50)
            
            # Stop FFmpeg
            if self.ffmpeg and self.ffmpeg.is_running():
                logger.info("Stopping current FFmpeg stream...")
                self.ffmpeg.stop()
            
            # Stop scheduler timer
            if self.scheduler:
                self.scheduler.stop_timer()
            
            # Complete current broadcast
            if self.current_broadcast_id and self.youtube:
                logger.info("Completing current broadcast: %s", self.current_broadcast_id)
                try:
                    self.youtube.complete_broadcast(self.current_broadcast_id)
                except YouTubeAPIError as e:
                    logger.warning("Failed to complete broadcast: %s", str(e))
            
            # Brief pause between streams
            logger.info("Waiting 10 seconds before creating new stream...")
            time.sleep(10)
            
            # Create new livestream
            if not self._start_new_stream():
                logger.error("Failed to start new stream, will retry in 60 seconds")
                time.sleep(60)
                if not self._start_new_stream():
                    logger.error("Second attempt failed, waiting for manual intervention")
                    # Keep trying every 5 minutes
                    while not self._shutdown_event.is_set():
                        time.sleep(300)
                        if self._start_new_stream():
                            break
            
            logger.info("=" * 50)
            logger.info("STREAM ROTATION COMPLETED")
            logger.info("=" * 50)
            
        finally:
            with self._rotation_lock:
                self._is_rotating = False
    
    def _start_new_stream(self) -> bool:
        """
        Create and start a new livestream.
        
        Returns:
            bool: True if successful
        """
        try:
            # Generate title
            title = self.scheduler.generate_title()
            logger.info("Creating new livestream: %s", title)
            
            # Create livestream on YouTube
            broadcast_id, stream_id, rtmp_url = self.youtube.create_livestream(
                title=title,
                description=self.description,
                privacy_status=self.privacy_status
            )
            
            self.current_broadcast_id = broadcast_id
            self.current_stream_id = stream_id
            self.current_rtmp_url = rtmp_url
            
            logger.info("Livestream created successfully")
            logger.info("Broadcast ID: %s", broadcast_id)
            logger.info("Stream ID: %s", stream_id)
            
            # Wait a moment for YouTube to be ready
            logger.info("Waiting for YouTube to be ready...")
            time.sleep(5)
            
            # Start FFmpeg
            logger.info("Starting FFmpeg...")
            if not self.ffmpeg.start(rtmp_url):
                logger.error("Failed to start FFmpeg")
                return False
            
            # Wait for stream to be active
            logger.info("Waiting for stream to become active...")
            max_wait = 120  # 2 minutes
            start_time = time.time()
            
            while time.time() - start_time < max_wait:
                status = self.youtube.get_stream_status(stream_id)
                logger.info("Stream status: %s", status)
                
                if status == "active":
                    logger.info("Stream is now active!")
                    break
                elif status in ["error", "noData"]:
                    if time.time() - start_time > 30:
                        logger.warning("Stream status is %s after 30s, continuing anyway", status)
                        break
                
                time.sleep(5)
            
            # Start scheduler timer
            self.scheduler.start_stream_timer()
            
            logger.info("New stream fully operational")
            return True
            
        except Exception as e:
            logger.error("Failed to start new stream: %s", str(e))
            return False
    
    def run(self):
        """Main run loop."""
        logger.info("=" * 50)
        logger.info("CAMERA LIVE STREAM TO YOUTUBE")
        logger.info("Starting up...")
        logger.info("=" * 50)
        
        # Setup signal handlers
        self._setup_signal_handlers()
        
        # Ensure log directory exists
        os.makedirs("/app/logs", exist_ok=True)
        os.makedirs("/app/data", exist_ok=True)
        
        try:
            # Initialize YouTube API
            logger.info("Initializing YouTube API...")
            self.youtube = YouTubeAPI(
                client_id=self.client_id,
                client_secret=self.client_secret,
                refresh_token=self.refresh_token
            )
            self.youtube.authenticate()
            
            # Initialize scheduler
            logger.info("Initializing scheduler...")
            self.scheduler = StreamScheduler(
                duration_hours=self.duration_hours,
                title_template=self.title_template,
                timezone=self.timezone
            )
            self.scheduler.on_rotation_needed = self._on_rotation_needed
            
            # Initialize FFmpeg
            logger.info("Initializing FFmpeg runner...")
            self.ffmpeg = FFmpegRunner(
                rtsp_url=self.rtsp_url,
                on_crash=self._on_ffmpeg_crash
            )
            
            # Start first stream
            logger.info("Starting initial stream...")
            if not self._start_new_stream():
                logger.error("Failed to start initial stream")
                raise RuntimeError("Could not start initial stream")
            
            # Main loop - just monitor and log status
            logger.info("Entering main monitoring loop...")
            
            while not self._shutdown_event.is_set():
                # Log status every 5 minutes
                stream_info = self.scheduler.get_stream_info()
                ffmpeg_state = self.ffmpeg.get_state() if self.ffmpeg else "N/A"
                
                logger.info(
                    "Status - Stream #%d | FFmpeg: %s | Remaining: %.1f hours",
                    stream_info.get("stream_count", 0),
                    ffmpeg_state.value if hasattr(ffmpeg_state, 'value') else ffmpeg_state,
                    stream_info.get("remaining_hours", 0)
                )
                
                # Check FFmpeg health
                if self.ffmpeg and not self.ffmpeg.is_running() and not self._is_rotating:
                    logger.warning("FFmpeg is not running, triggering restart...")
                    self._on_ffmpeg_crash()
                
                self._shutdown_event.wait(timeout=300)  # 5 minutes
            
            logger.info("Shutdown signal received, cleaning up...")
            
        except Exception as e:
            logger.exception("Fatal error in main loop: %s", str(e))
            raise
        
        finally:
            self._cleanup()
    
    def _cleanup(self):
        """Clean up resources on shutdown."""
        logger.info("Cleaning up resources...")
        
        # Stop FFmpeg
        if self.ffmpeg:
            logger.info("Stopping FFmpeg...")
            self.ffmpeg.stop()
        
        # Stop scheduler
        if self.scheduler:
            logger.info("Stopping scheduler...")
            self.scheduler.stop_timer()
        
        # Complete broadcast if active
        if self.current_broadcast_id and self.youtube:
            logger.info("Completing final broadcast...")
            try:
                self.youtube.complete_broadcast(self.current_broadcast_id)
            except Exception as e:
                logger.warning("Failed to complete final broadcast: %s", str(e))
        
        logger.info("Cleanup complete. Goodbye!")


def main():
    """Entry point."""
    try:
        orchestrator = CameraLiveOrchestrator()
        orchestrator.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.exception("Application error: %s", str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
