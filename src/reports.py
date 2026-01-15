"""Report generation and rollup calculations."""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Literal

from rich.console import Console
from rich.table import Table

from src.sheets_writer import SheetsWriter


console = Console()


class ReportGenerator:
    """Generates reports and rollups from audit data."""
    
    def __init__(self, spreadsheet_id: str | None = None):
        self.sheets = SheetsWriter(spreadsheet_id=spreadsheet_id)
    
    def generate_daily_rollup(self) -> list[dict]:
        """
        Generate daily rollup data from audit records.
        
        Returns:
            List of dicts with daily stats per technician
        """
        records = self.sheets.get_all_audit_records()
        
        if not records:
            return []
        
        # Group by (date, technician)
        daily_stats: dict[tuple[str, str], dict] = defaultdict(
            lambda: {"total": 0, "with_sig": 0, "without_sig": 0}
        )
        
        for record in records:
            # Parse audit date to get just the date part
            audit_date_str = record.get("Audit Date", "")
            if not audit_date_str:
                continue
            
            try:
                audit_date = datetime.strptime(
                    audit_date_str.split()[0], "%Y-%m-%d"
                ).strftime("%Y-%m-%d")
            except (ValueError, IndexError):
                continue
            
            tech = record.get("Technician", "UNKNOWN")
            has_sig = record.get("Signature Present", "No") == "Yes"
            
            key = (audit_date, tech)
            daily_stats[key]["total"] += 1
            if has_sig:
                daily_stats[key]["with_sig"] += 1
            else:
                daily_stats[key]["without_sig"] += 1
        
        # Convert to list and calculate rates
        rollup = []
        for (date, tech), stats in sorted(daily_stats.items()):
            rate = (stats["with_sig"] / stats["total"] * 100) if stats["total"] > 0 else 0
            rollup.append({
                "date": date,
                "technician": tech,
                "total": stats["total"],
                "with_sig": stats["with_sig"],
                "without_sig": stats["without_sig"],
                "rate": rate,
            })
        
        return rollup
    
    def generate_summary(self) -> list[dict]:
        """
        Generate overall summary stats per technician.
        
        Returns:
            List of dicts with overall stats per technician
        """
        records = self.sheets.get_all_audit_records()
        
        if not records:
            return []
        
        # Group by technician
        tech_stats: dict[str, dict] = defaultdict(
            lambda: {"total": 0, "with_sig": 0, "without_sig": 0}
        )
        
        for record in records:
            tech = record.get("Technician", "UNKNOWN")
            has_sig = record.get("Signature Present", "No") == "Yes"
            
            tech_stats[tech]["total"] += 1
            if has_sig:
                tech_stats[tech]["with_sig"] += 1
            else:
                tech_stats[tech]["without_sig"] += 1
        
        # Convert to list and calculate rates
        summary = []
        for tech, stats in sorted(tech_stats.items()):
            rate = (stats["with_sig"] / stats["total"] * 100) if stats["total"] > 0 else 0
            summary.append({
                "technician": tech,
                "total": stats["total"],
                "with_sig": stats["with_sig"],
                "without_sig": stats["without_sig"],
                "rate": rate,
            })
        
        # Sort by signature rate (ascending) to highlight problem areas
        summary.sort(key=lambda x: x["rate"])
        
        return summary
    
    def generate_weekly_rollup(self, weeks_back: int = 4) -> list[dict]:
        """
        Generate weekly rollup data.
        
        Args:
            weeks_back: Number of weeks to include
            
        Returns:
            List of dicts with weekly stats per technician
        """
        records = self.sheets.get_all_audit_records()
        
        if not records:
            return []
        
        # Calculate week boundaries
        cutoff = datetime.now() - timedelta(weeks=weeks_back)
        
        # Group by (week_start, technician)
        weekly_stats: dict[tuple[str, str], dict] = defaultdict(
            lambda: {"total": 0, "with_sig": 0, "without_sig": 0}
        )
        
        for record in records:
            audit_date_str = record.get("Audit Date", "")
            if not audit_date_str:
                continue
            
            try:
                audit_date = datetime.strptime(audit_date_str.split()[0], "%Y-%m-%d")
            except (ValueError, IndexError):
                continue
            
            if audit_date < cutoff:
                continue
            
            # Get start of week (Monday)
            week_start = audit_date - timedelta(days=audit_date.weekday())
            week_str = week_start.strftime("%Y-%m-%d")
            
            tech = record.get("Technician", "UNKNOWN")
            has_sig = record.get("Signature Present", "No") == "Yes"
            
            key = (week_str, tech)
            weekly_stats[key]["total"] += 1
            if has_sig:
                weekly_stats[key]["with_sig"] += 1
            else:
                weekly_stats[key]["without_sig"] += 1
        
        rollup = []
        for (week, tech), stats in sorted(weekly_stats.items()):
            rate = (stats["with_sig"] / stats["total"] * 100) if stats["total"] > 0 else 0
            rollup.append({
                "week_start": week,
                "technician": tech,
                "total": stats["total"],
                "with_sig": stats["with_sig"],
                "without_sig": stats["without_sig"],
                "rate": rate,
            })
        
        return rollup
    
    def generate_monthly_rollup(self, months_back: int = 3) -> list[dict]:
        """
        Generate monthly rollup data.
        
        Args:
            months_back: Number of months to include
            
        Returns:
            List of dicts with monthly stats per technician
        """
        records = self.sheets.get_all_audit_records()
        
        if not records:
            return []
        
        # Calculate cutoff
        cutoff = datetime.now() - timedelta(days=months_back * 30)
        
        # Group by (month, technician)
        monthly_stats: dict[tuple[str, str], dict] = defaultdict(
            lambda: {"total": 0, "with_sig": 0, "without_sig": 0}
        )
        
        for record in records:
            audit_date_str = record.get("Audit Date", "")
            if not audit_date_str:
                continue
            
            try:
                audit_date = datetime.strptime(audit_date_str.split()[0], "%Y-%m-%d")
            except (ValueError, IndexError):
                continue
            
            if audit_date < cutoff:
                continue
            
            month_str = audit_date.strftime("%Y-%m")
            tech = record.get("Technician", "UNKNOWN")
            has_sig = record.get("Signature Present", "No") == "Yes"
            
            key = (month_str, tech)
            monthly_stats[key]["total"] += 1
            if has_sig:
                monthly_stats[key]["with_sig"] += 1
            else:
                monthly_stats[key]["without_sig"] += 1
        
        rollup = []
        for (month, tech), stats in sorted(monthly_stats.items()):
            rate = (stats["with_sig"] / stats["total"] * 100) if stats["total"] > 0 else 0
            rollup.append({
                "month": month,
                "technician": tech,
                "total": stats["total"],
                "with_sig": stats["with_sig"],
                "without_sig": stats["without_sig"],
                "rate": rate,
            })
        
        return rollup
    
    def update_all_rollups(self):
        """Regenerate and update all rollup sheets."""
        console.print("[blue]Updating daily rollup...[/blue]")
        daily = self.generate_daily_rollup()
        self.sheets.update_daily_rollup(daily)
        
        console.print("[blue]Updating summary...[/blue]")
        summary = self.generate_summary()
        self.sheets.update_summary(summary)
        
        console.print("[green]✓ Rollups updated![/green]")
    
    def print_report(
        self, 
        period: Literal["daily", "weekly", "monthly", "summary"],
        technician: str | None = None
    ):
        """Print a formatted report to the console."""
        if period == "daily":
            data = self.generate_daily_rollup()
            title = "Daily Signature Report"
            date_col = "Date"
        elif period == "weekly":
            data = self.generate_weekly_rollup()
            title = "Weekly Signature Report"
            date_col = "Week Start"
        elif period == "monthly":
            data = self.generate_monthly_rollup()
            title = "Monthly Signature Report"
            date_col = "Month"
        else:  # summary
            data = self.generate_summary()
            title = "Technician Summary Report"
            date_col = None
        
        if technician:
            data = [d for d in data if d.get("technician", "").lower() == technician.lower()]
        
        if not data:
            console.print("[yellow]No data found for the specified criteria.[/yellow]")
            return
        
        table = Table(title=title)
        
        if date_col:
            table.add_column(date_col, style="cyan")
        table.add_column("Technician", style="magenta")
        table.add_column("Total", justify="right")
        table.add_column("With Sig", justify="right", style="green")
        table.add_column("Without Sig", justify="right", style="red")
        table.add_column("Rate %", justify="right")
        
        for row in data:
            rate = row["rate"]
            rate_style = "green" if rate >= 90 else "yellow" if rate >= 70 else "red"
            
            if date_col:
                date_val = row.get("date") or row.get("week_start") or row.get("month", "")
                table.add_row(
                    date_val,
                    row["technician"],
                    str(row["total"]),
                    str(row["with_sig"]),
                    str(row["without_sig"]),
                    f"[{rate_style}]{rate:.1f}%[/{rate_style}]",
                )
            else:
                table.add_row(
                    row["technician"],
                    str(row["total"]),
                    str(row["with_sig"]),
                    str(row["without_sig"]),
                    f"[{rate_style}]{rate:.1f}%[/{rate_style}]",
                )
        
        console.print(table)
    
    def get_technician_stats(self, technician: str) -> dict | None:
        """Get detailed stats for a specific technician."""
        summary = self.generate_summary()
        
        for tech_data in summary:
            if tech_data["technician"].lower() == technician.lower():
                return tech_data
        
        return None
