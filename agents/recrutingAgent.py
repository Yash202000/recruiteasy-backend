import asyncio
import datetime
import json
import logging

import os
import random
from typing import Union
from PIL import Image

import aiohttp
from dotenv import load_dotenv
from livekit import rtc,protocol, api
from livekit.agents import (
    JobContext,
    JobProcess,
    WorkerOptions,
    WorkerType,
    WorkerPermissions,
    cli,
    llm,
    metrics,
)
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import openai, silero
import elevenlabs
import boto3
import aiofiles
import redis


# Redis connection
redis_client = redis.StrictRedis(host='axionic2.discretal.com', port=6379, db=0, decode_responses=True)


load_dotenv()
logger = logging.getLogger("AI-Interview-assistant")

WIDTH, HEIGHT = 640, 480

def get_redis_client():
    try:
        redis_client.ping()
        return redis_client
    except redis.ConnectionError:
        print("Cannot connect to Redis")

def get_interview_request(user_id: str):
    key = f"user:{user_id}"
    value = redis_client.get(key)
    if value:
        interview = json.loads(value)
        return interview


async def get_user_profile(identity: str):
    logger.info(f"getting profile for {identity}")
    url = f"http://localhost:8000/users/{identity}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                profile_data = await response.json()
                return profile_data
            else:
                raise Exception(
                    f"Failed to get weather data, status code: {response.status}"
                )


async def start_recording(roomName: str):
    req = api.RoomCompositeEgressRequest(
        room_name=roomName,
        layout="speaker",
        preset=api.EncodingOptionsPreset.H264_720P_30,
        audio_only=False,
        file_outputs=[
            api.EncodedFileOutput(
                filepath=f"{roomName}/recording.mp4",
                s3=api.S3Upload(
                    bucket="livekit-egress",
                    region="us-east-1",
                    access_key="Tq7xJeOwGqbYbzLdjH1Z",
                    secret="7AxrHdw6OTb4N7OneDMQYIHUU9gLVoTtvmWCHzUD",
                    endpoint="http://192.168.31.78:9000",
                    force_path_style=True,
                ),
            )
        ],
    )
    lkapi = api.LiveKitAPI(url="http://localhost:7880", api_key="API2CkexsWtNdB5", api_secret="35pzHzV9pNXOSzMyCJHniWKrnyfu1hKU8TBKCz7r0yU")
    await lkapi.egress.start_room_composite_egress(req)
    

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    # Initialize S3 client
    # s3_client = boto3.client('s3')

    logger.info(f"connecting to room {ctx.room.name}")

    room = ctx.room

    # here add room related subscription.

    
    await ctx.connect()

    # wait for the first participant to connect
    participant = await ctx.wait_for_participant()

    logger.info(f"starting voice assistant for participant {participant.identity}")

    # profile_data = await get_user_profile(participant.identity)

    # interview = get_interview_request(participant.identity)
    # logger.debug(interview)

    # await start_recording(ctx.room.name)


    # Embedding profile data into the initial context
    # profile_text = (
    #     f"The candidate's profile:\n"
    #     f"- Name: {profile_data.get('username', 'Unknown')}\n"
    #     f"- Bio: {profile_data['job_seeker_profile'].get('bio', 'No bio provided')}\n"
    #     f"- Skills: {', '.join(profile_data['job_seeker_profile'].get('skills', [])) if profile_data['job_seeker_profile'].get('skills') else 'No skills listed'}\n"
    #     f"- Work Experience: {profile_data['job_seeker_profile'].get('work_experience', 'No work experience listed')}\n"
    #     f"- Education: {profile_data['job_seeker_profile'].get('education', 'No education details listed')}\n"
    # )


    # initial_ctx = llm.ChatContext().append(
    #     role="system",
    #     text=(
    #         "You are an AI interviewer created by Yash Panchwatkar, specialized in software development interviews. "
    #         "Your task is to ask precise, relevant, and challenging questions on programming, system design, algorithms, "
    #         "and data structures based on the candidate's background and the interview topic and description and difficulty which is set below. Avoid providing unnecessary details and ensure your responses "
    #         "are concise and focused on assessing the candidate's skills effectively. So only ask questions.\n\n"
    #         f"{profile_text}\n"
    #         f"{interview}"
    #     ),
    # )



    initial_ctx = llm.ChatContext().append(
        role="system",
        text=(
            "You are an AI Assistant created by Yash Panchwatkar  your name is Axionic"
            "You should use short and concise responses, avoiding unpronounceable punctuation."
            "You are voice assistant you will be cheerful and very cooperative."
        ),
    )
 

    dg_model = "nova-2-general"
    if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
        # use a model optimized for telephony
        dg_model = "nova-2-phonecall"

    agent = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=openai.STT.with_groq(),
        llm=openai.LLM.with_groq(),
        tts=elevenlabs.TTS(base_url='http://localhost:8080', model='voice-en-us-ryan-medium'),
        chat_ctx=initial_ctx,
    )

    agent.start(ctx.room, participant)


    usage_collector = metrics.UsageCollector()

    @agent.on("metrics_collected")
    def _on_metrics_collected(mtrcs: metrics.AgentMetrics):
        metrics.log_metrics(mtrcs)
        usage_collector.collect(mtrcs)


    # listen to incoming chat messages, only required if you'd like the agent to
    # answer incoming messages from Chat
    chat = rtc.ChatManager(ctx.room)

    async def answer_from_text(txt: str):
        chat_ctx = agent.chat_ctx.copy()
        chat_ctx.append(role="user", text=txt)
        stream = agent.llm.chat(chat_ctx=chat_ctx)
        await agent.say(stream)

    @chat.on("message_received")
    def on_chat_received(msg: rtc.ChatMessage):
        if msg.message:
            asyncio.create_task(answer_from_text(msg.message))

    @agent.on("user_speech_committed")
    def on_user_speech_committed(msg: llm.ChatMessage):
        # convert string lists to strings, drop images
        logger.debug('user speech committed')
        if isinstance(msg.content, list):
            msg.content = "\n".join(
                "[image]" if isinstance(x, llm.ChatImage) else x for x in msg
            )
        log_queue.put_nowait(f"[{datetime.datetime.now()}] USER: {msg.content}\n")

    @agent.on("agent_speech_committed")
    def on_agent_speech_committed(msg: llm.ChatMessage):
        logger.info("agent_speech_committed")
        log_queue.put_nowait(f"[{datetime.datetime.now()}] AGENT: {msg.content}\n")

    log_queue = asyncio.Queue()

    async def upload_file_to_s3(
        file_path: str,
        object_key: str,
        endpoint_url: str,
        bucket_name: str,
        aws_access_key_id: str = None,
        aws_secret_access_key: str = None,
        region_name: str = "us-east-1"
    ):
        s3_client = boto3.resource(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name,
        )
        try:
            s3_client.Bucket(bucket_name).upload_file(file_path,object_key)
            s3_client.upload_file(Filename=file_path, Bucket=bucket_name, Key=object_key)
            
        except Exception as e:
            print(e)

    async def write_transcription(roomName: str):
        logger.info("writing to the file")

        async with aiofiles.open(f"{roomName}-transcriptions.log", "w") as f:
            while True:
                msg = await log_queue.get()
                if msg is None:
                    break
                await f.write(msg)
        
        # await upload_file_to_s3(file_path=f"{roomName}-transcriptions.log",
        #                   object_key=f"{roomName}/{roomName}-transcriptions.log",
        #                   bucket_name="livekit-egress",
        #                   endpoint_url="http://192.168.31.78:9000",
        #                   aws_access_key_id="Tq7xJeOwGqbYbzLdjH1Z",
        #                   aws_secret_access_key="7AxrHdw6OTb4N7OneDMQYIHUU9gLVoTtvmWCHzUD",
        #                   region_name="us-east-1"
        #                 )

        os.remove(f"{roomName}-transcriptions.log")

    write_task = asyncio.create_task(write_transcription(ctx.room.name))

    async def finish_queue():
        log_queue.put_nowait(None)
        # await write_task
        summary = usage_collector.get_summary()
        logger.info(f"Usage: ${summary}")



    ctx.add_shutdown_callback(finish_queue)

    # await agent.say(f"Hello {participant.identity}, welcome to the Axionic AI interview. This interview will consist of basic questions about your background and the high-level skills you listed in your application. Please ensure you minimize long pauses, as this may lead to the interview being cut off prematurely. Are you ready to start the interview?", allow_interruptions=False)
    await agent.say(f"Hello {participant.identity}, How can I help you?", allow_interruptions=False)

    source = rtc.VideoSource(WIDTH, HEIGHT)
    track = rtc.LocalVideoTrack.create_video_track("single-color", source)
    options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_CAMERA)
    
    publication = await room.local_participant.publish_track(track, options)
    logging.info("published track", extra={"track_sid": publication.sid})


    async def _draw_image():
        logo_path = "agents/leaderlogo.png"
        logo = Image.open(logo_path).convert("RGBA")
        logo_width = WIDTH // 2
        logo_height = HEIGHT // 2
        logo = logo.resize((logo_width, logo_height), Image.Resampling.LANCZOS)
        frame_image = Image.new("RGBA", (WIDTH, HEIGHT), (30, 30, 30, 255))
        x = (WIDTH - logo_width) // 2
        y = (HEIGHT - logo_height) // 2
        frame_image.paste(logo, (x, y), logo)
        argb_frame = bytearray(frame_image.tobytes())

        while True:
            await asyncio.sleep(0.1)
            frame = rtc.VideoFrame(WIDTH, HEIGHT, rtc.VideoBufferType.RGBA, argb_frame)
            source.capture_frame(frame)

    await _draw_image()

    



# """Set agent_name to enable explicit dispatch. When explicit dispatch is enabled, jobs will not be dispatched to rooms automatically. Instead, you can either specify the agent(s) to be dispatched in the end-user's token, or use the AgentDispatch.createDispatch API"""

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name="recrutingAgent",
            permissions=WorkerPermissions(
                can_publish = True,
                can_subscribe = True,
                can_publish_data = True,
                can_update_metadata = True,
                hidden= False
            ),
            worker_type=WorkerType.ROOM,
        ),
    )
