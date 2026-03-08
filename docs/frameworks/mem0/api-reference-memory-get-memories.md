# Get Memories - Mem0

Source: https://docs.mem0.ai/api-reference/memory/get-memories

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

# Retrieve memories with filters

memories = client.get_all(

filters = {

"AND" : [

{

"user_id" : "alex"

},

{

"created_at" : {

"gte" : "2024-07-01" ,

"lte" : "2024-07-31"

}

}

]

},

version = "v2"

)

print (memories)

200

400

[

{

"id" : "<string>" ,

"memory" : "<string>" ,

"created_at" : "2023-11-07T05:31:56Z" ,

"updated_at" : "2023-11-07T05:31:56Z" ,

"owner" : "<string>" ,

"organization" : "<string>" ,

"immutable" : false ,

"expiration_date" : null ,

"metadata" : {}

}

]

POST

/

v2

/

memories

Try it

Python

Python

# To use the Python SDK, install the package:

# pip install mem0ai

from mem0 import MemoryClient

client = MemoryClient( api_key = "your_api_key" , org_id = "your_org_id" , project_id = "your_project_id" )

# Retrieve memories with filters

memories = client.get_all(

filters = {

"AND" : [

{

"user_id" : "alex"

},

{

"created_at" : {

"gte" : "2024-07-01" ,

"lte" : "2024-07-31"

}

}

]

},

version = "v2"

)

print (memories)

200

400

[

{

"id" : "<string>" ,

"memory" : "<string>" ,

"created_at" : "2023-11-07T05:31:56Z" ,

"updated_at" : "2023-11-07T05:31:56Z" ,

"owner" : "<string>" ,

"organization" : "<string>" ,

"immutable" : false ,

"expiration_date" : null ,

"metadata" : {}

}

]

The v2 get memories API is powerful and flexible, allowing for more precise memory listing without the need for a search query. It supports complex logical operations (AND, OR, NOT) and comparison operators for advanced filtering capabilities. The comparison operators include:

- in : Matches any of the values specified

- gte : Greater than or equal to

- lte : Less than or equal to

- gt : Greater than

- lt : Less than

- ne : Not equal to

- icontains : Case-insensitive containment check

- * : Wildcard character that matches everything

Code

Output

memories = client.get_all(

filters = {

"AND" : [

{

"user_id" : "alex"

},

{

"created_at" : { "gte" : "2024-07-01" , "lte" : "2024-07-31" }

}

]

}

)

​

Graph Memory

To retrieve graph memory relationships between entities, pass output_format="v1.1" in your request. This will return memories with entity and relationship information from the knowledge graph.

Code

Output

memories = client.get_all(

filters = {

"user_id" : "alex"

},

output_format = "v1.1"

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

filters

Filters · object

required

A dictionary of filters to apply to retrieve memories. Available fields are: user_id, agent_id, app_id, run_id, created_at, updated_at, categories, keywords. Supports logical operators (AND, OR) and comparison operators (in, gte, lte, gt, lt, ne, contains, icontains, *). For categories field, use 'contains' for partial matching (e.g., {"categories": {"contains": "finance"}}) or 'in' for exact matching (e.g., {"categories": {"in": ["personal_information"]}}).

Show child attributes

​

fields

string[]

A list of field names to include in the response. If not provided, all fields will be returned.

​

page

integer

default: 1

Page number for pagination. Default: 1

​

page_size

integer

default: 100

Number of items per page. Default: 100

​

org_id

string | null

The unique identifier of the organization associated with the memory.

​

project_id

string | null

The unique identifier of the project associated with the memory.

Response

200

application/json

Successfully retrieved memories.

​

id

string

required

​

memory

string

required

​

created_at

string<date-time>

required

​

updated_at

string<date-time>

required

​

owner

string

required

​

organization

string

required

​

immutable

boolean

default: false

Whether the memory is immutable.

​

expiration_date

string<date-time> | null

The date and time when the memory will expire. Format: YYYY-MM-DD.

​

metadata

object

Yes No

Add Memories
