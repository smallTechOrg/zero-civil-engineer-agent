"""In-process progress event bus — one channel per design run, consumed by the SSE endpoint.

Pinned cross-slice contract (spec/architecture.md — Progress streaming):

    register(run_id)                  # runner, before the graph thread starts
    publish(run_id, event_type, data) # graph nodes; thread-safe; no-op if unregistered
    stream(run_id)                    # SSE endpoint; replays earlier events, then blocks
                                      # for new ones; ends after a "done" or "error" event
    is_active(run_id)                 # registered and not yet finished

Each channel keeps a replay buffer so a late subscriber still sees the whole run.
Finished channels are dropped once a stream has drained them.
"""

import threading
from collections.abc import Iterator

_TERMINAL_EVENTS = frozenset({"done", "error"})

_registry_lock = threading.Lock()
_channels: dict[str, "_Channel"] = {}


class _Channel:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.finished = False
        self.condition = threading.Condition()


def register(run_id: str) -> None:
    """Create the channel for a run. Called by the runner before the graph thread starts."""
    with _registry_lock:
        _channels[run_id] = _Channel()


def publish(run_id: str, event_type: str, data: dict) -> None:
    """Append an event to the run's channel. Thread-safe; silently no-op if unregistered
    or if the run already emitted a terminal event."""
    with _registry_lock:
        channel = _channels.get(run_id)
    if channel is None:
        return
    with channel.condition:
        if channel.finished:
            return
        channel.events.append({"event": event_type, "data": data})
        if event_type in _TERMINAL_EVENTS:
            channel.finished = True
        channel.condition.notify_all()


def stream(run_id: str) -> Iterator[dict]:
    """Yield the run's events in order, blocking for new ones; end after "done"/"error".

    A late subscriber replays the full buffer first. Yields nothing for an
    unregistered (or already-dropped) run.
    """
    with _registry_lock:
        channel = _channels.get(run_id)
    if channel is None:
        return
    index = 0
    while True:
        with channel.condition:
            while index >= len(channel.events) and not channel.finished:
                channel.condition.wait()
            if index >= len(channel.events) and channel.finished:
                break
            event = channel.events[index]
        index += 1
        yield event
        if event["event"] in _TERMINAL_EVENTS:
            break
    _drop_if_finished(run_id, channel)


def is_active(run_id: str) -> bool:
    """True while the run is registered and has not yet emitted a terminal event."""
    with _registry_lock:
        channel = _channels.get(run_id)
    return channel is not None and not channel.finished


def _drop_if_finished(run_id: str, channel: "_Channel") -> None:
    with _registry_lock:
        if _channels.get(run_id) is channel and channel.finished:
            del _channels[run_id]
