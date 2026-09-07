from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from app.services.session_store import SessionAlreadyExistsError, SessionRecord, SessionStore


def test_get_or_create_returns_one_record_for_concurrent_calls() -> None:
    store = SessionStore()
    workers = 16
    barrier = Barrier(workers)

    def load(index: int) -> SessionRecord:
        barrier.wait()
        return store.get_or_create("shared-session", source_language=f"lang-{index}")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        records = list(executor.map(load, range(workers)))

    assert len({id(record) for record in records}) == 1
    assert store.get("shared-session") is records[0]
    assert records[0].session_id == "shared-session"


def test_create_rejects_duplicate_without_overwriting_existing_record() -> None:
    store = SessionStore()
    original = store.create("shared-session", source_language="en")

    with pytest.raises(SessionAlreadyExistsError, match="session already exists"):
        store.create("shared-session", source_language="zh")

    assert store.get("shared-session") is original
    assert original.source_language == "en"


def test_session_record_segment_access_keeps_index_and_ordered_list_in_sync() -> None:
    record = SessionRecord(session_id="session")
    first = record.get_or_create_segment("first", 1)
    second = record.get_or_create_segment("second", 2)

    assert record.get_segment("first") is first
    assert record.remove_segment("first") is first
    assert record.get_segment("first") is None
    assert record.segments == [second]
    assert record.remove_segment("missing") is None
