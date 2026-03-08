# Mem0 MCP - Mem0

Source: https://docs.mem0.ai/platform/mem0-mcp

Overview

-

Mem0 MCP

-

Platform vs Open Source

-

Quickstart

Core Concepts

-

Memory Types

-

Add Memory

-

Search Memory

-

Update Memory

-

Delete Memory

Platform Features

-

Overview

- Essential Features

- Advanced Features

- Data Management

- Integration Features

Support & Troubleshooting

-

FAQs

Migration Guide

-

Migrate from Open Source to Platform

-

Migrating from v0.x to v1.0.0

-

Breaking Changes in v1.0.0

-

API Reference Changes

Contribute

-

Contribution Hub

- Deployment Options

- Available Tools

- Quickstart with Python (UVX)

- Quickstart with Docker

- Quickstart with Smithery (Hosted)

- Quick Recovery

- Next Steps

- Additional Resources

Prerequisites

- Mem0 Platform account ( Sign up here )

- API key ( Get one from dashboard )

- Python 3.10+, Docker, or Node.js 14+

- An MCP-compatible client (Claude Desktop, Cursor, or custom agent)

​

What is Mem0 MCP?

Mem0 MCP Server exposes Mem0’s memory capabilities as MCP tools, letting AI agents decide when to save, search, or update information.

​

Deployment Options

Choose from three deployment methods:

- Python Package (Recommended) - Install locally with uvx for instant setup

- Docker Container - Isolated deployment with HTTP endpoint

- Smithery - Remote hosted service for managed deployments

​

Available Tools

The MCP server exposes these memory tools to your AI client:

Tool Description add_memory Save text or conversation history for a user/agent search_memories Semantic search across existing memories with filters get_memories List memories with structured filters and pagination get_memory Retrieve one memory by its memory_id update_memory Overwrite a memory’s text after confirming the ID delete_memory Delete a single memory by memory_id delete_all_memories Bulk delete all memories in scope delete_entities Delete a user/agent/app/run entity and its memories list_entities Enumerate users/agents/apps/runs stored in Mem0

​

Quickstart with Python (UVX)

1

Install the MCP Server

uv pip install mem0-mcp-server

2

Configure your MCP client

{

"mcpServers" : {

"mem0" : {

"command" : "uvx" ,

"args" : [ "mem0-mcp-server" ],

"env" : {

"MEM0_API_KEY" : "m0-..." ,

"MEM0_DEFAULT_USER_ID" : "your-handle"

}

}

}

}

export MEM0_API_KEY = "m0-..."

export MEM0_DEFAULT_USER_ID = "your-handle"

3

Test with the Python agent

# Clone the mem0-mcp repository

git clone https://github.com/mem0ai/mem0-mcp.git

cd mem0-mcp

# Set your API keys

export MEM0_API_KEY = "m0-..."

export OPENAI_API_KEY = "sk-openai-..."

# Run the interactive agent

python example/pydantic_ai_repl.py

User: Remember that I love tiramisu

Agent: Got it! I've saved that you love tiramisu.

User: What do you know about my food preferences?

Agent: Based on your memories, you love tiramisu.

User: Update my project: the mobile app is now 80% complete

Agent: Updated your project status successfully.

4

Verify the setup

Your AI client can now:

- Automatically save information with add_memory

- Search memories with search_memories

- Update memories with update_memory

- Delete memories with delete_memory

If you get “Connection failed”, ensure your API key is valid and the server is running.

​

Quickstart with Docker

1

Build the Docker image

docker build -t mem0-mcp-server https://github.com/mem0ai/mem0-mcp.git

2

Run the container

docker run --rm -d \

--name mem0-mcp \

-e MEM0_API_KEY="m0-..." \

-p 8080:8081 \

mem0-mcp-server

3

Configure your client for HTTP

{

"mcpServers" : {

"mem0-docker" : {

"command" : "curl" ,

"args" : [ "-X" , "POST" , "http://localhost:8080/mcp" , "--data-binary" , "@-" ],

"env" : {

"MEM0_API_KEY" : "m0-..."

}

}

}

}

4

Verify the setup

# Check container logs

docker logs mem0-mcp

# Test HTTP endpoint

curl http://localhost:8080/health

The container should start successfully and respond to HTTP requests. If port 8080 is occupied, change it with -p 8081:8081 .

​

Quickstart with Smithery (Hosted)

For the simplest integration, use Smithery’s hosted Mem0 MCP server - no installation required.

Example: One-click setup in Cursor

- Visit smithery.ai/server/@mem0ai/mem0-memory-mcp and select Cursor as your client

- Open Cursor → Settings → MCP

- Click mem0-mcp → Initiate authorization

- Configure Smithery with your environment:

- MEM0_API_KEY : Your Mem0 API key

- MEM0_DEFAULT_USER_ID : Your user ID

- MEM0_ENABLE_GRAPH_DEFAULT : Optional, set to true for graph memories

- Return to Cursor settings and wait for tools to load

- Start chatting with Cursor and begin storing preferences

For other clients:

Visit smithery.ai/server/@mem0ai/mem0-memory-mcp to connect any MCP-compatible client with your Mem0 credentials.

​

Quick Recovery

- “uvx command not found” → Install with pip install uv or use pip install mem0-mcp-server instead. Make sure your Python environment has uv installed (or system-wide).

- “Connection refused” → Check that the server is running and the correct port is configured

- “Invalid API key” → Get a new key from Mem0 Dashboard

- “Permission denied” → Ensure Docker has access to bind ports (try with sudo on Linux)

​

Next Steps

MCP Integration Feature

Gemini 3 with Mem0 MCP

​

Additional Resources

- Mem0 MCP Repository - Source code and examples

- Platform Quickstart - Direct API integration guide

- MCP Specification - Learn about MCP protocol

Yes No

Overview
