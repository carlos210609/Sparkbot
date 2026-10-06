from __future__ import annotations
from .skills import SkillRegistry

WORKFLOWS={
 "marketing_growth":["007.01","016.01","015.01","013.04","031.01","018.04","034.01","042.15","041.01","060.15","062.02","099.14"],
 "instagram_growth":["018.01","015.01","018.04","019.01","019.02","019.06","020.01","031.01","060.15","062.02","099.13"],
 "sales_growth":["015.01","041.02","041.03","042.05","040.04","043.06","043.07","041.09","064.01","099.12"],
 "product_launch":["007.11","013.04","054.01","032.05","031.01","021.01","039.01","050.01","060.15","099.14"],
}

class WorkflowEngine:
 def __init__(self,registry:SkillRegistry): self.registry=registry
 def compose(self,name:str)->dict:
  ids=WORKFLOWS.get(name)
  if not ids: raise KeyError(name)
  skills=[self.registry.get(i) for i in ids]
  return {"name":name,"skill_ids":ids,"skills":[s.to_dict() for s in skills if s],"verified":all(s is not None for s in skills)}
