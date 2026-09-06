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
        self._append_history(session_id, snapshot)

        stale: list[asyncio.Queue[dict[str, Any]]] = []
        for queue in list(self._subscribers.get(session_id, ())):
            try:
                self._enqueue_for_subscriber(queue, snapshot)
            except (asyncio.QueueEmpty, asyncio.QueueFull, RuntimeError):
                stale.append(queue)

        for queue in stale:
            self._subscribers[session_id].discard(queue)

    def _append_history(self, session_id: str, event: dict[str, Any]) -> None:
        history = self._history[session_id]
        if len(history) < self._history_limit:
            history.append(event)
            return

        # 保留控制面事件，避免 TTS 音频突发覆盖字幕修订或最终报告。
        buffered = list(history)
        drop_index = _first_audio_index(buffered)
        del buffered[0 if drop_index is None else drop_index]
        buffered.append(event)
        history.clear()
        history.extend(buffered)

    @staticmethod
    def _enqueue_for_subscriber(
        queue: asyncio.Queue[dict[str, Any]], event: dict[str, Any]
    ) -> None:
        if not queue.full():
            queue.put_nowait(deepcopy(event))
            return

        # Queue 操作在当前事件循环的同步片段内完成，不会与 forward_task 交错。
        buffered: list[dict[str, Any]] = []
        while True:
            try:
                buffered.append(queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        drop_index = _first_audio_index(buffered)
        del buffered[0 if drop_index is None else drop_index]
        for item in buffered:
            queue.put_nowait(item)
        queue.put_nowait(deepcopy(event))

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


def _first_audio_index(events: list[dict[str, Any]]) -> int | None:
    for index, event in enumerate(events):
        if event.get("type") == "audio_segment":
            return index
    return None
