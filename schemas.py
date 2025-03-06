from pydantic import BaseModel, EmailStr, HttpUrl, Field
from typing import List, Optional, Union
from datetime import date, datetime




#########################  #####################3

# --- JobSeekerProfile Schemas ---
class JobSeekerProfileBase(BaseModel):
    bio: Optional[str]
    date_of_birth: Optional[date]
    contact_number: Optional[str]
    address: Optional[str]
    resume_url: Optional[str]
    profiles: Optional[dict] = {}  # Example: {"linkedin": "", "github": "", "portfolio": ""}
    education: Optional[List[dict]] = []  # Example: [{"institution": "", "degree": "", "year": ""}]
    work_experience: Optional[List[dict]] = []  # Example: [{"company": "", "role": "", "duration": ""}]
    projects: Optional[List[dict]] = []  # Example: [{"name": "", "description": "", "url": ""}]
    publications: Optional[List[dict]] = []  # Example: [{"title": "", "link": "", "date": ""}]
    certifications: Optional[List[dict]] = []  # Example: [{"name": "", "authority": "", "date": ""}]
    awards: Optional[List[dict]] = []  # Example: [{"name": "", "reason": "", "date": ""}]
    skills: Optional[List[str]] = []  # Example: ["Python", "AWS", "Docker"]


class JobSeekerProfileCreate(JobSeekerProfileBase):
    user_id: int


class JobSeekerProfileUpdate(JobSeekerProfileBase):
    pass


class JobSeekerProfileResponse(JobSeekerProfileBase):
    id: int
    user_id: int

    class Config:
        orm_mode = True



class MessageBase(BaseModel):
    content: str

class MessageCreate(MessageBase):
    user_id: int

class Message(MessageBase):
    id: int
    timestamp: datetime
    room_id: int
    user_id: int

    class Config:
        orm_mode = True


class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str




class UserBasicInfo(BaseModel):
    id: int
    username: str
    email: str

    job_seeker_profile: JobSeekerProfileCreate

    class Config:
        orm_mode = True


class RoomCreate(BaseModel):
    user_ids: List[int]
    is_group: bool = False
    name: Optional[str] = None


class RoomParticipant(BaseModel):
    user_id: int

    class Config:
        orm_mode = True


class RoomResponse(BaseModel):
    id: str
    is_group: bool
    name: Optional[str] = None
    users: List[RoomParticipant] = []

    class Config:
        orm_mode = True


############################ call schema ###########

class RoomInfoResponse(BaseModel):
    id: str
    name: str
    empty_timeout: int
    creation_time: int
    turn_password: str
    departure_timeout: int
    enabled_codecs: list[str]


class RoomTokenRequest(BaseModel):
    identity: str
    name: str
    room: str
    iname: str



# --- Job Schemas ---
class JobBase(BaseModel):
    title: str
    description: str
    location: Optional[str]
    is_remote: bool = False


class JobCreate(JobBase):
    posted_by_id: int


class JobUpdate(BaseModel):
    title: Optional[str]
    description: Optional[str]
    location: Optional[str]
    is_remote: Optional[bool]


class JobResponse(JobBase):
    id: str
    posted_at: datetime
    posted_by_id: int

    class Config:
        orm_mode = True


# --- JobApplication Schemas ---
class JobApplicationBase(BaseModel):
    cover_letter: Optional[str]
    status: Optional[str] = Field("Pending", pattern="^(Pending|Accepted|Rejected)$")


class JobApplicationCreate(JobApplicationBase):
    job_id: str
    user_id: int


class JobApplicationUpdate(JobApplicationBase):
    pass


class JobApplicationResponse(JobApplicationBase):
    id: int
    job_id: str
    user_id: int
    applied_at: datetime

    class Config:
        orm_mode = True



class InterviewRequest(BaseModel):
    user_id: str
    interview_title: str
    description: str
    duration: str
    difficulty: str

