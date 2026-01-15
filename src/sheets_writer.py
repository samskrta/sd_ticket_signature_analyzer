"""Google Sheets client for storing audit results."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
import gspread
from gspread import Worksheet

from src.auth import get_sheets_client
from config import settings


@dataclass
class AuditRecord:
    """A single audit record to be written to sheets."""
    image_id: str
    filename: str
    technician_name: str | None
    has_signature: bool
    confidence: float
    audit_date: datetime
    ticket_date: datetime | None = None
    
    def to_row(self) -> list[Any]:
        """Convert to a row for Google Sheets."""
        return [
            self.image_id,
            self.filename,
            self.technician_name or "UNKNOWN",
            "Yes" if self.has_signature else "No",
            round(self.confidence, 2),
            self.audit_date.strftime("%Y-%m-%d %H:%M:%S"),
            self.ticket_date.strftime("%Y-%m-%d") if self.ticket_date else "",
        ]


class SheetsWriter:
    """Client for writing audit results to Google Sheets."""
    
    AUDIT_LOG_SHEET = "Audit Log"
    DAILY_ROLLUP_SHEET = "Daily Rollup"
    SUMMARY_SHEET = "Summary"
    
    AUDIT_LOG_HEADERS = [
        "Image ID",
        "Filename",
        "Technician",
        "Signature Present",
        "Confidence",
        "Audit Date",
        "Ticket Date",
    ]
    
    DAILY_ROLLUP_HEADERS = [
        "Date",
        "Technician",
        "Total Tickets",
        "With Signature",
        "Without Signature",
        "Signature Rate %",
    ]
    
    SUMMARY_HEADERS = [
        "Technician",
        "Total Tickets",
        "With Signature",
        "Without Signature",
        "Signature Rate %",
        "Last Updated",
    ]
    
    def __init__(self, spreadsheet_id: str | None = None):
        self.client = get_sheets_client()
        self.spreadsheet_id = spreadsheet_id or settings.spreadsheet_id
        
        if not self.spreadsheet_id:
            raise ValueError(
                "Spreadsheet ID not configured. Set SPREADSHEET_ID in .env "
                "or pass spreadsheet_id to SheetsWriter."
            )
        
        self.spreadsheet = self.client.open_by_key(self.spreadsheet_id)
        self._ensure_sheets_exist()
    
    def _ensure_sheets_exist(self):
        """Create required sheets if they don't exist."""
        existing_sheets = [ws.title for ws in self.spreadsheet.worksheets()]
        
        if self.AUDIT_LOG_SHEET not in existing_sheets:
            ws = self.spreadsheet.add_worksheet(
                title=self.AUDIT_LOG_SHEET, rows=1000, cols=10
            )
            ws.append_row(self.AUDIT_LOG_HEADERS)
            ws.format("A1:G1", {"textFormat": {"bold": True}})
        
        if self.DAILY_ROLLUP_SHEET not in existing_sheets:
            ws = self.spreadsheet.add_worksheet(
                title=self.DAILY_ROLLUP_SHEET, rows=1000, cols=10
            )
            ws.append_row(self.DAILY_ROLLUP_HEADERS)
            ws.format("A1:F1", {"textFormat": {"bold": True}})
        
        if self.SUMMARY_SHEET not in existing_sheets:
            ws = self.spreadsheet.add_worksheet(
                title=self.SUMMARY_SHEET, rows=100, cols=10
            )
            ws.append_row(self.SUMMARY_HEADERS)
            ws.format("A1:F1", {"textFormat": {"bold": True}})
    
    def _get_sheet(self, name: str) -> Worksheet:
        """Get a worksheet by name."""
        return self.spreadsheet.worksheet(name)
    
    def write_audit_record(self, record: AuditRecord):
        """Write a single audit record to the audit log."""
        ws = self._get_sheet(self.AUDIT_LOG_SHEET)
        ws.append_row(record.to_row())
    
    def write_audit_records(self, records: list[AuditRecord]):
        """Write multiple audit records efficiently."""
        if not records:
            return
        
        ws = self._get_sheet(self.AUDIT_LOG_SHEET)
        rows = [r.to_row() for r in records]
        ws.append_rows(rows)
    
    def get_all_audit_records(self) -> list[dict]:
        """Fetch all audit records from the sheet."""
        ws = self._get_sheet(self.AUDIT_LOG_SHEET)
        records = ws.get_all_records()
        return records
    
    def get_processed_image_ids(self) -> set[str]:
        """Get set of already-processed image IDs to avoid duplicates."""
        ws = self._get_sheet(self.AUDIT_LOG_SHEET)
        # Get all values in column A (Image ID), skip header
        image_ids = ws.col_values(1)[1:]
        return set(image_ids)
    
    def update_daily_rollup(self, rollup_data: list[dict]):
        """
        Update the daily rollup sheet.
        
        Args:
            rollup_data: List of dicts with keys:
                - date: str
                - technician: str
                - total: int
                - with_sig: int
                - without_sig: int
                - rate: float
        """
        ws = self._get_sheet(self.DAILY_ROLLUP_SHEET)
        
        # Clear existing data (keep header)
        ws.batch_clear(["A2:F1000"])
        
        if not rollup_data:
            return
        
        rows = [
            [
                d["date"],
                d["technician"],
                d["total"],
                d["with_sig"],
                d["without_sig"],
                round(d["rate"], 1),
            ]
            for d in rollup_data
        ]
        
        ws.append_rows(rows)
    
    def update_summary(self, summary_data: list[dict]):
        """
        Update the summary sheet.
        
        Args:
            summary_data: List of dicts with keys:
                - technician: str
                - total: int
                - with_sig: int
                - without_sig: int
                - rate: float
        """
        ws = self._get_sheet(self.SUMMARY_SHEET)
        
        # Clear existing data (keep header)
        ws.batch_clear(["A2:F100"])
        
        if not summary_data:
            return
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = [
            [
                d["technician"],
                d["total"],
                d["with_sig"],
                d["without_sig"],
                round(d["rate"], 1),
                now,
            ]
            for d in summary_data
        ]
        
        ws.append_rows(rows)
