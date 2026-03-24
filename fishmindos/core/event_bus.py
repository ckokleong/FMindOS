"""Global event bus for FishMindOS."""

from __future__ import annotations

from typing import Any, Callable, Dict, List


class EventBus:
    """Lightweight in-process pub/sub event bus."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable[..., Any]]] = {}

    def subscribe(self, event_type: str, callback: callable) -> None:
        """Subscribe a callback to an event type."""
        if not event_type or callback is None:
            return
        callbacks = self._subscribers.setdefault(event_type, [])
        if callback not in callbacks:
            callbacks.append(callback)

    def publish(self, event_type: str, data: dict = None) -> None:
        """Publish an event to all registered callbacks."""
        callbacks = list(self._subscribers.get(event_type, []))
        for callback in callbacks:
            try:
                callback(data)
            except Exception as exc:
                print(f"[EventBus] callback failed ({event_type}): {exc}")


global_event_bus = EventBus()

