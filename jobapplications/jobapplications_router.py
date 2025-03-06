from fastapi import APIRouter, Depends, HTTPException
from models import Job, JobApplication
from schemas import JobApplicationCreate, JobApplicationUpdate, JobCreate, JobUpdate
from sqlalchemy.orm import Session
from database import get_db


router = APIRouter()


@router.post("/", response_model=JobApplicationCreate)
def create_application(application: JobApplicationCreate, db: Session = Depends(get_db)):
    db_application = JobApplication(**application.dict())
    db.add(db_application)
    db.commit()
    db.refresh(db_application)
    return db_application


@router.get("/{application_id}", response_model=JobApplicationCreate)
def read_application(application_id: int, db: Session = Depends(get_db)):
    application = db.query(JobApplication).filter(JobApplication.id == application_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    return application


@router.put("/{application_id}", response_model=JobApplicationUpdate)
def update_application(application_id: int, application: JobApplicationUpdate, db: Session = Depends(get_db)):
    db_application = db.query(JobApplication).filter(JobApplication.id == application_id).first()
    if not db_application:
        raise HTTPException(status_code=404, detail="Application not found")
    for key, value in application.dict(exclude_unset=True).items():
        setattr(db_application, key, value)
    db.commit()
    db.refresh(db_application)
    return db_application


@router.delete("/{application_id}")
def delete_application(application_id: int, db: Session = Depends(get_db)):
    db_application = db.query(JobApplication).filter(JobApplication.id == application_id).first()
    if not db_application:
        raise HTTPException(status_code=404, detail="Application not found")
    db.delete(db_application)
    db.commit()
    return {"message": "Application deleted successfully"}