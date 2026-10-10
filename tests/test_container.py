import threading
import time

from src.core import container as container_mod


def test_concurrent_first_access_builds_one_instance(monkeypatch):
    built = []

    class Slow:
        def __init__(self):
            time.sleep(0.05)  # widen the window two threads could both build in
            built.append(self)

    monkeypatch.setattr(container_mod, "EventBus", Slow)
    c = container_mod.Container()
    seen = []
    threads = [threading.Thread(target=lambda: seen.append(c.event_bus)) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(built) == 1
    assert all(s is built[0] for s in seen)
