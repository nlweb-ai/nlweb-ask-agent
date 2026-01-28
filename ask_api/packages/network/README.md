# NLWeb Network

Network interfaces and server for NLWeb - provides HTTP, MCP, and A2A protocol adapters.

## Overview

`nlweb-network` provides transport layer adapters that convert protocol-specific requests into a common format for NLWeb handlers, and convert NLWeb outputs back into the appropriate protocol format.

## Architecture

```
┌──────────────────────────────────────────────┐
│           Protocol Adapters                   │
│  (HTTP SSE, HTTP JSON, MCP SSE, MCP HTTP)    │
└──────────────────┬───────────────────────────┘
                   │
                   ↓
         ┌─────────────────┐
         │  NLWeb Handlers │
         │  (Core Package) │
         └─────────────────┘
```

## Supported Protocols

### HTTP Interfaces

#### HTTP with Server-Sent Events (Default)
- **Endpoint**: `/ask` (GET/POST)
- **Parameter**: `streaming=true` (default)
- **Use case**: Real-time streaming of results as they're generated

```bash
curl "http://localhost:8080/ask?query=best+pasta+recipe"
```

#### HTTP with JSON Response
- **Endpoint**: `/ask` (GET/POST)
- **Parameter**: `streaming=false`
- **Use case**: Get complete results in single JSON response

```bash
curl "http://localhost:8080/ask?query=best+pasta+recipe&streaming=false"
```

### MCP (Model Context Protocol) Interfaces

#### MCP over HTTP (StreamableHTTP)
- **Endpoint**: `/mcp` (POST)
- **Format**: JSON-RPC 2.0
- **Use case**: Standard MCP integration for tools/agents

```bash
# Test with MCP Inspector
npx @modelcontextprotocol/inspector http://localhost:8080/mcp
```

#### MCP over Server-Sent Events
- **Endpoint**: `/mcp-sse` (GET/POST)
- **Format**: JSON-RPC 2.0 over SSE
- **Use case**: Streaming MCP responses in real-time

### A2A (Agent-to-Agent) Interfaces
*(Coming soon)*

## Installation

```bash
# Install from PyPI (when published)
pip install nlweb-network

# Or install from source
pip install -e packages/network
```

## Usage

### Starting the Server

```python
from nlweb_network.server import main

# Start server with default configuration
main()
```

Or use the command-line entry point:

```bash
nlweb-server
```

### Using Interface Adapters

You can use the interface adapters directly in your own applications:

```python
from aiohttp import web
from nlweb_network.interfaces import HTTPJSONInterface, HTTPSSEInterface
from nlweb_core.handler import NLWebHandler

# For non-streaming JSON responses
async def my_handler(request):
    interface = HTTPJSONInterface()
    return await interface.handle_request(request, NLWebHandler)

# For streaming SSE responses
async def my_streaming_handler(request):
    interface = HTTPSSEInterface()
    return await interface.handle_request(request, NLWebHandler)
```

## Interface Adapters

All interface adapters inherit from `BaseInterface` and implement:

- `parse_request()` - Extract query parameters from protocol-specific request
- `send_response()` - Send data in protocol-specific format
- `finalize_response()` - Close/finalize the response stream
- `handle_request()` - Complete request/response cycle

### Available Interfaces

| Interface | Class | Protocol | Streaming |
|-----------|-------|----------|-----------|
| HTTP JSON | `HTTPJSONInterface` | HTTP | No |
| HTTP SSE | `HTTPSSEInterface` | HTTP + SSE | Yes |
| MCP StreamableHTTP | `MCPStreamableInterface` | JSON-RPC 2.0 | No |
| MCP SSE | `MCPSSEInterface` | JSON-RPC 2.0 + SSE | Yes |

## Configuration

The server uses configuration from `nlweb-core`:

```yaml
# config.yaml
server:
  host: localhost
  port: 8080
  enable_cors: true
```

## Endpoints

### `/ask` - HTTP Query Endpoint

**GET/POST** - Natural language query with NLWeb RAG pipeline

**Parameters:**
- `query` (required) - Natural language query
- `site` (optional) - Filter by site (default: "all")
- `num_results` (optional) - Number of results (default: 50)
- `streaming` (optional) - Enable SSE streaming (default: true)

**Examples:**

```bash
# Streaming (SSE)
curl "http://localhost:8080/ask?query=spicy+snacks&site=seriouseats"

# Non-streaming (JSON)
curl "http://localhost:8080/ask?query=spicy+snacks&streaming=false"

# POST with JSON body
curl -X POST http://localhost:8080/ask \
     -H 'Content-Type: application/json' \
     -d '{"query": "spicy snacks", "streaming": false}'
```

### `/mcp` - MCP Protocol Endpoint

**POST** - JSON-RPC 2.0 requests for MCP protocol

**Methods:**
- `initialize` - Protocol handshake
- `tools/list` - List available tools
- `tools/call` - Execute tool (routes to NLWeb handlers)

**Example:**

```bash
curl -X POST http://localhost:8080/mcp \
     -H 'Content-Type: application/json' \
     -d '{
       "jsonrpc": "2.0",
       "id": 1,
       "method": "tools/call",
       "params": {
         "name": "ask",
         "arguments": {"query": "best pasta recipe"}
       }
     }'
```

### `/mcp-sse` - MCP with SSE Streaming

**GET/POST** - MCP protocol with Server-Sent Events

Same as `/mcp` but streams results via SSE for `tools/call`.

### `/health` - Health Check

**GET** - Simple health check

```bash
curl http://localhost:8080/health
# {"status": "ok"}
```

## Dependencies

- `nlweb-core>=0.5.0` - Core NLWeb handlers and business logic
- `aiohttp>=3.8.0` - Async HTTP server
- `aiohttp-cors>=0.7.0` - CORS support

## Development

```bash
# Install in editable mode with dev dependencies
pip install -e "packages/network[dev]"

# Run tests
pytest packages/network/tests
```

## License

MIT License - Copyright (c) 2025 Microsoft Corporation
