# Feedback - Mem0

Source: https://docs.mem0.ai/api-reference/memory/feedback

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

client = MemoryClient( api_key = "your_api_key" )

# Submit feedback for a memory

feedback = client.feedback( memory_id = "memory_id" , feedback = "POSITIVE" )

print (feedback)

200

{

"id" : "3c90c3cc-0d44-4b50-8888-8dd25736052a" ,

"feedback" : "POSITIVE" ,

"feedback_reason" : "<string>"

}

POST

/

v1

/

feedback

Try it

Python

Python

# To use the Python SDK, install the package:

# pip install mem0ai

from mem0 import MemoryClient

client = MemoryClient( api_key = "your_api_key" )

# Submit feedback for a memory

feedback = client.feedback( memory_id = "memory_id" , feedback = "POSITIVE" )

print (feedback)

200

{

"id" : "3c90c3cc-0d44-4b50-8888-8dd25736052a" ,

"feedback" : "POSITIVE" ,

"feedback_reason" : "<string>"

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

memory_id

string

required

ID of the memory to provide feedback for

​

feedback

enum<string> | null

Type of feedback

Available options : POSITIVE ,

NEGATIVE ,

VERY_NEGATIVE

​

feedback_reason

string | null

Reason for the feedback

Response

200

application/json

Successful operation.

​

id

string<uuid>

Feedback ID

​

feedback

enum<string> | null

Type of feedback

Available options : POSITIVE ,

NEGATIVE ,

VERY_NEGATIVE

​

feedback_reason

string | null

Reason for the feedback

Yes No

Create Memory Export
