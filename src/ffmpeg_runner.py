"""
FFmpeg Container Runner
Controls the FFmpeg container via Docker CLI for RTSP to RTMP streaming.
Uses linuxserver/ffmpeg image for reliable HEVC/H.265 support.

Strategy: Start a new container with the FFmpeg command instead of exec.
"""

import os
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
    FFmpeg container manager for RTSP to RTMP streaming.
    
    Starts a new container with FFmpeg command directly.
    Uses linuxserver/ffmpeg for reliable codec support.
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
        
        # Container names
        self.ffmpeg_container = "camera-ffmpeg-stream"
        self.ffmpeg_image = "linuxserver/ffmpeg:latest"
        
        self.state = FFmpegState.STOPPED
        self.monitor_thread: Optional[threading.Thread] = None
        self.should_stop = threading.Event()
        self.rtmp_url: Optional[str] = None
        
        self._lock = threading.Lock()
    
    def _build_ffmpeg_args(self, rtmp_url: str) -> list:
        """
        Build FFmpeg command arguments.
        
        Args:
            rtmp_url: Full RTMP URL including stream key
            
        Returns:
            List of command arguments
        """
        return [
            "-rtsp_transport", "tcp",
            "-i", self.rtsp_url,
            "-map", "0:v:0",
            "-map", "0:a?",
            "-c:v", "copy",
            "-c:a", "copy",
            "-f", "flv",
            rtmp_url
        ]
    
    def _run_docker_command(self, args: list, timeout: int = 30) -> tuple:
        """
        Run a Docker command.
        
        Returns:
            Tuple of (success, stdout, stderr)
        """
        cmd = ["docker"] + args
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return (result.returncode == 0, result.stdout, result.stderr)
        except subprocess.TimeoutExpired:
            logger.error("Docker command timed out: %s", " ".join(args[:5]))
            return (False, "", "Command timed out")
        except Exception as e:
            logger.error("Docker command failed: %s", str(e))
            return (False, "", str(e))
    
    def _stop_ffmpeg_container(self):
        """Stop and remove the FFmpeg streaming container if it exists."""
        # Stop container
        self._run_docker_command([
            "stop", "-t", "5", self.ffmpeg_container
        ], timeout=10)
        
        # Remove container
        self._run_docker_command([
            "rm", "-f", self.ffmpeg_container
        ], timeout=10)
    
    def _is_container_running(self) -> bool:
        """Check if the FFmpeg container is running."""
        success, stdout, _ = self._run_docker_command([
            "inspect", "-f", "{{.State.Running}}", self.ffmpeg_container
        ], timeout=10)
        return success and stdout.strip() == "true"
    
    def start(self, rtmp_url: str) -> bool:
        """
        Start FFmpeg streaming by creating a new container.
        
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
        
        logger.info("Starting FFmpeg stream via container...")
        logger.info("RTSP URL: %s", self.rtsp_url)
        logger.info("RTMP URL: %s", rtmp_url)
        
        try:
            # Stop any existing container
            self._stop_ffmpeg_container()
            time.sleep(1)
            
            # Build FFmpeg arguments
            ffmpeg_args = self._build_ffmpeg_args(rtmp_url)
            
            logger.info("FFmpeg command: ffmpeg %s", " ".join(ffmpeg_args))
            
            # Start new container with FFmpeg command
            docker_run_cmd = [
                "run", "-d",
                "--name", self.ffmpeg_container,
                "--network", "host",
                "--rm",  # Auto-remove when stopped
                self.ffmpeg_image
            ] + ffmpeg_args
            
            success, stdout, stderr = self._run_docker_command(docker_run_cmd, timeout=30)
            
            if not success:
                logger.error("Failed to start FFmpeg container: %s", stderr)
                with self._lock:
                    self.state = FFmpegState.CRASHED
                return False
            
            container_id = stdout.strip()[:12]
            logger.info("FFmpeg container started: %s", container_id)
            
            # Wait a moment for container to start
            time.sleep(3)
            
            # Verify container is running
            if not self._is_container_running():
                # Get logs to see what went wrong
                _, logs, _ = self._run_docker_command([
                    "logs", "--tail", "20", self.ffmpeg_container
                ], timeout=10)
                logger.error("FFmpeg container not running. Logs: %s", logs)
                with self._lock:
                    self.state = FFmpegState.CRASHED
                return False
            
            with self._lock:
                self.state = FFmpegState.RUNNING
            
            # Start monitor thread
            self.monitor_thread = threading.Thread(
                target=self._monitor_container,
                daemon=True
            )
            self.monitor_thread.start()
            
            logger.info("FFmpeg container is running")
            return True
            
        except Exception as e:
            logger.error("Failed to start FFmpeg: %s", str(e))
            with self._lock:
                self.state = FFmpegState.CRASHED
            return False
    
    def stop(self, timeout: int = 10) -> bool:
        """
        Stop FFmpeg container.
        
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
        
        logger.info("Stopping FFmpeg container...")
        self.should_stop.set()
        
        self._stop_ffmpeg_container()
        
        # Wait for monitor thread to finish
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
        
        with self._lock:
            self.state = FFmpegState.STOPPED
            self.rtmp_url = None
        
        logger.info("FFmpeg fully stopped")
        return True
    
    def _monitor_container(self):
        """Monitor FFmpeg container and detect crashes."""
        logger.info("FFmpeg monitor started")
        
        consecutive_failures = 0
        
        while not self.should_stop.is_set():
            try:
                if not self._is_container_running():
                    if not self.should_stop.is_set():
                        consecutive_failures += 1
                        
                        if consecutive_failures >= 2:
                            # Get logs before declaring crash
                            _, logs, _ = self._run_docker_command([
                                "logs", "--tail", "30", self.ffmpeg_container
                            ], timeout=10)
                            
                            logger.error("FFmpeg container stopped unexpectedly")
                            if logs:
                                logger.error("Last logs: %s", logs)
                            
                            with self._lock:
                                self.state = FFmpegState.CRASHED
                            
                            # Trigger crash callback
                            if self.on_crash:
                                logger.info("Triggering crash callback")
                                try:
                                    self.on_crash()
                                except Exception as e:
                                    logger.error("Crash callback error: %s", str(e))
                            
                            break
                else:
                    consecutive_failures = 0
                
            except Exception as e:
                logger.error("Error monitoring FFmpeg: %s", str(e))
            
            # Check every 5 seconds
            for _ in range(5):
                if self.should_stop.is_set():
                    break
                time.sleep(1)
        
        logger.info("FFmpeg monitor stopped")
    
    def is_running(self) -> bool:
        """Check if FFmpeg is currently running."""
        with self._lock:
            if self.state != FFmpegState.RUNNING:
                return False
        
        return self._is_container_running()
    
    def get_state(self) -> FFmpegState:
        """Get current FFmpeg state."""
        with self._lock:
            return self.state
    
    def restart(self, rtmp_url: Optional[str] = None) -> bool:
        """
        Restart FFmpeg with optional new RTMP URL.
        
        Returns:
            bool: True if restart successful
        """
        logger.info("Restarting FFmpeg...")
        
        new_rtmp_url = rtmp_url or self.rtmp_url
        
        if not new_rtmp_url:
            logger.error("No RTMP URL available for restart")
            return False
        
        self.stop()
        time.sleep(self.reconnect_delay)
        
        return self.start(new_rtmp_url)
    
    def get_logs(self, lines: int = 50) -> str:
        """Get recent logs from FFmpeg container."""
        success, stdout, _ = self._run_docker_command([
            "logs", "--tail", str(lines), self.ffmpeg_container
        ], timeout=10)
        
        return stdout if success else ""
