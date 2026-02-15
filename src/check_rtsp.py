
import os
import sys
import logging
import argparse
from dotenv import load_dotenv

# Add current directory to path so we can import modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ffmpeg_runner import FFmpegRunner

def setup_logging(debug: bool = False):
    """Configure logging based on debug flag."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True # Ensure we overwrite any previous config
    )
    # Set ffmpeg_runner logger to DEBUG if requested
    if debug:
        logging.getLogger("ffmpeg_runner").setLevel(logging.DEBUG)

def check_rtsp(debug: bool = False):
    """Check if RTSP stream is available using FFmpegRunner."""
    setup_logging(debug)
    logger = logging.getLogger(__name__)
    
    # Load environment variables
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
        
    masked_url = rtsp_url.split('@')[-1] if '@' in rtsp_url else rtsp_url
    logger.info(f"Checking RTSP URL: {masked_url}")
    
    runner = FFmpegRunner(rtsp_url=rtsp_url)
    is_available = runner.check_stream_availability(timeout=10)
    
    if is_available:
        logger.info("✅ Stream is UP and reachable.")
        return True
    else:
        logger.error("❌ Stream is DOWN or unreachable.")
        if debug:
            logger.debug("Tip: Check if the RTSP URL is correct and the camera is online.")
            logger.debug("Tip: Ensure no firewall is blocking the connection.")
        else:
            logger.info("Run with --debug for more details.")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check RTSP stream availability.")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()
    
    if check_rtsp(debug=args.debug):
        sys.exit(0)
    else:
        sys.exit(1)
