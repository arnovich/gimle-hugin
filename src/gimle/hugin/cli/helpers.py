"""Helper functions for app runners."""

import subprocess
import sys
import time
import webbrowser
from typing import Optional


def start_monitor_dashboard(
    storage_path: str,
    port: int = 8080,
    config_path: Optional[str] = None,
    no_browser: bool = True,
) -> subprocess.Popen:
    """
    Start the agent monitor dashboard as a subprocess.

    Args:
        storage_path: Path to the storage directory
        port: Port for the monitor server (default: 8080)
        config_path: Optional path to config directory for loading agent configs
        no_browser: If True, don't auto-open browser from monitor (default: True)

    Returns:
        The subprocess.Popen object for the monitor process
    """
    cmd = [
        sys.executable,
        "-m",
        "gimle.hugin.cli.monitor_agents",
        "--storage-path",
        storage_path,
        "--port",
        str(port),
    ]
    if config_path:
        cmd.extend(["--config-path", config_path])
    if no_browser:
        cmd.append("--no-browser")

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(3)  # Wait for startup
    return process


def open_in_browser(url: str, delay: float = 0) -> None:
    """
    Open a URL in the default browser.

    Args:
        url: The URL to open
        delay: Optional delay in seconds before opening (default: 0)
    """
    if delay:
        time.sleep(delay)
    try:
        webbrowser.open(url)
    except Exception as e:
        print(f"Could not open browser: {e}")


def configure_logging(log_level: str) -> None:
    """
    Configure logging based on log level string.

    Args:
        log_level: One of "DEBUG", "INFO", "WARNING", "ERROR"
    """
    import logging

    level = getattr(logging, log_level)
    if log_level == "DEBUG":
        logging.basicConfig(
            level=level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%H:%M:%S",
            force=True,
        )
    else:
        logging.basicConfig(
            level=level,
            format="%(message)s",
            force=True,
        )
