from uuid import uuid4
from sqlalchemy import Boolean, Column, Integer, String, ForeignKey, DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)


    # Updates to User model for relationships
    posted_jobs = relationship("Job", back_populates="posted_by")
    applications = relationship("JobApplication", back_populates="user")
    job_seeker_profile = relationship("JobSeekerProfile", back_populates="user", uselist=False)

    # Relationships
    rooms = relationship("UserRoom", back_populates="user")
    messages = relationship("Message", back_populates="sender")

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class Room(Base):
    __tablename__ = "rooms"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()), index=True)
    is_group = Column(Boolean, default=False)
    name = Column(String, nullable=True)  # Optional for group chats

    # Relationships
    messages = relationship("Message", back_populates="room")
    users = relationship("UserRoom", back_populates="room")

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class UserRoom(Base):
    __tablename__ = "user_rooms"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    room_id = Column(String, ForeignKey("rooms.id"), primary_key=True)
    
    # Relationships
    user = relationship("User", back_populates="rooms")
    room = relationship("Room", back_populates="users")

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=func.now())
    sender_id = Column(Integer, ForeignKey("users.id"))
    room_id = Column(String, ForeignKey("rooms.id"))

    # Relationships
    sender = relationship("User", back_populates="messages")
    room = relationship("Room", back_populates="messages")

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class Job(Base):
    __tablename__ = "jobs"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()), index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    location = Column(String, nullable=True)
    posted_at = Column(DateTime, default=func.now())
    is_remote = Column(Boolean, default=False)

    # Relationships
    posted_by_id = Column(Integer, ForeignKey("users.id"))
    posted_by = relationship("User", back_populates="posted_jobs")
    applications = relationship("JobApplication", back_populates="job")

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class JobApplication(Base):
    __tablename__ = "job_applications"
    id = Column(Integer, primary_key=True, index=True)
    cover_letter = Column(Text, nullable=True)
    applied_at = Column(DateTime, default=func.now())
    status = Column(String, default="Pending")  # Status: Pending, Accepted, Rejected

    # Foreign keys and relationships
    job_id = Column(String, ForeignKey("jobs.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    job = relationship("Job", back_populates="applications")
    user = relationship("User", back_populates="applications")

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)



class JobSeekerProfile(Base):
    __tablename__ = "job_seeker_profiles"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    # Basic Information
    bio = Column(Text, nullable=True)
    date_of_birth = Column(DateTime, nullable=True)
    contact_number = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    resume_url = Column(String, nullable=True)

    # Dynamic JSON fields
    profiles = Column(JSON, default={})  # {"linkedin": "...", "github": "...", "portfolio": "..."}
    education = Column(JSON, default=[])  # [{"institution": "...", "degree": "...", "year": "..."}]
    work_experience = Column(JSON, default=[])  # [{"company": "...", "role": "...", "duration": "..."}]
    projects = Column(JSON, default=[])  # [{"name": "...", "description": "...", "url": "..."}]
    publications = Column(JSON, default=[])  # [{"title": "...", "link": "...", "date": "..."}]
    certifications = Column(JSON, default=[])  # [{"name": "...", "authority": "...", "date": "..."}]
    awards = Column(JSON, default=[])  # [{"name": "...", "reason": "...", "date": "..."}]
    skills = Column(JSON, default=[])  # ["Python", "SQL", "AWS"]

    # Relationships
    user = relationship("User", back_populates="job_seeker_profile")

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

