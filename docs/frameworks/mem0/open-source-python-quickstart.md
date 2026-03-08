# Python SDK Quickstart - Mem0

Source: https://docs.mem0.ai/open-source/python-quickstart

Overview

-

Python SDK Quickstart

-

Node SDK Quickstart

Self-Hosting Features

-

Overview

-

Graph Memory

-

Enhanced Metadata Filtering

-

Reranker-Enhanced Search

-

Async Memory

-

Multimodal Support

-

Custom Fact Extraction Prompt

-

Custom Update Memory Prompt

-

REST API Server

-

OpenAI Compatibility

Configuration

-

Configure the OSS Stack

- LLMs

- Vector Databases

- Embedding Models

- Rerankers

Community & Support

-

Development

-

Documentation

- Installation

- What’s Next?

- Additional Resources

Get started with Mem0’s Python SDK in under 5 minutes. This guide shows you how to install Mem0 and store your first memory.

​

Prerequisites

- Python 3.10 or higher

- OpenAI API key ( Get one here )

Set your OpenAI API key:

export OPENAI_API_KEY = "your-openai-api-key"

Uses OpenAI by default. Want to use Ollama, Anthropic, or local models? See Configuration .

​

Installation

1

Install via pip

pip install mem0ai

2

Initialize Memory

from mem0 import Memory

m = Memory()

3

Add a memory

messages = [

{ "role" : "user" , "content" : "Hi, I'm Alex. I love basketball and gaming." },

{ "role" : "assistant" , "content" : "Hey Alex! I'll remember your interests." }

]

m.add(messages, user_id = "alex" )

4

Search memories

results = m.search( "What do you know about me?" , filters = { "user_id" : "alex" })

print (results)

{

"results" : [

{

"id" : "mem_123abc" ,

"memory" : "Name is Alex. Enjoys basketball and gaming." ,

"user_id" : "alex" ,

"categories" : [ "personal_info" ],

"created_at" : "2025-10-22T04:40:22.864647-07:00" ,

"score" : 0.89

}

]

}

By default Memory() wires up:

- OpenAI gpt-4.1-nano-2025-04-14 for fact extraction and updates

- OpenAI text-embedding-3-small embeddings (1536 dimensions)

- Qdrant vector store with on-disk data at /tmp/qdrant

- SQLite history at ~/.mem0/history.db

- No reranker (add one in the config when you need it)

​

What’s Next?

Memory Operations

Learn how to search, update, and manage memories with full CRUD operations

Configuration

Customize Mem0 with different LLMs, vector stores, and embedders for production use

Advanced Features

Explore async support, graph memory, and multi-agent memory organization

​

Additional Resources

- OpenAI Compatibility - Use Mem0 with OpenAI-compatible chat completions

- Contributing Guide - Learn how to contribute to Mem0

- Examples - See Mem0 in action with Ollama and other integrations

Yes No

Overview
