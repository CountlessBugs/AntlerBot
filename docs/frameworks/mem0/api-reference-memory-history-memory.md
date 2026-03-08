# Memory History - Mem0

Source: https://docs.mem0.ai/api-reference/memory/history-memory

Overview

-

Organizations & Projects

Core Memory Operations

- POST

Add Memories

- POST

Get Memories

- POST

Search Memories

- PUT

Update Memory

- DEL

Delete Memory

Memory APIs

- POST

Create Memory Export

- POST

Feedback

- GET

Get Memory

- GET

Memory History

- POST

Get Memory Export

- PUT

Batch Update Memories

- DEL

Batch Delete Memories

- DEL

Delete Memories

Events APIs

- GET

Get Events

- GET

Get Event

Entities APIs

- GET

Get Users

- DEL

Delete User

Organizations APIs

- POST

Create Organization

- GET

Get Organizations

- GET

Get Organization

- GET

Get Members

- POST

Add Member

- DEL

Delete Organization

Project APIs

- POST

Create Project

- GET

Get Projects

- GET

Get Project

- GET

Get Members

- POST

Add Member

- DEL

Delete Project

Webhook APIs

- POST

Create Webhook

- GET

Get Webhook

- PUT

Update Webhook

- DEL

Delete Webhook

Python

Python

# To use the Python SDK, install the package:

# pip install mem0ai

from mem0 import MemoryClient

client = MemoryClient( api_key = "your_api_key" , org_id = "your_org_id" , project_id = "your_project_id" )

# Add some message to create history

messages = [{ "role" : "user" , "content" : "<user-message>" }]

client.add(messages, user_id = "<user-id>" )

# Add second message to update history

messages.append({ "role" : "user" , "content" : "<user-message>" })

client.add(messages, user_id = "<user-id>" )

# Get history of how memory changed over time

memory_id = "<memory-id-here>"

history = client.history(memory_id)

200

[

{

"id" : "3c90c3cc-0d44-4b50-8888-8dd25736052a" ,

"memory_id" : "3c90c3cc-0d44-4b50-8888-8dd25736052a" ,

"input" : [

{

"role" : "user" ,

"content" : "<string>"

}

],

"new_memory" : "<string>" ,

"user_id" : "<string>" ,

"event" : "ADD" ,

"created_at" : "2023-11-07T05:31:56Z" ,

"updated_at" : "2023-11-07T05:31:56Z" ,

"old_memory" : "<string>" ,

"metadata" : {}

}

]

GET

/

v1

/

memories

/

{memory_id}

/

history

Try it

Python

Python

# To use the Python SDK, install the package:

# pip install mem0ai

from mem0 import MemoryClient

client = MemoryClient( api_key = "your_api_key" , org_id = "your_org_id" , project_id = "your_project_id" )

# Add some message to create history

messages = [{ "role" : "user" , "content" : "<user-message>" }]

client.add(messages, user_id = "<user-id>" )

# Add second message to update history

messages.append({ "role" : "user" , "content" : "<user-message>" })

client.add(messages, user_id = "<user-id>" )

# Get history of how memory changed over time

memory_id = "<memory-id-here>"

history = client.history(memory_id)

200

[

{

"id" : "3c90c3cc-0d44-4b50-8888-8dd25736052a" ,

"memory_id" : "3c90c3cc-0d44-4b50-8888-8dd25736052a" ,

"input" : [

{

"role" : "user" ,

"content" : "<string>"

}

],

"new_memory" : "<string>" ,

"user_id" : "<string>" ,

"event" : "ADD" ,

"created_at" : "2023-11-07T05:31:56Z" ,

"updated_at" : "2023-11-07T05:31:56Z" ,

"old_memory" : "<string>" ,

"metadata" : {}

}

]

Authorizations

​

Authorization

string

header

required

API key authentication. Prefix your Mem0 API key with 'Token '. Example: 'Token your_api_key'

Path Parameters

​

memory_id

string<uuid>

required

The unique identifier of the memory to retrieve.

Response

200 - application/json

Successfully retrieved the memory history.

​

id

string<uuid>

required

Unique identifier for the history entry.

​

memory_id

string<uuid>

required

Unique identifier of the associated memory.

​

input

object[]

required

The conversation input that led to this memory change

Show child attributes

​

new_memory

string

required

The new or updated state of the memory

​

user_id

string

required

The identifier of the user associated with this memory

​

event

enum<string>

required

The type of event that occurred

Available options : ADD ,

UPDATE ,

DELETE

​

created_at

string<date-time>

required

The timestamp when this history entry was created.

​

updated_at

string<date-time>

required

The timestamp when this history entry was last updated.

​

old_memory

string | null

The previous state of the memory, if applicable

​

metadata

object

Additional metadata associated with the memory change

Yes No

Get Memory
