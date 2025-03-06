# ospf_meet

uvicorn main:app --reload --port 8000


## signup api: user able to signup with email, username, password
## signin api: user able to signin with email, password then the authentication token will be genrated from this.
## user list api: application will able to list users
## user by id api: get user details from id
## create room api: will create room from selecting participants and add entries in userroom table as room and user are many to many

## https://github.com/livekit/python-sdks use this high priority.