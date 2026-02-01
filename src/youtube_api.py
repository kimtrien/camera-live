"""
YouTube Data API v3 Client
Handles OAuth2 authentication, livestream creation, broadcast management.
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

TOKEN_FILE = "/app/data/token.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl"
]


class YouTubeAPIError(Exception):
    """Custom exception for YouTube API errors."""
    pass


class YouTubeAPI:
    """
    YouTube Data API v3 client for managing livestreams.
    
    Handles:
    - OAuth2 token management with automatic refresh
    - Creating live streams (RTMP ingest endpoints)
    - Creating live broadcasts
    - Binding streams to broadcasts
    - Transitioning broadcast states
    """
    
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: Optional[str] = None
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.credentials: Optional[Credentials] = None
        self.youtube = None
        
    def authenticate(self) -> bool:
        """
        Authenticate with YouTube API using OAuth2.
        
        Returns:
            bool: True if authentication successful
            
        Raises:
            YouTubeAPIError: If authentication fails
        """
        try:
            # Try to load existing token
            if os.path.exists(TOKEN_FILE):
                logger.info("Loading existing OAuth token from %s", TOKEN_FILE)
                with open(TOKEN_FILE, 'r') as f:
                    token_data = json.load(f)
                    
                self.credentials = Credentials(
                    token=token_data.get('token'),
                    refresh_token=token_data.get('refresh_token'),
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    scopes=SCOPES
                )
            elif self.refresh_token:
                logger.info("Creating credentials from refresh token")
                self.credentials = Credentials(
                    token=None,
                    refresh_token=self.refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    scopes=SCOPES
                )
            else:
                raise YouTubeAPIError(
                    "No token file found and no refresh token provided. "
                    "Please run the OAuth setup first."
                )
            
            # Refresh token if expired
            if self.credentials and (not self.credentials.valid or self.credentials.expired):
                logger.info("Refreshing OAuth token...")
                self.credentials.refresh(Request())
                self._save_token()
                logger.info("Token refreshed successfully")
            
            # Build YouTube API client
            self.youtube = build('youtube', 'v3', credentials=self.credentials)
            logger.info("YouTube API client initialized successfully")
            return True
            
        except Exception as e:
            logger.error("Authentication failed: %s", str(e))
            raise YouTubeAPIError(f"Authentication failed: {str(e)}")
    
    def _save_token(self):
        """Save current credentials to token file."""
        if self.credentials:
            token_data = {
                'token': self.credentials.token,
                'refresh_token': self.credentials.refresh_token,
                'token_uri': self.credentials.token_uri,
                'client_id': self.credentials.client_id,
                'client_secret': self.credentials.client_secret,
                'scopes': list(self.credentials.scopes) if self.credentials.scopes else SCOPES
            }
            
            os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
            with open(TOKEN_FILE, 'w') as f:
                json.dump(token_data, f, indent=2)
            logger.info("Token saved to %s", TOKEN_FILE)
    
    def _api_call_with_retry(self, func, max_retries: int = 3, **kwargs) -> Any:
        """
        Execute API call with retry logic.
        
        Args:
            func: API function to call
            max_retries: Maximum number of retry attempts
            **kwargs: Arguments to pass to the function
            
        Returns:
            API response
            
        Raises:
            YouTubeAPIError: If all retries fail
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                return func(**kwargs).execute()
            except HttpError as e:
                last_error = e
                logger.warning(
                    "API call failed (attempt %d/%d): %s",
                    attempt + 1, max_retries, str(e)
                )
                
                # Check for quota exceeded or permanent errors
                if e.resp.status in [403, 404]:
                    raise YouTubeAPIError(f"API error (non-retryable): {str(e)}")
                    
                # Token might have expired, try refreshing
                if e.resp.status == 401:
                    logger.info("Token expired, refreshing...")
                    try:
                        self.credentials.refresh(Request())
                        self._save_token()
                        self.youtube = build('youtube', 'v3', credentials=self.credentials)
                    except Exception as refresh_error:
                        logger.error("Token refresh failed: %s", str(refresh_error))
                        
            except Exception as e:
                last_error = e
                logger.warning(
                    "API call failed (attempt %d/%d): %s",
                    attempt + 1, max_retries, str(e)
                )
        
        raise YouTubeAPIError(f"API call failed after {max_retries} attempts: {str(last_error)}")
    
    def create_stream(self, title: str) -> Dict[str, str]:
        """
        Create a new YouTube Live Stream (RTMP ingest endpoint).
        
        Args:
            title: Stream title
            
        Returns:
            Dict containing stream_id, rtmp_url, and stream_key
        """
        logger.info("Creating new YouTube stream: %s", title)
        
        stream_body = {
            "snippet": {
                "title": title,
                "description": f"RTMP stream for {title}"
            },
            "cdn": {
                "frameRate": "variable",
                "ingestionType": "rtmp",
                "resolution": "variable"
            }
        }
        
        response = self._api_call_with_retry(
            self.youtube.liveStreams().insert,
            part="snippet,cdn,status",
            body=stream_body
        )
        
        stream_id = response['id']
        ingestion_info = response['cdn']['ingestionInfo']
        rtmp_url = ingestion_info['ingestionAddress']
        stream_key = ingestion_info['streamName']
        
        logger.info(
            "Stream created successfully. ID: %s, RTMP: %s",
            stream_id, rtmp_url
        )
        
        return {
            "stream_id": stream_id,
            "rtmp_url": rtmp_url,
            "stream_key": stream_key,
            "full_rtmp_url": f"{rtmp_url}/{stream_key}"
        }
    
    def create_broadcast(
        self,
        title: str,
        description: str,
        privacy_status: str = "public",
        scheduled_start_time: Optional[datetime] = None
    ) -> str:
        """
        Create a new YouTube Live Broadcast.
        
        Args:
            title: Broadcast title
            description: Broadcast description
            privacy_status: One of "public", "unlisted", "private"
            scheduled_start_time: When the broadcast should start
            
        Returns:
            Broadcast ID
        """
        logger.info("Creating new broadcast: %s (privacy: %s)", title, privacy_status)
        
        if scheduled_start_time is None:
            scheduled_start_time = datetime.utcnow()
        
        broadcast_body = {
            "snippet": {
                "title": title,
                "description": description,
                "scheduledStartTime": scheduled_start_time.isoformat() + "Z"
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False
            },
            "contentDetails": {
                "enableAutoStart": True,
                "enableAutoStop": False,
                "monitorStream": {
                    "enableMonitorStream": False
                }
            }
        }
        
        response = self._api_call_with_retry(
            self.youtube.liveBroadcasts().insert,
            part="snippet,status,contentDetails",
            body=broadcast_body
        )
        
        broadcast_id = response['id']
        logger.info("Broadcast created successfully. ID: %s", broadcast_id)
        
        return broadcast_id
    
    def bind_stream_to_broadcast(self, broadcast_id: str, stream_id: str) -> bool:
        """
        Bind a live stream to a broadcast.
        
        Args:
            broadcast_id: The broadcast ID
            stream_id: The stream ID
            
        Returns:
            bool: True if binding successful
        """
        logger.info("Binding stream %s to broadcast %s", stream_id, broadcast_id)
        
        self._api_call_with_retry(
            self.youtube.liveBroadcasts().bind,
            id=broadcast_id,
            part="id,contentDetails",
            streamId=stream_id
        )
        
        logger.info("Stream bound to broadcast successfully")
        return True
    
    def get_stream_status(self, stream_id: str) -> str:
        """
        Get the current status of a stream.
        
        Args:
            stream_id: The stream ID
            
        Returns:
            Stream status string
        """
        response = self._api_call_with_retry(
            self.youtube.liveStreams().list,
            part="status",
            id=stream_id
        )
        
        if response.get('items'):
            status = response['items'][0]['status']['streamStatus']
            logger.debug("Stream %s status: %s", stream_id, status)
            return status
        
        return "unknown"
    
    def get_broadcast_status(self, broadcast_id: str) -> str:
        """
        Get the current status of a broadcast.
        
        Args:
            broadcast_id: The broadcast ID
            
        Returns:
            Broadcast lifecycle status
        """
        response = self._api_call_with_retry(
            self.youtube.liveBroadcasts().list,
            part="status",
            id=broadcast_id
        )
        
        if response.get('items'):
            status = response['items'][0]['status']['lifeCycleStatus']
            logger.debug("Broadcast %s status: %s", broadcast_id, status)
            return status
        
        return "unknown"
    
    def transition_broadcast(self, broadcast_id: str, status: str) -> bool:
        """
        Transition a broadcast to a new status.
        
        Args:
            broadcast_id: The broadcast ID
            status: Target status ("testing", "live", "complete")
            
        Returns:
            bool: True if transition successful
        """
        logger.info("Transitioning broadcast %s to %s", broadcast_id, status)
        
        self._api_call_with_retry(
            self.youtube.liveBroadcasts().transition,
            broadcastStatus=status,
            id=broadcast_id,
            part="id,status"
        )
        
        logger.info("Broadcast transitioned to %s successfully", status)
        return True
    
    def complete_broadcast(self, broadcast_id: str) -> bool:
        """
        Complete/end a broadcast.
        
        Args:
            broadcast_id: The broadcast ID
            
        Returns:
            bool: True if successful
        """
        return self.transition_broadcast(broadcast_id, "complete")
    
    def create_livestream(
        self,
        title: str,
        description: str,
        privacy_status: str = "public"
    ) -> Tuple[str, str, str]:
        """
        Create a complete livestream setup (stream + broadcast + binding).
        
        This is a convenience method that:
        1. Creates a new live stream
        2. Creates a new broadcast
        3. Binds them together
        
        Args:
            title: Livestream title
            description: Livestream description
            privacy_status: Privacy status
            
        Returns:
            Tuple of (broadcast_id, stream_id, full_rtmp_url)
        """
        logger.info("Creating complete livestream setup: %s", title)
        
        # Create stream
        stream_info = self.create_stream(title)
        stream_id = stream_info['stream_id']
        full_rtmp_url = stream_info['full_rtmp_url']
        
        # Create broadcast
        broadcast_id = self.create_broadcast(
            title=title,
            description=description,
            privacy_status=privacy_status
        )
        
        # Bind stream to broadcast
        self.bind_stream_to_broadcast(broadcast_id, stream_id)
        
        logger.info(
            "Livestream setup complete. Broadcast: %s, Stream: %s",
            broadcast_id, stream_id
        )
        
        return broadcast_id, stream_id, full_rtmp_url
    
    def delete_stream(self, stream_id: str) -> bool:
        """
        Delete a live stream.
        
        Args:
            stream_id: The stream ID to delete
            
        Returns:
            bool: True if deletion successful
        """
        logger.info("Deleting stream: %s", stream_id)
        
        try:
            self._api_call_with_retry(
                self.youtube.liveStreams().delete,
                id=stream_id
            )
            logger.info("Stream %s deleted successfully", stream_id)
            return True
        except YouTubeAPIError as e:
            logger.warning("Failed to delete stream %s: %s", stream_id, str(e))
            return False
