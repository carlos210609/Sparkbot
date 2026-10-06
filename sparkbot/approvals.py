"""Approval facade backed by SparkBot persistent memory."""
from __future__ import annotations
import json, uuid
from .db import execute, fetch_all

class ApprovalStore:
    def create(self, action, args, reason, actor="sparkbot"):
        aid=uuid.uuid4().hex
        value={"action":action,"args":args,"reason":reason,"status":"PENDING","actor":actor}
        execute("INSERT INTO memories(kind,key,value,importance) VALUES (?,?,?,?)",
                ("approval",aid,json.dumps(value,ensure_ascii=False),1.0))
        return aid
    def get(self, approval_id):
        rows=fetch_all("SELECT * FROM memories WHERE kind='approval' AND key=? LIMIT 1",(approval_id,))
        if not rows: return None
        value=json.loads(rows[0]["value"]); return {"id":approval_id,**value}
    def list(self,status="PENDING",limit=100):
        rows=fetch_all("SELECT * FROM memories WHERE kind='approval' ORDER BY id DESC LIMIT ?",(max(1,min(limit,500)),))
        out=[]
        for row in rows:
            value=json.loads(row["value"]); item={"id":row["key"],**value}
            if not status or value.get("status")==status: out.append(item)
        return out
    def _set(self, approval_id, status):
        item=self.get(approval_id)
        if not item or item.get("status")!="PENDING": return item
        item["status"]=status
        execute("UPDATE memories SET value=?,updated_at=CURRENT_TIMESTAMP WHERE kind='approval' AND key=?",
                (json.dumps({k:v for k,v in item.items() if k!="id"},ensure_ascii=False),approval_id))
        return self.get(approval_id)
    def approve(self, approval_id): return self._set(approval_id,"APPROVED")
    def reject(self, approval_id): return self._set(approval_id,"REJECTED")
