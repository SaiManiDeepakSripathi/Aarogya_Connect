"""
Automatic doctor-certificate verification.

This runs real OCR (Tesseract, via pytesseract) on the uploaded certificate
image, then scores the extracted text against the markers you'd expect on a
genuine medical qualification/registration certificate: a recognized degree
(MBBS, MD, BDS, ...), council/registration language, and the doctor's own
name appearing on the document.

Important honesty note: this is text-pattern verification, not a lookup
against any real medical council or licensing database — there is no such
API wired in. It's meant to auto-clear obviously-genuine uploads and
auto-reject obviously-wrong ones (a random photo, a blank scan), while
routing anything ambiguous to "pending" for a human to review. Treat
"verified" here as "passed automated screening," not a legal credential
check.
"""

import re

try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

DEGREE_KEYWORDS = [
    "mbbs", "md", "ms", "bams", "bhms", "bds", "do", "dnb", "mci",
    "doctor of medicine", "bachelor of medicine", "medical degree",
]
COUNCIL_KEYWORDS = [
    "medical council", "registration no", "registration number", "reg. no",
    "reg no", "license no", "licence no", "board of medical",
    "council of medicine", "medical board", "medical registration",
]
GENERIC_KEYWORDS = [
    "certificate", "certify", "certifies", "hereby", "awarded", "graduated",
    "diploma", "degree",
]


def _extract_text(image_path):
    if not OCR_AVAILABLE:
        return None  # signals "OCR engine unavailable" to the caller
    try:
        img = Image.open(image_path)
        return pytesseract.image_to_string(img) or ""
    except Exception:
        return None


def _name_tokens(name):
    # Drop honorifics and keep tokens that are meaningful to match on.
    cleaned = re.sub(r"\bdr\.?\b", "", name, flags=re.IGNORECASE)
    return [t for t in re.findall(r"[A-Za-z]+", cleaned) if len(t) >= 3]


def verify_certificate(image_path, doctor_name):
    """
    Returns dict: {status, notes, extractedPreview}
    status is one of: verified, pending, rejected
    """
    text = _extract_text(image_path)

    if text is None:
        return {
            "status": "pending",
            "notes": "Automatic verification unavailable (OCR engine not installed on the server) — flagged for manual review.",
            "extractedPreview": "",
        }

    lowered = text.lower()
    clean_len = len(text.strip())

    degree_hits = [k for k in DEGREE_KEYWORDS if k in lowered]
    council_hits = [k for k in COUNCIL_KEYWORDS if k in lowered]
    generic_hits = [k for k in GENERIC_KEYWORDS if k in lowered]

    tokens = _name_tokens(doctor_name)
    name_match = any(tok.lower() in lowered for tok in tokens) if tokens else False

    preview = " ".join(text.split())[:220]

    if clean_len < 20:
        return {
            "status": "rejected",
            "notes": "No readable text was detected on the image — please upload a clearer scan or photo of the certificate.",
            "extractedPreview": preview,
        }

    if name_match and (degree_hits or council_hits):
        found = degree_hits[:2] + council_hits[:2]
        return {
            "status": "verified",
            "notes": f"Doctor's name matched the document, and detected: {', '.join(found)}. Automatically verified.",
            "extractedPreview": preview,
        }

    if degree_hits or council_hits or (name_match and generic_hits):
        found = (degree_hits + council_hits + (["name match"] if name_match else []))[:3]
        return {
            "status": "pending",
            "notes": f"Some certificate markers were detected ({', '.join(found) or 'partial match'}) but this couldn't be fully confirmed automatically — flagged for manual review.",
            "extractedPreview": preview,
        }

    return {
        "status": "rejected",
        "notes": "Couldn't detect recognizable certificate markers (a medical degree, council/registration text, or the doctor's name) on this image.",
        "extractedPreview": preview,
    }
