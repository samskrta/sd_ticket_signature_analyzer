"""Technician name normalization and fuzzy matching."""

from difflib import SequenceMatcher

# Manual corrections for common OCR errors
OCR_CORRECTIONS = {
    # General typos
    "Dgrtey B": "Darren B",
    "Nigh F": "Nick F",
    "Aap B": "Anthony B",
    "Chugk B": "Chuck D",
    "Chugk D": "Chuck D",
    # Koby H corrections (H often misread as A, I, D, etc.)
    "Koby A": "Koby H",
    "Koby I": "Koby H",
    "Koby D": "Koby H",
    # Darren B corrections (B often misread as P, D)
    "Darren P": "Darren B",
    "Darren D": "Darren B",
    # Chuck D corrections
    "Chuck B": "Chuck D",
    # Chance H corrections
    "Chance A": "Chance H",
    "Chance I": "Chance H",
}

# Known good technician names (first name + last initial)
KNOWN_TECHS = [
    "Ali Z",
    "Anthony A",
    "Anthony B",
    "Austin L",
    "Bryce K",
    "Chance H",
    "Chris S",
    "Chuck D",
    "Darren B",
    "Darrin S",
    "Derek F",
    "Jimmy Y",
    "Kelvin B",
    "Koby H",
    "Ky S",
    "Lucas H",
    "Mark F",
    "Michael M",
    "Mike F",
    "Nick F",
    "Rory T",
    "Shannon G",
    "Travis M",
]


def similarity(a: str, b: str) -> float:
    """Calculate similarity ratio between two strings."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def normalize_tech_name(name: str | None) -> str | None:
    """
    Normalize a technician name to match known techs.
    
    Uses manual corrections first, then fuzzy matching.
    Returns None for garbage OCR that doesn't match any known tech.
    """
    if not name:
        return None
    
    name = name.strip()
    
    # Check manual corrections first
    if name in OCR_CORRECTIONS:
        return OCR_CORRECTIONS[name]
    
    # Exact match to known techs
    if name in KNOWN_TECHS:
        return name
    
    # Find best fuzzy match
    best_match = None
    best_score = 0.0
    
    for known in KNOWN_TECHS:
        score = similarity(name, known)
        if score > best_score:
            best_score = score
            best_match = known
    
    # Only accept if similarity is high enough (> 65%)
    if best_score >= 0.65:
        return best_match
    
    # If no good match, return None (will show as UNKNOWN)
    # This filters out OCR garbage like "Hmsfec I" or "Anthgpybptec G"
    return None


def add_known_tech(name: str):
    """Add a new technician to the known list."""
    if name and name not in KNOWN_TECHS:
        KNOWN_TECHS.append(name)
        KNOWN_TECHS.sort()
