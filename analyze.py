#!/usr/bin/env python3
"""
Quick analysis script for testing ticket signature detection.

Usage:
    python analyze.py                    # Analyze recent month
    python analyze.py 2026-01            # Analyze specific month
    python analyze.py --sample 10        # Sample 10 random tickets
    python analyze.py --stats            # Show stats from database
"""

import sys
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.progress import Progress

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.local_scanner import LocalScanner, TicketImage
from src.ticket_analyzer import TicketAnalyzer
from src.database import AuditDatabase, AuditRecord

console = Console()

# Default tickets path
TICKETS_PATH = Path(__file__).parent / "tickets" / "Tckts"


def analyze_tickets(
    month: str | None = None,
    sample_size: int | None = None,
    use_vision_api: bool = False,
    skip_processed: bool = True,
):
    """Analyze ticket images and store results."""
    
    scanner = LocalScanner(TICKETS_PATH)
    analyzer = TicketAnalyzer(use_vision_api=use_vision_api)
    db = AuditDatabase()
    
    # Get months to process
    if month:
        months = [month]
    else:
        months = scanner.list_month_folders()[-1:]  # Just latest month
    
    console.print(f"[blue]Scanning months: {', '.join(months)}[/blue]")
    
    # Get already processed
    processed = db.get_processed_paths() if skip_processed else set()
    console.print(f"[dim]Already processed: {len(processed)} tickets[/dim]")
    
    # Collect images to process
    images: list[TicketImage] = []
    for m in months:
        for img in scanner.scan_folder(m):
            if str(img.path) not in processed:
                images.append(img)
    
    if sample_size and len(images) > sample_size:
        import random
        images = random.sample(images, sample_size)
    
    console.print(f"[green]Processing {len(images)} tickets[/green]")
    
    if not images:
        console.print("[yellow]No new tickets to process[/yellow]")
        return
    
    records = []
    
    with Progress() as progress:
        task = progress.add_task("[cyan]Analyzing...", total=len(images))
        
        for img in images:
            try:
                result = analyzer.analyze(img.path)
                
                record = AuditRecord(
                    id=None,
                    ticket_number=img.ticket_number,
                    variant=img.variant,
                    month_folder=img.month_folder,
                    file_path=str(img.path),
                    technician_name=result.technician_name,
                    technician_role=result.technician_role,
                    has_signature=result.has_signature,
                    signature_confidence=result.signature_confidence,
                    ticket_date=result.ticket_date,
                    audit_date=datetime.now(),
                    has_legal_text=result.has_legal_text,
                )
                records.append(record)
                
            except Exception as e:
                console.print(f"[red]Error: {img.path.name}: {e}[/red]")
            
            progress.advance(task)
    
    # Save to database
    if records:
        db.insert_records(records)
        console.print(f"[green]✓ Saved {len(records)} records to database[/green]")
    
    # Show quick summary
    show_quick_stats(records)


def show_quick_stats(records: list[AuditRecord]):
    """Show quick stats for just-processed records."""
    if not records:
        return
    
    total = len(records)
    sig_required = sum(1 for r in records if r.has_legal_text)
    has_sig = sum(1 for r in records if r.has_signature)
    missing = sig_required - has_sig
    
    console.print(f"\n[bold]Quick Summary:[/bold]")
    console.print(f"  Total tickets: {total}")
    console.print(f"  Signature required: {sig_required}")
    console.print(f"  With signature: [green]{has_sig}[/green]")
    console.print(f"  Missing signature: [red]{missing}[/red]")
    
    if sig_required > 0:
        rate = has_sig / sig_required * 100
        color = "green" if rate >= 90 else "yellow" if rate >= 70 else "red"
        console.print(f"  Signature rate: [{color}]{rate:.1f}%[/{color}]")


def show_stats():
    """Show statistics from the database."""
    db = AuditDatabase()
    
    stats = db.get_total_stats()
    
    console.print("\n[bold]Overall Statistics[/bold]")
    console.print(f"  Total tickets: {stats['total_tickets']}")
    console.print(f"  Unique technicians: {stats['unique_technicians']}")
    console.print(f"  Months covered: {stats['months_covered']}")
    
    if stats['total_sig_required']:
        rate = stats['overall_signature_rate'] or 0
        color = "green" if rate >= 90 else "yellow" if rate >= 70 else "red"
        console.print(f"  Overall signature rate: [{color}]{rate:.1f}%[/{color}]")
    
    # Technician breakdown
    tech_stats = db.get_signature_stats_by_technician()
    
    if tech_stats:
        table = Table(title="\nSignature Rates by Technician")
        table.add_column("Technician", style="cyan")
        table.add_column("Total", justify="right")
        table.add_column("Signed", justify="right", style="green")
        table.add_column("Missing", justify="right", style="red")
        table.add_column("Rate", justify="right")
        
        for row in tech_stats:
            rate = row['signature_rate'] or 0
            rate_color = "green" if rate >= 90 else "yellow" if rate >= 70 else "red"
            
            table.add_row(
                row['technician'] or "UNKNOWN",
                str(row['total']),
                str(row['with_sig']),
                str(row['missing_sig']),
                f"[{rate_color}]{rate:.1f}%[/{rate_color}]" if rate else "N/A",
            )
        
        console.print(table)
    
    # Monthly breakdown
    month_stats = db.get_signature_stats_by_month()
    
    if month_stats:
        table = Table(title="\nSignature Rates by Month")
        table.add_column("Month", style="cyan")
        table.add_column("Total", justify="right")
        table.add_column("Signed", justify="right", style="green")
        table.add_column("Missing", justify="right", style="red")
        table.add_column("No Sig Req", justify="right", style="dim")
        
        for row in month_stats:
            table.add_row(
                row['month_folder'],
                str(row['total']),
                str(row['with_sig']),
                str(row['missing_sig']),
                str(row['no_sig_required']),
            )
        
        console.print(table)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Analyze ticket signatures")
    parser.add_argument("month", nargs="?", help="Month to analyze (YYYY-MM)")
    parser.add_argument("--sample", type=int, help="Sample size for testing")
    parser.add_argument("--stats", action="store_true", help="Show database stats")
    parser.add_argument("--vision", action="store_true", help="Use Google Vision API")
    parser.add_argument("--reprocess", action="store_true", help="Reprocess all tickets")
    
    args = parser.parse_args()
    
    if args.stats:
        show_stats()
    else:
        analyze_tickets(
            month=args.month,
            sample_size=args.sample,
            use_vision_api=args.vision,
            skip_processed=not args.reprocess,
        )


if __name__ == "__main__":
    main()
