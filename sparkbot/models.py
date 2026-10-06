from pydantic import BaseModel, Field
class GoalCreate(BaseModel):
 title: str = Field(min_length=1, max_length=200); description: str = Field(default="", max_length=4000); kpi: str = Field(default="", max_length=500)
class TaskCreate(BaseModel):
 title: str = Field(min_length=1, max_length=200); description: str = Field(default="", max_length=4000); priority: str = Field(default="P2", pattern=r"^P[0-3]$"); goal_id: int | None = None; tool: str = Field(default="internal", max_length=100); expected_output: str = Field(default="", max_length=1000)
class CommandRequest(BaseModel): command: str = Field(min_length=1, max_length=4000)
class SkillRouteRequest(BaseModel): request: str = Field(min_length=1, max_length=4000); limit: int = Field(default=10, ge=1, le=50)
class SkillExecuteRequest(BaseModel): skill_id: str = Field(pattern=r"^\d{3}\.\d{2}$"); mode: str = Field(default="DRY_RUN", pattern=r"^(SIMULATION|DRY_RUN|PRODUCTION)$"); permissions: list[str] = Field(default=["READ"]); payload: dict = Field(default_factory=dict); human_approved: bool = False
class TaskStatusUpdate(BaseModel): status: str = Field(pattern=r"^(QUEUED|PLANNING|RUNNING|WAITING|BLOCKED|REVIEW|COMPLETED|FAILED|CANCELLED)$")
