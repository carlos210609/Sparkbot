from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Any

from .db import execute, fetch_all


@dataclass
class BrowserEvent:
    event_id: str
    action: str
    url: str = ""
    target: str = ""
    status: str = "observed"
    details: dict[str, Any] | None = None
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BrowserMonitor:
    """Auditable browser-action telemetry.

    It records observations only. It does not bypass authentication, CAPTCHA,
    platform limits, or other security controls.
    """

    def record(self, action: str, *, url: str = "", target: str = "",
               status: str = "observed", details: dict[str, Any] | None = None) -> dict[str, Any]:
        event = BrowserEvent(
            event_id=str(uuid.uuid4()),
            action=action,
            url=url,
            target=target,
            status=status,
            details=details or {},
            timestamp=time.time(),
        )
        execute(
            "INSERT INTO browser_events(event_id,action,url,target,status,details) VALUES (?,?,?,?,?,?)",
            (event.event_id, event.action, event.url, event.target, event.status, json.dumps(event.details)),
        )
        execute(
            "INSERT INTO activity_logs(event_type,message,metadata) VALUES (?,?,?)",
            ("BROWSER_ACTION", action, json.dumps(event.to_dict())),
        )
        return event.to_dict()

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = fetch_all(
            "SELECT * FROM browser_events ORDER BY id DESC LIMIT ?",
            (max(1, min(limit, 500)),),
        )
        for row in rows:
            try:
                row["details"] = json.loads(row["details"])
            except (TypeError, ValueError):
                pass
        return rows
