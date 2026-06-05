from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any


class RealtimeProvider(ABC):
    """Common interface for ASR, live-translate, and mock streaming providers."""

    @abstractmethod
    async def start(self, session_id: str) -> AsyncIterator[dict[str, Any]]:
        raise NotImplementedError

    async def send_audio(self, _: bytes) -> None:
        return None

    async def stop(self) -> None:
        return None
