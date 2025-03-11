import json
import aiohttp
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from auth.dependencies import get_current_user
from database import get_db
from models import User, Room, UserRoom
from schemas import InterviewRequest, RoomInfoResponse, RoomTokenRequest   
from auth.jwt_handler import verify_token
from livekit import api
from config import settings

from livekit.protocol.agent_dispatch import (
    RoomAgentDispatch,
    CreateAgentDispatchRequest,
)
from livekit.api import AccessToken, VideoGrants


from livekit.protocol.room import RoomConfiguration

from livekit import api
import asyncio
import boto3

import os
from groq import Groq
import redis

router = APIRouter()

s3_client = boto3.client(
            "s3",
            endpoint_url=os.environ.get("STORAGE_ENDPOINT"),
            aws_access_key_id=os.environ.get("STORAGE_ACCESS_KEY"),
            aws_secret_access_key=os.environ.get("STORAGE_SECRET_KEY"),
            region_name=os.environ.get("STORAGE_REGION")
        )
        

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))


# Redis connection
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)

def get_redis_client():
    try:
        redis_client.ping()
        return redis_client
    except redis.ConnectionError:
        raise HTTPException(status_code=500, detail="Cannot connect to Redis")



@router.get("/")
async def list_rooms_with_files(user_id: int, db: Session = Depends(get_db)):
    # Query rooms for the user
    rooms = (
        db.query(Room)
        .join(UserRoom, Room.id == UserRoom.room_id)
        .filter(UserRoom.user_id == user_id)
        .all()
    )
    
    if not rooms:
        raise HTTPException(status_code=404, detail="No rooms found for the user")

    # S3 bucket configuration
    bucket_name = "livekit-egress"

    room_files = []
    for room in rooms:
        folder_prefix = f"{room.id}/"  # Folder for each room in S3
        try:
            response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=folder_prefix)
            files = []
            if 'Contents' in response:
                files = [
                    {
                        "file_name": obj["Key"].split("/")[-1],
                        "size": obj["Size"],
                        "last_modified": obj["LastModified"].isoformat(),
                        
                    }
                    for obj in response["Contents"]
                ]
            room_files.append({
                "room": {
                    "id": room.id,
                    "name": room.name,
                    "is_group": room.is_group,
                },
                "files": files,
            })
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error fetching files for room {room.id}: {str(e)}")
    
    return room_files

    
    # lkapi = api.LiveKitAPI(
    #     settings.LIVEKIT_SERVER_URL,
    #     settings.LIVEKIT_API_KEY,
    #     settings.LIVEKIT_API_SECRET,
    #     timeout=aiohttp.ClientTimeout(total=60 * 10)  # 10 minutes
    # )
    
    # try:
    #     results = await lkapi.room.list_rooms(api.ListRoomsRequest())
    #     room_list = []
    #     for room in results.rooms:
    #         room_list.append(RoomInfoResponse(
    #             id=room.sid,
    #             name=room.name,
    #             empty_timeout=room.empty_timeout,
    #             creation_time=room.creation_time,
    #             turn_password=room.turn_password,
    #             departure_timeout=room.departure_timeout,
    #             enabled_codecs=[codec.mime for codec in room.enabled_codecs]
    #         ))
    #     return room_list
    # finally:
    #     await lkapi.aclose()  # Ensure the client session closes
   
    

@router.get("/{room_id}")
async def list_room_with_files(room_id: str, db: Session = Depends(get_db)):
    # Query rooms for the user
    room = (
        db.query(Room)
        .join(UserRoom, Room.id == UserRoom.room_id)
        .filter(UserRoom.room_id == room_id)
        .first()
    )
    
    if not room:
        raise HTTPException(status_code=404, detail="No room found for the user")

    # S3 bucket configuration
    bucket_name = "livekit-egress"

    
    folder_prefix = f"{room.id}/"  # Folder for each room in S3
    try:
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=folder_prefix)
        files = []
        if 'Contents' in response:
            files = [
                {
                    "file_name": obj["Key"].split("/")[-1],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                    "signed_url": s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket_name, "Key": obj["Key"]},
                ExpiresIn=3600,  # URL expiration time in seconds
            )
                }
                for obj in response["Contents"]
            ]
        return({
            "room": {
                "id": room.id,
                "name": room.name,
                "is_group": room.is_group,
            },
            "files": files,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching files for room {room.id}: {str(e)}")
    
   


@router.get("/{room_id}/analyze-log")
async def analyze_room_log(room_id: str, db: Session = Depends(get_db)):
    # Query room details
    room = (
        db.query(Room)
        .join(UserRoom, Room.id == UserRoom.room_id)
        .filter(UserRoom.room_id == room_id)
        .first()
    )

    if not room:
        raise HTTPException(status_code=404, detail="No room found for the user")

    # S3 bucket configuration
    bucket_name = os.environ.get("BUCKET_NAME")
    folder_prefix = f"{room.id}/"
    
    try:
        # List objects in S3 bucket
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=folder_prefix)
        if "Contents" not in response:
            raise HTTPException(status_code=404, detail="No files found in the room's S3 folder")
        
        # Filter for .log files
        log_file = next(
            (obj for obj in response["Contents"] if obj["Key"].endswith(".log")), None
        )
        if not log_file:
            raise HTTPException(status_code=404, detail="No .log file found in the room's S3 folder")

        # Fetch log file content
        log_file_key = log_file["Key"]
        log_file_content = s3_client.get_object(Bucket=bucket_name, Key=log_file_key)["Body"].read().decode("utf-8")


        feedback_response=[]

        prompt = """
       Analyze the following conversation log and generate a detailed feedback report.
        Answer Feedback: Analyze the user's response in detail, focusing on multiple factors but you should include only three major points which is much needed 

        Overall Feedback: Summarize the quality of the response as one of the following: excellent, good, needs improvement, bad, or worst.
        Response Format:
        '"Keypoint which user lags": "<Feedback>" 
        "keypoint which user lags": "<Feedback>", 
        "Avoid Redundancy": "<Feedback>" },
        "overall_feedback": "<Overall assessment>"}
        """
        
        for line in log_file_content.splitlines():
            if "AGENT:" in line:
                # Extract the question part
                current_question = line.split("AGENT:")[-1].strip()
            elif "USER:" in line and current_question:
                # Extract the answer part
                user_answer = line.split("USER:")[-1].strip()
                # Append the question-answer pair

                chat_completion = groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt+f" question : {current_question}, User_answer: {user_answer}"}],
                    model="llama3-8b-8192",
                )

                # Extract analysis
                feedback_report = chat_completion.choices[0].message.content


                feedback_response.append({
                    "question": current_question,
                    "answer": user_answer,
                    "feedback": feedback_report
                })
                # Reset current_question for the next pair
                current_question = None

        
        return {
            "room": {
                "id": room.id,
                "name": room.name,
                "is_group": room.is_group,
            },
            "feedback_report": feedback_response,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing log file: {str(e)}")


async def createRoomHelper(room_name: str):
    lkapi = api.LiveKitAPI(
        settings.LIVEKIT_SERVER_URL,
        settings.LIVEKIT_API_KEY,
        settings.LIVEKIT_API_SECRET,
        timeout=aiohttp.ClientTimeout(total=60 * 10)  # 10 minutes
    )

    try:
        room_info = await lkapi.room.create_room(
            api.CreateRoomRequest(name=room_name),
        )
    
        response_data = RoomInfoResponse(
            id=room_info.sid,
            name=room_info.name,
            empty_timeout=room_info.empty_timeout,
            creation_time=room_info.creation_time,
            turn_password=room_info.turn_password,
            departure_timeout=room_info.departure_timeout,
            enabled_codecs=[codec.mime for codec in room_info.enabled_codecs]
        )

        return response_data
    finally:
        await lkapi.aclose()

    


@router.post("/create/{room_name}")
def create_room(room_name: str):
    try:
        # Run the createRoomHelper coroutine in the main event loop
        room_info = asyncio.run(createRoomHelper(room_name))
        print(room_info)
        return {"message": "Room created successfully", "room_info": room_info}
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error creating room: {str(e)}")
    

async def deleteRoomHelper(room_name: str):
    lkapi = api.LiveKitAPI(
        settings.LIVEKIT_SERVER_URL,
        settings.LIVEKIT_API_KEY,
        settings.LIVEKIT_API_SECRET,
        timeout=aiohttp.ClientTimeout(total=60 * 10)  # 10 minutes
    )
    
    try:
        await lkapi.room.delete_room(
            api.DeleteRoomRequest(room=room_name),
        )
    finally:
        await lkapi.aclose()  # Ensure the client session closes


@router.delete("/delete/{room_name}")
async def delete_room(room_name: str):
    try:
        # Run the createRoomHelper coroutine in the main event loop
        results = await deleteRoomHelper(room_name)
        return results
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"{str(e)}")
    


@router.post('/getToken')
def getToken(reqbody : RoomTokenRequest,  db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == reqbody.identity).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User {reqbody.identity} not found")
    
    # room = db.query(Room).filter(Room.id==reqbody.room).first()
    # if not room:
    #     db_profile = Room(id=reqbody.room,name=reqbody.iname)
    #     db.add(db_profile)

    #     userRoom = UserRoom(user_id=reqbody.identity, room_id=reqbody.room)
    #     db.add(userRoom)

    #     db.commit()
    #     db.refresh(db_profile)
    
    token = AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET) \
        .with_identity(reqbody.identity) \
        .with_name(reqbody.name) \
        .with_grants(VideoGrants(room_join=True, room=reqbody.room)) \
        # .with_room_config(
        #     RoomConfiguration(
        #         agents=[
        #             RoomAgentDispatch(agent_name="aiagent")
        #         ],
        #     ),
        # )
    return {
        "serverUrl": settings.LIVEKIT_SERVER_URL,
        "roomName": reqbody.room,
        "participantToken": token.to_jwt(),
        "participantName": reqbody.name
    }





# POST: Create or update interview request
@router.post("/interviews")
def post_interview(interview: InterviewRequest, redis_client=Depends(get_redis_client)):
    key = f"user:{interview.user_id}"
    value = json.dumps(interview.dict())
    redis_client.set(key, value)  # Upsert operation
    return {"message": "Interview request saved successfully", "data": interview}


# GET: Retrieve the latest interview request for a user
@router.get("/interviews/{user_id}")
def get_interview(user_id: str, redis_client=Depends(get_redis_client)):
    key = f"user:{user_id}"
    value = redis_client.get(key)
    if value:
        interview = json.loads(value)
        return {"message": "Latest interview request retrieved", "data": interview}
    else:
        raise HTTPException(status_code=404, detail="No interview request found for this user")


# DELETE: Delete the interview request for a user
@router.delete("/interviews/{user_id}")
def delete_interview(user_id: str, redis_client=Depends(get_redis_client)):
    key = f"user:{user_id}"
    result = redis_client.delete(key)
    if result == 1:
        return {"message": "Interview request deleted successfully"}
    else:
        raise HTTPException(status_code=404, detail="No interview request found to delete")






