"""Log manager singleton for the TUI."""

import logging
from pathlib import Path
from typing import List, Optional

from gimle.hugin.cli.interactive.logging.handler import (
    RingBuffer,
    TUILogHandler,
)
from gimle.hugin.cli.interactive.state import LogRecord

# Log levels in cycle order
LOG_LEVELS = [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR]


class LogManager:
    """Singleton manager for TUI logging.

    Manages the log ring buffer, file output, and provides methods
    for changing log levels and retrieving logs.
    """

    _instance: Optional["LogManager"] = None

    def __init__(self, storage_path: Path):
        """Initialize the log manager.

        Args:
            storage_path: Base path for storage (logs go in storage_path/logs/).
        """
        self.storage_path = storage_path
        self.log_dir = storage_path / "logs"
        self.ring_buffer: RingBuffer[LogRecord] = RingBuffer(10000)
        self.handler: TUILogHandler = TUILogHandler(
            self.ring_buffer,
            self.log_dir,
        )
        self._current_level = logging.DEBUG
        self._attached = False

        # Set a simple formatter for the handler
        self.handler.setFormatter(logging.Formatter("%(message)s"))
        self.handler.setLevel(self._current_level)

    @classmethod
    def get_instance(cls) -> Optional["LogManager"]:
        """Get the singleton instance."""
        return cls._instance

    @classmethod
    def initialize(cls, storage_path: Path) -> "LogManager":
        """Initialize the singleton.

        Args:
            storage_path: Base path for storage.

        Returns:
            The LogManager instance.
        """
        if cls._instance is None:
            cls._instance = cls(storage_path)
        return cls._instance

    @classmethod
    def shutdown(cls) -> None:
        """Shutdown and cleanup the log manager."""
        if cls._instance:
            cls._instance.detach_from_loggers()
            cls._instance.handler.close()
            cls._instance = None

    @property
    def current_level(self) -> int:
        """Get the current log level."""
        return self._current_level

    @property
    def current_level_name(self) -> str:
        """Get the current log level name."""
        return logging.getLevelName(self._current_level)

    def set_level(self, level: int) -> None:
        """Change the log level.

        Args:
            level: The new log level (e.g., logging.DEBUG).
        """
        self._current_level = level
        self.handler.setLevel(level)

        # Also update the root logger for gimle.hugin
        hugin_logger = logging.getLogger("gimle.hugin")
        hugin_logger.setLevel(level)

    def cycle_level(self) -> int:
        """Cycle to the next log level.

        Order: DEBUG -> INFO -> WARNING -> ERROR -> DEBUG

        Returns:
            The new log level.
        """
        try:
            current_idx = LOG_LEVELS.index(self._current_level)
            next_idx = (current_idx + 1) % len(LOG_LEVELS)
        except ValueError:
            next_idx = 1  # Default to INFO if current level not in list

        self.set_level(LOG_LEVELS[next_idx])
        return self._current_level

    def get_logs(
        self,
        agent_id: Optional[str] = None,
        limit: int = 100,
        min_level: Optional[int] = None,
    ) -> List[LogRecord]:
        """Get logs filtered by agent and level.

        Args:
            agent_id: If provided, only return logs for this agent.
            limit: Maximum number of logs to return.
            min_level: Minimum log level. If None, uses current level.

        Returns:
            List of LogRecord objects (oldest first).
        """
        level = min_level if min_level is not None else self._current_level
        return self.ring_buffer.get_filtered(
            agent_id=agent_id,
            min_level=level,
            limit=limit,
        )

    def attach_to_loggers(self) -> None:
        """Attach the handler to Hugin loggers.

        Attaches to the gimle.hugin logger hierarchy.
        """
        if self._attached:
            return

        # Get the root hugin logger
        hugin_logger = logging.getLogger("gimle.hugin")
        hugin_logger.addHandler(self.handler)
        hugin_logger.setLevel(self._current_level)

        # Ensure propagation is off to avoid duplicate logs
        # if root logger also has handlers
        hugin_logger.propagate = False

        self._attached = True

        # Log a startup message to confirm logging is working
        hugin_logger.info("TUI logging initialized")

    def detach_from_loggers(self) -> None:
        """Detach the handler from loggers."""
        if not self._attached:
            return

        hugin_logger = logging.getLogger("gimle.hugin")
        hugin_logger.removeHandler(self.handler)

        self._attached = False

    def clear_logs(self) -> None:
        """Clear all logs from the ring buffer."""
        self.ring_buffer.clear()
