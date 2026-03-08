# Delete Memory - Mem0

Source: https://docs.mem0.ai/api-reference/memory/delete-memory

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

memory_id = "<memory_id>"

client.delete( memory_id = memory_id)

204

{

"message" : "Memory deleted successfully!"

}

DELETE

/

v1

/

memories

/

{memory_id}

Try it

Python

Python

# To use the Python SDK, install the package:

# pip install mem0ai

from mem0 import MemoryClient

client = MemoryClient( api_key = "your_api_key" , org_id = "your_org_id" , project_id = "your_project_id" )

memory_id = "<memory_id>"

client.delete( memory_id = memory_id)

204

{

"message" : "Memory deleted successfully!"

}

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

204 - application/json

Successful deletion of memory.

​

message

string

Example : "Memory deleted successfully!"

Yes No

Update Memory
