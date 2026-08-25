class CamtError(Exception):
    """Base class for all errors raised by the camt package."""


class CamtParseError(CamtError):
    """Raised when a CAMT document cannot be parsed."""


class UnsupportedMessageType(CamtError):
    """Raised when a document's root element does not match a supported CAMT message type."""