"""Threaded tinytuya client with one persistent local connection (no HA imports)."""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Callable

_LOGGER = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 8.0
FULL_REFRESH_INTERVAL = 20.0
RETRY_DELAY = 5.0


def make_device(device_id: str, host: str, local_key: str, version: str, timeout: float = 1.0):
    import tinytuya

    dev = tinytuya.Device(device_id, host, local_key, version=float(version), persist=True)
    try:
        dev.set_socketPersistent(True)
    except Exception:  # noqa: BLE001
        pass
    try:
        dev.set_socketTimeout(timeout)
    except Exception:  # noqa: BLE001
        pass
    return dev


def query(dev) -> dict[str, Any]:
    """Return dps dict or raise RuntimeError."""
    data = dev.status()
    if not isinstance(data, dict) or "Error" in data or "dps" not in data:
        raise RuntimeError(f"status failed: {data}")
    return {str(k): v for k, v in data["dps"].items()}


def test_connection(device_id: str, host: str, local_key: str, version: str) -> str | None:
    """Return None if OK, otherwise an error message (blocking)."""
    try:
        dev = make_device(device_id, host, local_key, version, timeout=5)
        query(dev)
        dev.close()
    except Exception as err:  # noqa: BLE001
        return str(err)
    return None


class StripClient:
    def __init__(
        self,
        host: str,
        device_id: str,
        local_key: str,
        version: str,
        on_state: Callable[[dict[str, Any]], None],
        on_available: Callable[[bool], None],
        factory=make_device,
    ) -> None:
        self._args = (device_id, host, local_key, version)
        self._on_state = on_state
        self._on_available = on_available
        self._factory = factory
        self._queue: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_full: dict[str, Any] = {}

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="lsc_strip_direct", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout=10)

    def send(self, writes: list[tuple[int, Any]], atomic: bool = False) -> None:
        """Queue DP writes; atomic=True sends them in ONE packet."""
        self._queue.put((list(writes), atomic))

    def _run(self) -> None:
        while not self._stop.is_set():
            dev = None
            try:
                dev = self._factory(*self._args)
                self._on_state(query(dev))
                self._on_available(True)
                now = time.monotonic()
                last_hb = last_full = now
                while not self._stop.is_set():
                    # 1) pending commands
                    try:
                        while True:
                            job = self._queue.get_nowait()
                            if job is None:
                                continue
                            writes, atomic = job
                            if atomic and hasattr(dev, "set_multiple_values"):
                                res = dev.set_multiple_values({str(dp): v for dp, v in writes})
                                if isinstance(res, dict) and "Error" in res:
                                    raise RuntimeError(f"set {writes} failed: {res}")
                            else:
                                for dp, value in writes:
                                    res = dev.set_value(int(dp), value)
                                    if isinstance(res, dict) and "Error" in res:
                                        raise RuntimeError(f"set {dp} failed: {res}")
                    except queue.Empty:
                        pass
                    if self._stop.is_set():
                        break
                    # 2) wait for pushed updates (blocks until data or socket timeout)
                    t0 = time.monotonic()
                    data = dev.receive()
                    if data is not None:
                        _LOGGER.info("LSC strip %s rx: %s", self._args[0], data)
                    if isinstance(data, dict) and isinstance(data.get("dps"), dict) and "Error" not in data:
                        self._on_state({str(k): v for k, v in data["dps"].items()})
                    if time.monotonic() - t0 < 0.05:
                        self._stop.wait(0.2)  # receive returned immediately: avoid busy loop
                    # 3) keep-alive and periodic full refresh
                    now = time.monotonic()
                    if now - last_hb >= HEARTBEAT_INTERVAL:
                        try:
                            dev.heartbeat(nowait=True)
                        except Exception:  # noqa: BLE001
                            pass
                        last_hb = now
                    if now - last_full >= FULL_REFRESH_INTERVAL:
                        full = query(dev)  # raises (-> reconnect) if the link is dead
                        if full != self._last_full:
                            _LOGGER.info("LSC strip %s full refresh changed: %s", self._args[0], full)
                            self._last_full = full
                        self._on_state(full)
                        last_full = now
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("LSC strip %s: %s", self._args[0], err)
                self._on_available(False)
            finally:
                if dev is not None:
                    try:
                        dev.close()
                    except Exception:  # noqa: BLE001
                        pass
            self._stop.wait(RETRY_DELAY)
