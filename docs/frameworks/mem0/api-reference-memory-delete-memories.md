# Delete Memories - Mem0

Source: https://docs.mem0.ai/api-reference/memory/delete-memories

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

# Delete all memories for a specific user

client.delete_all( user_id = "<user_id>" )

# Delete all memories for every user in the project (wildcard)

client.delete_all( user_id = "*" )

# Full project wipe — all four filters must be explicitly set to "*"

client.delete_all( user_id = "*" , agent_id = "*" , app_id = "*" , run_id = "*" )

# NOTE : Calling delete_all() with no filters raises a validation error.

# At least one filter is required to prevent accidental data loss.

204

{

"message" : "Memories deleted successfully!"

}

DELETE

/

v1

/

memories

Try it

Python

Python

# To use the Python SDK, install the package:

# pip install mem0ai

from mem0 import MemoryClient

client = MemoryClient( api_key = "your_api_key" , org_id = "your_org_id" , project_id = "your_project_id" )

# Delete all memories for a specific user

client.delete_all( user_id = "<user_id>" )

# Delete all memories for every user in the project (wildcard)

client.delete_all( user_id = "*" )

# Full project wipe — all four filters must be explicitly set to "*"

client.delete_all( user_id = "*" , agent_id = "*" , app_id = "*" , run_id = "*" )

# NOTE : Calling delete_all() with no filters raises a validation error.

# At least one filter is required to prevent accidental data loss.

204

{

"message" : "Memories deleted successfully!"

}

Authorizations

​

Authorization

string

header

required

API key authentication. Prefix your Mem0 API key with 'Token '. Example: 'Token your_api_key'

Query Parameters

​

user_id

string

Filter by user ID. Pass * to delete memories for all users.

​

agent_id

string

Filter by agent ID. Pass * to delete memories for all agents.

​

app_id

string

Filter by app ID. Pass * to delete memories for all apps.

​

run_id

string

Filter by run ID. Pass * to delete memories for all runs.

​

metadata

object

Filter memories by metadata (JSON string).

​

org_id

string

Filter memories by organization ID.

​

project_id

string

Filter memories by project ID.

Response

204 - application/json

Successful deletion of memories.

​

message

string

Example : "Memories deleted successfully!"

Yes No

Batch Delete Memories
