"""Local filesystem scanner for ticket images."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator
import re


@dataclass
class TicketImage:
    """Represents a ticket image from local filesystem."""
    path: Path
    ticket_number: str
    variant: str  # a, b, c, d suffix
    month_folder: str  # YYYY-MM
    modified_time: datetime
    
    @property
    def content(self) -> bytes:
        """Load image content on demand."""
        return self.path.read_bytes()


class LocalScanner:
    """Scans local filesystem for ticket images."""
    
    def __init__(self, tickets_root: str | Path):
        self.root = Path(tickets_root)
        if not self.root.exists():
            raise FileNotFoundError(f"Tickets folder not found: {self.root}")
    
    def list_month_folders(self) -> list[str]:
        """List all YYYY-MM folders."""
        folders = []
        for item in sorted(self.root.iterdir()):
            if item.is_dir() and re.match(r"\d{4}-\d{2}", item.name):
                folders.append(item.name)
        return folders
    
    def scan_folder(self, month_folder: str) -> Iterator[TicketImage]:
        """
        Scan a specific month folder for ticket images.
        
        Args:
            month_folder: YYYY-MM format folder name
            
        Yields:
            TicketImage objects
        """
        folder_path = self.root / month_folder
        if not folder_path.exists():
            return
        
        # Pattern: 123456a.png, 123456b.png, etc.
        pattern = re.compile(r"^(\d+)([a-z])\.png$", re.IGNORECASE)
        
        for file_path in sorted(folder_path.glob("*.png")):
            match = pattern.match(file_path.name)
            if match:
                ticket_num, variant = match.groups()
                stat = file_path.stat()
                
                yield TicketImage(
                    path=file_path,
                    ticket_number=ticket_num,
                    variant=variant.lower(),
                    month_folder=month_folder,
                    modified_time=datetime.fromtimestamp(stat.st_mtime),
                )
    
    def scan_all(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        months: list[str] | None = None,
    ) -> Iterator[TicketImage]:
        """
        Scan all folders for ticket images.
        
        Args:
            since: Only return images modified after this time
            until: Only return images modified before this time
            months: Specific YYYY-MM folders to scan (or all if None)
            
        Yields:
            TicketImage objects
        """
        folders = months or self.list_month_folders()
        
        for folder in folders:
            for image in self.scan_folder(folder):
                if since and image.modified_time < since:
                    continue
                if until and image.modified_time > until:
                    continue
                yield image
    
    def get_image(self, ticket_number: str, variant: str, month: str) -> TicketImage | None:
        """Get a specific ticket image."""
        filename = f"{ticket_number}{variant}.png"
        file_path = self.root / month / filename
        
        if not file_path.exists():
            return None
        
        stat = file_path.stat()
        return TicketImage(
            path=file_path,
            ticket_number=ticket_number,
            variant=variant,
            month_folder=month,
            modified_time=datetime.fromtimestamp(stat.st_mtime),
        )
    
    def count_by_month(self) -> dict[str, int]:
        """Count tickets per month folder."""
        counts = {}
        for folder in self.list_month_folders():
            folder_path = self.root / folder
            count = len(list(folder_path.glob("*.png")))
            counts[folder] = count
        return counts
