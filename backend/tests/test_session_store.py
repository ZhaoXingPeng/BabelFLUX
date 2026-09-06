from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from app.services.session_store import SessionRecord, SessionStore


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
