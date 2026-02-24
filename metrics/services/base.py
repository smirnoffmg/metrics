"""Base service with shared logging setup."""

from __future__ import annotations

import logging


class BaseService:
    """Base class providing a logger for all services."""

    def __init__(self) -> None:
        """Initialize the service logger."""
        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}",
        )
