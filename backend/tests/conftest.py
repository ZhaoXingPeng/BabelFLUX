"""测试夹具：保证后端测试在 mock 模式下 hermetic，不触达真实云端 API。"""

import pytest

from app.core.config import settings
from app.services.session_history import session_history_store
from app.services.session_store import session_store


@pytest.fixture(autouse=True)
def force_mock_provider() -> None:
    """全局强制 mock provider，并清理会话状态，避免测试间串扰与真实联网。"""
    original = settings.model_provider
    original_api_key = settings.dashscope_api_key
    object.__setattr__(settings, "model_provider", "mock")
    object.__setattr__(settings, "dashscope_api_key", original_api_key or "sk-test")
    session_store._sessions.clear()
    session_history_store.reset()
    yield
    object.__setattr__(settings, "model_provider", original)
    object.__setattr__(settings, "dashscope_api_key", original_api_key)
    session_store._sessions.clear()
    session_history_store.reset()
