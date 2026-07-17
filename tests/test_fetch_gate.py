"""fetch._PriorityGate: okuyucu (interactive) toplu işten (bulk) önce geçer.

Deterministik iş parçacığı testleri — ağ/Playwright çağrısı yok. Kapının üç
sözleşmesi: (1) bekleyen okuyucu, sırada bekleyen bulk'tan ÖNCE alır;
(2) okuyucular bitince bulk devam eder; (3) birden çok bulk bekleyeni,
bekleyen okuyucunun önüne dalamaz (barging yok).
"""
import threading
import time

import pytest

from core.fetch import _PriorityGate


def _wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


def test_free_gate_lets_bulk_through():
    gate = _PriorityGate()
    gate.acquire("bulk")  # boş kapıyı bulk da alabilir (okuyucu yokken)
    gate.release()
    gate.acquire("interactive")
    gate.release()


def test_waiting_reader_acquires_before_queued_bulk():
    gate = _PriorityGate()
    gate.acquire("bulk")  # toplu iş kapıyı tutuyor (bölüm çekiyor)
    order = []
    done = threading.Event()

    def reader():
        gate.acquire("interactive")
        order.append("reader")
        gate.release()

    def bulk():
        gate.acquire("bulk")
        order.append("bulk")
        gate.release()
        done.set()

    reader_t = threading.Thread(target=reader, daemon=True)
    reader_t.start()
    assert _wait_until(lambda: gate._interactive_waiting == 1)

    bulk_t = threading.Thread(target=bulk, daemon=True)
    bulk_t.start()
    time.sleep(0.05)  # bulk da kuyruğa girsin
    assert order == []  # kapı hâlâ tutuluyor, kimse geçmedi

    gate.release()  # toplu işin elindeki bölüm bitti
    assert done.wait(2)
    assert order == ["reader", "bulk"]  # okuyucu önce, bulk sonra


def test_many_bulk_waiters_cannot_barge_past_reader():
    gate = _PriorityGate()
    gate.acquire("bulk")
    order = []
    lock = threading.Lock()
    done = threading.Barrier(4, timeout=2)

    def worker(kind):
        gate.acquire(kind)
        with lock:
            order.append(kind)
        gate.release()
        done.wait()

    reader_t = threading.Thread(target=worker, args=("interactive",), daemon=True)
    reader_t.start()
    assert _wait_until(lambda: gate._interactive_waiting == 1)

    bulk_threads = [
        threading.Thread(target=worker, args=("bulk",), daemon=True) for _ in range(2)
    ]
    for t in bulk_threads:
        t.start()
    time.sleep(0.05)

    gate.release()
    try:
        done.wait()
    except threading.BrokenBarrierError:
        pytest.fail(f"Kapı bekleyenleri bırakmadı; geçebilenler: {order}")
    assert order[0] == "interactive"  # okuyucu her zaman ilk
    assert sorted(order[1:]) == ["bulk", "bulk"]
