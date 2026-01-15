"""Google Cloud authentication module."""

from pathlib import Path
from functools import lru_cache

from google.oauth2 import service_account
from google.cloud import vision
from googleapiclient.discovery import build
import gspread

from config import settings


SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/cloud-vision",
]


@lru_cache()
def get_credentials() -> service_account.Credentials:
    """Load and cache service account credentials."""
    creds_path = Path(settings.google_credentials_path)
    if not creds_path.exists():
        raise FileNotFoundError(
            f"Credentials file not found at {creds_path}. "
            "Please download your service account JSON from Google Cloud Console."
        )
    return service_account.Credentials.from_service_account_file(
        str(creds_path), scopes=SCOPES
    )


def get_drive_service():
    """Get authenticated Google Drive API service."""
    creds = get_credentials()
    return build("drive", "v3", credentials=creds)


def get_vision_client() -> vision.ImageAnnotatorClient:
    """Get authenticated Google Cloud Vision client."""
    creds = get_credentials()
    return vision.ImageAnnotatorClient(credentials=creds)


def get_sheets_client() -> gspread.Client:
    """Get authenticated gspread client for Google Sheets."""
    creds = get_credentials()
    return gspread.authorize(creds)
