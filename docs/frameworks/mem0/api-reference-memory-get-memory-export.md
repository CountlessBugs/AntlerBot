# Get Memory Export - Mem0

Source: https://docs.mem0.ai/api-reference/memory/get-memory-export

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

client = MemoryClient( api_key = "your_api_key" , org_id = "your_org_id" , project_id = "project_id" )

memory_export_id = "<memory_export_id>"

response = client.get_memory_export( memory_export_id = memory_export_id)

print (response)

200

400

404

{}

POST

/

v1

/

exports

/

get

Try it

Python

Python

# To use the Python SDK, install the package:

# pip install mem0ai

from mem0 import MemoryClient

client = MemoryClient( api_key = "your_api_key" , org_id = "your_org_id" , project_id = "project_id" )

memory_export_id = "<memory_export_id>"

response = client.get_memory_export( memory_export_id = memory_export_id)

print (response)

200

400

404

{}

Retrieve the latest structured memory export after submitting an export job. You can filter the export by user_id , run_id , session_id , or app_id to get the most recent export matching your filters. Authorizations

​

Authorization

string

header

required

API key authentication. Prefix your Mem0 API key with 'Token '. Example: 'Token your_api_key'

Body

application/json

​

memory_export_id

string

The unique identifier of the memory export.

​

filters

object

Filters to apply while exporting memories. Available fields are: user_id, agent_id, app_id, run_id, created_at, updated_at.

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

200

application/json

Successful export.

Export data response in an object format.

Yes No

Memory History
