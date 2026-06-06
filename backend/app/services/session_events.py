from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from copy import deepcopy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SessionEventSubscription:
    session_id: str
    queue: asyncio.Queue[dict[str, Any]]
    replay: list[dict[str, Any]]


class SessionEventHub:
    def __init__(self, *, history_limit: int = 100, queue_size: int = 100) -> None:
        self._history_limit = history_limit
        self._queue_size = queue_size
        self._history: dict[str, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=self._history_limit)
        )
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)

    def publish(self, session_id: str, event: dict[str, Any]) -> None:
        snapshot = deepcopy(event)
        self._history[session_id].append(snapshot)

        stale: list[asyncio.Queue[dict[str, Any]]] = []
        for queue in list(self._subscribers.get(session_id, ())):
            try:
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(deepcopy(snapshot))
            except (asyncio.QueueEmpty, RuntimeError):
                stale.append(queue)

        for queue in stale:
            self._subscribers[session_id].discard(queue)

    def subscribe(self, session_id: str) -> SessionEventSubscription:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._queue_size)
        replay = [deepcopy(event) for event in self._history.get(session_id, ())]
        self._subscribers[session_id].add(queue)
        return SessionEventSubscription(session_id=session_id, queue=queue, replay=replay)

    def unsubscribe(self, subscription: SessionEventSubscription) -> None:
        self._subscribers[subscription.session_id].discard(subscription.queue)

    def reset(self) -> None:
        self._history.clear()
        self._subscribers.clear()


session_event_hub = SessionEventHub()
