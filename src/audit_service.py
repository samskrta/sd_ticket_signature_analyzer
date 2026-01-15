"""Main audit orchestration service."""

from datetime import datetime
from typing import Callable
import re

from rich.console import Console
from rich.progress import Progress, TaskID

from src.drive_client import DriveClient, DriveImage
from src.vision_analyzer import VisionAnalyzer, AnalysisResult
from src.sheets_writer import SheetsWriter, AuditRecord


console = Console()


class AuditService:
    """Orchestrates the audit process from Drive to Sheets."""
    
    def __init__(
        self,
        drive_folder_id: str | None = None,
        spreadsheet_id: str | None = None
    ):
        self.drive = DriveClient(folder_id=drive_folder_id)
        self.analyzer = VisionAnalyzer()
        self.sheets = SheetsWriter(spreadsheet_id=spreadsheet_id)
    
    def run_audit(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        skip_processed: bool = True,
        progress_callback: Callable[[str, int, int], None] | None = None
    ) -> list[AuditRecord]:
        """
        Run the audit process on images in Google Drive.
        
        Args:
            since: Only process images modified after this time
            until: Only process images modified before this time
            skip_processed: Skip images already in the audit log
            progress_callback: Called with (image_name, current, total)
            
        Returns:
            List of AuditRecord objects that were processed
        """
        # Get list of images to process
        console.print("[blue]Fetching image list from Google Drive...[/blue]")
        images = list(self.drive.list_images(since=since, until=until))
        
        if not images:
            console.print("[yellow]No images found in the specified date range.[/yellow]")
            return []
        
        console.print(f"[green]Found {len(images)} images[/green]")
        
        # Get already processed IDs if skipping
        processed_ids = set()
        if skip_processed:
            processed_ids = self.sheets.get_processed_image_ids()
            console.print(f"[dim]Skipping {len(processed_ids)} already-processed images[/dim]")
        
        # Filter out already processed
        images_to_process = [img for img in images if img.id not in processed_ids]
        
        if not images_to_process:
            console.print("[yellow]All images have already been processed.[/yellow]")
            return []
        
        console.print(f"[blue]Processing {len(images_to_process)} new images...[/blue]")
        
        records: list[AuditRecord] = []
        
        with Progress() as progress:
            task = progress.add_task(
                "[cyan]Analyzing tickets...", 
                total=len(images_to_process)
            )
            
            for i, image in enumerate(images_to_process):
                try:
                    record = self._process_image(image)
                    records.append(record)
                    
                    if progress_callback:
                        progress_callback(image.name, i + 1, len(images_to_process))
                    
                except Exception as e:
                    console.print(f"[red]Error processing {image.name}: {e}[/red]")
                
                progress.update(task, advance=1)
        
        # Write records to sheets
        if records:
            console.print(f"[blue]Writing {len(records)} records to Google Sheets...[/blue]")
            self.sheets.write_audit_records(records)
            console.print("[green]✓ Audit complete![/green]")
        
        return records
    
    def _process_image(self, image: DriveImage) -> AuditRecord:
        """Process a single image and return an AuditRecord."""
        # Download the image content
        image = self.drive.download_image(image)
        
        # Analyze with Vision API
        result = self.analyzer.analyze(image)
        
        # Extract ticket date from filename if possible
        ticket_date = self._extract_date_from_filename(image.name)
        
        return AuditRecord(
            image_id=image.id,
            filename=image.name,
            technician_name=result.technician_name,
            has_signature=result.has_signature,
            confidence=result.confidence,
            audit_date=datetime.now(),
            ticket_date=ticket_date or image.created_time,
        )
    
    def _extract_date_from_filename(self, filename: str) -> datetime | None:
        """Try to extract a date from the filename."""
        # Common date patterns in filenames
        patterns = [
            r"(\d{4}-\d{2}-\d{2})",  # 2026-01-13
            r"(\d{2}-\d{2}-\d{4})",  # 01-13-2026
            r"(\d{8})",              # 20260113
            r"(\d{2})(\d{2})(\d{4})",  # 01132026
        ]
        
        for pattern in patterns:
            match = re.search(pattern, filename)
            if match:
                try:
                    date_str = match.group(0)
                    # Try different formats
                    for fmt in ["%Y-%m-%d", "%m-%d-%Y", "%Y%m%d", "%m%d%Y"]:
                        try:
                            return datetime.strptime(date_str, fmt)
                        except ValueError:
                            continue
                except Exception:
                    pass
        
        return None
    
    def process_single_image(self, file_id: str) -> AuditRecord:
        """Process a single image by its Drive file ID."""
        image = self.drive.get_image_by_id(file_id)
        record = self._process_image(image)
        self.sheets.write_audit_record(record)
        return record
