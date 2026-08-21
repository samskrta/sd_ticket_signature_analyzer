#!/bin/zsh
# Analyze every month folder under dataIn/ that has unprocessed tickets. Safe to re-run.
cd "$(dirname "$0")" && source venv/bin/activate
for m in $(ls dataIn | grep -E '^[0-9]{4}-[0-9]{2}$'); do
  echo "=== $m $(date) ==="
  python analyze.py "$m" || echo "!!! $m FAILED"
done
echo "=== resolve techs from ServiceDesk $(date) ==="
python resolve_techs.py
echo "=== DONE $(date) ==="
