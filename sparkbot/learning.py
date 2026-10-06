"""Persistent operational learning using SparkBot's existing memory store."""
from __future__ import annotations
import json
from .db import execute, fetch_all

class LearningEngine:
    def record(self, *, subject: str, action: str, success: bool, verified: bool,
               latency_ms: float = 0.0, context: dict | None = None) -> None:
        score = (1.0 if success else 0.0) * 0.55 + (1.0 if verified else 0.0) * 0.35
        score += max(0.0, 1.0 - min(float(latency_ms) / 15000.0, 1.0)) * 0.10
        value = {"subject":subject,"action":action,"success":bool(success),
                 "verified":bool(verified),"score":score,"latency_ms":float(latency_ms),
                 "context":context or {}}
        execute("INSERT INTO memories(kind,key,value,importance) VALUES (?,?,?,?)",
                ("learning_event", f"{subject}:{action}", json.dumps(value,ensure_ascii=False), score))
    def recommend(self, subject: str, limit: int = 5) -> list[dict]:
        rows=fetch_all("SELECT * FROM memories WHERE kind='learning_event' ORDER BY importance DESC, updated_at DESC LIMIT 500")
        grouped={}
        for row in rows:
            try: v=json.loads(row["value"])
            except Exception: continue
            if v.get("subject") != subject: continue
            key=v.get("action","unknown"); g=grouped.setdefault(key,{"subject":subject,"action":key,"runs":0,"successes":0,"verified":0,"score_sum":0.0,"latency_sum":0.0})
            g["runs"]+=1; g["successes"]+=int(v.get("success")); g["verified"]+=int(v.get("verified"))
            g["score_sum"]+=float(v.get("score",0)); g["latency_sum"]+=float(v.get("latency_ms",0))
        out=[]
        for g in grouped.values():
            g["avg_score"]=g.pop("score_sum")/g["runs"]; g["avg_latency_ms"]=g.pop("latency_sum")/g["runs"]
            out.append(g)
        return sorted(out,key=lambda x:(-x["avg_score"],-x["verified"],-x["runs"]))[:max(1,min(limit,20))]
    def snapshot(self, limit: int = 100) -> list[dict]:
        rows=fetch_all("SELECT * FROM memories WHERE kind='learning_event' ORDER BY id DESC LIMIT ?",(max(1,min(limit,500)),))
        for row in rows:
            try: row["value"]=json.loads(row["value"])
            except Exception: pass
        return rows
    def summary(self) -> dict:
        rows=self.snapshot(500)
        return {"events":len(rows),"successes":sum(int(r["value"].get("success",0)) for r in rows if isinstance(r.get("value"),dict)),
                "verified":sum(int(r["value"].get("verified",0)) for r in rows if isinstance(r.get("value"),dict)),
                "avg_score":sum(float(r["value"].get("score",0)) for r in rows if isinstance(r.get("value"),dict))/max(1,len(rows))}
