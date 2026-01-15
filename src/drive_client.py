"""Google Drive client for fetching service ticket images."""

from dataclasses import dataclass
from datetime import datetime
from typing import Iterator
import io

from googleapiclient.http import MediaIoBaseDownload

from src.auth import get_drive_service
from config import settings


@dataclass
class DriveImage:
    """Represents an image file from Google Drive."""
    id: str
    name: str
    created_time: datetime
    modified_time: datetime
    content: bytes | None = None


class DriveClient:
    """Client for interacting with Google Drive to fetch ticket images."""
    
    def __init__(self, folder_id: str | None = None):
        self.service = get_drive_service()
        self.folder_id = folder_id or settings.drive_folder_id
        
        if not self.folder_id:
            raise ValueError(
                "Drive folder ID not configured. Set DRIVE_FOLDER_ID in .env "
                "or pass folder_id to DriveClient."
            )
    
    def list_images(
        self,
        since: datetime | None = None,
        until: datetime | None = None
    ) -> Iterator[DriveImage]:
        """
        List PNG images in the configured folder.
        
        Args:
            since: Only return images modified after this time
            until: Only return images modified before this time
            
        Yields:
            DriveImage objects (without content loaded)
        """
        query_parts = [
            f"'{self.folder_id}' in parents",
            "mimeType='image/png'",
            "trashed=false"
        ]
        
        if since:
            query_parts.append(f"modifiedTime > '{since.isoformat()}Z'")
        if until:
            query_parts.append(f"modifiedTime < '{until.isoformat()}Z'")
        
        query = " and ".join(query_parts)
        page_token = None
        
        while True:
            response = self.service.files().list(
                q=query,
                spaces="drive",
                fields="nextPageToken, files(id, name, createdTime, modifiedTime)",
                pageToken=page_token,
                pageSize=100
            ).execute()
            
            for file in response.get("files", []):
                yield DriveImage(
                    id=file["id"],
                    name=file["name"],
                    created_time=datetime.fromisoformat(
                        file["createdTime"].rstrip("Z")
                    ),
                    modified_time=datetime.fromisoformat(
                        file["modifiedTime"].rstrip("Z")
                    )
                )
            
            page_token = response.get("nextPageToken")
            if not page_token:
                break
    
    def download_image(self, image: DriveImage) -> DriveImage:
        """
        Download the content of a DriveImage.
        
        Args:
            image: DriveImage to download
            
        Returns:
            DriveImage with content populated
        """
        request = self.service.files().get_media(fileId=image.id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        
        done = False
        while not done:
            _, done = downloader.next_chunk()
        
        buffer.seek(0)
        image.content = buffer.read()
        return image
    
    def get_image_by_id(self, file_id: str) -> DriveImage:
        """Fetch a specific image by its Drive file ID."""
        file = self.service.files().get(
            fileId=file_id,
            fields="id, name, createdTime, modifiedTime"
        ).execute()
        
        image = DriveImage(
            id=file["id"],
            name=file["name"],
            created_time=datetime.fromisoformat(file["createdTime"].rstrip("Z")),
            modified_time=datetime.fromisoformat(file["modifiedTime"].rstrip("Z"))
        )
        return self.download_image(image)
