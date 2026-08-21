#!/usr/bin/env python3
"""
Resolve the technician for every audited ticket from ServiceDesk instead of OCR.

The ticket number is the SD invoice number, and SD's work_history records which
tech emailed each ticket image:

    8/7/26 12:24: SZ there 8/7 FRI, ... O-emld tckt [Tckts\\605070a.png] ...

Precedence per ticket variant:
  1. work_history line that names the exact Tckts\\NNNNNNx.png file  (exact)
  2. appointment order — variant 'a' = 1st appointment, 'b' = 2nd, ...  (inferred)
  3. leave the OCR name in place                                         (fallback)

Usage:
    python resolve_techs.py            # resolve every record in audit.db
    python resolve_techs.py --dry-run  # report only, write nothing

Requires SD_DATABASE_URL in .env (the rossware-sync Supabase mirror).
"""

import argparse
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import psycopg
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent))
from src.database import AuditDatabase
from src.tech_names import name_for_code

console = Console()

# "8/7/26 12:24: SZ there ..." — tech code is the first token after the timestamp
LINE_RX = re.compile(r"^\d{1,2}/\d{1,2}/\d{2} \d{1,2}:\d{2}:?\s*([A-Za-z0-9]{2})\b")
TCKT_RX = re.compile(r"Tckts\\(\d+[a-z])\.png", re.I)


def load_db_url() -> str:
    url = os.environ.get("SD_DATABASE_URL")
    if not url:
        env = Path(__file__).parent / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("SD_DATABASE_URL="):
                    url = line.split("=", 1)[1].strip()
    if not url:
        sys.exit("SD_DATABASE_URL not set (add it to .env)")
    return url


def fetch_sd(url: str, invoices: list[int]) -> tuple[dict[str, str], dict[int, list[str]]]:
    """
    Returns:
      ticket_tech:  {"605070a": "SZ"} from work_history lines
      appt_techs:   {605070: ["JY", "SZ"]} in appointment date order
    """
    lo, hi = min(invoices), max(invoices)
    ticket_tech: dict[str, str] = {}
    appt_techs: dict[int, list[str]] = defaultdict(list)
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT invoice_number, work_history FROM jobs "
            "WHERE invoice_number BETWEEN %s AND %s AND work_history LIKE '%%Tckts%%'",
            (lo, hi),
        )
        for _inv, history in cur:
            for line in (history or "").splitlines():
                tickets = TCKT_RX.findall(line)
                if not tickets:
                    continue
                m = LINE_RX.match(line.strip())
                if not m:
                    continue
                for t in tickets:
                    ticket_tech[t.lower()] = m.group(1).upper()
        cur.execute(
            "SELECT invoice_number, technician FROM appointments "
            "WHERE invoice_number BETWEEN %s AND %s AND technician IS NOT NULL "
            "ORDER BY invoice_number, date_string",
            (lo, hi),
        )
        for inv, tech in cur:
            appt_techs[inv].append(tech.upper())
    return ticket_tech, appt_techs


def resolve(keys, ticket_tech, appt_techs):
    """Yield (file_path, code, name, source) for each resolvable record."""
    for file_path, ticket_number, variant in keys:
        key = f"{ticket_number}{variant}".lower()
        code, source = None, None
        if key in ticket_tech:
            code, source = ticket_tech[key], "history"
        else:
            appts = appt_techs.get(int(ticket_number), [])
            idx = ord(variant.lower()) - ord("a")
            if 0 <= idx < len(appts):
                code, source = appts[idx], "appointment"
        if code:
            yield file_path, code, name_for_code(code), source


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Report only; don't write to audit.db")
    args = parser.parse_args()

    db = AuditDatabase()
    keys = db.get_ticket_keys()
    invoices = sorted({int(t) for _, t, _ in keys})
    console.print(f"[blue]{len(keys)} records, {len(invoices)} invoices ({invoices[0]}–{invoices[-1]})[/blue]")

    ticket_tech, appt_techs = fetch_sd(load_db_url(), invoices)
    console.print(f"[dim]SD: {len(ticket_tech)} ticket images in work_history, {len(appt_techs)} jobs with appointments[/dim]")

    assignments = list(resolve(keys, ticket_tech, appt_techs))
    sources = Counter(src for *_, src in assignments)
    unresolved = len(keys) - len(assignments)

    table = Table(title="Resolution")
    table.add_column("Source"); table.add_column("Records", justify="right")
    table.add_row("work_history (exact)", str(sources["history"]))
    table.add_row("appointment order (inferred)", str(sources["appointment"]))
    table.add_row("unresolved (OCR name kept)", str(unresolved))
    console.print(table)

    unknown_codes = Counter(code for _, code, name, _ in assignments if name == code)
    if unknown_codes:
        console.print(f"[yellow]Codes with no display name in TECH_CODES: {dict(unknown_codes)}[/yellow]")

    if args.dry_run:
        console.print("[yellow]Dry run — nothing written[/yellow]")
        return
    db.assign_technicians([(p, c, n) for p, c, n, _ in assignments])
    console.print(f"[green]✓ Assigned technician on {len(assignments)} records[/green]")


if __name__ == "__main__":
    main()
