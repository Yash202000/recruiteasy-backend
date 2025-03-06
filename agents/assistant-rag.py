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
    cli,
    llm,
    metrics,
)
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import openai, silero, rag
import elevenlabs
import boto3
import aiofiles
import redis
import pickle


embeddings_dimension = 2048
annoy_index = rag.annoy.AnnoyIndex.load("vdb_data")  # see build_data.py
with open("my_data.pkl", "rb") as f:
    paragraphs_by_uuid = pickle.load(f)

# Redis connection
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)


load_dotenv()
logger = logging.getLogger("AI-Interview-assistant")


# Set the video frame dimensions
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

    async def _enrich_with_rag(agent: VoicePipelineAgent, chat_ctx: llm.ChatContext):
        # locate the last user message and use it to query the RAG model
        # to get the most relevant paragraph
        # then provide that as additional context to the LLM
        user_msg = chat_ctx.messages[-1]
        user_embedding = await openai.create_embeddings(
            input=user_msg.content,
            model="bert-embeddings",
            dimensions=embeddings_dimension,
        )

        result = annoy_index.query(user_embedding[0].embedding, n=1)[0]
        paragraph = paragraphs_by_uuid[result.userdata]
        if paragraph:
            logger.info(f"enriching with RAG: {paragraph}")
            rag_msg = llm.ChatMessage.create(
                text="Context:\n" + paragraph,
                role="assistant",
            )
            # replace last message with RAG, and append user message at the end
            chat_ctx.messages[-1] = rag_msg
            chat_ctx.messages.append(user_msg)

    # Initialize S3 client
    # s3_client = boto3.client('s3')

    logger.info(f"connecting to room {ctx.room.name}")

    room = ctx.room

    # here add room related subscription.

    
    await ctx.connect()

    # wait for the first participant to connect
    participant = await ctx.wait_for_participant()

    logger.info(f"starting voice assistant for participant {participant.identity}")

    profile_data = await get_user_profile(participant.identity)

    interview = get_interview_request(participant.identity)
    logger.debug(interview)

    # await start_recording(ctx.room.name)

    # Embedding profile data into the initial context
    profile_text = (
        f"The candidate's profile:\n"
        f"- Name: {profile_data.get('username', 'Unknown')}\n"
        f"- Bio: {profile_data['job_seeker_profile'].get('bio', 'No bio provided')}\n"
        f"- Skills: {', '.join(profile_data['job_seeker_profile'].get('skills', [])) if profile_data['job_seeker_profile'].get('skills') else 'No skills listed'}\n"
        f"- Work Experience: {profile_data['job_seeker_profile'].get('work_experience', 'No work experience listed')}\n"
        f"- Education: {profile_data['job_seeker_profile'].get('education', 'No education details listed')}\n"
    )



    initial_ctx = llm.ChatContext().append(
        role="system",
        text=(
            "You are an AI interviewer created by Yash Panchwatkar,  Your interface with users will be voice. "
            "You should use short and concise responses, and avoiding usage of unpronouncable punctuation."
            "Use the provided context to answer the user's question if needed."
           
        ),
    )


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
    

    dg_model = "nova-2-general"
    if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
        # use a model optimized for telephony
        dg_model = "nova-2-phonecall"

    agent = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=openai.LLM.with_groq(),
        # stt=openai.STT(base_url='http://localhost:8080', model='whisper'),
        llm=openai.LLM.with_groq(),
        tts=elevenlabs.TTS(base_url='http://localhost:8080', model='voice-en-us-ryan-medium'),
        chat_ctx=initial_ctx,
        before_llm_cb=_enrich_with_rag,
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
        """
        Uploads a file to S3 with optional access and secret keys.
        
        Args:
            file_path (str): Local path of the file to upload.
            bucket_name (str): Name of the S3 bucket.
            object_key (str): Key (path) in the S3 bucket.
            aws_access_key_id (str, optional): AWS access key ID.
            aws_secret_access_key (str, optional): AWS secret access key.
            aws_session_token (str, optional): AWS session token for temporary credentials.
            region_name (str, optional): AWS region (default is 'us-east-1').
        """
        # Create S3 client with custom credentials if provided
        
        s3_client = boto3.resource(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name,
        )
        
        try:
            s3_client.Bucket(bucket_name).upload_file(file_path,object_key)
            
            # s3_client.upload_file(Filename=file_path, Bucket=bucket_name, Key=object_key)
            
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
        await write_task
        summary = usage_collector.get_summary()
        logger.info(f"Usage: ${summary}")



    ctx.add_shutdown_callback(finish_queue)

    await agent.say(f"Hello {profile_data['username']}, I am your jarvis ask me anything and will try to help you.", allow_interruptions=False)


    source = rtc.VideoSource(WIDTH, HEIGHT)
    track = rtc.LocalVideoTrack.create_video_track("single-color", source)
    options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_CAMERA)
    publication = await room.local_participant.publish_track(track, options)
    logging.info("published track", extra={"track_sid": publication.sid})


    async def _draw_image():
        # Load the logo or image
        logo_path = "leaderlogo.png"
        logo = Image.open(logo_path).convert("RGBA")  # Ensure image is in RGBA format

        # Calculate the size for the logo (e.g., half the width and height of the frame)
        logo_width = WIDTH // 2
        logo_height = HEIGHT // 2
        logo = logo.resize((logo_width, logo_height), Image.Resampling.LANCZOS)

        # Create a blank RGBA canvas for the frame
        frame_image = Image.new("RGBA", (WIDTH, HEIGHT), (30, 30, 30, 255))  # Gray background

        # Calculate position to center the logo
        x = (WIDTH - logo_width) // 2
        y = (HEIGHT - logo_height) // 2

        # Paste the logo onto the center of the frame
        frame_image.paste(logo, (x, y), logo)  # Use the logo as its own mask for transparency

        # Convert the frame image to raw bytes
        argb_frame = bytearray(frame_image.tobytes())

        while True:
            await asyncio.sleep(0.1)  # 100ms

            # Create a video frame with the logo/image
            frame = rtc.VideoFrame(WIDTH, HEIGHT, rtc.VideoBufferType.RGBA, argb_frame)
            source.capture_frame(frame)

    await _draw_image()

    




if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            # agent_name="aiagent"  # """Set agent_name to enable explicit dispatch. When explicit dispatch is enabled, jobs will not be dispatched to rooms automatically. Instead, you can either specify the agent(s) to be dispatched in the end-user's token, or use the AgentDispatch.createDispatch API"""
        ),
    )
