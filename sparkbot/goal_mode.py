"""Bounded, persistent /goal execution loop for SparkBot missions.

The loop keeps working across multiple agent turns, emits durable progress events,
and only reports completion when the agent supplies an explicit verification summary.
It has a configurable iteration budget and honors cancellation between turns.
"""
from __future__ import annotations

import os
import re
from typing import Any, Callable

MAX_GOAL_ITERATIONS = max(1, min(int(os.getenv("SPARKBOT_GOAL_MAX_ITERATIONS", "12")), 30))

GOAL_SYSTEM = """You are running SparkBot's persistent /goal mode.
Keep working toward the user's goal instead of stopping after a plan or one answer.
On each turn, choose the next useful action, use available tools when appropriate, inspect
their actual results, recover from retryable failures, and avoid repeating failed actions.
Do not claim that an action occurred without tool evidence. Never bypass authentication,
CAPTCHA, security controls, user consent, approval gates, or platform limits. Ask for human
input only when a genuine external checkpoint or missing required information blocks progress.
Do not perform irreversible or externally visible actions without the existing approval flow.

At the END of every response, include exactly one status line:
GOAL_STATUS: CONTINUE
GOAL_STATUS: COMPLETE
GOAL_STATUS: BLOCKED

Use COMPLETE only when the goal's acceptance criteria have actually been met and include a
separate line beginning VERIFICATION: with concrete evidence/results. If incomplete, use
CONTINUE and name the next action. If a human checkpoint or unavailable capability blocks
further safe progress, use BLOCKED and explain exactly what is needed. Do not treat a plan as
completion. Keep each turn focused on making real progress.
"""


def run_goal(
    goal: str,
    emit: Callable[..., None],
    mission_id: str,
    run_turn: Callable[[list[dict[str, str]]], dict[str, Any]],
    should_stop: Callable[[], bool],
) -> dict[str, Any]:
    goal = goal.strip()
    messages: list[dict[str, str]] = [
        {"role": "system", "content": GOAL_SYSTEM},
        {"role": "user", "content": goal},
    ]
    transcript: list[str] = []
    last_result: dict[str, Any] = {}
    emit("goal", "Goal mode started; acceptance criteria are being evaluated.", iteration=0,
         max_iterations=MAX_GOAL_ITERATIONS, goal=goal)

    for iteration in range(1, MAX_GOAL_ITERATIONS + 1):
        if should_stop():
            emit("cancelled", "Goal stopped by user.", iteration=iteration - 1)
            return {"mission_id": mission_id, "status": "CANCELLED", "verified": False,
                    "iterations": iteration - 1, "transcript": transcript[-8:]}

        emit("iteration", f"Working on goal (step {iteration}/{MAX_GOAL_ITERATIONS}).",
             iteration=iteration, max_iterations=MAX_GOAL_ITERATIONS)
        result = run_turn(messages)
        last_result = result if isinstance(result, dict) else {}
        reply = str(last_result.get("reply", "")).strip()
        if not reply or reply.startswith("AI unavailable:"):
            emit("blocked", "AI execution is unavailable; the goal remains unfinished.",
                 iteration=iteration, error=reply or "Empty agent response")
            return {"mission_id": mission_id, "status": "BLOCKED", "verified": False,
                    "iterations": iteration, "error": reply or "Empty agent response",
                    "transcript": transcript[-8:]}

        transcript.append(reply[-2500:])
        events = last_result.get("events", [])
        if isinstance(events, list):
            for event in events[-12:]:
                if isinstance(event, dict):
                    emit(str(event.get("type", "agent")), str(event.get("message", "Agent progress")),
                         iteration=iteration,
                         **{k: v for k, v in event.items() if k not in {"type", "message"}})
        emit("progress", reply[-1800:], iteration=iteration)

        status_match = re.search(r"GOAL_STATUS\s*:\s*(CONTINUE|COMPLETE|BLOCKED)", reply, re.I)
        status = status_match.group(1).upper() if status_match else "CONTINUE"
        verification_match = re.search(r"^VERIFICATION\s*:\s*(.+)$", reply, re.I | re.M)
        verification = verification_match.group(1).strip() if verification_match else ""

        if status == "COMPLETE" and verification:
            emit("verification", "Completion criteria reported with verification evidence.",
                 iteration=iteration, evidence=verification[:1200])
            return {"mission_id": mission_id, "status": "COMPLETED", "verified": True,
                    "iterations": iteration, "verification": verification,
                    "reply": reply, "transcript": transcript[-8:],
                    "last_mission": last_result.get("mission")}
        if status == "BLOCKED":
            emit("blocked", "A genuine blocker requires attention; the goal is not marked complete.",
                 iteration=iteration, detail=reply[-1200:])
            return {"mission_id": mission_id, "status": "BLOCKED", "verified": False,
                    "iterations": iteration, "reply": reply, "transcript": transcript[-8:]}
        if status == "COMPLETE" and not verification:
            messages.append({"role": "assistant", "content": reply})
            messages.append({"role": "user", "content":
                "You declared completion without a concrete VERIFICATION line. Do not claim completion yet. "
                "Check the actual outcome, gather evidence using available tools, or explain the blocker. "
                "Continue toward the original goal and end with GOAL_STATUS plus VERIFICATION only if proven."})
        else:
            messages.append({"role": "assistant", "content": reply})
            messages.append({"role": "user", "content":
                "Continue the original goal from the current state. Do not repeat completed steps. "
                "Take the next concrete action, verify its result, and end with GOAL_STATUS. "
                "Only use COMPLETE with a concrete VERIFICATION line."})

    emit("limit", "Iteration budget reached; goal is unfinished and needs continuation.",
         iterations=MAX_GOAL_ITERATIONS)
    return {"mission_id": mission_id, "status": "PARTIAL", "verified": False,
            "iterations": MAX_GOAL_ITERATIONS, "reply": transcript[-1] if transcript else "",
            "transcript": transcript[-8:], "last_mission": last_result.get("mission")}
