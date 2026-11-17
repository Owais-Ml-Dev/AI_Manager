"""Shared exception types, mapped to HTTP responses by feature routers."""


class AppError(Exception):
    """Base class for all application-level errors."""


class NotFoundError(AppError):
    """Raised when a requested resource does not exist or isn't owned by the caller."""


class ValidationError(AppError):
    """Raised when input passes Pydantic but fails a business rule."""
