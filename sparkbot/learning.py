"""Persistent operational learning for SparkBot.

This is outcome learning, not weight training: SparkBot records verified results,
latency, failures and platform-specific patterns, then uses those observations to
rank future strategies. It never changes security policy automatically.
"""
from __future__ import annotations

import json
import time
from typing import Any

from .db import execute, fetch_all

class LearningEngine:
    def record(self, *, subject: str, action: str, success: bool, verified: bool,
               latency_ms: float = 0.0, context: dict[str, Any] | None = None) -> None:
        score = (1.0 if success else 0.0) * 0.55 + (1.0 if verified else 0.0) * 0.35
        score += max(0.0, 1.0 - min(float(latency_ms) / 15000.0, 1.0)) * 0.10
        execute(
            "INSERT INTO learning_events(subject,action,success,verified,score,latency_ms,context) VALUES (?,?,?,?,?,?,?)",
            (subject, action, int(success), int(verified), score, float(latency_ms),
             json.dumps(context or {}, ensure_ascii=False)[:12000]),
        )
        execute(
            """INSERT INTO strategy_scores(subject,action,runs,successes,verified,avg_score,avg_latency_ms,updated_at)
               VALUES (?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(subject,action) DO UPDATE SET
                 runs=runs+1,
                 successes=successes+excluded.successes,
                 verified=verified+excluded.verified,
                 avg_score=((strategy_scores.avg_score*strategy_scores.runs)+excluded.avg_score)/(strategy_scores.runs+1),
                 avg_latency_ms=((strategy_scores.avg_latency_ms*strategy_scores.runs)+excluded.avg_latency_ms)/(strategy_scores.runs+1),
                 updated_at=CURRENT_TIMESTAMP""",
            (subject, action, 1, int(success), int(verified), score, float(latency_ms)),
        )

    def recommend(self, subject: str, limit: int = 5) -> list[dict[str, Any]]:
        return fetch_all(
            """SELECT subject,action,runs,successes,verified,avg_score,avg_latency_ms
               FROM strategy_scores WHERE subject=? ORDER BY avg_score DESC, verified DESC, runs DESC LIMIT ?""",
            (subject, max(1, min(limit, 20))),
        )

    def snapshot(self, limit: int = 100) -> list[dict[str, Any]]:
        return fetch_all(
            "SELECT * FROM learning_events ORDER BY id DESC LIMIT ?",
            (max(1, min(limit, 500)),),
        )

    def summary(self) -> dict[str, Any]:
        row = fetch_all("""SELECT COUNT(*) AS events,
                                  COALESCE(SUM(success),0) AS successes,
                                  COALESCE(SUM(verified),0) AS verified,
                                  COALESCE(AVG(score),0) AS avg_score
                           FROM learning_events""")[0]
        return row
