
import os
import sys
import logging
from dotenv import load_dotenv

# Add current directory to path so we can import modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ffmpeg_runner import FFmpegRunner

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

def check_rtsp():
    """Check if RTSP stream is available using FFmpegRunner."""
    
    # Load environment variables
    # Check for .env in current directory or parent directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    
    if os.path.exists(os.path.join(current_dir, ".env")):
        load_dotenv(os.path.join(current_dir, ".env"))
    elif os.path.exists(os.path.join(parent_dir, ".env")):
        load_dotenv(os.path.join(parent_dir, ".env"))
    else:
        logger.warning("No .env file found. Relying on system environment variables.")

    rtsp_url = os.getenv("RTSP_URL")
    
    if not rtsp_url:
        logger.error("RTSP_URL not found in environment variables.")
        return False
        
    logger.info(f"Checking RTSP URL: {rtsp_url.split('@')[-1] if '@' in rtsp_url else rtsp_url}") # Simple masking
    
    runner = FFmpegRunner(rtsp_url=rtsp_url)
    is_available = runner.check_stream_availability(timeout=10)
    
    if is_available:
        logger.info("✅ Stream is UP and reachable.")
        return True
    else:
        logger.error("❌ Stream is DOWN or unreachable.")
        return False

if __name__ == "__main__":
    if check_rtsp():
        sys.exit(0)
    else:
        sys.exit(1)
