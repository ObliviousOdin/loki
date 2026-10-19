"""Completion handling for detached adapter tasks."""
import asyncio
import logging

logger = logging.getLogger("gateway.platforms.base")


def consume_detached_handler_exception(task: asyncio.Task) -> None:
    """Done-callback for a detached fatal-error handler task (carrier cancelled in
    ``_notify_fatal_error``): retrieve its exception so asyncio never logs "never retrieved"."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("Detached fatal-error handler task failed: %s", exc, exc_info=exc)
