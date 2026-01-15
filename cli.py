#!/usr/bin/env python3
"""CLI for Service Ticket Signature Auditor."""

from datetime import datetime
from typing import Optional

import typer
from rich.console import Console

from src.audit_service import AuditService
from src.reports import ReportGenerator


app = typer.Typer(
    name="paperplease",
    help="Audit service tickets for signature compliance",
    add_completion=False,
)
console = Console()


@app.command()
def audit(
    since: Optional[str] = typer.Option(
        None,
        "--from", "-f",
        help="Process images from this date (YYYY-MM-DD)"
    ),
    until: Optional[str] = typer.Option(
        None,
        "--to", "-t", 
        help="Process images until this date (YYYY-MM-DD)"
    ),
    reprocess: bool = typer.Option(
        False,
        "--reprocess", "-r",
        help="Reprocess already-audited images"
    ),
    update_rollups: bool = typer.Option(
        True,
        "--update-rollups/--no-rollups",
        help="Update rollup sheets after audit"
    ),
):
    """
    Run the audit process on service ticket images.
    
    Scans Google Drive for new ticket images, extracts technician names,
    detects signatures, and records results to Google Sheets.
    """
    since_dt = None
    until_dt = None
    
    if since:
        try:
            since_dt = datetime.strptime(since, "%Y-%m-%d")
        except ValueError:
            console.print(f"[red]Invalid date format: {since}. Use YYYY-MM-DD[/red]")
            raise typer.Exit(1)
    
    if until:
        try:
            until_dt = datetime.strptime(until, "%Y-%m-%d")
        except ValueError:
            console.print(f"[red]Invalid date format: {until}. Use YYYY-MM-DD[/red]")
            raise typer.Exit(1)
    
    try:
        service = AuditService()
        records = service.run_audit(
            since=since_dt,
            until=until_dt,
            skip_processed=not reprocess
        )
        
        console.print(f"\n[green]Processed {len(records)} tickets[/green]")
        
        if update_rollups and records:
            reporter = ReportGenerator()
            reporter.update_all_rollups()
            
    except Exception as e:
        console.print(f"[red]Audit failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def report(
    period: str = typer.Argument(
        "summary",
        help="Report period: daily, weekly, monthly, or summary"
    ),
    technician: Optional[str] = typer.Option(
        None,
        "--tech", "-t",
        help="Filter by technician name"
    ),
    update: bool = typer.Option(
        False,
        "--update", "-u",
        help="Update rollup sheets before generating report"
    ),
):
    """
    Generate and display signature compliance reports.
    
    Available periods:
    - daily: Stats per technician per day
    - weekly: Stats per technician per week
    - monthly: Stats per technician per month
    - summary: Overall stats per technician
    """
    if period not in ["daily", "weekly", "monthly", "summary"]:
        console.print(f"[red]Invalid period: {period}[/red]")
        console.print("Choose from: daily, weekly, monthly, summary")
        raise typer.Exit(1)
    
    try:
        reporter = ReportGenerator()
        
        if update:
            reporter.update_all_rollups()
        
        reporter.print_report(period=period, technician=technician)
        
    except Exception as e:
        console.print(f"[red]Report failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def stats(
    technician: Optional[str] = typer.Option(
        None,
        "--tech", "-t",
        help="Show stats for specific technician"
    ),
    all_techs: bool = typer.Option(
        False,
        "--all", "-a",
        help="Show stats for all technicians"
    ),
):
    """
    Show signature statistics for technicians.
    """
    try:
        reporter = ReportGenerator()
        
        if all_techs:
            reporter.print_report(period="summary")
        elif technician:
            stats = reporter.get_technician_stats(technician)
            if stats:
                rate = stats["rate"]
                rate_color = "green" if rate >= 90 else "yellow" if rate >= 70 else "red"
                
                console.print(f"\n[bold]{stats['technician']}[/bold]")
                console.print(f"  Total Tickets: {stats['total']}")
                console.print(f"  With Signature: [green]{stats['with_sig']}[/green]")
                console.print(f"  Without Signature: [red]{stats['without_sig']}[/red]")
                console.print(f"  Signature Rate: [{rate_color}]{rate:.1f}%[/{rate_color}]")
            else:
                console.print(f"[yellow]No data found for technician: {technician}[/yellow]")
        else:
            console.print("[yellow]Specify --tech NAME or --all[/yellow]")
            
    except Exception as e:
        console.print(f"[red]Stats failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def schedule(
    action: str = typer.Argument(
        "status",
        help="Action: start, stop, or status"
    ),
):
    """
    Manage the audit scheduler.
    
    Actions:
    - start: Start the background scheduler
    - stop: Stop the scheduler
    - status: Show scheduler status
    """
    if action == "start":
        console.print("[blue]Starting scheduler...[/blue]")
        console.print("Run 'python scheduler.py' to start the scheduler daemon")
    elif action == "stop":
        console.print("[yellow]To stop the scheduler, terminate the scheduler.py process[/yellow]")
    elif action == "status":
        console.print("[dim]Scheduler status check not implemented yet[/dim]")
    else:
        console.print(f"[red]Unknown action: {action}[/red]")
        raise typer.Exit(1)


@app.command()
def process_one(
    file_id: str = typer.Argument(..., help="Google Drive file ID to process"),
):
    """
    Process a single image by its Google Drive file ID.
    
    Useful for testing or reprocessing specific tickets.
    """
    try:
        service = AuditService()
        record = service.process_single_image(file_id)
        
        console.print(f"\n[green]Processed: {record.filename}[/green]")
        console.print(f"  Technician: {record.technician_name or 'UNKNOWN'}")
        console.print(f"  Signature: {'✓' if record.has_signature else '✗'}")
        console.print(f"  Confidence: {record.confidence:.2f}")
        
    except Exception as e:
        console.print(f"[red]Processing failed: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
