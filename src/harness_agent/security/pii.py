"""PII (Personally Identifiable Information) detection middleware.

Phase 5 — Security Hardening (per AIDLC §5.6 PII Protection).

Detects and warns about PII in:
- Tool inputs (prevent storing PII)
- Tool outputs (prevent leaking PII)
- Memory writes (prevent persisting PII)

Does NOT block — it warns and redacts, letting the human operator decide.
"""

from __future__ import annotations

import re


class PIIMiddleware:
    """Middleware that detects and warns about PII in agent interactions.

    Scans for common PII patterns:
    - Email addresses
    - Credit card numbers
    - SSN (US Social Security numbers)
    - Phone numbers (various formats)
    - API keys / tokens
    - IP addresses (potential PII in some jurisdictions)

    Attributes:
        redact: If True, redact detected PII instead of just warning.
        patterns: Dict of pattern name → compiled regex for detection.
    """

    def __init__(self, redact: bool = False) -> None:
        self.redact = redact
        self.patterns = _build_pii_patterns()
        self._detected: list[dict[str, str]] = []

    def scan(self, text: str, source: str = "unknown") -> str:
        """Scan text for PII and optionally redact.

        Args:
            text: The text to scan for PII.
            source: Where the text came from (e.g., "tool_input", "memory").

        Returns:
            The text with PII redacted (if redact=True), or original text.
        """
        self._detected.clear()

        for name, pattern in self.patterns.items():
            matches = pattern.findall(text)
            for match in matches:
                match_str = str(match)
                self._detected.append({
                    "type": name,
                    "source": source,
                    "value_preview": match_str[:50] + ("..." if len(match_str) > 50 else ""),
                })

        if self.redact and self._detected:
            text = self._redact_all(text)

        return text

    def has_pii(self) -> bool:
        """Check if any PII was detected in the last scan.

        Returns:
            True if PII was detected.
        """
        return len(self._detected) > 0

    def get_detected(self) -> list[dict[str, str]]:
        """Get the list of detected PII items.

        Returns:
            List of dicts with type, source, and value_preview.
        """
        return list(self._detected)

    def clear(self) -> None:
        """Clear the detection log."""
        self._detected.clear()

    def _redact_all(self, text: str) -> str:
        """Redact all known PII patterns from text.

        Args:
            text: The text to redact.

        Returns:
            Redacted text with PII replaced by [REDACTED_<type>].
        """
        for name, pattern in self.patterns.items():
            text = pattern.sub(f"[REDACTED_{name.upper()}]", text)
        return text


def _build_pii_patterns() -> dict[str, re.Pattern[str]]:
    """Build the compiled PII detection regex patterns.

    Returns:
        Dict mapping pattern names to compiled regex patterns.
    """
    return {
        "email": re.compile(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        ),
        "credit_card": re.compile(
            r"\b(?:\d[ -]*?){13,16}\b"
        ),
        "ssn": re.compile(
            r"\b\d{3}[ -]\d{2}[ -]\d{4}\b"
        ),
        "phone": re.compile(
            r"\b(?:\+?\d{1,3}[ -])?\(?\d{3}\)?[ -]?\d{3}[ -]?\d{4}\b"
        ),
        "api_key": re.compile(
            r"\b(?:sk|api|key|token|secret)[-_][A-Za-z0-9]{20,}\b"
        ),
        "ip_address": re.compile(
            r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
        ),
        "aws_access_key": re.compile(
            r"\bAKIA[0-9A-Z]{16}\b"
        ),
        "github_token": re.compile(
            r"\bgh[pousr]_[A-Za-z0-9_]{36,}\b"
        ),
    }


__all__ = ["PIIMiddleware"]
