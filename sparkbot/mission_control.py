"""Persistent background mission control with live event streams."""
from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from typing import Any

from .db import execute, fetch_all, fetch_one


class MissionStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._missions: dict[str, dict[str, Any]] = {}

    def create(self, request: str) -> str:
        mid = uuid.uuid4().hex
        with self._lock:
            self._missions[mid] = {"id": mid, "request": request, "status": "QUEUED", "events": [], "result": None}
        execute(
            "INSERT INTO missions(id,request,goal,status) VALUES (?,?,?,?)",
            (mid, request, request[:500], "QUEUED"),
        )
        self.event(mid, "queued", "Mission queued.")
        return mid

    def event(self, mid: str, kind: str, message: str, **data: Any) -> None:
        event = {"type": kind, "message": message, "timestamp": time.time(), **data}
        with self._lock:
            mission = self._missions.get(mid)
            if mission:
                mission["events"].append(event)
        execute(
            "INSERT INTO mission_events(mission_id,event_type,message,metadata) VALUES (?,?,?,?)",
            (mid, kind, message, json.dumps(data, ensure_ascii=False)),
        )

    def update(self, mid: str, **data: Any) -> None:
        with self._lock:
            if mid in self._missions:
                self._missions[mid].update(data)
        status = data.get("status")
        if status:
            execute("UPDATE missions SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (status, mid))

    def get(self, mid: str) -> dict[str, Any]:
        with self._lock:
            value = dict(self._missions.get(mid, {}))
        if value:
            return value
        row = fetch_one("SELECT * FROM missions WHERE id=?", (mid,))
        if row:
            row["events"] = fetch_all("SELECT * FROM mission_events WHERE mission_id=? ORDER BY id", (mid,))
            return row
        return {}

    def all(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = fetch_all("SELECT * FROM missions ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 200)),))
        return rows

    def events(self, mid: str, after: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            cached = list(self._missions.get(mid, {}).get("events", []))[after:]
        if cached:
            return cached
        return fetch_all(
            "SELECT * FROM mission_events WHERE mission_id=? ORDER BY id LIMIT ? OFFSET ?",
            (mid, 500, max(0, after)),
        )


class MissionRunner:
    def __init__(self, store: MissionStore, worker):
        self.store = store
        self.worker = worker
        self.queue: queue.Queue[str] = queue.Queue()
        self.thread = threading.Thread(target=self._loop, name="sparkbot-missions", daemon=True)
        self.thread.start()

    def submit(self, request: str) -> str:
        mid = self.store.create(request)
        self.queue.put(mid)
        return mid

    def _loop(self) -> None:
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
