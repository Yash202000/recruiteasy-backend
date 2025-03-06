from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from models import User, Room, UserRoom
from schemas import RoomCreate, RoomResponse, RoomParticipant
from uuid import uuid4

router = APIRouter()


def get_or_create_one_to_one_room(user1_id: int, user2_id: int, db: Session):
    room = (
        db.query(Room)
        .join(UserRoom)
        .filter(
            UserRoom.user_id.in_([user1_id, user2_id]),
            Room.is_group == False
        )
        .group_by(Room.id)
        .having(func.count(Room.id) == 2)
        .first()
    )
    
    if not room:
        room = Room(is_group=False)
        db.add(room)
        db.commit()
        db.add_all([
            UserRoom(user_id=user1_id, room_id=room.id),
            UserRoom(user_id=user2_id, room_id=room.id)
        ])
        db.commit()
    return room



@router.post("/", response_model=RoomResponse)
def create_room(user_ids: List[int], is_group: bool = False, name: str = None, db: Session = Depends(get_db)):
    # Handle one-to-one room creation
    if not is_group and len(user_ids) == 2:
        room = get_or_create_one_to_one_room(user_ids[0], user_ids[1], db)
        return room

    # Create a new group room or non-duplicate one-to-one room if above conditions don't apply
    room = Room(id=str(uuid4()), is_group=is_group, name=name)
    db.add(room)
    db.commit()

    for user_id in user_ids:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User {user_id} not found")
        db.add(UserRoom(user_id=user.id, room_id=room.id))

    db.commit()
    return room

@router.post("/{room_id}/add_participants", response_model=RoomResponse)
def add_participants(room_id: str, user_ids: List[int], db: Session = Depends(get_db)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")

    for user_id in user_ids:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User {user_id} not found")
        
        # Check if the user is already in the room
        if db.query(UserRoom).filter(UserRoom.user_id == user_id, UserRoom.room_id == room_id).first():
            continue

        db.add(UserRoom(user_id=user_id, room_id=room_id))

    db.commit()
    return room


@router.delete("/{room_id}/remove_participant/{user_id}", response_model=RoomResponse)
def remove_participant(room_id: str, user_id: int, db: Session = Depends(get_db)):
    user_room = db.query(UserRoom).filter(UserRoom.room_id == room_id, UserRoom.user_id == user_id).first()
    if not user_room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found in the room")
    
    db.delete(user_room)
    db.commit()

    room = db.query(Room).filter(Room.id == room_id).first()
    return room


@router.get("/{room_id}", response_model=RoomResponse)
def get_room(room_id: str, db: Session = Depends(get_db)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    return room


@router.get("/", response_model=List[RoomResponse])
def list_rooms(db: Session = Depends(get_db)):
    return db.query(Room).all()