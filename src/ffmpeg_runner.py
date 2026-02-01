"""
FFmpeg Process Runner
Handles RTSP to RTMP streaming with process management.
"""

import os
import signal
import subprocess
import threading
import logging
import time
from typing import Optional, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class FFmpegState(Enum):
    """FFmpeg process states."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    CRASHED = "crashed"


class FFmpegRunner:
    """
    FFmpeg process manager for RTSP to RTMP streaming.
    
    Features:
    - Stream copy (no transcoding)
    - RTSP over TCP
    - Process monitoring
    - Graceful shutdown
    - Crash detection with callbacks
    """
    
    def __init__(
        self,
        rtsp_url: str,
        on_crash: Optional[Callable[[], None]] = None,
        reconnect_delay: int = 5
    ):
        """
        Initialize FFmpeg runner.
        
        Args:
            rtsp_url: RTSP camera URL
            on_crash: Callback function when FFmpeg crashes
            reconnect_delay: Delay in seconds before reconnect attempts
        """
        self.rtsp_url = rtsp_url
        self.on_crash = on_crash
        self.reconnect_delay = reconnect_delay
        
        self.process: Optional[subprocess.Popen] = None
        self.state = FFmpegState.STOPPED
        self.monitor_thread: Optional[threading.Thread] = None
        self.should_stop = threading.Event()
        self.rtmp_url: Optional[str] = None
        
        self._lock = threading.Lock()
    
    def _build_command(self, rtmp_url: str) -> list:
        """
        Build FFmpeg command for RTSP to RTMP streaming.
        
        Args:
            rtmp_url: Full RTMP URL including stream key
            
        Returns:
            List of command arguments
        """
        cmd = [
            "ffmpeg",
            # Input options
            "-rtsp_transport", "tcp",           # Use TCP for RTSP
            "-i", self.rtsp_url,                # RTSP input
            
            # Reconnection options
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            
            # Output options - no transcoding
            "-c:v", "copy",                     # Copy video codec
            "-c:a", "copy",                     # Copy audio codec
            
            # RTMP output settings
            "-f", "flv",                        # FLV format for RTMP
            "-flvflags", "no_duration_filesize",
            
            # Buffer settings
            "-bufsize", "3000k",
            "-maxrate", "3000k",
            
            # Overwrite output
            "-y",
            
            rtmp_url
        ]
        
        return cmd
    
    def start(self, rtmp_url: str) -> bool:
        """
        Start FFmpeg streaming process.
        
        Args:
            rtmp_url: Full RTMP URL including stream key
            
        Returns:
            bool: True if started successfully
        """
        with self._lock:
            if self.state in [FFmpegState.RUNNING, FFmpegState.STARTING]:
                logger.warning("FFmpeg is already running or starting")
                return False
            
            self.state = FFmpegState.STARTING
            self.rtmp_url = rtmp_url
            self.should_stop.clear()
        
        logger.info("Starting FFmpeg stream...")
        logger.info("RTSP URL: %s", self.rtsp_url)
        logger.info("RTMP URL: %s", rtmp_url)
        
        try:
            cmd = self._build_command(rtmp_url)
            logger.debug("FFmpeg command: %s", " ".join(cmd))
            
            # Start FFmpeg process
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE
            )
            
            with self._lock:
                self.state = FFmpegState.RUNNING
            
            # Start monitor thread
            self.monitor_thread = threading.Thread(
                target=self._monitor_process,
                daemon=True
            )
            self.monitor_thread.start()
            
            logger.info("FFmpeg started with PID: %d", self.process.pid)
            return True
            
        except Exception as e:
            logger.error("Failed to start FFmpeg: %s", str(e))
            with self._lock:
                self.state = FFmpegState.CRASHED
            return False
    
    def stop(self, timeout: int = 10) -> bool:
        """
        Stop FFmpeg process gracefully.
        
        Args:
            timeout: Maximum seconds to wait for graceful shutdown
            
        Returns:
            bool: True if stopped successfully
        """
        with self._lock:
            if self.state == FFmpegState.STOPPED:
                logger.info("FFmpeg is already stopped")
                return True
            
            if self.state == FFmpegState.STOPPING:
                logger.info("FFmpeg is already stopping")
                return True
                
            self.state = FFmpegState.STOPPING
        
        logger.info("Stopping FFmpeg...")
        self.should_stop.set()
        
        if self.process:
            try:
                # Send 'q' to FFmpeg for graceful shutdown
                if self.process.stdin:
                    try:
                        self.process.stdin.write(b'q')
                        self.process.stdin.flush()
                    except Exception:
                        pass
                
                # Wait for process to terminate
                try:
                    self.process.wait(timeout=timeout)
                    logger.info("FFmpeg stopped gracefully")
                except subprocess.TimeoutExpired:
                    logger.warning("FFmpeg did not stop gracefully, sending SIGTERM")
                    self.process.terminate()
                    
                    try:
                        self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        logger.warning("FFmpeg did not respond to SIGTERM, sending SIGKILL")
                        self.process.kill()
                        self.process.wait()
                
            except Exception as e:
                logger.error("Error stopping FFmpeg: %s", str(e))
                if self.process:
                    try:
                        self.process.kill()
                    except Exception:
                        pass
        
        # Wait for monitor thread to finish
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
        
        with self._lock:
            self.state = FFmpegState.STOPPED
            self.process = None
            self.rtmp_url = None
        
        logger.info("FFmpeg fully stopped")
        return True
    
    def _monitor_process(self):
        """Monitor FFmpeg process and detect crashes."""
        logger.info("FFmpeg monitor started")
        
        stderr_lines = []
        
        while not self.should_stop.is_set():
            if self.process is None:
                break
            
            # Check if process is still running
            return_code = self.process.poll()
            
            if return_code is not None:
                # Process has terminated
                if not self.should_stop.is_set():
                    # Collect stderr for debugging
                    if self.process.stderr:
                        try:
                            for line in self.process.stderr:
                                stderr_lines.append(line.decode('utf-8', errors='ignore'))
                                if len(stderr_lines) > 50:
                                    stderr_lines.pop(0)
                        except Exception:
                            pass
                    
                    logger.error(
                        "FFmpeg crashed with return code: %d",
                        return_code
                    )
                    if stderr_lines:
                        logger.error(
                            "Last FFmpeg output:\n%s",
                            "".join(stderr_lines[-20:])
                        )
                    
                    with self._lock:
                        self.state = FFmpegState.CRASHED
                        self.process = None
                    
                    # Trigger crash callback
                    if self.on_crash:
                        logger.info("Triggering crash callback")
                        try:
                            self.on_crash()
                        except Exception as e:
                            logger.error("Crash callback error: %s", str(e))
                
                break
            
            # Read stderr non-blocking for logging
            if self.process.stderr:
                try:
                    line = self.process.stderr.readline()
                    if line:
                        decoded = line.decode('utf-8', errors='ignore').strip()
                        if decoded:
                            # Log important messages
                            if any(x in decoded.lower() for x in ['error', 'warning', 'failed']):
                                logger.warning("FFmpeg: %s", decoded)
                            else:
                                logger.debug("FFmpeg: %s", decoded)
                except Exception:
                    pass
            
            time.sleep(1)
        
        logger.info("FFmpeg monitor stopped")
    
    def is_running(self) -> bool:
        """Check if FFmpeg is currently running."""
        with self._lock:
            return self.state == FFmpegState.RUNNING and self.process is not None
    
    def get_state(self) -> FFmpegState:
        """Get current FFmpeg state."""
        with self._lock:
            return self.state
    
    def restart(self, rtmp_url: Optional[str] = None) -> bool:
        """
        Restart FFmpeg with optional new RTMP URL.
        
        Args:
            rtmp_url: New RTMP URL (uses previous if not provided)
            
        Returns:
            bool: True if restart successful
        """
        logger.info("Restarting FFmpeg...")
        
        # Use provided URL or fallback to previous
        new_rtmp_url = rtmp_url or self.rtmp_url
        
        if not new_rtmp_url:
            logger.error("No RTMP URL available for restart")
            return False
        
        # Stop current process
        self.stop()
        
        # Brief delay before restart
        time.sleep(self.reconnect_delay)
        
        # Start with new/same URL
        return self.start(new_rtmp_url)
