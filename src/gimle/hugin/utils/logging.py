"""Logging utilities."""

import logging


class ConditionalFormatter(logging.Formatter):
    """Formatter that includes file/line info only for DEBUG level."""

    def __init__(self, datefmt: str = "%H:%M:%S"):
        """Initialize the formatter with format strings."""
        self.debug_fmt = (
            "%(asctime)s - %(name)s - %(levelname)s - "
            "%(filename)s:%(lineno)d - %(message)s"
        )
        self.default_fmt = (
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        self.datefmt = datefmt
        super().__init__(fmt=self.default_fmt, datefmt=datefmt)

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record, adding file/line for DEBUG level."""
        if record.levelno == logging.DEBUG:
            self._style._fmt = self.debug_fmt
        else:
            self._style._fmt = self.default_fmt
        return super().format(record)


def setup_logging(level: int = logging.WARNING) -> None:
    """Configure logging with conditional formatting.

    Args:
        level: The logging level to set (default: WARNING)
    """
    handler = logging.StreamHandler()
    handler.setFormatter(ConditionalFormatter())
    logging.root.handlers = []
    logging.root.addHandler(handler)
    logging.root.setLevel(level)
