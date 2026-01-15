"""SQLite database for local audit storage."""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator


@dataclass
class AuditRecord:
    """A single audit record."""
    id: int | None
    ticket_number: str
    variant: str
    month_folder: str
    file_path: str
    technician_name: str | None
    technician_role: str | None
    has_signature: bool
    signature_confidence: float
    ticket_date: str | None
    audit_date: datetime
    has_legal_text: bool


class AuditDatabase:
    """SQLite database for storing audit records locally."""
    
    def __init__(self, db_path: str | Path = "audit.db"):
        self.db_path = Path(db_path)
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_number TEXT NOT NULL,
                    variant TEXT NOT NULL,
                    month_folder TEXT NOT NULL,
                    file_path TEXT NOT NULL UNIQUE,
                    technician_name TEXT,
                    technician_role TEXT,
                    has_signature INTEGER NOT NULL,
                    signature_confidence REAL NOT NULL,
                    ticket_date TEXT,
                    audit_date TEXT NOT NULL,
                    has_legal_text INTEGER NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_month ON audit_records(month_folder)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tech ON audit_records(technician_name)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ticket ON audit_records(ticket_number)
            """)
    
    @contextmanager
    def _connect(self):
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    
    def insert_record(self, record: AuditRecord) -> int:
        """Insert a new audit record."""
        with self._connect() as conn:
            cursor = conn.execute("""
                INSERT OR REPLACE INTO audit_records (
                    ticket_number, variant, month_folder, file_path,
                    technician_name, technician_role, has_signature,
                    signature_confidence, ticket_date, audit_date, has_legal_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.ticket_number,
                record.variant,
                record.month_folder,
                record.file_path,
                record.technician_name,
                record.technician_role,
                1 if record.has_signature else 0,
                record.signature_confidence,
                record.ticket_date,
                record.audit_date.isoformat(),
                1 if record.has_legal_text else 0,
            ))
            return cursor.lastrowid
    
    def insert_records(self, records: list[AuditRecord]):
        """Insert multiple records efficiently."""
        with self._connect() as conn:
            conn.executemany("""
                INSERT OR REPLACE INTO audit_records (
                    ticket_number, variant, month_folder, file_path,
                    technician_name, technician_role, has_signature,
                    signature_confidence, ticket_date, audit_date, has_legal_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    r.ticket_number, r.variant, r.month_folder, r.file_path,
                    r.technician_name, r.technician_role,
                    1 if r.has_signature else 0, r.signature_confidence,
                    r.ticket_date, r.audit_date.isoformat(),
                    1 if r.has_legal_text else 0,
                )
                for r in records
            ])
    
    def get_processed_paths(self) -> set[str]:
        """Get set of already-processed file paths."""
        with self._connect() as conn:
            cursor = conn.execute("SELECT file_path FROM audit_records")
            return {row["file_path"] for row in cursor}
    
    def get_all_records(self) -> list[AuditRecord]:
        """Fetch all audit records."""
        with self._connect() as conn:
            cursor = conn.execute("SELECT * FROM audit_records ORDER BY month_folder, ticket_number")
            return [self._row_to_record(row) for row in cursor]
    
    def get_records_by_month(self, month: str) -> list[AuditRecord]:
        """Get records for a specific month."""
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM audit_records WHERE month_folder = ? ORDER BY ticket_number",
                (month,)
            )
            return [self._row_to_record(row) for row in cursor]
    
    def get_records_by_technician(self, tech_name: str) -> list[AuditRecord]:
        """Get records for a specific technician."""
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM audit_records WHERE technician_name = ? ORDER BY month_folder",
                (tech_name,)
            )
            return [self._row_to_record(row) for row in cursor]
    
    def _row_to_record(self, row: sqlite3.Row) -> AuditRecord:
        """Convert database row to AuditRecord."""
        return AuditRecord(
            id=row["id"],
            ticket_number=row["ticket_number"],
            variant=row["variant"],
            month_folder=row["month_folder"],
            file_path=row["file_path"],
            technician_name=row["technician_name"],
            technician_role=row["technician_role"],
            has_signature=bool(row["has_signature"]),
            signature_confidence=row["signature_confidence"],
            ticket_date=row["ticket_date"],
            audit_date=datetime.fromisoformat(row["audit_date"]),
            has_legal_text=bool(row["has_legal_text"]),
        )
    
    # === Reporting queries ===
    
    def get_signature_stats_by_month(self) -> list[dict]:
        """Get signature statistics grouped by month."""
        with self._connect() as conn:
            cursor = conn.execute("""
                SELECT 
                    month_folder,
                    COUNT(*) as total,
                    SUM(CASE WHEN has_signature = 1 THEN 1 ELSE 0 END) as with_sig,
                    SUM(CASE WHEN has_signature = 0 AND has_legal_text = 1 THEN 1 ELSE 0 END) as missing_sig,
                    SUM(CASE WHEN has_legal_text = 0 THEN 1 ELSE 0 END) as no_sig_required
                FROM audit_records
                GROUP BY month_folder
                ORDER BY month_folder
            """)
            return [dict(row) for row in cursor]
    
    def get_signature_stats_by_technician(self) -> list[dict]:
        """Get signature statistics grouped by technician."""
        with self._connect() as conn:
            cursor = conn.execute("""
                SELECT 
                    COALESCE(technician_name, 'UNKNOWN') as technician,
                    COUNT(*) as total,
                    SUM(CASE WHEN has_signature = 1 THEN 1 ELSE 0 END) as with_sig,
                    SUM(CASE WHEN has_signature = 0 AND has_legal_text = 1 THEN 1 ELSE 0 END) as missing_sig,
                    ROUND(
                        100.0 * SUM(CASE WHEN has_signature = 1 THEN 1 ELSE 0 END) / 
                        NULLIF(SUM(CASE WHEN has_legal_text = 1 THEN 1 ELSE 0 END), 0),
                        1
                    ) as signature_rate
                FROM audit_records
                GROUP BY technician_name
                ORDER BY signature_rate ASC
            """)
            return [dict(row) for row in cursor]
    
    def get_signature_stats_by_tech_and_month(self) -> list[dict]:
        """Get signature stats grouped by technician and month."""
        with self._connect() as conn:
            cursor = conn.execute("""
                SELECT 
                    month_folder,
                    COALESCE(technician_name, 'UNKNOWN') as technician,
                    COUNT(*) as total,
                    SUM(CASE WHEN has_signature = 1 THEN 1 ELSE 0 END) as with_sig,
                    SUM(CASE WHEN has_signature = 0 AND has_legal_text = 1 THEN 1 ELSE 0 END) as missing_sig,
                    ROUND(
                        100.0 * SUM(CASE WHEN has_signature = 1 THEN 1 ELSE 0 END) / 
                        NULLIF(SUM(CASE WHEN has_legal_text = 1 THEN 1 ELSE 0 END), 0),
                        1
                    ) as signature_rate
                FROM audit_records
                WHERE has_legal_text = 1
                GROUP BY month_folder, technician_name
                ORDER BY month_folder, technician_name
            """)
            return [dict(row) for row in cursor]
    
    def get_total_stats(self) -> dict:
        """Get overall statistics."""
        with self._connect() as conn:
            row = conn.execute("""
                SELECT 
                    COUNT(*) as total_tickets,
                    COUNT(DISTINCT technician_name) as unique_technicians,
                    COUNT(DISTINCT month_folder) as months_covered,
                    SUM(CASE WHEN has_signature = 1 THEN 1 ELSE 0 END) as total_with_sig,
                    SUM(CASE WHEN has_legal_text = 1 THEN 1 ELSE 0 END) as total_sig_required,
                    ROUND(
                        100.0 * SUM(CASE WHEN has_signature = 1 THEN 1 ELSE 0 END) / 
                        NULLIF(SUM(CASE WHEN has_legal_text = 1 THEN 1 ELSE 0 END), 0),
                        1
                    ) as overall_signature_rate
                FROM audit_records
            """).fetchone()
            return dict(row)
