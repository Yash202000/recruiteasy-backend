from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base, get_db
import models
import schemas
from typing import List

from auth import auth_routes
from users import user_routes
from sockets import socket_routes
from calls import call_routes
from rooms import room_router
from profiles import profile_routes
from jobs import jobs_router
from jobapplications import jobapplications_router

# Initialize FastAPI app
app = FastAPI()

origins = [
    '*'
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Create the database tables
Base.metadata.create_all(bind=engine)


app.include_router(auth_routes.router, prefix="/auth", tags=["auth"])
app.include_router(user_routes.router, prefix="/users", tags=["users"])
app.include_router(call_routes.router, prefix="/calls", tags=['calls'])
app.include_router(room_router.router, prefix="/rooms", tags=['rooms'])
app.include_router(jobs_router.router, prefix='/jobs', tags=['jobs'])
app.include_router(profile_routes.router, prefix='/profiles', tags=['profiles'])
app.include_router(jobapplications_router.router, prefix='/jobapplications', tags=['jobapplications'])


# WebSocket route
app.include_router(socket_routes.router)