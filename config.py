"""Configuration settings for the Service Ticket Auditor."""

from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment or .env file."""
    
    # Google Cloud credentials
    google_credentials_path: Path = Field(
        default=Path("service_account.json"),
        description="Path to Google service account JSON file"
    )
    
    # Google Drive settings
    drive_folder_id: str = Field(
        default="",
        description="Google Drive folder ID containing ticket images"
    )
    
    # Google Sheets settings
    spreadsheet_id: str = Field(
        default="",
        description="Google Sheets spreadsheet ID for audit results"
    )
    
    # OCR settings - define regions where technician name appears
    tech_name_region: dict = Field(
        default={"top": 0, "left": 0, "width": 500, "height": 100},
        description="Region coordinates for technician name extraction"
    )
    
    signature_region: dict = Field(
        default={"top": 800, "left": 0, "width": 600, "height": 200},
        description="Region coordinates for signature detection"
    )
    
    # Scheduling
    audit_schedule_hours: int = Field(
        default=24,
        description="Hours between scheduled audit runs"
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
