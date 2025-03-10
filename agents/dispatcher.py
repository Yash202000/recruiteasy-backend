from livekit.api import (
  AccessToken,
  RoomAgentDispatch,
  RoomConfiguration,
  VideoGrants,
)

import asyncio
from livekit import api


room_name = "test_room"
agent_name = "recrutingAgent"

# def create_token_with_agent_dispatch() -> str:
#     token = (
#         AccessToken()
#         .with_identity("yash")
#         .with_grants(VideoGrants(room_join=True, room=room_name))
#         .with_room_config(
#             RoomConfiguration(
#                 agents=[
#                     RoomAgentDispatch(agent_name=agent_name)
#                 ],
#             ),
#         )
#         .to_jwt()
#     )
#     return token

# print(create_token_with_agent_dispatch())

async def create_explicit_dispatch():
    lkapi = api.LiveKitAPI()
    dispatch = await lkapi.agent_dispatch.create_dispatch(
        api.CreateAgentDispatchRequest(
            agent_name=agent_name, room=room_name, metadata="my_job_metadata"
        )
    )
    print("created dispatch", dispatch)

    dispatches = await lkapi.agent_dispatch.list_dispatch(room_name=room_name)
    print(f"there are {len(dispatches)} dispatches in {room_name}")
    await lkapi.aclose()

asyncio.run(create_explicit_dispatch())
