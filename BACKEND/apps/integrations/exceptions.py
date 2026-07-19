"""Exceptions for Universal Assistance / Siebel integrations."""


class IntegrationError(Exception):
    """Base error for external integration failures."""

    def __init__(self, message: str, *, code: str | None = None, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class SiebelSoapError(IntegrationError):
    """SOAP transport or parsing error."""


class SiebelBusinessError(IntegrationError):
    """Siebel returned a business error (ErrorCode != 00)."""
