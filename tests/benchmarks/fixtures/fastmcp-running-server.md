<!-- Source: https://gofastmcp.com/deployment/running-server -->
<!-- Fetched: 2026-05-21 for Synaptic Drift vs WebFetch benchmark -->
<!-- If this page has changed, re-fetch and update this file and the benchmark results in .work/research_spikes.md -->

# Running Your Server

FastMCP servers can be run in different ways depending on your needs. This guide focuses on running servers locally for development and testing. For production deployment to a URL, see the HTTP Deployment guide.

## The `run()` Method

Every FastMCP server needs to be started to accept connections. The simplest way to run a server is by calling the `run()` method on your FastMCP instance. This method starts the server and blocks until it's stopped, handling all the connection management for you.

For maximum compatibility, it's best practice to place the `run()` call within an `if __name__ == "__main__":` block. This ensures the server starts only when the script is executed directly, not when imported as a module.

```python
from fastmcp import FastMCP

mcp = FastMCP(name="MyServer")

@mcp.tool
def hello(name: str) -> str:
    return f"Hello, {name}!"

if __name__ == "__main__":
    mcp.run()
```

You can now run this MCP server by executing `python my_server.py`.

## Transport Protocols

MCP servers communicate with clients through different transport protocols. Think of transports as the "language" your server speaks to communicate with clients. FastMCP supports three main transport protocols, each designed for specific use cases and deployment scenarios.

The choice of transport determines how clients connect to your server, what network capabilities are available, and how many clients can connect simultaneously. Understanding these transports helps you choose the right approach for your application.

### STDIO Transport (Default)

STDIO (Standard Input/Output) is the default transport for FastMCP servers. When you call `run()` without arguments, your server uses STDIO transport. This transport communicates through standard input and output streams, making it perfect for command-line tools and desktop applications like Claude Desktop.

With STDIO transport, the client spawns a new server process for each session and manages its lifecycle. The server reads MCP messages from stdin and writes responses to stdout. This is why STDIO servers don't stay running - they're started on-demand by the client.

```python
from fastmcp import FastMCP

mcp = FastMCP("MyServer")

@mcp.tool
def hello(name: str) -> str:
    return f"Hello, {name}!"

if __name__ == "__main__":
    mcp.run()  # Uses STDIO transport by default
```

STDIO is ideal for:

* Local development and testing
* Claude Desktop integration
* Command-line tools
* Single-user applications

### HTTP Transport (Streamable)

HTTP transport turns your MCP server into a web service accessible via a URL. This transport uses the Streamable HTTP protocol, which allows clients to connect over the network. Unlike STDIO where each client gets its own process, an HTTP server can handle multiple clients simultaneously.

The Streamable HTTP protocol provides full bidirectional communication between client and server, supporting all MCP operations including streaming responses. This makes it the recommended choice for network-based deployments.

To use HTTP transport, specify it in the `run()` method along with networking options:

```python
from fastmcp import FastMCP

mcp = FastMCP("MyServer")

@mcp.tool
def hello(name: str) -> str:
    return f"Hello, {name}!"

if __name__ == "__main__":
    # Start an HTTP server on port 8000
    mcp.run(transport="http", host="127.0.0.1", port=8000)
```

Your server is now accessible at `http://localhost:8000/mcp`. This URL is the MCP endpoint that clients will connect to. HTTP transport enables:

* Network accessibility
* Multiple concurrent clients
* Integration with web infrastructure
* Remote deployment capabilities

For production HTTP deployment with authentication and advanced configuration, see the HTTP Deployment guide.

### SSE Transport (Legacy)

Server-Sent Events (SSE) transport was the original HTTP-based transport for MCP. While still supported for backward compatibility, it has limitations compared to the newer Streamable HTTP transport. SSE only supports server-to-client streaming, making it less efficient for bidirectional communication.

```python
if __name__ == "__main__":
    # SSE transport - use HTTP instead for new projects
    mcp.run(transport="sse", host="127.0.0.1", port=8000)
```

We recommend using HTTP transport instead of SSE for all new projects. SSE remains available only for compatibility with older clients that haven't upgraded to Streamable HTTP.

### Choosing the Right Transport

Each transport serves different needs. STDIO is perfect when you need simple, local execution - it's what Claude Desktop and most command-line tools expect. HTTP transport is essential when you need network access, want to serve multiple clients, or plan to deploy your server remotely. SSE exists only for backward compatibility and shouldn't be used in new projects.

Consider your deployment scenario: Are you building a tool for local use? STDIO is your best choice. Need a centralized service that multiple clients can access? HTTP transport is the way to go.

## The FastMCP CLI

FastMCP provides a powerful command-line interface for running servers without modifying the source code. The CLI can automatically find and run your server with different transports, manage dependencies, and handle development workflows:

```bash
fastmcp run server.py
```

The CLI automatically finds a FastMCP instance in your file (named `mcp`, `server`, or `app`) and runs it with the specified options. This is particularly useful for testing different transports or configurations without changing your code.

### Dependency Management

The CLI integrates with `uv` to manage Python environments and dependencies:

```bash
# Run with a specific Python version
fastmcp run server.py --python 3.11

# Run with additional packages
fastmcp run server.py --with pandas --with numpy

# Run with dependencies from a requirements file
fastmcp run server.py --with-requirements requirements.txt

# Combine multiple options
fastmcp run server.py --python 3.10 --with httpx --transport http

# Run within a specific project directory
fastmcp run server.py --project /path/to/project
```

### Passing Arguments to Servers

When servers accept command line arguments (using argparse, click, or other libraries), you can pass them after `--`:

```bash
fastmcp run config_server.py -- --config config.json
fastmcp run database_server.py -- --database-path /tmp/db.sqlite --debug
```

### Auto-Reload for Development

During development, you can use the `--reload` flag to automatically restart your server when source files change:

```bash
fastmcp run server.py --reload
```

The server watches for changes to Python files in the current directory and restarts automatically when you save changes.

```bash
# Watch specific directories for changes
fastmcp run server.py --reload --reload-dir ./src --reload-dir ./lib

# Combine with other options
fastmcp run server.py --reload --transport http --port 8080
```

### Async Usage

FastMCP servers are built on async Python, but the framework provides both synchronous and asynchronous APIs to fit your application needs. The `run()` method is a synchronous wrapper around the async server implementation.

For applications that are already running in an async context, FastMCP provides the `run_async()` method:

```python
from fastmcp import FastMCP
import asyncio

mcp = FastMCP(name="MyServer")

@mcp.tool
def hello(name: str) -> str:
    return f"Hello, {name}!"

async def main():
    await mcp.run_async(transport="http", port=8000)

if __name__ == "__main__":
    asyncio.run(main())
```

The `run()` method cannot be called from inside an async function because it creates its own async event loop internally. Always use `run_async()` inside async functions and `run()` in synchronous contexts.

## Custom Routes

When using HTTP transport, you might want to add custom web endpoints alongside your MCP server. FastMCP lets you add custom routes using the `@custom_route` decorator:

```python
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse

mcp = FastMCP("MyServer")

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")

@mcp.tool
def process(data: str) -> str:
    return f"Processed: {data}"

if __name__ == "__main__":
    mcp.run(transport="http")
```

## Alternative Initialization Patterns

### CLI-Only Servers

When using the FastMCP CLI, you don't need the `if __name__` block at all:

```python
from fastmcp import FastMCP

mcp = FastMCP("MyServer")

@mcp.tool
def process(data: str) -> str:
    return f"Processed: {data}"
```

### ASGI Applications

For ASGI deployment with Uvicorn or similar:

```python
from fastmcp import FastMCP

def create_app():
    mcp = FastMCP("MyServer")

    @mcp.tool
    def process(data: str) -> str:
        return f"Processed: {data}"

    return mcp.http_app()

app = create_app()
```
