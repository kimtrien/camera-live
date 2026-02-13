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
import requests
import json
from typing import Optional, Dict

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


class StateStore:
    """Simple JSON file-based state persistence."""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        
    def save(self, broadcast_id: str, stream_id: str, rtmp_url: str):
        """Save stream state to file."""
        data = {
            "broadcast_id": broadcast_id,
            "stream_id": stream_id,
            "rtmp_url": rtmp_url,
            "updated_at": time.time()
        }
        try:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, 'w') as f:
                json.dump(data, f)
            logger.info("State saved to %s", self.file_path)
        except Exception as e:
            logger.error("Failed to save state: %s", str(e))

    def load(self) -> Optional[Dict[str, str]]:
        """Load stream state from file."""
        if not os.path.exists(self.file_path):
            return None
        try:
            with open(self.file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load state: %s", str(e))
            return None

    def clear(self):
        """Clear stored state file."""
        if os.path.exists(self.file_path):
            try:
                os.remove(self.file_path)
                logger.info("State cleared")
            except Exception as e:
                logger.error("Failed to clear state: %s", str(e))



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
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        self.max_retry_attempts = int(os.getenv("MAX_RETRY_ATTEMPTS", "3"))
        self.rtsp_check_timeout = int(os.getenv("RTSP_CHECK_TIMEOUT", "60"))
        self.stream_check_timeout = int(os.getenv("STREAM_CHECK_TIMEOUT", "60"))
        

        
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
        self._shutdown_event = threading.Event()
        self._rotation_lock = threading.Lock()
        self._is_rotating = False
        self.retry_count = 0
        
        # Persistence
        self.state_store = StateStore("/app/data/stream_state.json")
        self._restore_state()
        
    def _restore_state(self):
        """Restore state from persistence if available."""
        saved_state = self.state_store.load()
        if saved_state:
            logger.info("Found persisted state, restoring...")
            self.current_broadcast_id = saved_state.get("broadcast_id")
            self.current_stream_id = saved_state.get("stream_id")
            self.current_rtmp_url = saved_state.get("rtmp_url")
            
            logger.info("Restored Broadcast ID: %s", self.current_broadcast_id)
            logger.info("Restored Stream ID: %s", self.current_stream_id)
        else:
            logger.info("No persisted state found")
    
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
        logger.info("Max retry attempts: %d", self.max_retry_attempts)
        logger.info("RTSP check timeout: %d seconds", self.rtsp_check_timeout)
    
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
    
    def _send_telegram_notification(self, message: str):
        """Send notification to Telegram."""
        if not self.telegram_bot_token or not self.telegram_chat_id:
            return
            
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            payload = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code != 200:
                logger.error("Failed to send Telegram notification: %s", response.text)
        except Exception as e:
            logger.error("Error sending Telegram notification: %s", str(e))



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
                
                # Ensure FFmpeg is truly stopped
                waited = 0
                while self.ffmpeg.is_running() and waited < 10:
                    time.sleep(1)
                    waited += 1
                
                if self.ffmpeg.is_running():
                    logger.warning("FFmpeg did not stop gracefully, forcing cleanup")
                    # This might need more aggressive cleanup if implemented in ffmpeg_runner
            
            # Stop scheduler timer
            if self.scheduler:
                self.scheduler.stop_timer()
            
            # Complete current broadcast
            if self.current_broadcast_id and self.youtube:
                # Give YouTube a moment to process the end of the stream
                logger.info("Waiting 5 seconds for YouTube to process remaining data...")
                time.sleep(5)
                
                logger.info("Completing current broadcast: %s", self.current_broadcast_id)
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        if self.youtube.complete_broadcast(self.current_broadcast_id):
                            logger.info("Broadcast completed successfully")
                            break
                        else:
                            logger.warning("Broadcast completion returned False (attempt %d/%d)", attempt + 1, max_retries)
                    except Exception as e:
                        logger.warning("Failed to complete broadcast (attempt %d/%d): %s", attempt + 1, max_retries, str(e))
                    
                    if attempt < max_retries - 1:
                        time.sleep(5)
            
            # Brief pause between streams
            logger.info("Waiting 10 seconds before creating new stream...")
            time.sleep(10)
            
            # Create new livestream
            
            # Explicitly clear old stream details to force new creation
            self.current_broadcast_id = None
            self.current_stream_id = None
            self.current_rtmp_url = None
            
            # Clear persisted state
            self.state_store.clear()

            if not self._start_stream_with_retries():
                logger.error("All attempts to start new stream failed")
                # Send failure notification
                self._send_telegram_notification(
                    f"⛔ <b>Stream Rotation Failed</b>\n\n"
                    f"Failed to start new stream after {self.max_retry_attempts} attempts.\n"
                    f"Please check the server logs."
                )
                
                # Keep trying every 5 minutes (fallback safety)
                while not self._shutdown_event.is_set():
                    time.sleep(300)
                    # Standby recovery Logic: Check source -> Start -> Reset
                    logger.info("Retrying stream rotation (standby mode)...")
                    if self.ffmpeg.check_stream_availability():
                        logger.info("Source became available. Attempting to start stream...")
                        if self._start_new_stream():
                             # Notification on recovery
                            self._send_telegram_notification(
                                "✅ <b>Stream Recovered</b>\n\n"
                                "Stream has been successfully restarted after previous failure."
                            )
                            self._reset_retry_count()
                            break
                    else:
                        logger.info("Source still unavailable in standby mode.")
            
            logger.info("=" * 50)
            logger.info("STREAM ROTATION COMPLETED")
            logger.info("=" * 50)
            
        finally:
            with self._rotation_lock:
                self._is_rotating = False

    def _cleanup_failed_start(self, broadcast_id: str, stream_id: str):
        """
        Clean up resources after a failed stream start.
        
        Args:
            broadcast_id: Broadcast ID to delete
            stream_id: Stream ID to delete
        """
        logger.info("Cleaning up failed stream start...")
        
        if self.youtube:
            # Delete broadcast
            if broadcast_id:
                try:
                    self.youtube.delete_broadcast(broadcast_id)
                except Exception as e:
                    logger.warning("Failed to delete broadcast during cleanup: %s", str(e))
            
            # Delete stream
            if stream_id:
                try:
                    self.youtube.delete_stream(stream_id)
                except Exception as e:
                    logger.warning("Failed to delete stream during cleanup: %s", str(e))

    def _start_new_stream(self) -> bool:
        """
        Create (or reuse) and start a new livestream.
        
        Returns:
            bool: True if successful
        """
        try:
            # Check if we already have a valid broadcast to reuse (e.g. from a failed attempt)
            if self.current_broadcast_id and self.current_stream_id and self.current_rtmp_url:
                logger.info("Reusing existing broadcast/stream details...")
                broadcast_id = self.current_broadcast_id
                stream_id = self.current_stream_id
                rtmp_url = self.current_rtmp_url
                
                logger.info("Reusing Broadcast ID: %s", broadcast_id)
                logger.info("Reusing Stream ID: %s", stream_id)
                
            else:
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
                
                # Save state
                self.state_store.save(broadcast_id, stream_id, rtmp_url)
                
                logger.info("Livestream created successfully")
                logger.info("Broadcast ID: %s", broadcast_id)
                logger.info("Stream ID: %s", stream_id)
                
                # Send Telegram notification
                stream_url = f"https://youtu.be/{broadcast_id}"
                self._send_telegram_notification(
                    f"🔴 <b>Camera Live Stream Started</b>\n\n"
                    f"<b>Title:</b> {title}\n"
                    f"<b>Link:</b> {stream_url}"
                )
            
            # Wait a moment for YouTube to be ready
            logger.info("Waiting for YouTube to be ready...")
            time.sleep(5)
            
            # Start FFmpeg
            logger.info("Starting FFmpeg...")
            if not self.ffmpeg.start(rtmp_url):
                logger.error("Failed to start FFmpeg")
                # Do NOT cleanup here; allow retry to reuse existing broadcast
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
                elif status in ["error", "noData", "unknown"]:
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
            # Only cleanup if it was a creation error (implied by lack of IDs being set yet)
            # giving up on this attempt, but keeping state for retry if IDs were set
            return False

        except Exception as e:
            logger.error("Failed to start new stream: %s", str(e))
            return False


    def _reset_retry_count(self):
        """Reset retry count to 0."""
        logger.info("Resetting retry count to 0")
        self.retry_count = 0

    def _wait_for_rtsp_source(self) -> bool:
        """
        Wait for RTSP source to be available within timeout.
        
        Returns:
            bool: True if source is ready, False if timed out
        """
        logger.info("Waiting for RTSP source to be ready (timeout: %ds)...", self.rtsp_check_timeout)
        start_time = time.time()
        
        while time.time() - start_time < self.rtsp_check_timeout:
            if self.ffmpeg.check_stream_availability(timeout=self.stream_check_timeout):
                logger.info("RTSP source is ready")
                return True
            
            logger.info("RTSP source not ready, retrying in 5s...")
            if self._shutdown_event.wait(timeout=5):
                return False
                
        logger.error("RTSP Source check timed out after %d seconds", self.rtsp_check_timeout)
        
        # Send notification
        error_msg = f"RTSP Source unavailable after {self.rtsp_check_timeout} seconds"
        self._send_telegram_notification(f"⚠️ <b>Source Check Failed</b>\n\n{error_msg}")
        
        return False

    def _start_stream_with_retries(self) -> bool:
        """
        Attempt to start the stream with persistent retries.
        
        Returns:
            bool: True if successful, False if all retries failed
        """
        # Load current retry count
        current_retry = self.retry_count
        
        while current_retry < self.max_retry_attempts:
            current_retry += 1
            self.retry_count = current_retry
            logger.info("Stream start attempt %d/%d (In-Memory)", current_retry, self.max_retry_attempts)
            
            # 1. Pre-flight Check: Wait for Source
            if not self._wait_for_rtsp_source():
                logger.warning("Pre-flight check failed, aborting this attempt")
                # Pre-flight failed, count as a failure attempt
            else:
                # 2. Try to start stream
                if self._start_new_stream():
                    logger.info("Stream started successfully")
                    self._reset_retry_count()
                    return True
            
            logger.warning("Attempt %d failed", current_retry)
            
            if current_retry < self.max_retry_attempts:
                wait_time = 60
                logger.info("Waiting %d seconds before next retry...", wait_time)
                if self._shutdown_event.wait(timeout=wait_time):
                    return False
        
        # If we reach here, we exceeded max retries
        logger.error("Max retry attempts (%d) reached", self.max_retry_attempts)
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

            if not self._start_stream_with_retries():
                error_msg = f"Failed to start initial stream after {self.max_retry_attempts} attempts"
                logger.error(error_msg)
                
                self._send_telegram_notification(
                    f"⛔ <b>Initial Startup Failed</b>\n\n"
                    f"{error_msg}.\n"
                    f"Entering standby mode (retrying every 5 minutes)."
                )
                
                # Enter Standby Loop instead of crashing
                logger.info("Entering standby mode...")
                while not self._shutdown_event.is_set():
                    time.sleep(300)
                    logger.info("Standby mode: Checking source availability...")
                    if self.ffmpeg.check_stream_availability():
                        logger.info("Source is available. Attempting to start initial stream...")
                        if self._start_new_stream():
                            logger.info("Stream started from standby mode.")
                            self._reset_retry_count()
                            break
                    else:
                        logger.info("Source still unavailable.")
            
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
            # Brief pause before final completion
            time.sleep(3)
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
