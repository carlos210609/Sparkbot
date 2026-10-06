from __future__ import annotations
from dataclasses import dataclass
from .db import execute, fetch_all
@dataclass
class PlanResult:
 intent: str
 goal: str
 tasks: list[dict[str, str]]
 note: str
class SparkAgent:
 def interpret(self, command: str) -> PlanResult:
  text = command.strip(); lower = text.lower()
  if any(k in lower for k in ("instagram", "reels", "social")):
   intent, goal = "SOCIAL_GROWTH", "Improve qualified social-media growth"
   tasks = [
    {"title":"Audit current social presence","priority":"P1","tool":"internal"},
    {"title":"Define three content pillars","priority":"P1","tool":"internal"},
    {"title":"Create a 7-day content plan","priority":"P2","tool":"internal"},
    {"title":"Define measurement baseline","priority":"P1","tool":"internal"}]
  elif any(k in lower for k in ("cliente","clientes","leads","vendas","sales")):
   intent, goal = "SALES_GROWTH", "Increase qualified pipeline and conversion"
   tasks = [
    {"title":"Define ICP and qualification rules","priority":"P1","tool":"internal"},
    {"title":"Create lead-scoring baseline","priority":"P1","tool":"internal"},
    {"title":"Map the sales funnel","priority":"P1","tool":"internal"},
    {"title":"Create follow-up experiment","priority":"P2","tool":"internal"}]
  else:
   intent, goal = "GROWTH_STRATEGY", text
   tasks = [
    {"title":"Clarify measurable success criteria","priority":"P0","tool":"internal"},
    {"title":"Research market and audience","priority":"P1","tool":"internal"},
    {"title":"Build a prioritized growth plan","priority":"P1","tool":"internal"},
    {"title":"Define measurement baseline","priority":"P1","tool":"internal"}]
  return PlanResult(intent, goal, tasks, "Offline planning mode: no external action was performed.")
 def run_command(self, command: str) -> dict:
  plan = self.interpret(command)
  goal_id = execute("INSERT INTO goals(title, description, kpi) VALUES (?, ?, ?)", (plan.goal, command, "Define after baseline"))
  for task in plan.tasks:
   execute("""INSERT INTO tasks(goal_id,title,description,priority,tool,expected_output)
              VALUES (?,?,?,?,?,?)""", (goal_id, task["title"], command, task["priority"], task["tool"], "Verified task result"))
  execute("INSERT INTO activity_logs(event_type,message,metadata) VALUES (?,?,?)",
          ("PLAN_CREATED", f"Plan created for: {plan.goal}", '{"mode":"offline"}'))
  return {"intent":plan.intent,"goal_id":goal_id,"goal":plan.goal,"tasks":plan.tasks,"note":plan.note}
 def snapshot(self) -> dict:
  goals = fetch_all("SELECT * FROM goals ORDER BY id DESC LIMIT 20")
  tasks = fetch_all("SELECT * FROM tasks ORDER BY CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END, id DESC LIMIT 50")
  activity = fetch_all("SELECT * FROM activity_logs ORDER BY id DESC LIMIT 30")
  return {"goals":goals,"tasks":tasks,"activity":activity}
