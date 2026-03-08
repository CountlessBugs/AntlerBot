# Search Memories - Mem0

Source: https://docs.mem0.ai/api-reference/memory/search-memories

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

query = "What do you know about me?"

filters = {

"OR" :[

{

"user_id" : "alex"

},

{

"agent_id" :{

"in" :[

"travel-assistant" ,

"customer-support"

]

}

}

]

}

client.search(query, version = "v2" , filters = filters)

200

[

{

"id" : "3c90c3cc-0d44-4b50-8888-8dd25736052a" ,

"memory" : "<string>" ,

"user_id" : "<string>" ,

"created_at" : "2023-11-07T05:31:56Z" ,

"updated_at" : "2023-11-07T05:31:56Z" ,

"metadata" : {},

"categories" : [

"<string>"

],

"immutable" : false ,

"expiration_date" : null

}

]

POST

/

v2

/

memories

/

search

Try it

Python

Python

# To use the Python SDK, install the package:

# pip install mem0ai

from mem0 import MemoryClient

client = MemoryClient( api_key = "your_api_key" , org_id = "your_org_id" , project_id = "your_project_id" )

query = "What do you know about me?"

filters = {

"OR" :[

{

"user_id" : "alex"

},

{

"agent_id" :{

"in" :[

"travel-assistant" ,

"customer-support"

]

}

}

]

}

client.search(query, version = "v2" , filters = filters)

200

[

{

"id" : "3c90c3cc-0d44-4b50-8888-8dd25736052a" ,

"memory" : "<string>" ,

"user_id" : "<string>" ,

"created_at" : "2023-11-07T05:31:56Z" ,

"updated_at" : "2023-11-07T05:31:56Z" ,

"metadata" : {},

"categories" : [

"<string>"

],

"immutable" : false ,

"expiration_date" : null

}

]

The v2 search API is powerful and flexible, allowing for more precise memory retrieval. It supports complex logical operations (AND, OR, NOT) and comparison operators for advanced filtering capabilities. The comparison operators include:

- in : Matches any of the values specified

- gte : Greater than or equal to

- lte : Less than or equal to

- gt : Greater than

- lt : Less than

- ne : Not equal to

- icontains : Case-insensitive containment check

- * : Wildcard character that matches everything

Platform API Example

Output

related_memories = client.search(

query = "What are Alice's hobbies?" ,

filters = {

"OR" : [

{

"user_id" : "alice"

},

{

"agent_id" : { "in" : [ "travel-agent" , "sports-agent" ]}

}

]

},

)

Wildcard Example

# Using wildcard to match all run_ids for a specific user

all_memories = client.search(

query = "What are Alice's hobbies?" ,

filters = {

"AND" : [

{

"user_id" : "alice"

},

{

"run_id" : "*"

}

]

},

)

Categories Filter Examples

# Example 1: Using 'contains' for partial matching

finance_memories = client.search(

query = "What are my financial goals?" ,

filters = {

"AND" : [

{ "user_id" : "alice" },

{

"categories" : {

"contains" : "finance"

}

}

]

},

)

# Example 2: Using 'in' for exact matching

personal_memories = client.search(

query = "What personal information do you have?" ,

filters = {

"AND" : [

{ "user_id" : "alice" },

{

"categories" : {

"in" : [ "personal_information" ]

}

}

]

},

)

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

query

string

required

The query to search for in the memory.

​

filters

Filters · object

required

A dictionary of filters to apply to the search. Available fields are: user_id, agent_id, app_id, run_id, created_at, updated_at, categories, keywords. Supports logical operators (AND, OR) and comparison operators (in, gte, lte, gt, lt, ne, contains, icontains). For categories field, use 'contains' for partial matching (e.g., {"categories": {"contains": "finance"}}) or 'in' for exact matching (e.g., {"categories": {"in": ["personal_information"]}}).

Show child attributes

​

version

string

default: v2

The version of the memory to use. This should always be v2.

​

top_k

integer

default: 10

The number of top results to return.

​

fields

string[]

A list of field names to include in the response. If not provided, all fields will be returned.

​

rerank

boolean

default: false

Whether to rerank the memories.

​

keyword_search

boolean

default: false

Whether to search for memories based on keywords.

​

filter_memories

boolean

default: false

Whether to filter the memories.

​

threshold

number

default: 0.3

The minimum similarity threshold for returned results.

​

org_id

string | null

The unique identifier of the organization associated with the memory.

​

project_id

string | null

The unique identifier of the project associated with the memory.

Response

200 - application/json

Successfully retrieved search results.

​

id

string<uuid>

required

Unique identifier for the memory.

​

memory

string

required

The content of the memory

​

user_id

string

required

The identifier of the user associated with this memory

​

created_at

string<date-time>

required

The timestamp when the memory was created.

​

updated_at

string<date-time>

required

The timestamp when the memory was last updated.

​

metadata

object

Additional metadata associated with the memory

​

categories

string[]

Categories associated with the memory

​

immutable

boolean

default: false

Whether the memory is immutable.

​

expiration_date

string<date-time> | null

The date and time when the memory will expire. Format: YYYY-MM-DD.

Yes No

Get Memories
