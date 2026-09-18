"""Enterprise PII and Secret Sanitizer.
Ensures sensitive information (passwords, API keys, credit cards) is never stored.
"""

import re
from typing import Tuple


# Regex patterns for high-risk secrets and PII
PATTERNS = {
    # API Keys & Secrets
    "OPENAI_KEY": r"\bsk-[a-zA-Z0-9]{32,}\b",
    "GEMINI_KEY": r"\bAIza[0-9A-Za-z-_]{35}\b",
    "GITHUB_TOKEN": r"\bgh[pousr]_[0-9a-zA-Z]{36}\b",
    "GENERIC_BEARER": r"(?i)bearer\s+[a-zA-Z0-9\-_\.]{20,}",
    "GENERIC_API_KEY": r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*['\"][a-zA-Z0-9\-_\.]{16,}['\"]",
    
    # Financial & Identification PII
    "CREDIT_CARD": r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b",
    "SSN": r"\b\d{3}-\d{2}-\d{4}\b",
    
    # Contact Info
    "EMAIL": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    "PHONE": r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
}


def sanitize_text(text: str) -> Tuple[str, bool]:
    """
    Sanitizes raw text by replacing secrets and sensitive PII with safe tokens.
    
    Returns:
        (sanitized_text, had_redactions)
    """
    if not text:
        return text, False

    sanitized = text
    had_redaction = False

    for label, pattern in PATTERNS.items():
        replacement = f"<REDACTED_{label}>"
        new_text, count = re.subn(pattern, replacement, sanitized)
        if count > 0:
            sanitized = new_text
            had_redaction = True

    return sanitized, had_redaction
