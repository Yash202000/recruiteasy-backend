from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from auth.dependencies import get_current_user
from database import get_db
from models import User
from schemas import UserBasicInfo, UserCreate
from auth.jwt_handler import verify_token

router = APIRouter()

@router.get("/me", response_model=UserCreate)
def read_users_me(current_user: UserCreate = Depends(get_current_user)):
    return current_user


@router.get("/", response_model=list[UserBasicInfo])
def list_users(db: Session = Depends(get_db)):
    db_users = db.query(User).all()
    if not db_users:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No users found")
    return db_users
    

@router.get("/{user_id}", response_model=UserBasicInfo)
def get_user_by_id(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user




