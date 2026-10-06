"""Background mission control with in-memory live event streams."""
from __future__ import annotations
import queue
import threading
import time
import uuid
from typing import Any

class MissionStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._missions: dict[str, dict[str, Any]] = {}

    def create(self, request: str) -> str:
        mid = uuid.uuid4().hex
        with self._lock:
            self._missions[mid] = {"id": mid, "request": request, "status": "QUEUED", "events": [], "result": None}
        return mid

    def event(self, mid: str, kind: str, message: str, **data):
        with self._lock:
            mission = self._missions.get(mid)
            if mission:
                mission["events"].append({"type": kind, "message": message, "timestamp": time.time(), **data})

    def update(self, mid: str, **data):
        with self._lock:
            if mid in self._missions:
                self._missions[mid].update(data)

    def get(self, mid: str):
        with self._lock:
            return dict(self._missions.get(mid, {}))

    def events(self, mid: str, after: int = 0):
        with self._lock:
            return list(self._missions.get(mid, {}).get("events", []))[after:]

class MissionRunner:
    def __init__(self, store, worker):
        self.store = store
        self.worker = worker
        self.queue = queue.Queue()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def submit(self, request: str) -> str:
        mid = self.store.create(request)
        self.queue.put(mid)
        return mid

    def _loop(self):
        while True:
            mid = self.queue.get()
            mission = self.store.get(mid)
            self.store.update(mid, status="RUNNING")
            self.store.event(mid, "start", "Mission started.")
            try:
                result = self.worker(
                    mission["request"],
                    lambda kind, msg, **data: self.store.event(mid, kind, msg, **data),
                )
                self.store.update(mid, status=result.get("status", "COMPLETED"), result=result)
                self.store.event(mid, "complete", "Mission finished.", verified=result.get("verified", False))
            except Exception as exc:
                self.store.update(mid, status="FAILED", error=f"{type(exc).__name__}: {exc}")
                self.store.event(mid, "error", "Mission failed safely.", error=str(exc))
            finally:
                self.queue.task_done()
