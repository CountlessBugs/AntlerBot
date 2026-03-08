# Batch Update Memories - Mem0

Source: https://docs.mem0.ai/api-reference/memory/batch-update

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

update_memories = [

{

"memory_id" : "285ed74b-6e05-4043-b16b-3abd5b533496" ,

"text" : "Watches football"

},

{

"memory_id" : "2c9bd859-d1b7-4d33-a6b8-94e0147c4f07" ,

"text" : "Likes to travel"

}

]

response = client.batch_update(update_memories)

print (response)

200

400

{

"message" : "Successfully updated 2 memories"

}

PUT

/

v1

/

batch

Try it

Python

Python

# To use the Python SDK, install the package:

# pip install mem0ai

from mem0 import MemoryClient

client = MemoryClient( api_key = "your_api_key" , org_id = "your_org_id" , project_id = "your_project_id" )

update_memories = [

{

"memory_id" : "285ed74b-6e05-4043-b16b-3abd5b533496" ,

"text" : "Watches football"

},

{

"memory_id" : "2c9bd859-d1b7-4d33-a6b8-94e0147c4f07" ,

"text" : "Likes to travel"

}

]

response = client.batch_update(update_memories)

print (response)

200

400

{

"message" : "Successfully updated 2 memories"

}

Authorizations

​

Authorization

string

header

required

API key authentication. Prefix your Mem0 API key with 'Token '. Example: 'Token your_api_key'

Body

application/json

​

memories

object[]

required

Maximum array length: 1000

Show child attributes

Response

200

application/json

Successfully updated memories

​

message

string

Example : "Successfully updated 2 memories"

Yes No

Get Memory Export
