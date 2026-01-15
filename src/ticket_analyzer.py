"""Ticket image analyzer - extracts technician name and detects signatures."""

from dataclasses import dataclass
from pathlib import Path
import re

from PIL import Image
import io
import pytesseract
from src.tech_names import normalize_tech_name


@dataclass
class TicketAnalysis:
    """Result of analyzing a ticket image."""
    technician_name: str | None
    technician_role: str | None
    has_signature: bool
    signature_confidence: float
    ticket_number: str | None
    ticket_date: str | None
    has_legal_text: bool  # Indicates signature-required ticket type


class TicketAnalyzer:
    """
    Analyzes ticket images using OCR and image processing.
    
    For full OCR, requires Google Cloud Vision API.
    For signature detection, uses local image analysis.
    """
    
    def __init__(self, use_vision_api: bool = False):
        self.use_vision_api = use_vision_api
        self._vision_client = None
        
        if use_vision_api:
            from src.auth import get_vision_client
            self._vision_client = get_vision_client()
    
    def analyze(self, image_path: Path | str, image_bytes: bytes | None = None) -> TicketAnalysis:
        """
        Analyze a ticket image.
        
        Args:
            image_path: Path to the image file
            image_bytes: Optional pre-loaded image bytes
            
        Returns:
            TicketAnalysis with extracted data
        """
        if image_bytes is None:
            image_bytes = Path(image_path).read_bytes()
        
        # Use Vision API for full OCR if available
        if self.use_vision_api and self._vision_client:
            return self._analyze_with_vision(image_bytes)
        
        # Otherwise use local analysis (signature detection only)
        return self._analyze_local(image_bytes)
    
    def _analyze_with_vision(self, image_bytes: bytes) -> TicketAnalysis:
        """Full analysis using Google Cloud Vision API."""
        from google.cloud import vision
        
        image = vision.Image(content=image_bytes)
        response = self._vision_client.document_text_detection(image=image)
        
        if response.error.message:
            raise RuntimeError(f"Vision API error: {response.error.message}")
        
        full_text = response.full_text_annotation.text if response.full_text_annotation else ""
        
        # Extract technician name from "by [Name] [Role]" pattern
        tech_name, tech_role = self._extract_technician(full_text)
        
        # Extract ticket number and date
        ticket_num = self._extract_ticket_number(full_text)
        ticket_date = self._extract_date(full_text)
        
        # Check for legal text (indicates signature-required ticket)
        has_legal = "I have reviewed this form" in full_text
        
        # Detect signature
        has_sig, sig_conf = self._detect_signature(image_bytes, has_legal)
        
        return TicketAnalysis(
            technician_name=tech_name,
            technician_role=tech_role,
            has_signature=has_sig,
            signature_confidence=sig_conf,
            ticket_number=ticket_num,
            ticket_date=ticket_date,
            has_legal_text=has_legal,
        )
    
    def _analyze_local(self, image_bytes: bytes) -> TicketAnalysis:
        """
        Local analysis using Tesseract OCR.
        
        All tickets require signatures - check for signature presence.
        """
        img = Image.open(io.BytesIO(image_bytes))
        
        # Extract text using Tesseract OCR
        # Focus on the tech name region (bottom-left, ~78-82% down)
        width, height = img.size
        tech_region = img.crop((0, int(height * 0.78), int(width * 0.50), int(height * 0.82)))
        
        try:
            text = pytesseract.image_to_string(tech_region, config='--psm 7')
            tech_name, tech_role = self._extract_technician(text)
            # Normalize to correct OCR errors
            tech_name = normalize_tech_name(tech_name)
        except Exception:
            tech_name, tech_role = None, None
        
        # Also try to get ticket number from top-right
        ticket_num = None
        ticket_date = None
        try:
            header_region = img.crop((int(width * 0.6), 60, width - 10, 120))
            header_text = pytesseract.image_to_string(header_region, config='--psm 7')
            ticket_num = self._extract_ticket_number(header_text)
            ticket_date = self._extract_date(header_text)
        except Exception:
            pass
        
        has_sig, sig_conf = self._detect_signature_universal(image_bytes)
        
        return TicketAnalysis(
            technician_name=tech_name,
            technician_role=tech_role,
            has_signature=has_sig,
            signature_confidence=sig_conf,
            ticket_number=ticket_num,
            ticket_date=ticket_date,
            has_legal_text=True,  # All tickets require signatures
        )
    
    def _extract_technician(self, text: str) -> tuple[str | None, str | None]:
        """Extract technician name and role from ticket text."""
        # Clean up common OCR artifacts
        text = text.replace("|", "I").replace("/", "").replace("\\", "")
        text = re.sub(r'[^\w\s]', ' ', text)  # Remove special chars
        text = re.sub(r'\s+', ' ', text)  # Collapse whitespace
        
        # Pattern 1: "by FirstName LastInitial Role" with space
        pattern1 = r"by\s+([A-Z][a-z]+)\s+([A-Z])\s+(?:Ld\s+)?([A-Z][A-Za-z]+)"
        match = re.search(pattern1, text, re.IGNORECASE)
        if match:
            first_name = match.group(1).title()
            last_initial = match.group(2).upper()
            role = match.group(3)
            return f"{first_name} {last_initial}", role
        
        # Pattern 2: "by FirstName LastInitialRole" (no space before role)
        pattern2 = r"by\s+([A-Z][a-z]+)\s+([A-Z])([A-Z][A-Za-z]+)"
        match = re.search(pattern2, text, re.IGNORECASE)
        if match:
            first_name = match.group(1).title()
            last_initial = match.group(2).upper()
            role = match.group(3)
            return f"{first_name} {last_initial}", role
        
        # Pattern 3: Just "by FirstName Initial" (role may be garbled)
        pattern3 = r"by\s+([A-Z][a-z]+)\s+([A-Z])"
        match = re.search(pattern3, text, re.IGNORECASE)
        if match:
            first_name = match.group(1).title()
            last_initial = match.group(2).upper()
            return f"{first_name} {last_initial}", None
        
        return None, None
    
    def _extract_ticket_number(self, text: str) -> str | None:
        """Extract ticket number from text."""
        # Pattern: #123456
        match = re.search(r"#(\d{5,7})", text)
        return match.group(1) if match else None
    
    def _extract_date(self, text: str) -> str | None:
        """Extract date from ticket text."""
        # Pattern: M/DD/YY or MM/DD/YY
        match = re.search(r"(\d{1,2}/\d{1,2}/\d{2})", text)
        return match.group(1) if match else None
    
    def _detect_signature_universal(self, image_bytes: bytes) -> tuple[bool, float]:
        """
        Detect if a signature is present on any ticket.
        
        All tickets require signatures. Signature appears BELOW the 
        technician name line ("by [Name]"), above any footer content.
        """
        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size
        
        # Signature region: BELOW the "by [Tech Name]" line
        # Tech name is at ~76-78% down, signature starts at ~82%
        # Only check left side (avoid payment info on right)
        # Exclude very bottom (legal text if present)
        
        sig_left = 10
        sig_right = int(width * 0.45)  # Left side only
        sig_top = int(height * 0.82)   # Well below "by [Name]" line
        sig_bottom = int(height * 0.94)  # Above footer
        
        if sig_bottom <= sig_top:
            return False, 0.5
        
        # Crop to signature region (below tech name)
        sig_region = img.crop((sig_left, sig_top, sig_right, sig_bottom))
        
        # Convert to grayscale
        sig_gray = sig_region.convert("L")
        pixels = list(sig_gray.getdata())
        
        if not pixels:
            return False, 0.5
        
        # Count dark pixels (ink marks)
        dark_threshold = 170
        dark_pixels = sum(1 for p in pixels if p < dark_threshold)
        ink_density = dark_pixels / len(pixels)
        
        # Signature detection thresholds:
        # Very low (< 2%) = no signature or tiny dot (not valid sig)
        # Medium (2-10%) = likely real signature
        # High (> 12%) = probably printed text or overlapping elements
        
        if ink_density < 0.02:
            # Too sparse - blank or just a dot, not a real signature
            return False, 0.92
        elif 0.02 <= ink_density <= 0.10:
            # Good signature range
            confidence = 0.88 if 0.025 <= ink_density <= 0.07 else 0.72
            return True, confidence
        else:
            # High density - could be signature or printed content
            return True, 0.55
