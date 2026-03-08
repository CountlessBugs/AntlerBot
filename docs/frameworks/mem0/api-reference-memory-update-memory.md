# Update Memory - Mem0

Source: https://docs.mem0.ai/api-reference/memory/update-memory

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

# Update a memory

memory_id = "<memory_id>"

client.update(

memory_id = memory_id,

text = "Your updated memory message here" ,

metadata = { "category" : "example" }

)

200

{

"id" : "3c90c3cc-0d44-4b50-8888-8dd25736052a" ,

"text" : "<string>" ,

"user_id" : "<string>" ,

"agent_id" : "<string>" ,

"app_id" : "<string>" ,

"run_id" : "<string>" ,

"hash" : "<string>" ,

"metadata" : {},

"created_at" : "2023-11-07T05:31:56Z" ,

"updated_at" : "2023-11-07T05:31:56Z"

}

PUT

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

# Update a memory

memory_id = "<memory_id>"

client.update(

memory_id = memory_id,

text = "Your updated memory message here" ,

metadata = { "category" : "example" }

)

200

{

"id" : "3c90c3cc-0d44-4b50-8888-8dd25736052a" ,

"text" : "<string>" ,

"user_id" : "<string>" ,

"agent_id" : "<string>" ,

"app_id" : "<string>" ,

"run_id" : "<string>" ,

"hash" : "<string>" ,

"metadata" : {},

"created_at" : "2023-11-07T05:31:56Z" ,

"updated_at" : "2023-11-07T05:31:56Z"

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

Body

application/json

​

text

string

The updated text content of the memory

​

metadata

object

Additional metadata associated with the memory

Response

200 - application/json

Successfully updated memory.

​

id

string<uuid>

The unique identifier of the updated memory.

​

text

string

The updated text content of the memory

​

user_id

string | null

The user ID associated with the memory, if any

​

agent_id

string | null

The agent ID associated with the memory, if any

​

app_id

string | null

The app ID associated with the memory, if any

​

run_id

string | null

The run ID associated with the memory, if any

​

hash

string

Hash of the memory content

​

metadata

object

Additional metadata associated with the memory

​

created_at

string<date-time>

Timestamp of when the memory was created.

​

updated_at

string<date-time>

Timestamp of when the memory was last updated.

Yes No

Search Memories
