"""Career ↔ KeySkill mapping router.
Exposes mapping endpoints under /v1/career-keyskill-map/.
Role gate: authenticated users.
Reads/writes: career_keyskill_association table.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import models, deps
from app.auth.auth import get_current_active_user

router = APIRouter(
    prefix="",
    tags=["Career ↔ KeySkill"],
    dependencies=[Depends(get_current_active_user)],
)

# ✅ Link a Career to a KeySkill
@router.post("")
def link_keyskill_to_career(career_id: int, keyskill_id: int, db: Session = Depends(deps.get_db)):
    career = db.query(models.Career).filter(models.Career.id == career_id).first()
    keyskill = db.query(models.KeySkill).filter(models.KeySkill.id == keyskill_id).first()

    if not career:
        raise HTTPException(status_code=404, detail="Career not found")
    if not keyskill:
        raise HTTPException(status_code=404, detail="KeySkill not found")

    # Avoid duplicates
    if keyskill in career.keyskills:
        raise HTTPException(status_code=400, detail="Mapping already exists")

    career.keyskills.append(keyskill)
    db.commit()
    return {"message": f"Linked KeySkill {keyskill_id} to Career {career_id}"}

# 📋 List all Career ↔ KeySkill Mappings
@router.get("")
def get_all_career_keyskill_mappings(db: Session = Depends(deps.get_db)):
    careers = db.query(models.Career).all()
    result = []
    for career in careers:
        for keyskill in career.keyskills:
            result.append({
                "career_id": career.id,
                "career_title": career.title,
                "keyskill_id": keyskill.id,
                "keyskill_name": keyskill.name
            })
    return result

# ❌ Unlink a Career from a KeySkill
@router.delete("")
def unlink_keyskill_from_career(career_id: int, keyskill_id: int, db: Session = Depends(deps.get_db)):
    career = db.query(models.Career).filter(models.Career.id == career_id).first()
    keyskill = db.query(models.KeySkill).filter(models.KeySkill.id == keyskill_id).first()

    if not career or not keyskill:
        raise HTTPException(status_code=404, detail="Career or KeySkill not found")

    if keyskill not in career.keyskills:
        raise HTTPException(status_code=404, detail="Mapping not found")

    career.keyskills.remove(keyskill)
    db.commit()
    return {"message": f"Unlinked KeySkill {keyskill_id} from Career {career_id}"}
