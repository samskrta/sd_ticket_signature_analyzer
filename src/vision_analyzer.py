"""Google Cloud Vision API client for OCR and signature detection."""

from dataclasses import dataclass
from google.cloud import vision
from PIL import Image
import io
import re

from src.auth import get_vision_client
from src.drive_client import DriveImage
from config import settings


@dataclass
class AnalysisResult:
    """Result of analyzing a service ticket image."""
    technician_name: str | None
    has_signature: bool
    confidence: float
    raw_text: str
    signature_confidence: float


class VisionAnalyzer:
    """Analyzes service ticket images using Google Cloud Vision API."""
    
    def __init__(self):
        self.client = get_vision_client()
        self.tech_region = settings.tech_name_region
        self.sig_region = settings.signature_region
    
    def analyze(self, image: DriveImage) -> AnalysisResult:
        """
        Analyze a service ticket image.
        
        Args:
            image: DriveImage with content loaded
            
        Returns:
            AnalysisResult with extracted data
        """
        if not image.content:
            raise ValueError("Image content not loaded. Call download_image first.")
        
        # Perform OCR on full image
        vision_image = vision.Image(content=image.content)
        response = self.client.document_text_detection(image=vision_image)
        
        if response.error.message:
            raise RuntimeError(f"Vision API error: {response.error.message}")
        
        full_text = response.full_text_annotation.text if response.full_text_annotation else ""
        
        # Extract technician name from the expected region
        tech_name = self._extract_technician_name(response, image.content)
        
        # Detect signature presence
        has_sig, sig_confidence = self._detect_signature(image.content)
        
        # Calculate overall confidence from OCR
        confidence = self._calculate_confidence(response)
        
        return AnalysisResult(
            technician_name=tech_name,
            has_signature=has_sig,
            confidence=confidence,
            raw_text=full_text,
            signature_confidence=sig_confidence
        )
    
    def _extract_technician_name(
        self, 
        response: vision.AnnotateImageResponse,
        image_content: bytes
    ) -> str | None:
        """
        Extract technician name from the configured region.
        
        Looks for common patterns like:
        - "Technician: John Smith"
        - "Tech: John Smith"
        - "Service by: John Smith"
        """
        full_text = response.full_text_annotation.text if response.full_text_annotation else ""
        
        # Common patterns for technician names
        patterns = [
            r"(?:Technician|Tech|Service\s*by|Performed\s*by|Serviced\s*by)\s*[:\-]?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
            r"(?:Tech\s*Name|Technician\s*Name)\s*[:\-]?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        # Fallback: Look for text blocks in the tech name region
        # This requires analyzing word positions
        if response.full_text_annotation and response.full_text_annotation.pages:
            img = Image.open(io.BytesIO(image_content))
            img_width, img_height = img.size
            
            region = self.tech_region
            names_in_region = []
            
            for page in response.full_text_annotation.pages:
                for block in page.blocks:
                    for paragraph in block.paragraphs:
                        for word in paragraph.words:
                            # Check if word is in tech name region
                            vertices = word.bounding_box.vertices
                            if vertices:
                                x = vertices[0].x
                                y = vertices[0].y
                                
                                if (region["left"] <= x <= region["left"] + region["width"] and
                                    region["top"] <= y <= region["top"] + region["height"]):
                                    word_text = "".join([s.text for s in word.symbols])
                                    names_in_region.append(word_text)
            
            if names_in_region:
                # Join words that look like a name
                potential_name = " ".join(names_in_region)
                # Filter to just capitalized words (likely names)
                name_parts = [w for w in potential_name.split() if w[0].isupper()]
                if len(name_parts) >= 2:
                    return " ".join(name_parts[:3])  # First/Last or First/Middle/Last
        
        return None
    
    def _detect_signature(self, image_content: bytes) -> tuple[bool, float]:
        """
        Detect if a signature is present in the signature region.
        
        Uses a combination of:
        1. Handwriting detection via Vision API
        2. Pixel density analysis in signature region
        
        Returns:
            Tuple of (has_signature, confidence)
        """
        img = Image.open(io.BytesIO(image_content))
        
        # Crop to signature region
        region = self.sig_region
        sig_box = (
            region["left"],
            region["top"],
            region["left"] + region["width"],
            region["top"] + region["height"]
        )
        
        # Ensure crop box is within image bounds
        sig_box = (
            max(0, sig_box[0]),
            max(0, sig_box[1]),
            min(img.width, sig_box[2]),
            min(img.height, sig_box[3])
        )
        
        sig_region_img = img.crop(sig_box)
        
        # Convert to grayscale for analysis
        sig_gray = sig_region_img.convert("L")
        
        # Count dark pixels (potential ink marks)
        pixels = list(sig_gray.getdata())
        total_pixels = len(pixels)
        
        if total_pixels == 0:
            return False, 0.0
        
        # Count pixels darker than threshold (ink marks)
        dark_threshold = 180  # Pixels darker than this are "ink"
        dark_pixels = sum(1 for p in pixels if p < dark_threshold)
        
        # Calculate ink density
        ink_density = dark_pixels / total_pixels
        
        # Signature typically has 1-15% ink coverage
        # Too low = no signature, too high = printed text/graphics
        if 0.01 <= ink_density <= 0.20:
            # Likely a signature
            # Higher confidence for "sweet spot" density (3-10%)
            if 0.03 <= ink_density <= 0.10:
                confidence = 0.9
            else:
                confidence = 0.7
            return True, confidence
        elif ink_density < 0.01:
            # Too sparse - probably no signature
            return False, 0.9
        else:
            # Too dense - might be printed text, not handwriting
            # Use Vision API to check for handwriting
            return self._check_handwriting_in_region(image_content, sig_box)
    
    def _check_handwriting_in_region(
        self, 
        image_content: bytes, 
        region: tuple
    ) -> tuple[bool, float]:
        """Use Vision API to detect handwriting in a region."""
        img = Image.open(io.BytesIO(image_content))
        cropped = img.crop(region)
        
        # Convert cropped image to bytes
        buffer = io.BytesIO()
        cropped.save(buffer, format="PNG")
        cropped_bytes = buffer.getvalue()
        
        vision_image = vision.Image(content=cropped_bytes)
        response = self.client.document_text_detection(image=vision_image)
        
        # Check for handwritten text
        if response.full_text_annotation and response.full_text_annotation.pages:
            for page in response.full_text_annotation.pages:
                for block in page.blocks:
                    # Check block confidence - handwriting typically has lower confidence
                    if block.confidence < 0.8:
                        return True, 0.75
        
        return False, 0.5
    
    def _calculate_confidence(self, response: vision.AnnotateImageResponse) -> float:
        """Calculate overall OCR confidence score."""
        if not response.full_text_annotation or not response.full_text_annotation.pages:
            return 0.0
        
        confidences = []
        for page in response.full_text_annotation.pages:
            for block in page.blocks:
                confidences.append(block.confidence)
        
        if not confidences:
            return 0.0
        
        return sum(confidences) / len(confidences)
