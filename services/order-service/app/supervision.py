"""Exit the process if a background worker dies while the service is running.

Each service runs its Kafka consumer (and order-service its outbox publisher)
as an asyncio task inside the FastAPI app. If that task raises, the API keeps
serving and /health keeps answering, so Docker, ECS and the load balancer see
a healthy container while nothing is being consumed any more.

watch() turns that silent failure into a loud one: the process exits with
status 1, the orchestrator restarts the container, and Kafka redelivers the
batch that was never committed. That is the at-least-once guarantee the
consumers already rely on; this makes sure a restart actually happens.

A normal shutdown (stop_event set, or the task cancelled) is left alone.
"""

from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)


def watch(task: asyncio.Task, stop_event: asyncio.Event, name: str, _exit=os._exit) -> None:
    """Exit the process if `task` finishes before `stop_event` is set."""

    def _on_done(t: asyncio.Task) -> None:
        if t.cancelled() or stop_event.is_set():
            return
        logger.critical(
            "%s stopped while the service was running (%r); exiting so the container is restarted",
            name, t.exception())
        # os._exit, not sys.exit: this runs in an event-loop callback, where a
        # SystemExit would be caught and logged instead of ending the process.
        _exit(1)

    task.add_done_callback(_on_done)
