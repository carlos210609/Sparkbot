"""Human approval queue for externally visible or high-risk actions."""
from __future__ import annotations

import json
import uuid
from .db import execute, fetch_all, fetch_one

class ApprovalStore:
    def create(self, action: str, args: dict, reason: str, actor: str = "sparkbot") -> str:
        approval_id = uuid.uuid4().hex
        execute(
            """INSERT INTO approvals(id,action,args,reason,status,actor)
               VALUES (?,?,?,?,?,?)""",
            (approval_id, action, json.dumps(args, ensure_ascii=False), reason, "PENDING", actor),
        )
        return approval_id

    def get(self, approval_id: str) -> dict | None:
        row = fetch_one("SELECT * FROM approvals WHERE id=?", (approval_id,))
        if not row:
            return None
        row["args"] = json.loads(row.get("args") or "{}")
        return row

    def list(self, status: str | None = "PENDING", limit: int = 100) -> list[dict]:
        sql = "SELECT * FROM approvals"
        params: tuple = ()
        if status:
            sql += " WHERE status=?"
            params = (status.upper(),)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params += (max(1, min(limit, 500)),)
        rows = fetch_all(sql, params)
        for row in rows:
            row["args"] = json.loads(row.get("args") or "{}")
        return rows

    def approve(self, approval_id: str) -> dict | None:
        row = self.get(approval_id)
        if not row or row["status"] != "PENDING":
            return row
        execute("UPDATE approvals SET status='APPROVED', approved_at=CURRENT_TIMESTAMP WHERE id=?",
                (approval_id,))
        return self.get(approval_id)

    def reject(self, approval_id: str) -> dict | None:
        row = self.get(approval_id)
        if not row or row["status"] != "PENDING":
            return row
        execute("UPDATE approvals SET status='REJECTED', approved_at=CURRENT_TIMESTAMP WHERE id=?",
                (approval_id,))
        return self.get(approval_id)
