from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from models import JobSeekerProfile
from schemas import JobSeekerProfileCreate, JobSeekerProfileUpdate
from database import get_db


router = APIRouter()


# --- JobSeekerProfile CRUD ---
@router.post("/", response_model=JobSeekerProfileCreate)
def create_profile(profile: JobSeekerProfileCreate, db: Session = Depends(get_db)):
    db_profile = JobSeekerProfile(**profile.dict())
    db.add(db_profile)
    db.commit()
    db.refresh(db_profile)
    return db_profile


@router.get("/{profile_id}", response_model=JobSeekerProfileCreate)
def read_profile(profile_id: int, db: Session = Depends(get_db)):
    profile = db.query(JobSeekerProfile).filter(JobSeekerProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.put("/{profile_id}", response_model=JobSeekerProfileUpdate)
def update_profile(profile_id: int, profile: JobSeekerProfileUpdate, db: Session = Depends(get_db)):
    db_profile = db.query(JobSeekerProfile).filter(JobSeekerProfile.id == profile_id).first()
    if not db_profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    for key, value in profile.dict(exclude_unset=True).items():
        setattr(db_profile, key, value)
    db.commit()
    db.refresh(db_profile)
    return db_profile


@router.delete("/{profile_id}")
def delete_profile(profile_id: int, db: Session = Depends(get_db)):
    db_profile = db.query(JobSeekerProfile).filter(JobSeekerProfile.id == profile_id).first()
    if not db_profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    db.delete(db_profile)
    db.commit()
    return {"message": "Profile deleted successfully"}

