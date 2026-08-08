"""Application-specific exception types."""


class ReposterError(Exception):
    """Base class for expected application errors."""


class TelegramServiceError(ReposterError):
    """A Telegram client or bot operation failed."""


class DatabaseServiceError(ReposterError):
    """A database operation failed."""


class UnauthorizedAdminError(ReposterError):
    """A Telegram user is not authorized to use the admin interface."""