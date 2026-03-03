from pydantic import BaseModel, Field
from typing import List, Dict


class SkillKeySkillOrphans(BaseModel):
    student_skill_not_found: List[str] = Field(default_factory=list)
    keyskill_not_found: List[str] = Field(default_factory=list)
    ambiguous_keyskill: List[str] = Field(default_factory=list)


class UploadSkillKeySkillMapResponse(BaseModel):
    rows_received: int
    rows_valid: int
    inserted: int
    skipped_existing: int
    orphans: SkillKeySkillOrphans
    dry_run: bool
