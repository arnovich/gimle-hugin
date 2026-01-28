"""Custom logging handler for the TUI with ring buffer and file output."""

import contextvars
import logging
import threading
from collections import deque
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Generic, List, Optional, TypeVar

from gimle.hugin.cli.interactive.state import LogRecord

T = TypeVar("T")

# Context variable for tracking current agent ID in threads
_agent_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "agent_id", default=None
)
_session_context: contextvars.ContextVar[Optional[str]] = (
    contextvars.ContextVar("session_id", default=None)
)


def set_agent_context(agent_id: str, session_id: Optional[str] = None) -> None:
    """Set the current agent context for logging.

    Call this at the start of agent execution in a thread.
    """
    _agent_context.set(agent_id)
    if session_id:
        _session_context.set(session_id)


def clear_agent_context() -> None:
    """Clear the current agent context."""
    _agent_context.set(None)
    _session_context.set(None)


class RingBuffer(Generic[T]):
    """Thread-safe fixed-size ring buffer."""

    def __init__(self, capacity: int = 10000):
        """Initialize the ring buffer.

        Args:
            capacity: Maximum number of items to store.
        """
        self._buffer: deque[T] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def append(self, item: T) -> None:
        """Add an item to the buffer (thread-safe)."""
        with self._lock:
            self._buffer.append(item)

    def get_all(self) -> List[T]:
        """Get all items (oldest first, newest last)."""
        with self._lock:
            return list(self._buffer)

    def get_last(self, count: int) -> List[T]:
        """Get the last N items (oldest first)."""
        with self._lock:
            items = list(self._buffer)
            return items[-count:] if count < len(items) else items

    def get_filtered(
        self,
        agent_id: Optional[str] = None,
        min_level: int = logging.DEBUG,
        limit: Optional[int] = None,
    ) -> List[LogRecord]:
        """Get filtered items (LogRecord only).

        This method only works for RingBuffer[LogRecord] instances.
        It filters logs by agent_id and level.

        Args:
            agent_id: If provided, only return logs for this agent.
            min_level: Minimum log level to include.
            limit: Maximum number of items to return (from end).

        Returns:
            List of matching LogRecord objects (oldest first).
        """
        with self._lock:
            result: List[LogRecord] = []
            for item in self._buffer:
                if not isinstance(item, LogRecord):
                    continue
                if item.level < min_level:
                    continue
                if agent_id is not None and item.agent_id != agent_id:
                    continue
                result.append(item)

            if limit and len(result) > limit:
                return result[-limit:]
            return result

    def __len__(self) -> int:
        """Return the number of items in the buffer."""
        with self._lock:
            return len(self._buffer)

    def clear(self) -> None:
        """Clear all items from the buffer."""
        with self._lock:
            self._buffer.clear()


class TUILogHandler(logging.Handler):
    """Custom logging handler for TUI with ring buffer and file output."""

    def __init__(
        self,
        ring_buffer: RingBuffer[LogRecord],
        log_dir: Optional[Path] = None,
        max_file_size: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 5,
    ):
        """Initialize the handler.

        Args:
            ring_buffer: The ring buffer to store log records.
            log_dir: Directory to write log files. If None, no file output.
            max_file_size: Maximum size of log file before rotation.
            backup_count: Number of backup files to keep.
        """
        super().__init__()
        self._ring_buffer = ring_buffer
        self._file_handler: Optional[RotatingFileHandler] = None

        # Set up file handler if log_dir provided
        if log_dir:
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "hugin.log"
            self._file_handler = RotatingFileHandler(
                log_file,
                maxBytes=max_file_size,
                backupCount=backup_count,
            )
            self._file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s [%(levelname)-5s] %(name)s - %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )

    def emit(self, record: logging.LogRecord) -> None:
        """Process a log record.

        Stores the record in the ring buffer and writes to file if configured.
        """
        try:
            # Get agent context from thread-local storage
            agent_id = _agent_context.get()
            session_id = _session_context.get()

            # Create our LogRecord dataclass
            log_record = LogRecord(
                timestamp=datetime.fromtimestamp(record.created),
                level=record.levelno,
                level_name=record.levelname,
                logger_name=record.name,
                message=self.format(record),
                agent_id=agent_id,
                session_id=session_id,
                filename=record.filename,
                lineno=record.lineno,
            )

            # Add to ring buffer
            self._ring_buffer.append(log_record)

            # Write to file if configured
            if self._file_handler:
                # Add agent context to file log message
                if agent_id:
                    original_msg = record.msg
                    record.msg = f"({agent_id[:8]}) {original_msg}"
                self._file_handler.emit(record)
                if agent_id:
                    record.msg = original_msg

        except Exception:
            self.handleError(record)

    def close(self) -> None:
        """Close the handler and any file handlers."""
        if self._file_handler:
            self._file_handler.close()
        super().close()
