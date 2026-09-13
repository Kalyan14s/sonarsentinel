"""Typed errors shared by the pipeline, CLI and API.

Each error has a stable ``code`` and HTTP status matching the API error model in
``docs/architecture/05-api-specification.md`` section 4.
"""

from __future__ import annotations


class SonarSentinelError(Exception):
    """Base class for expected, user-facing SonarSentinel errors."""

    code: str = "INTERNAL_ERROR"
    http_status: int = 500

    def __init__(self, message: str, **details: object) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, object] = dict(details)

    def to_dict(self) -> dict[str, object]:
        """Serialise to the API error shape ``{"error": {code, message, details}}``."""
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class ValidationError(SonarSentinelError):
    """Bad parameter, option or configuration."""

    code = "VALIDATION_ERROR"
    http_status = 400


class NavCsvInvalidError(SonarSentinelError):
    """Navigation CSV is missing required columns or has invalid values."""

    code = "NAV_CSV_INVALID"
    http_status = 400


class NotFoundError(SonarSentinelError):
    """Survey, job or detection does not exist."""

    code = "NOT_FOUND"
    http_status = 404


class JobNotCancellableError(SonarSentinelError):
    """The job has already finished."""

    code = "JOB_NOT_CANCELLABLE"
    http_status = 409


class FileTooLargeError(SonarSentinelError):
    """Upload exceeds the configured size limit."""

    code = "FILE_TOO_LARGE"
    http_status = 413


class UnsupportedFormatError(SonarSentinelError):
    """File type is not supported."""

    code = "UNSUPPORTED_FORMAT"
    http_status = 415


class CorruptHeaderError(SonarSentinelError):
    """File extension is supported but the content can't be parsed."""

    code = "CORRUPT_HEADER"
    http_status = 422


class CrsRequiredError(SonarSentinelError):
    """Projected coordinates were found but no EPSG code is known."""

    code = "CRS_REQUIRED"
    http_status = 422


class ModelsNotLoadedError(SonarSentinelError):
    """Model files are missing or failed to load."""

    code = "MODELS_NOT_LOADED"
    http_status = 503
