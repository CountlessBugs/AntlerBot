# Create Memory Export - Mem0

Source: https://docs.mem0.ai/api-reference/memory/create-memory-export

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

json_schema = {pydantic_json_schema}

filters = {

"AND" : [

{ "user_id" : "alex" }

]

}

response = client.create_memory_export(

schema = json_schema,

filters = filters

)

print (response)

201

400

{

"message" : "Memory export request received. The export will be ready in a few seconds." ,

"id" : "550e8400-e29b-41d4-a716-446655440000"

}

POST

/

v1

/

exports

Try it

Python

Python

# To use the Python SDK, install the package:

# pip install mem0ai

from mem0 import MemoryClient

client = MemoryClient( api_key = "your_api_key" , org_id = "your_org_id" , project_id = "your_project_id" )

json_schema = {pydantic_json_schema}

filters = {

"AND" : [

{ "user_id" : "alex" }

]

}

response = client.create_memory_export(

schema = json_schema,

filters = filters

)

print (response)

201

400

{

"message" : "Memory export request received. The export will be ready in a few seconds." ,

"id" : "550e8400-e29b-41d4-a716-446655440000"

}

Submit a job to create a structured export of memories using a customizable Pydantic schema. This process may take some time to complete, especially if you’re exporting a large number of memories. You can tailor the export by applying various filters (e.g., user_id , agent_id , run_id , or session_id ) and by modifying the Pydantic schema to ensure the final data matches your exact needs. Authorizations

​

Authorization

string

header

required

API key authentication. Prefix your Mem0 API key with 'Token '. Example: 'Token your_api_key'

Body

application/json

​

schema

object

required

Schema definition for the export

​

filters

object

Filters to apply while exporting memories. Available fields are: user_id, agent_id, app_id, run_id.

Show child attributes

​

org_id

string

Filter exports by organization ID.

​

project_id

string

Filter exports by project ID.

Response

201

application/json

Export created successfully.

​

message

string

required

Example : "Memory export request received. The export will be ready in a few seconds."

​

id

string<uuid>

required

Example : "550e8400-e29b-41d4-a716-446655440000"

Yes No

Delete Memory
