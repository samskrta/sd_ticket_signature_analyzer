#!/usr/bin/env python3
"""Scheduler daemon for automated audit runs."""

import signal
import sys
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from rich.console import Console

from config import settings
from src.audit_service import AuditService
from src.reports import ReportGenerator


console = Console()
scheduler = BlockingScheduler()


def run_scheduled_audit():
    """Run the audit job."""
    console.print(f"\n[blue]═══ Scheduled Audit Starting at {datetime.now()} ═══[/blue]")
    
    try:
        service = AuditService()
        records = service.run_audit(skip_processed=True)
        
        console.print(f"[green]Processed {len(records)} new tickets[/green]")
        
        if records:
            reporter = ReportGenerator()
            reporter.update_all_rollups()
            console.print("[green]Rollups updated[/green]")
        
    except Exception as e:
        console.print(f"[red]Scheduled audit failed: {e}[/red]")
    
    console.print(f"[blue]═══ Audit Complete ═══[/blue]\n")


def shutdown(signum, frame):
    """Handle shutdown signals gracefully."""
    console.print("\n[yellow]Shutting down scheduler...[/yellow]")
    scheduler.shutdown(wait=False)
    sys.exit(0)


def main():
    """Start the scheduler daemon."""
    # Register signal handlers
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    hours = settings.audit_schedule_hours
    
    console.print(f"[green]Starting audit scheduler[/green]")
    console.print(f"[dim]Running every {hours} hour(s)[/dim]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")
    
    # Schedule the audit job
    scheduler.add_job(
        run_scheduled_audit,
        trigger=IntervalTrigger(hours=hours),
        id="audit_job",
        name="Service Ticket Audit",
        replace_existing=True,
        next_run_time=datetime.now(),  # Run immediately on start
    )
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
