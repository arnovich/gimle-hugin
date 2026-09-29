"""Contain aiohttp protocol errors that occur before application handlers.

This small adapter depends on the pinned aiohttp RequestHandler interface.
The raw-TLS regression test must pass before upgrading aiohttp. It is not a
production connection/handshake limiter.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from aiohttp import web
from aiohttp.web_protocol import RequestHandler


class _RedactedHandler(RequestHandler):
    def handle_error(
        self,
        request: web.BaseRequest,
        status: int = 500,
        exc: BaseException | None = None,
        message: str | None = None,
    ) -> web.StreamResponse:
        """Suppress parser exception text, headers and remote addresses."""
        if request.writer.output_size:
            raise ConnectionError("response_already_started")
        response = web.Response(
            status=status,
            body=b'{"error":"rejected"}',
            content_type="application/json",
        )
        response.force_close()
        return response


class RedactedServer(web.Server):
    """Use constant protocol errors and a private, non-propagating logger."""

    def __init__(
        self,
        handler: Callable[[web.BaseRequest], Awaitable[web.StreamResponse]],
    ) -> None:
        """Keep the adapter isolated from globally configured application logs."""
        self._probe_loop = asyncio.get_running_loop()
        self._probe_logger = logging.Logger("hugin.swarm.probe")
        self._probe_logger.addHandler(logging.NullHandler())
        self._probe_logger.propagate = False
        self._probe_logger.disabled = True
        super().__init__(handler, loop=self._probe_loop)

    def __call__(self) -> RequestHandler:
        """Construct the pinned protocol with redacted error handling."""
        return _RedactedHandler(
            self,
            loop=self._probe_loop,
            logger=self._probe_logger,
            access_log=self._probe_logger,
            auto_decompress=False,
            keepalive_timeout=5,
        )
