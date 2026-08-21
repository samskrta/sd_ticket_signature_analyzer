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

# ServiceDesk technician codes → display name ("First L"). This is the
# authoritative identity; OCR names are only a fallback. Source: ServiceDesk
# appointments / work_history, cross-checked against rossware-sync's
# tech_commission.json roster (2026-08-21).
TECH_CODES = {
    "AB": "Anthony B",   # Anthony Bellmer
    "AD": "Addy N",      # Addyson Nelson
    "AI": "Derek I",     # 1 ticket in 2026-08; image reads "by Derek I" — alias of DI
    "AR": "Austin R",    # Austin Rutenschroer (OCR merged into "Austin L")
    "AZ": "Ali Z",       # Ali Zangeneh
    "BC": "Brian C",     # Brian Connolly
    "BK": "Bryce K",     # Bryce Kopf
    "CD": "Chuck D",     # Chuck Dalton
    "CH": "Chance H",    # Chance Holcer
    "CR": "Cole R",      # Cole Rudeen
    "CS": "Chris S",     # Chris Statham
    "DI": "Derek I",     # Derek Irvin (OCR merged into "Derek F")
    "DK": "Darrin S",    # not in commission roster; OCR reads "Darrin S" 219/219
    "DN": "Darren B",    # Darren Bitzer
    "DR": "Derek F",     # Derek Frenzel
    "EC": "Eric C",      # Eric Cardwell
    "JL": "Jacob L",     # Jacob Loncke
    "JY": "Jimmy Y",     # Jimmy Young
    "KB": "Kelvin B",    # Kelvin Blessing
    "KH": "Koby H",      # Koby Ham
    "KY": "Ky S",        # Ky Sage
    "LA": "Lucas H",     # Lucas Hinton
    "MF": "Mark F",      # Mark Fleming
    "MM": "Michael M",   # Mike Marnik
    "MP": "Mike F",      # Mike Fleming
    "NF": "Nick F",      # Nick Farrow
    "OL": "Owen L",      # Owen L — started 2026-08
    "RL": "Austin L",    # Austin Loncke
    "RT": "Rory T",      # Rory Tierney
    "SG": "Shannon G",   # Shannon Goedde
    "SZ": "Sal Z",       # Sal Z — started 2026-06 (OCR merged into "Ali Z")
    "TB": "Tyke B",      # not in commission roster; ticket prints "by Tyke B Ctec"
    "TM": "Travis M",    # Travis Moulder
}


# Techs whose work never produces a customer signature — excluded from compliance
# charts so they don't drag the numbers down for a reason that isn't non-compliance.
NO_SIGNATURE_CODES = {
    "DK",   # Darrin S — remote/virtual visits only
}


def name_for_code(code: str | None) -> str | None:
    """Display name for a ServiceDesk tech code; falls back to the code itself."""
    if not code:
        return None
    code = code.upper()
    return TECH_CODES.get(code, code)


# Known good technician names (first name + last initial)
KNOWN_TECHS = [
    "Addy N",
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
    "Owen L",
    "Rory T",
    "Sal Z",
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
