# Add Memories - Mem0

Source: https://docs.mem0.ai/api-reference/memory/add-memories

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

client = MemoryClient(api_key="your_api_key", org_id="your_org_id", project_id="your_project_id")

messages = [

{"role": "user", "content": "<user-message>"},

{"role": "assistant", "content": "<assistant-response>"}

]

client.add(messages, user_id="<user-id>", version="v2")

200

400

[

{

"id": "<string>",

"data": {

"memory": "<string>"

},

"event": "ADD"

}

]

POST

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

client = MemoryClient(api_key="your_api_key", org_id="your_org_id", project_id="your_project_id")

messages = [

{"role": "user", "content": "<user-message>"},

{"role": "assistant", "content": "<assistant-response>"}

]

client.add(messages, user_id="<user-id>", version="v2")

200

400

[

{

"id": "<string>",

"data": {

"memory": "<string>"

},

"event": "ADD"

}

]

Add new facts, messages, or metadata to a user’s memory store. The Add Memories endpoint accepts either raw text or conversational turns and commits them asynchronously so the memory is ready for later search, retrieval, and graph queries.

​

Endpoint

- Method : POST

- URL : /v1/memories/

- Content-Type : application/json

Memories are processed asynchronously by default. The response contains queued events you can track while the platform finalizes enrichment.

​

Required headers

Header Required Description Authorization: Token <MEM0_API_KEY> Yes API key scoped to your workspace. Accept: application/json Yes Ensures a JSON response.

​

Request body

Provide at least one message or direct memory string. Most callers supply messages so Mem0 can infer structured memories as part of ingestion.

Basic request

{

"user_id" : "alice" ,

"messages" : [

{ "role" : "user" , "content" : "I moved to Austin last month." }

],

"metadata" : {

"source" : "onboarding_form"

}

}

​

Common fields

Field Type Required Description user_id string No* Associates the memory with a user. Provide when you want the memory scoped to a specific identity. messages array No* Conversation turns for Mem0 to infer memories from. Each object should include role and content . metadata object Optional Custom key/value metadata (e.g., {"topic": "preferences"} ). infer boolean (default true ) Optional Set to false to skip inference and store the provided text as-is. async_mode boolean (default true ) Optional Controls asynchronous processing. Most clients leave this enabled. output_format string (default v1.1 ) Optional Response format. v1.1 wraps results in a results array.

* Provide at least one messages entry to describe what you are storing. For scoped memories, include user_id . You can also attach agent_id , app_id , run_id , project_id , or org_id to refine ownership.

​

Response

Successful requests return an array of events queued for processing. Each event includes the generated memory text and an identifier you can persist for auditing.

200 response

400 response

[

{

"id" : "mem_01JF8ZS4Y0R0SPM13R5R6H32CJ" ,

"event" : "ADD" ,

"data" : {

"memory" : "The user moved to Austin in 2025."

}

}

]

​

Graph relationships

Add Memories can enrich the knowledge graph on write. Set enable_graph: true to create entity nodes and relationships for the stored memory. Use this when you want downstream get_all or search calls to traverse connected entities.

Graph-aware request

{

"user_id" : "alice" ,

"messages" : [

{ "role" : "user" , "content" : "I met with Dr. Lee at General Hospital." }

],

"enable_graph" : true

}

The response follows the same format, and related entities become available in Graph Memory queries. Authorizations

​

Authorization

string

header

required

API key authentication. Prefix your Mem0 API key with 'Token '. Example: 'Token your_api_key'

Body

application/json

​

messages

object[]

An array of message objects representing the content of the memory. Each message object typically contains 'role' and 'content' fields, where 'role' indicates the sender either 'user' or 'assistant' and 'content' contains the actual message text. This structure allows for the representation of conversations or multi-part memories.

Show child attributes

​

agent_id

string | null

The unique identifier of the agent associated with this memory.

​

user_id

string | null

The unique identifier of the user associated with this memory.

​

app_id

string | null

The unique identifier of the application associated with this memory.

​

run_id

string | null

The unique identifier of the run associated with this memory.

​

metadata

Metadata · object

Additional metadata associated with the memory, which can be used to store any additional information or context about the memory. Best practice for incorporating additional information is through metadata (e.g. location, time, ids, etc.). During retrieval, you can either use these metadata alongside the query to fetch relevant memories or retrieve memories based on the query first and then refine the results using metadata during post-processing.

​

includes

string | null

String to include the specific preferences in the memory.

Minimum string length: 1

​

excludes

string | null

String to exclude the specific preferences in the memory.

Minimum string length: 1

​

infer

boolean

default: true

Whether to infer the memories or directly store the messages.

​

output_format

string | null

default: v1.1

Controls the response format structure. v1.0 (deprecated) returns a direct array of memory objects: [{...}, {...}] . v1.1 (recommended) returns an object with a 'results' key containing the array: {"results": [...]} . The v1.0 format will be removed in future versions.

​

custom_categories

Custom categories · object

A list of categories with category name and its description.

​

custom_instructions

string | null

Defines project-specific guidelines for handling and organizing memories. When set at the project level, they apply to all new memories in that project.

​

immutable

boolean

default: false

Whether the memory is immutable.

​

async_mode

boolean

default: true

Whether to add the memory completely asynchronously.

​

timestamp

integer | null

The timestamp of the memory. Format: Unix timestamp

​

expiration_date

string | null

The date and time when the memory will expire. Format: YYYY-MM-DD

​

org_id

string | null

The unique identifier of the organization associated with this memory.

​

project_id

string | null

The unique identifier of the project associated with this memory.

​

version

string | null

The version of the memory to use. The default version is v1, which is deprecated. We recommend using v2 for new applications.

Response

200

application/json

Successful memory creation.

​

id

string

required

​

data

object

required

Show child attributes

​

event

enum<string>

required

Available options : ADD ,

UPDATE ,

DELETE

Yes No

Organizations & Projects
