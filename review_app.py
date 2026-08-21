#!/usr/bin/env python3
"""Web app for reviewing signature detection accuracy."""

import random
import base64
import io
from pathlib import Path
from flask import Flask, render_template_string, jsonify, request, Response
from PIL import Image

import os
import sys
sys.path.insert(0, str(Path(__file__).parent))

from src.database import AuditDatabase
from src.tech_names import NO_SIGNATURE_CODES, name_for_code

# Root folder containing YYYY-MM subfolders of ticket PNGs (keep in sync with analyze.py)
TICKETS_ROOT = Path(os.environ.get("TICKETS_ROOT", Path(__file__).parent / "dataIn"))

app = Flask(__name__)
db = AuditDatabase()


def current_month() -> str:
    """Month being reviewed: ?month=YYYY-MM, else the latest month in the DB."""
    months = [m["month_folder"] for m in db.get_signature_stats_by_month()]
    requested = request.args.get("month")
    if requested in months:
        return requested
    return months[-1] if months else ""

# Signature region as percentages of the page, for display crops.
# Form geometry (two layouts, 1004/1012 px tall): the "by [Tech]" rule is at 78.5–79.1%,
# the signature baseline at 93.5–94.3%, and the "Total Ticket" box starts at ~70% width.
SIG_LEFT = 0.0
SIG_RIGHT = 0.68
SIG_TOP = 0.77
SIG_BOTTOM = 0.94

# Store review results in memory
reviews: dict[str, dict] = {}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Signature Detection Review</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        
        body {
            font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif;
            background: #0a0a0f;
            color: #e0e0e0;
            min-height: 100vh;
        }
        
        .header {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            padding: 24px 40px;
            border-bottom: 1px solid #2a2a4a;
        }
        
        h1 {
            font-size: 28px;
            font-weight: 600;
            color: #fff;
            letter-spacing: -0.5px;
        }
        
        .stats-bar {
            display: flex;
            gap: 32px;
            margin-top: 16px;
            font-size: 14px;
        }
        
        .stat {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .stat-label { color: #888; }
        .stat-value { font-weight: 600; color: #fff; }
        .stat-value.correct { color: #4ade80; }
        .stat-value.incorrect { color: #f87171; }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 32px;
        }
        
        .cards {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
            gap: 24px;
        }
        
        .card {
            background: #12121a;
            border-radius: 16px;
            overflow: hidden;
            border: 1px solid #2a2a3a;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        
        .card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        }
        
        .card.reviewed { opacity: 0.6; }
        .card.reviewed:hover { opacity: 1; }
        
        .card-image {
            width: 100%;
            height: 300px;
            object-fit: contain;
            background: #fff;
            cursor: pointer;
        }
        
        .card-body {
            padding: 20px;
        }
        
        .ticket-info {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }
        
        .ticket-id {
            font-size: 18px;
            font-weight: 600;
            color: #fff;
        }
        
        .detection-badge {
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
        }
        
        .detection-badge.has-sig {
            background: rgba(74, 222, 128, 0.15);
            color: #4ade80;
        }
        
        .detection-badge.no-sig {
            background: rgba(248, 113, 113, 0.15);
            color: #f87171;
        }
        
        .meta {
            font-size: 13px;
            color: #666;
            margin-bottom: 16px;
        }
        
        .buttons {
            display: flex;
            gap: 12px;
        }
        
        .btn {
            flex: 1;
            padding: 12px 16px;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .btn-correct {
            background: #166534;
            color: #4ade80;
        }
        
        .btn-correct:hover {
            background: #15803d;
        }
        
        .btn-incorrect {
            background: #7f1d1d;
            color: #f87171;
        }
        
        .btn-incorrect:hover {
            background: #991b1b;
        }
        
        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        
        .review-result {
            text-align: center;
            padding: 12px;
            font-weight: 600;
            border-radius: 8px;
            margin-top: 12px;
        }
        
        .review-result.correct {
            background: rgba(74, 222, 128, 0.1);
            color: #4ade80;
        }
        
        .review-result.incorrect {
            background: rgba(248, 113, 113, 0.1);
            color: #f87171;
        }
        
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.9);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }
        
        .modal.active { display: flex; }
        
        .modal img {
            max-width: 95%;
            max-height: 95%;
            object-fit: contain;
        }
        
        .modal-close {
            position: absolute;
            top: 20px;
            right: 30px;
            font-size: 40px;
            color: #fff;
            cursor: pointer;
        }
        
        .accuracy-summary {
            background: linear-gradient(135deg, #1e3a5f 0%, #1a1a2e 100%);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 32px;
            border: 1px solid #2a4a6a;
        }
        
        .accuracy-title {
            font-size: 16px;
            color: #888;
            margin-bottom: 8px;
        }
        
        .accuracy-value {
            font-size: 48px;
            font-weight: 700;
            color: #fff;
        }
        
        .confidence { color: #888; font-size: 14px; margin-top: 4px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Signature Detection Review</h1>
        <div class="stats-bar">
            <div class="stat">
                <span class="stat-label">Sample Size:</span>
                <span class="stat-value" id="total-count">{{ total }}</span>
            </div>
            <div class="stat">
                <span class="stat-label">Reviewed:</span>
                <span class="stat-value" id="reviewed-count">0</span>
            </div>
            <div class="stat">
                <span class="stat-label">Correct:</span>
                <span class="stat-value correct" id="correct-count">0</span>
            </div>
            <div class="stat">
                <span class="stat-label">Incorrect:</span>
                <span class="stat-value incorrect" id="incorrect-count">0</span>
            </div>
            <div class="stat">
                <span class="stat-label">Accuracy:</span>
                <span class="stat-value" id="accuracy">-</span>
            </div>
            <div class="stat" style="margin-left:auto">
                <a href="/techs?month={{ month }}" style="color:#60a5fa;text-decoration:none">Signature Gallery</a>
                <a href="/stats" style="color:#60a5fa;text-decoration:none;margin-left:16px">Compliance Stats</a>
            </div>
        </div>
    </div>
    
    <div class="container">
        <div class="cards" id="cards">
            {% for record in records %}
            <div class="card" id="card-{{ record.ticket_number }}{{ record.variant }}">
                <img 
                    class="card-image" 
                    src="/image/{{ record.ticket_number }}/{{ record.variant }}/{{ record.month_folder }}"
                    onclick="openModal(this.src)"
                    loading="lazy"
                >
                <div class="card-body">
                    <div class="ticket-info">
                        <span class="ticket-id">#{{ record.ticket_number }}{{ record.variant }}</span>
                        <span class="detection-badge {{ 'has-sig' if record.has_signature else 'no-sig' }}">
                            {{ 'Signature Detected' if record.has_signature else 'No Signature' }}
                        </span>
                    </div>
                    <div class="meta">
                        {{ record.month_folder }} · Confidence: {{ "%.0f"|format(record.signature_confidence * 100) }}%
                    </div>
                    <div class="buttons">
                        <button class="btn btn-correct" onclick="review('{{ record.ticket_number }}{{ record.variant }}', true)">
                            ✓ Correct
                        </button>
                        <button class="btn btn-incorrect" onclick="review('{{ record.ticket_number }}{{ record.variant }}', false)">
                            ✗ Incorrect
                        </button>
                    </div>
                    <div class="review-result" id="result-{{ record.ticket_number }}{{ record.variant }}" style="display:none;"></div>
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
    
    <div class="modal" id="modal" onclick="closeModal()">
        <span class="modal-close">&times;</span>
        <img id="modal-img" src="">
    </div>
    
    <script>
        let reviewed = 0, correct = 0, incorrect = 0;
        
        function review(id, isCorrect) {
            fetch('/review', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({id: id, correct: isCorrect})
            }).then(r => r.json()).then(data => {
                const card = document.getElementById('card-' + id);
                const result = document.getElementById('result-' + id);
                
                card.classList.add('reviewed');
                card.querySelectorAll('.btn').forEach(b => b.disabled = true);
                
                result.style.display = 'block';
                result.className = 'review-result ' + (isCorrect ? 'correct' : 'incorrect');
                result.textContent = isCorrect ? '✓ Marked Correct' : '✗ Marked Incorrect';
                
                reviewed++;
                if (isCorrect) correct++; else incorrect++;
                
                updateStats();
            });
        }
        
        function updateStats() {
            document.getElementById('reviewed-count').textContent = reviewed;
            document.getElementById('correct-count').textContent = correct;
            document.getElementById('incorrect-count').textContent = incorrect;
            
            if (reviewed > 0) {
                const acc = (correct / reviewed * 100).toFixed(1);
                document.getElementById('accuracy').textContent = acc + '%';
            }
        }
        
        function openModal(src) {
            document.getElementById('modal-img').src = src;
            document.getElementById('modal').classList.add('active');
        }
        
        function closeModal() {
            document.getElementById('modal').classList.remove('active');
        }
        
        document.addEventListener('keydown', e => {
            if (e.key === 'Escape') closeModal();
        });
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    """Show random sample of tickets for review."""
    records = db.get_records_by_month(current_month())

    # Get balanced sample: some with sig, some without
    with_sig = [r for r in records if r.has_signature]
    without_sig = [r for r in records if not r.has_signature]
    
    # Sample 25 from each category (or all if less)
    sample_size = 25
    sample = []
    sample.extend(random.sample(with_sig, min(sample_size, len(with_sig))))
    sample.extend(random.sample(without_sig, min(sample_size, len(without_sig))))
    random.shuffle(sample)
    
    return render_template_string(HTML_TEMPLATE, records=sample, total=len(sample), month=current_month())


@app.route('/image/<ticket_num>/<variant>/<month>')
def get_image(ticket_num, variant, month):
    """Serve ticket image."""
    image_path = TICKETS_ROOT / month / f"{ticket_num}{variant}.png"

    if not image_path.exists():
        return "Not found", 404

    image_data = image_path.read_bytes()
    return image_data, 200, {'Content-Type': 'image/png'}


@app.route('/review', methods=['POST'])
def submit_review():
    """Record a review decision."""
    data = request.json
    ticket_id = data['id']
    is_correct = data['correct']
    
    reviews[ticket_id] = {'correct': is_correct}
    
    # Calculate current accuracy
    total = len(reviews)
    correct = sum(1 for r in reviews.values() if r['correct'])
    accuracy = correct / total * 100 if total > 0 else 0
    
    return jsonify({
        'success': True,
        'total_reviewed': total,
        'correct': correct,
        'accuracy': accuracy
    })


@app.route('/results')
def results():
    """Show review results."""
    total = len(reviews)
    correct = sum(1 for r in reviews.values() if r['correct'])
    incorrect = total - correct
    accuracy = correct / total * 100 if total > 0 else 0
    
    incorrect_ids = [k for k, v in reviews.items() if not v['correct']]
    
    return jsonify({
        'total_reviewed': total,
        'correct': correct,
        'incorrect': incorrect,
        'accuracy': round(accuracy, 1),
        'incorrect_tickets': incorrect_ids
    })


GALLERY_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Signature Gallery - {{ tech_name }}</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        
        body {
            font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif;
            background: #0a0a0f;
            color: #e0e0e0;
            min-height: 100vh;
        }
        
        .header {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            padding: 24px 40px;
            border-bottom: 1px solid #2a2a4a;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        h1 {
            font-size: 28px;
            font-weight: 600;
            color: #fff;
        }
        
        .tech-selector {
            display: flex;
            gap: 12px;
            align-items: center;
        }
        
        .tech-selector select {
            padding: 10px 16px;
            border-radius: 8px;
            background: #12121a;
            color: #fff;
            border: 1px solid #2a2a4a;
            font-size: 14px;
            cursor: pointer;
        }
        
        .stats {
            font-size: 14px;
            color: #888;
        }
        
        .stats span { color: #4ade80; font-weight: 600; }
        
        .container {
            max-width: 1600px;
            margin: 0 auto;
            padding: 32px;
        }
        
        .gallery {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 16px;
        }
        
        .sig-card {
            background: #fff;
            border-radius: 8px;
            overflow: hidden;
            cursor: pointer;
            transition: transform 0.2s;
            position: relative;
        }
        
        .sig-card:hover {
            transform: scale(1.05);
            z-index: 10;
        }
        
        .sig-card img {
            width: 100%;
            height: 80px;
            object-fit: contain;
            background: #fff;
        }
        
        .sig-card .ticket-id {
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            background: rgba(0,0,0,0.7);
            color: #fff;
            font-size: 11px;
            padding: 4px 8px;
            text-align: center;
        }
        
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.95);
            z-index: 1000;
            justify-content: center;
            align-items: center;
            flex-direction: column;
        }
        
        .modal.active { display: flex; }
        
        .modal img {
            max-width: 90%;
            max-height: 80%;
            object-fit: contain;
            background: #fff;
            border-radius: 8px;
        }
        
        .modal-info {
            color: #fff;
            margin-top: 16px;
            font-size: 16px;
        }
        
        .modal-close {
            position: absolute;
            top: 20px;
            right: 30px;
            font-size: 40px;
            color: #fff;
            cursor: pointer;
        }
        
        .back-link {
            color: #60a5fa;
            text-decoration: none;
            font-size: 14px;
        }
        
        .back-link:hover { text-decoration: underline; }
        
        .warning {
            background: rgba(248, 113, 113, 0.15);
            border: 1px solid #f87171;
            color: #f87171;
            padding: 16px 24px;
            border-radius: 8px;
            margin-bottom: 24px;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="header">
        <div>
            <a href="/techs?month={{ month }}" class="back-link">← All Technicians</a>
            <h1>{{ tech_name }}</h1>
        </div>
        <div class="stats">
            Showing <span>{{ signatures|length }}</span> signatures
        </div>
    </div>
    
    <div class="container">
        {% if signatures|length > 20 %}
        <div class="warning">
            ⚠️ Review these signatures for patterns that may indicate fraud (same handwriting style, similar shapes, etc.)
        </div>
        {% endif %}
        
        <div class="gallery">
            {% for sig in signatures %}
            <div class="sig-card" onclick="openModal('/signature/{{ sig.ticket_number }}/{{ sig.variant }}/{{ sig.month_folder }}', '{{ sig.ticket_number }}{{ sig.variant }}')">
                <img src="/signature/{{ sig.ticket_number }}/{{ sig.variant }}/{{ sig.month_folder }}" loading="lazy">
                <div class="ticket-id">#{{ sig.ticket_number }}{{ sig.variant }}</div>
            </div>
            {% endfor %}
        </div>
    </div>
    
    <div class="modal" id="modal" onclick="closeModal()">
        <span class="modal-close">&times;</span>
        <img id="modal-img" src="">
        <div class="modal-info" id="modal-info"></div>
    </div>
    
    <script>
        function openModal(src, id) {
            document.getElementById('modal-img').src = src;
            document.getElementById('modal-info').textContent = 'Ticket #' + id;
            document.getElementById('modal').classList.add('active');
        }
        
        function closeModal() {
            document.getElementById('modal').classList.remove('active');
        }
        
        document.addEventListener('keydown', e => {
            if (e.key === 'Escape') closeModal();
        });
    </script>
</body>
</html>
"""

TECHS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Technician Signature Gallery</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        
        body {
            font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif;
            background: #0a0a0f;
            color: #e0e0e0;
            min-height: 100vh;
        }
        
        .header {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            padding: 24px 40px;
            border-bottom: 1px solid #2a2a4a;
        }
        
        h1 {
            font-size: 28px;
            font-weight: 600;
            color: #fff;
        }
        
        .subtitle {
            color: #888;
            margin-top: 8px;
            font-size: 14px;
        }
        
        .container {
            max-width: 1000px;
            margin: 0 auto;
            padding: 32px;
        }
        
        .tech-list {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 16px;
        }
        
        .tech-card {
            background: #12121a;
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #2a2a3a;
            text-decoration: none;
            color: inherit;
            transition: all 0.2s;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .tech-card:hover {
            background: #1a1a2a;
            border-color: #4a4a6a;
            transform: translateY(-2px);
        }
        
        .tech-name {
            font-size: 18px;
            font-weight: 600;
            color: #fff;
        }
        
        .tech-stats {
            text-align: right;
        }
        
        .sig-count {
            font-size: 24px;
            font-weight: 700;
            color: #4ade80;
        }
        
        .sig-label {
            font-size: 12px;
            color: #666;
        }
        
        .nav-links {
            margin-top: 12px;
        }
        
        .nav-links a {
            color: #60a5fa;
            text-decoration: none;
            margin-right: 16px;
            font-size: 14px;
        }
        
        .nav-links a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Technician Signature Gallery</h1>
        <p class="subtitle">Click a technician to view all their collected signatures</p>
        <div class="nav-links">
            <a href="/?month={{ month }}">← Review Detection</a>
            <a href="/stats">Compliance Stats</a>
        </div>
    </div>
    
    <div class="container">
        <div class="tech-list">
            {% for tech in techs %}
            <a href="/techs/{{ tech.name|urlencode }}?month={{ month }}" class="tech-card">
                <div class="tech-name">{{ tech.name or 'UNKNOWN' }}</div>
                <div class="tech-stats">
                    <div class="sig-count">{{ tech.count }}</div>
                    <div class="sig-label">signatures</div>
                </div>
            </a>
            {% endfor %}
        </div>
    </div>
</body>
</html>
"""


@app.route('/techs')
def techs_list():
    """List all technicians with signature counts."""
    records = db.get_records_by_month(current_month())
    
    # Count signatures per tech
    tech_counts = {}
    for r in records:
        if r.has_signature:
            name = r.technician_name or "UNKNOWN"
            tech_counts[name] = tech_counts.get(name, 0) + 1
    
    # Sort by count descending
    techs = [{'name': k, 'count': v} for k, v in tech_counts.items()]
    techs.sort(key=lambda x: -x['count'])
    
    return render_template_string(TECHS_TEMPLATE, techs=techs, month=current_month())


@app.route('/techs/<tech_name>')
def tech_gallery(tech_name):
    """Show all signatures for a specific technician."""
    records = db.get_records_by_month(current_month())
    
    # Handle UNKNOWN
    if tech_name == "UNKNOWN" or tech_name == "None":
        signatures = [r for r in records if r.has_signature and r.technician_name is None]
    else:
        signatures = [r for r in records if r.has_signature and r.technician_name == tech_name]
    
    # Sort by ticket number
    signatures.sort(key=lambda x: x.ticket_number)
    
    return render_template_string(GALLERY_TEMPLATE, tech_name=tech_name, signatures=signatures, month=current_month())


@app.route('/signature/<ticket_num>/<variant>/<month>')
def get_signature(ticket_num, variant, month):
    """Serve cropped signature region."""
    image_path = TICKETS_ROOT / month / f"{ticket_num}{variant}.png"

    if not image_path.exists():
        return "Not found", 404

    # Open and crop to signature region
    img = Image.open(image_path)
    width, height = img.size
    
    # Convert percentage coords to pixels
    left = int(SIG_LEFT * width) + 10  # Match the 10px offset in analyzer
    top = int(SIG_TOP * height)
    right = int(SIG_RIGHT * width)
    bottom = int(SIG_BOTTOM * height)
    
    sig_crop = img.crop((left, top, right, bottom))
    
    # Convert to bytes
    buf = io.BytesIO()
    sig_crop.save(buf, format='PNG')
    buf.seek(0)
    
    return Response(buf.getvalue(), mimetype='image/png')


STATS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Signature Compliance</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        :root {
            --surface: #0a0a0f; --surface-2: #12121a; --border: #2a2a3a;
            --text: #e0e0e0; --text-2: #9a9aa8; --text-3: #666;
            --bar: #3987e5; --track: #1c1c28; --link: #60a5fa;
        }
        body { font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif; background: var(--surface); color: var(--text); }
        .header { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 24px 40px; border-bottom: 1px solid #2a2a4a; }
        h1 { font-size: 28px; font-weight: 600; color: #fff; }
        h2 { font-size: 16px; font-weight: 600; color: #fff; margin: 0 0 4px; }
        .subtitle { color: #888; margin-top: 8px; font-size: 14px; }
        .nav-links { margin-top: 12px; }
        .nav-links a { color: var(--link); text-decoration: none; margin-right: 16px; font-size: 14px; }
        .nav-links a:hover { text-decoration: underline; }
        .container { max-width: 1100px; margin: 0 auto; padding: 32px; }
        .filters { display: flex; gap: 12px; align-items: center; margin-bottom: 24px; font-size: 14px; color: var(--text-2); }
        .filters select { background: var(--surface-2); color: var(--text); border: 1px solid var(--border); border-radius: 6px; padding: 6px 10px; font-size: 14px; }
        .filters button { background: var(--bar); color: #fff; border: 0; border-radius: 6px; padding: 7px 14px; font-size: 14px; cursor: pointer; }
        .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 32px; }
        .tile { background: var(--surface-2); border: 1px solid var(--border); border-radius: 12px; padding: 16px 20px; }
        .tile .v { font-size: 28px; font-weight: 700; color: #fff; font-variant-numeric: tabular-nums; }
        .tile .l { font-size: 12px; color: var(--text-3); margin-top: 4px; }
        .card { background: var(--surface-2); border: 1px solid var(--border); border-radius: 12px; padding: 20px 24px; margin-bottom: 24px; }
        .card .note { font-size: 12px; color: var(--text-3); margin-bottom: 16px; }

        /* ranked bar chart: one row per tech, label | track | value */
        .bars { display: grid; grid-template-columns: 110px 1fr 120px; row-gap: 6px; column-gap: 12px; align-items: center; font-size: 13px; }
        .bars .name { color: var(--text); text-align: right; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .bars .name a { color: inherit; text-decoration: none; }
        .bars .name a:hover { text-decoration: underline; }
        .bars .track { position: relative; height: 10px; background: var(--track); border-radius: 4px; cursor: default; }
        .bars .fill { position: absolute; left: 0; top: 0; bottom: 0; background: var(--bar); border-radius: 0 4px 4px 0; }
        .bars .fill.low-n { opacity: 0.45; background: repeating-linear-gradient(135deg, var(--bar) 0 4px, transparent 4px 8px); }
        .bars .val { color: var(--text); font-variant-numeric: tabular-nums; white-space: nowrap; }
        .bars .val span { color: var(--text-3); }
        .axis { display: grid; grid-template-columns: 110px 1fr 120px; column-gap: 12px; font-size: 11px; color: var(--text-3); margin-bottom: 6px; }
        .axis .ticks { display: flex; justify-content: space-between; border-bottom: 1px solid var(--border); padding-bottom: 2px; }

        /* heatmap */
        .heat { border-collapse: separate; border-spacing: 2px; font-size: 12px; font-variant-numeric: tabular-nums; }
        .heat th { color: var(--text-3); font-weight: 500; padding: 4px 6px; text-align: center; }
        .heat th.row { text-align: right; white-space: nowrap; color: var(--text); }
        .heat th.row a { color: inherit; text-decoration: none; }
        .heat td { width: 64px; height: 28px; text-align: center; border-radius: 4px; cursor: default; }
        .heat td.empty { background: transparent; color: var(--text-3); }
        .heat td.low-n { opacity: 0.5; font-style: italic; }
        .scale { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--text-3); margin-top: 12px; }
        .scale .sw { width: 22px; height: 12px; border-radius: 2px; }

        #tip { position: fixed; pointer-events: none; background: #1e1e2c; color: var(--text); border: 1px solid #3a3a4e; border-radius: 6px; padding: 8px 10px; font-size: 12px; line-height: 1.5; display: none; z-index: 10; box-shadow: 0 4px 16px rgba(0,0,0,.5); }
        #tip b { color: #fff; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Signature Compliance</h1>
        <p class="subtitle">Share of service tickets carrying a customer signature, by technician</p>
        <div class="nav-links">
            <a href="/?month={{ months[-1] }}">← Review Detection</a>
            <a href="/techs?month={{ months[-1] }}">Signature Gallery</a>
            <a href="/customers">Repeat Customers</a>
        </div>
    </div>

    <div class="container">
        <form class="filters" method="get">
            <label>From <select name="from">{% for m in all_months %}<option value="{{ m }}" {% if m == month_from %}selected{% endif %}>{{ m }}</option>{% endfor %}</select></label>
            <label>To <select name="to">{% for m in all_months %}<option value="{{ m }}" {% if m == month_to %}selected{% endif %}>{{ m }}</option>{% endfor %}</select></label>
            <button type="submit">Apply</button>
            {% if show_all %}<input type="hidden" name="all" value="1">{% endif %}
            {% if hidden %}
            <span style="margin-left:auto">
                {% if show_all %}Including {{ hidden|length }} former techs with no tickets in {{ latest }} · <a href="/stats?from={{ month_from }}&to={{ month_to }}" style="color:var(--link)">hide</a>
                {% else %}{{ hidden|length }} former techs with no tickets in {{ latest }} hidden · <a href="/stats?from={{ month_from }}&to={{ month_to }}&all=1" style="color:var(--link)">show</a>{% endif %}
                {% if excluded %} · {{ excluded|join(', ') }} excluded (remote visits, no signature expected){% endif %}
            </span>
            {% endif %}
        </form>

        <div class="tiles">
            <div class="tile"><div class="v">{{ overall.rate }}%</div><div class="l">signed overall</div></div>
            <div class="tile"><div class="v">{{ "{:,}".format(overall.total) }}</div><div class="l">tickets</div></div>
            <div class="tile"><div class="v">{{ "{:,}".format(overall.missing) }}</div><div class="l">missing signature</div></div>
            <div class="tile"><div class="v">{{ techs|length }}</div><div class="l">technicians</div></div>
        </div>

        <div class="card">
            <h2>% signed by technician</h2>
            <div class="note">Sorted worst → best. Hatched bars have fewer than {{ low_n }} tickets in range — treat as noise.</div>
            <div class="axis"><div></div><div class="ticks"><span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span></div><div></div></div>
            <div class="bars">
                {% for t in techs %}
                <div class="name"><a href="/techs/{{ t.name|urlencode }}?month={{ months[-1] }}">{{ t.name }}</a></div>
                <div class="track" data-tip="<b>{{ t.name }}</b><br>{{ t.signed }} signed / {{ t.total - t.signed }} missing<br>{{ t.total }} tickets, {{ month_from }} – {{ month_to }}">
                    <div class="fill {% if t.total < low_n %}low-n{% endif %}" style="width: {{ t.rate }}%"></div>
                </div>
                <div class="val">{{ t.rate }}% <span>· n={{ t.total }}</span></div>
                {% endfor %}
            </div>
        </div>

        <div class="card">
            <h2>% signed by technician and month</h2>
            <div class="note">Same order as above. Darker = lower. Italic cells have fewer than {{ low_n_cell }} tickets that month.</div>
            <div style="overflow-x: auto">
            <table class="heat">
                <tr><th></th>{% for m in months %}<th>{{ m[2:] }}</th>{% endfor %}</tr>
                {% for t in techs %}
                <tr>
                    <th class="row"><a href="/techs/{{ t.name|urlencode }}?month={{ months[-1] }}">{{ t.name }}</a></th>
                    {% for c in t.cells %}
                    {% if c %}
                    <td class="{% if c.total < low_n_cell %}low-n{% endif %}" style="background: {{ c.bg }}; color: {{ c.fg }}"
                        data-tip="<b>{{ t.name }} · {{ c.month }}</b><br>{{ c.rate }}% signed<br>{{ c.signed }} of {{ c.total }} tickets">{{ c.rate }}</td>
                    {% else %}
                    <td class="empty">–</td>
                    {% endif %}
                    {% endfor %}
                </tr>
                {% endfor %}
            </table>
            </div>
            <div class="scale">0%{% for sw in ramp %}<span class="sw" style="background: {{ sw }}"></span>{% endfor %}100%</div>
        </div>
    </div>
    <div id="tip"></div>
    <script>
        const tip = document.getElementById('tip');
        document.querySelectorAll('[data-tip]').forEach(el => {
            el.addEventListener('mouseenter', () => { tip.innerHTML = el.dataset.tip; tip.style.display = 'block'; });
            el.addEventListener('mousemove', e => {
                const x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
                tip.style.left = x + 'px'; tip.style.top = (e.clientY + 14) + 'px';
            });
            el.addEventListener('mouseleave', () => { tip.style.display = 'none'; });
        });
    </script>
</body>
</html>
"""

# Sequential blue ramp (dataviz reference palette, steps 700 → 100) for the heatmap on the dark surface:
# low % signed sits near the surface, high % signed is light. Text flips to dark ink on the light steps.
HEAT_RAMP = ["#0d366b", "#104281", "#184f95", "#1c5cab", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"]
LOW_N_TECH = 20   # fewer tickets than this in range → hatched bar
LOW_N_CELL = 10   # fewer tickets than this in a month → italic cell


def heat_color(rate: float) -> tuple[str, str]:
    idx = min(len(HEAT_RAMP) - 1, int(rate / 100 * len(HEAT_RAMP)))
    bg = HEAT_RAMP[idx]
    fg = "#0b0b0b" if idx >= 6 else "#ffffff"
    return bg, fg


@app.route('/stats')
def stats():
    """Signature compliance: ranked bars per tech + tech × month heatmap."""
    all_months = [m["month_folder"] for m in db.get_signature_stats_by_month()]
    if not all_months:
        return "No data", 404
    month_from = request.args.get("from") if request.args.get("from") in all_months else all_months[0]
    month_to = request.args.get("to") if request.args.get("to") in all_months else all_months[-1]
    if month_from > month_to:
        month_from, month_to = month_to, month_from
    months = [m for m in all_months if month_from <= m <= month_to]

    rows = db.get_tech_month_counts(month_from, month_to)
    by_tech: dict[str, dict] = {}
    for r in rows:
        t = by_tech.setdefault(r["technician"], {"name": r["technician"], "total": 0, "signed": 0, "months": {}})
        t["total"] += r["total"]; t["signed"] += r["signed"]
        t["months"][r["month_folder"]] = r

    techs = []
    for t in by_tech.values():
        t["rate"] = round(100 * t["signed"] / t["total"], 1) if t["total"] else 0
        cells = []
        for m in months:
            r = t["months"].get(m)
            if not r:
                cells.append(None); continue
            rate = round(100 * r["signed"] / r["total"]) if r["total"] else 0
            bg, fg = heat_color(rate)
            cells.append({"month": m, "rate": rate, "total": r["total"], "signed": r["signed"], "bg": bg, "fg": fg})
        t["cells"] = cells
        techs.append(t)
    techs.sort(key=lambda t: (t["rate"], -t["total"]))

    # Former techs: nobody with zero tickets in the latest month belongs on the chart.
    latest = all_months[-1]
    active_names = {r["technician"] for r in db.get_tech_month_counts(latest, latest)}
    show_all = request.args.get("all") == "1"
    hidden = [t["name"] for t in techs if t["name"] not in active_names]
    if not show_all:
        techs = [t for t in techs if t["name"] in active_names]
    # Remote-only techs never collect a signature — never on the chart, even with ?all=1.
    no_sig_names = {name_for_code(c) for c in NO_SIGNATURE_CODES}
    excluded = [t["name"] for t in techs if t["name"] in no_sig_names]
    techs = [t for t in techs if t["name"] not in no_sig_names]

    total = sum(t["total"] for t in techs); signed = sum(t["signed"] for t in techs)
    overall = {"total": total, "missing": total - signed, "rate": round(100 * signed / total, 1) if total else 0}
    return render_template_string(
        STATS_TEMPLATE, techs=techs, months=months, all_months=all_months,
        month_from=month_from, month_to=month_to, overall=overall,
        ramp=HEAT_RAMP, low_n=LOW_N_TECH, low_n_cell=LOW_N_CELL,
        latest=latest, hidden=hidden, show_all=show_all, excluded=excluded,
    )


CUSTOMERS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Repeat Customers</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif; background: #0a0a0f; color: #e0e0e0; }
        .header { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 24px 40px; border-bottom: 1px solid #2a2a4a; }
        h1 { font-size: 28px; font-weight: 600; color: #fff; }
        .subtitle { color: #888; margin-top: 8px; font-size: 14px; max-width: 900px; line-height: 1.5; }
        .nav-links { margin-top: 12px; }
        .nav-links a { color: #60a5fa; text-decoration: none; margin-right: 16px; font-size: 14px; }
        .nav-links a:hover { text-decoration: underline; }
        .container { max-width: 1400px; margin: 0 auto; padding: 32px; }
        .filters { display: flex; gap: 16px; align-items: center; margin-bottom: 24px; font-size: 14px; color: #9a9aa8; }
        .filters a { color: #60a5fa; text-decoration: none; padding: 6px 12px; border: 1px solid #2a2a3a; border-radius: 6px; }
        .filters a.on { background: #1c5cab; color: #fff; border-color: #1c5cab; }
        .group { background: #12121a; border: 1px solid #2a2a3a; border-radius: 12px; padding: 16px 20px; margin-bottom: 16px; }
        .group.cross { border-color: #3a4a7a; }
        .group h2 { font-size: 15px; font-weight: 600; color: #fff; margin-bottom: 2px; }
        .group .addr { font-size: 12px; color: #666; margin-bottom: 12px; }
        .group .tag { font-size: 11px; color: #9ec5f4; background: #1c2b4a; border-radius: 4px; padding: 2px 8px; margin-left: 8px; vertical-align: middle; }
        .sigs { display: flex; flex-wrap: wrap; gap: 12px; }
        .sig { background: #fff; border-radius: 8px; overflow: hidden; width: 300px; cursor: pointer; }
        .sig img { width: 100%; height: 80px; object-fit: contain; display: block; }
        .sig .cap { background: #1a1a24; color: #c3c2b7; font-size: 12px; padding: 6px 10px; display: flex; justify-content: space-between; }
        .sig .cap b { color: #fff; }
        .modal { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.9); z-index: 1000; justify-content: center; align-items: center; }
        .modal.active { display: flex; }
        .modal img { max-width: 95%; max-height: 95%; background: #fff; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Repeat Customers</h1>
        <p class="subtitle">Customers with signed tickets on more than one job, side by side. A person signs about the same way regardless of who's standing there — so a customer whose signature under one tech looks nothing like their signature under another is a lead worth a second look. Same-tech repeats are the consistency baseline.</p>
        <div class="nav-links">
            <a href="/stats">Compliance Stats</a>
            <a href="/techs">Signature Gallery</a>
            <a href="/">Review Detection</a>
        </div>
    </div>
    <div class="container">
        <div class="filters">
            <a href="/customers?mode=cross" class="{% if mode == 'cross' %}on{% endif %}">Different techs ({{ n_cross }})</a>
            <a href="/customers?mode=same" class="{% if mode == 'same' %}on{% endif %}">Same tech ({{ n_same }})</a>
            <a href="/customers?mode=all" class="{% if mode == 'all' %}on{% endif %}">All ({{ n_all }})</a>
            <span>{{ groups|length }} customers shown, {{ n_sigs }} signatures</span>
        </div>
        {% for g in groups %}
        <div class="group {% if g.cross %}cross{% endif %}">
            <h2>{{ g.name }}{% if g.cross %}<span class="tag">{{ g.techs|length }} techs</span>{% endif %}</h2>
            <div class="addr">{{ g.street }}</div>
            <div class="sigs">
                {% for r in g.records %}
                <div class="sig" onclick="openModal('/image/{{ r.ticket_number }}/{{ r.variant }}/{{ r.month_folder }}')">
                    <img src="/signature/{{ r.ticket_number }}/{{ r.variant }}/{{ r.month_folder }}" loading="lazy">
                    <div class="cap"><b>{{ r.technician_name }}</b><span>{{ r.ticket_number }}{{ r.variant }} · {{ r.month_folder }}</span></div>
                </div>
                {% endfor %}
            </div>
        </div>
        {% endfor %}
    </div>
    <div class="modal" id="modal" onclick="this.classList.remove('active')"><img id="modal-img"></div>
    <script>
        function openModal(src) { document.getElementById('modal-img').src = src; document.getElementById('modal').classList.add('active'); }
    </script>
</body>
</html>
"""


@app.route('/customers')
def customers():
    """Repeat customers' signatures side by side, grouped by customer."""
    mode = request.args.get("mode", "cross")
    by_customer: dict[str, list] = {}
    for r in db.get_signed_with_customer():
        if not (TICKETS_ROOT / r.month_folder / f"{r.ticket_number}{r.variant}.png").exists():
            continue   # e.g. 2026-01 — analyzed, but the images are no longer on disk
        by_customer.setdefault(r.customer, []).append(r)
    groups = []
    for customer, records in by_customer.items():
        if len(records) < 2:
            continue
        techs = sorted({r.technician_name or "UNKNOWN" for r in records})
        name, _, street = customer.partition(" · ")
        groups.append({"name": name, "street": street, "records": records, "techs": techs, "cross": len(techs) > 1})
    n_cross = sum(1 for g in groups if g["cross"]); n_all = len(groups); n_same = n_all - n_cross
    if mode == "cross":
        groups = [g for g in groups if g["cross"]]
    elif mode == "same":
        groups = [g for g in groups if not g["cross"]]
    groups.sort(key=lambda g: (not g["cross"], -len(g["records"]), g["name"]))
    return render_template_string(
        CUSTOMERS_TEMPLATE, groups=groups, mode=mode,
        n_cross=n_cross, n_same=n_same, n_all=n_all, n_sigs=sum(len(g["records"]) for g in groups),
    )


if __name__ == '__main__':
    print("\n" + "="*50)
    print("  Signature Detection Review App")
    print("="*50)
    print("\n  Open in browser: http://localhost:5050\n")
    print("  Routes:")
    print("    /       - Review random sample")
    print("    /techs  - Signature gallery by technician")
    print("    /stats  - Signature compliance charts")
    print("    /customers - Repeat customers' signatures side by side")
    print("\n  Press Ctrl+C to stop\n")
    
    app.run(host='0.0.0.0', port=5050, debug=False)
