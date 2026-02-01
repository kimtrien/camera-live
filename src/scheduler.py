"""
Stream Scheduler
Handles timing, rotation, and lifecycle management of livestreams.
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Optional, Callable
from enum import Enum
import pytz

logger = logging.getLogger(__name__)


class SchedulerState(Enum):
    """Scheduler states."""
    IDLE = "idle"
    STREAMING = "streaming"
    ROTATING = "rotating"
    STOPPING = "stopping"


class StreamScheduler:
    """
    Scheduler for managing stream rotation and timing.
    
    Features:
    - Configurable stream duration
    - Automatic rotation at duration expiry
    - Timezone-aware title generation
    - Callback-based stream lifecycle events
    """
    
    def __init__(
        self,
        duration_hours: float = 10,
        title_template: str = "Camera Live - {date}",
        timezone: str = "UTC"
    ):
        """
        Initialize scheduler.
        
        Args:
            duration_hours: Duration of each stream in hours
            title_template: Template for stream titles (supports {date}, {time}, {datetime})
            timezone: IANA timezone string
        """
        self.duration_hours = duration_hours
        self.duration_seconds = int(duration_hours * 3600)
        self.title_template = title_template
        
        try:
            self.timezone = pytz.timezone(timezone)
        except Exception as e:
            logger.warning("Invalid timezone '%s', using UTC: %s", timezone, str(e))
            self.timezone = pytz.UTC
        
        self.state = SchedulerState.IDLE
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._timer_thread: Optional[threading.Thread] = None
        
        # Stream session info
        self.current_stream_start: Optional[datetime] = None
        self.stream_count = 0
        
        # Callbacks
        self.on_rotation_needed: Optional[Callable[[], None]] = None
        self.on_stream_started: Optional[Callable[[str], None]] = None
    
    def generate_title(self) -> str:
        """
        Generate stream title using template and current time.
        
        Returns:
            Formatted title string
        """
        now = datetime.now(self.timezone)
        
        replacements = {
            "{date}": now.strftime("%Y-%m-%d"),
            "{time}": now.strftime("%H:%M"),
            "{datetime}": now.strftime("%Y-%m-%d %H:%M"),
            "{timestamp}": now.strftime("%Y%m%d_%H%M%S"),
            "{stream_number}": str(self.stream_count + 1),
        }
        
        title = self.title_template
        for key, value in replacements.items():
            title = title.replace(key, value)
        
        return title
    
    def start_stream_timer(self) -> bool:
        """
        Start the stream duration timer.
        
        Returns:
            bool: True if timer started successfully
        """
        with self._lock:
            if self.state == SchedulerState.STREAMING:
                logger.warning("Stream timer already running")
                return False
            
            self.state = SchedulerState.STREAMING
            self.current_stream_start = datetime.now(self.timezone)
            self.stream_count += 1
            self._stop_event.clear()
        
        logger.info(
            "Stream #%d started at %s (duration: %s hours)",
            self.stream_count,
            self.current_stream_start.strftime("%Y-%m-%d %H:%M:%S %Z"),
            self.duration_hours
        )
        
        # Start timer thread
        self._timer_thread = threading.Thread(
            target=self._run_timer,
            daemon=True
        )
        self._timer_thread.start()
        
        return True
    
    def _run_timer(self):
        """Timer thread that monitors stream duration."""
        logger.info("Stream timer started, will rotate in %d seconds", self.duration_seconds)
        
        # Calculate end time
        end_time = self.current_stream_start + timedelta(seconds=self.duration_seconds)
        
        while not self._stop_event.is_set():
            now = datetime.now(self.timezone)
            remaining = (end_time - now).total_seconds()
            
            if remaining <= 0:
                logger.info("Stream duration reached, initiating rotation")
                
                with self._lock:
                    self.state = SchedulerState.ROTATING
                
                # Trigger rotation callback
                if self.on_rotation_needed:
                    try:
                        self.on_rotation_needed()
                    except Exception as e:
                        logger.error("Rotation callback error: %s", str(e))
                
                break
            
            # Log progress every 30 minutes
            elapsed = (now - self.current_stream_start).total_seconds()
            if int(elapsed) % 1800 == 0 and int(elapsed) > 0:
                hours_remaining = remaining / 3600
                logger.info(
                    "Stream progress: %.1f hours elapsed, %.1f hours remaining",
                    elapsed / 3600,
                    hours_remaining
                )
            
            time.sleep(1)
        
        logger.info("Stream timer stopped")
    
    def stop_timer(self):
        """Stop the stream timer."""
        logger.info("Stopping stream timer")
        
        self._stop_event.set()
        
        if self._timer_thread and self._timer_thread.is_alive():
            self._timer_thread.join(timeout=5)
        
        with self._lock:
            self.state = SchedulerState.IDLE
            self.current_stream_start = None
        
        logger.info("Stream timer stopped")
    
    def get_remaining_time(self) -> Optional[float]:
        """
        Get remaining time in current stream.
        
        Returns:
            Remaining seconds, or None if not streaming
        """
        with self._lock:
            if self.state != SchedulerState.STREAMING or not self.current_stream_start:
                return None
            
            elapsed = (datetime.now(self.timezone) - self.current_stream_start).total_seconds()
            remaining = self.duration_seconds - elapsed
            
            return max(0, remaining)
    
    def get_stream_info(self) -> dict:
        """
        Get current stream information.
        
        Returns:
            Dict with stream state and timing info
        """
        with self._lock:
            info = {
                "state": self.state.value,
                "stream_count": self.stream_count,
                "duration_hours": self.duration_hours,
            }
            
            if self.current_stream_start:
                now = datetime.now(self.timezone)
                elapsed = (now - self.current_stream_start).total_seconds()
                remaining = self.duration_seconds - elapsed
                
                info.update({
                    "start_time": self.current_stream_start.isoformat(),
                    "elapsed_seconds": elapsed,
                    "remaining_seconds": max(0, remaining),
                    "elapsed_hours": elapsed / 3600,
                    "remaining_hours": max(0, remaining) / 3600,
                })
            
            return info
    
    def is_streaming(self) -> bool:
        """Check if currently in streaming state."""
        with self._lock:
            return self.state == SchedulerState.STREAMING
    
    def reset(self):
        """Reset scheduler to initial state."""
        self.stop_timer()
        
        with self._lock:
            self.stream_count = 0
            self.state = SchedulerState.IDLE
        
        logger.info("Scheduler reset")
