#!/usr/bin/env python3
"""Web app for reviewing signature detection accuracy."""

import random
import base64
import io
from pathlib import Path
from flask import Flask, render_template_string, jsonify, request, Response
from PIL import Image

import sys
sys.path.insert(0, str(Path(__file__).parent))

from src.database import AuditDatabase

app = Flask(__name__)
db = AuditDatabase()

# Signature region as percentages (matches ticket_analyzer.py)
SIG_LEFT = 0.0
SIG_RIGHT = 0.45
SIG_TOP = 0.82
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
    records = db.get_all_records()
    
    # Get balanced sample: some with sig, some without
    with_sig = [r for r in records if r.has_signature]
    without_sig = [r for r in records if not r.has_signature]
    
    # Sample 25 from each category (or all if less)
    sample_size = 25
    sample = []
    sample.extend(random.sample(with_sig, min(sample_size, len(with_sig))))
    sample.extend(random.sample(without_sig, min(sample_size, len(without_sig))))
    random.shuffle(sample)
    
    return render_template_string(HTML_TEMPLATE, records=sample, total=len(sample))


@app.route('/image/<ticket_num>/<variant>/<month>')
def get_image(ticket_num, variant, month):
    """Serve ticket image."""
    tickets_path = Path(__file__).parent / "tickets" / "Tckts"
    image_path = tickets_path / month / f"{ticket_num}{variant}.png"
    
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
            <a href="/techs" class="back-link">← All Technicians</a>
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
            <a href="/">← Review Detection</a>
        </div>
    </div>
    
    <div class="container">
        <div class="tech-list">
            {% for tech in techs %}
            <a href="/techs/{{ tech.name|urlencode }}" class="tech-card">
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
    records = db.get_all_records()
    
    # Count signatures per tech
    tech_counts = {}
    for r in records:
        if r.has_signature:
            name = r.technician_name or "UNKNOWN"
            tech_counts[name] = tech_counts.get(name, 0) + 1
    
    # Sort by count descending
    techs = [{'name': k, 'count': v} for k, v in tech_counts.items()]
    techs.sort(key=lambda x: -x['count'])
    
    return render_template_string(TECHS_TEMPLATE, techs=techs)


@app.route('/techs/<tech_name>')
def tech_gallery(tech_name):
    """Show all signatures for a specific technician."""
    records = db.get_all_records()
    
    # Handle UNKNOWN
    if tech_name == "UNKNOWN" or tech_name == "None":
        signatures = [r for r in records if r.has_signature and r.technician_name is None]
    else:
        signatures = [r for r in records if r.has_signature and r.technician_name == tech_name]
    
    # Sort by ticket number
    signatures.sort(key=lambda x: x.ticket_number)
    
    return render_template_string(GALLERY_TEMPLATE, tech_name=tech_name, signatures=signatures)


@app.route('/signature/<ticket_num>/<variant>/<month>')
def get_signature(ticket_num, variant, month):
    """Serve cropped signature region."""
    tickets_path = Path(__file__).parent / "tickets" / "Tckts"
    image_path = tickets_path / month / f"{ticket_num}{variant}.png"
    
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


if __name__ == '__main__':
    print("\n" + "="*50)
    print("  Signature Detection Review App")
    print("="*50)
    print("\n  Open in browser: http://localhost:5050\n")
    print("  Routes:")
    print("    /       - Review random sample")
    print("    /techs  - Signature gallery by technician")
    print("\n  Press Ctrl+C to stop\n")
    
    app.run(host='0.0.0.0', port=5050, debug=False)
