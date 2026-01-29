# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
NLWeb Network Server - HTTP/MCP/A2A server using pluggable interface adapters.

This server provides multiple protocol endpoints:
- /ask: HTTP endpoint (GET/POST) with streaming (SSE) or non-streaming (JSON) responses
- /mcp: MCP protocol endpoint (JSON-RPC 2.0)
- /mcp-sse: MCP protocol with Server-Sent Events streaming
- /a2a: A2A protocol endpoint (JSON-RPC 2.0)
- /a2a-sse: A2A protocol with Server-Sent Events streaming
- /health: Health check endpoint

Each endpoint uses an interface adapter to handle protocol-specific
formatting while routing to the appropriate NLWeb handler.
"""

from aiohttp import request, web
from aiohttp.web_request import Request
from aiohttp.web_exceptions import HTTPInternalServerError
from nlweb_core.config import (
    get_config,
    set_config_overrides,
    reset_config,
    initialize_config,
)
from nlweb_core.handler import NLWebHandler
from nlweb_network.interfaces import (
    HTTPJSONInterface,
    HTTPSSEInterface,
    MCPStreamableInterface,
    MCPSSEInterface,
    A2AStreamableInterface,
    A2ASSEInterface,
)
from nlweb_network.admin_handlers import (
    get_site_config_handler,
    get_config_type_handler,
    update_config_type_handler,
    delete_config_type_handler,
    delete_site_config_handler,
)
import os
from pyinstrument import Profiler, processors
from pyinstrument.renderers import HTMLRenderer


async def health_handler(request):
    """Simple health check endpoint."""
    return web.json_response({"status": "ok"})


async def config_handler(request):
    """Expose client configuration."""
    from nlweb_core.config import get_config

    return web.json_response({"test_user": get_config().test_user})


async def ask_handler(request):
    """
    Handle /ask requests (both GET and POST).

    Routes to either HTTP SSE (streaming=true, default) or
    HTTP JSON (streaming=false) interface based on prefer.streaming parameter.

    Expected v0.54 format:
    {
        "query": {"text": "...", ...},
        "context": {...},
        "prefer": {"streaming": true/false, ...},
        "meta": {...}
    }

    Returns:
    - If prefer.streaming=false: JSON response with the complete NLWeb answer
    - Otherwise (default): Server-Sent Events stream
    """
    # Get query parameters to check streaming preference
    query_params = dict(request.query)

    # For POST requests, check JSON body too
    if request.method == "POST":
        try:
            body = await request.json()
            query_params = {**query_params, **body}
        except Exception:
            pass

    # Extract streaming from prefer section (default: true)
    prefer = query_params.get("prefer", {})
    streaming = prefer.get("streaming", True) if isinstance(prefer, dict) else True

    # Route to appropriate interface
    if streaming:
        interface = HTTPSSEInterface()
    else:
        interface = HTTPJSONInterface()

    return await interface.handle_request(request, NLWebHandler)


async def mcp_handler(request):
    """
    Handle MCP protocol requests (JSON-RPC 2.0 over HTTP).

    This is the standard MCP StreamableHTTP transport.
    Handles initialize, tools/list, and tools/call methods.

    Returns:
    - JSON-RPC 2.0 formatted responses
    """
    interface = MCPStreamableInterface()
    return await interface.handle_request(request, NLWebHandler)


async def mcp_sse_handler(request):
    """
    Handle MCP protocol requests with Server-Sent Events streaming.

    Similar to /mcp but streams results via SSE for tools/call.
    Supports both GET and POST requests.

    Returns:
    - JSON-RPC 2.0 formatted responses via SSE
    """
    interface = MCPSSEInterface()
    return await interface.handle_request(request, NLWebHandler)


async def a2a_handler(request):
    """
    Handle A2A protocol requests (JSON-RPC 2.0 over HTTP).

    This is the standard A2A StreamableHTTP transport.
    Handles agent/card and message/send methods.

    Returns:
    - JSON-RPC 2.0 formatted responses
    """
    interface = A2AStreamableInterface()
    return await interface.handle_request(request, NLWebHandler)


async def a2a_sse_handler(request):
    """
    Handle A2A protocol requests with Server-Sent Events streaming.

    Similar to /a2a but streams results via SSE for message/stream.
    Supports both GET and POST requests.

    Returns:
    - JSON-RPC 2.0 formatted responses via SSE
    """
    interface = A2ASSEInterface()
    return await interface.handle_request(request, NLWebHandler)


async def await_handler(request):
    """
    Handle /await requests for promise checking.

    Expected POST body (v0.54 format):
    {
        "promise_token": "promise_xyz789",
        "action": "checkin",  // or "cancel"
        "meta": {...}
    }

    Returns:
    - JSON response with promise status or final answer
    """
    try:
        body = await request.json()

        # Validate required fields
        if "promise_token" not in body:
            return web.json_response(
                {
                    "_meta": {"response_type": "Failure", "version": "0.54"},
                    "error": {
                        "code": "MISSING_FIELD",
                        "message": "Missing required field: promise_token",
                    },
                },
                status=400,
            )

        if "action" not in body or body["action"] not in ["checkin", "cancel"]:
            return web.json_response(
                {
                    "_meta": {"response_type": "Failure", "version": "0.54"},
                    "error": {
                        "code": "INVALID_ACTION",
                        "message": 'Action must be "checkin" or "cancel"',
                    },
                },
                status=400,
            )

        # TODO: Implement promise tracking/checking logic
        # For now, return a placeholder Promise response
        return web.json_response(
            {
                "_meta": {"response_type": "Promise", "version": "0.54"},
                "promise": {"token": body["promise_token"], "estimated_time": 60},
            }
        )

    except Exception as e:
        return web.json_response(
            {
                "_meta": {"response_type": "Failure", "version": "0.54"},
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            },
            status=500,
        )


async def profile_request(app, handler):
    """Middleware to profile requests if X-Profile-Request header is set."""

    async def middleware(request: Request):
        if request.headers.get("X-Profile-Request", "false") != "true":
            return await handler(request)
        profiler = Profiler(async_mode="enabled")
        profiler.start()
        await handler(request)
        profiler.stop()
        session = profiler.last_session
        if session is None:
            raise HTTPInternalServerError(reason="Profiling session is None")
        renderer = HTMLRenderer()
        renderer.preprocessors.insert(0, processors.group_library_frames_processor)
        renderer.preprocessor_options = {
            "hide_regex": ".*/(starlette|httpx|asyncio)/.*"
        }
        return web.Response(body=renderer.render(session))

    return middleware


async def require_admin_api_key(app, handler):
    """
    Optional API key middleware for admin endpoints.

    Only protects /site-configs/* endpoints if ADMIN_API_KEY environment variable is set.
    If ADMIN_API_KEY is not set, endpoints are open (for internal use).
    """

    async def middleware(request: Request):
        # Only protect /site-configs/* endpoints
        if request.path.startswith("/site-configs"):
            expected_key = os.getenv("ADMIN_API_KEY")

            # If ADMIN_API_KEY is set, require it
            if expected_key:
                provided_key = request.headers.get("X-API-Key")
                if provided_key != expected_key:
                    return web.json_response(
                        {"error": "Unauthorized", "message": "Valid API key required"},
                        status=401,
                    )

        return await handler(request)

    return middleware


# Query param to config attribute mapping for per-request overrides
_OVERRIDE_PARAM_MAP = {
    "tool_selection": "tool_selection_enabled",
    "memory": "memory_enabled",
    "analyze_query": "analyze_query_enabled",
    "decontextualize": "decontextualize_enabled",
    "required_info": "required_info_enabled",
    "aggregation": "aggregation_enabled",
    "who_endpoint": "who_endpoint_enabled",
}


def _parse_bool(value: str) -> bool:
    """Parse boolean from query param string."""
    return value.lower() in ("true", "1", "yes", "on")


async def config_override_middleware(app, handler):
    """
    Middleware to set per-request config overrides from query/body params.

    Supports:
    - Query params: ?prefer.config.memory=true
    - JSON body: {"prefer": {"config": {"memory": true}}}
    """

    async def middleware(request: Request):
        overrides = {}

        # Parse prefer.config.* from query params
        for key, value in request.query.items():
            if key.startswith("prefer.config."):
                param_name = key[len("prefer.config.") :]
                if param_name in _OVERRIDE_PARAM_MAP:
                    overrides[_OVERRIDE_PARAM_MAP[param_name]] = _parse_bool(value)

        # For POST, also check JSON body prefer.config section
        if request.method == "POST":
            content_type = request.content_type or ""
            if "application/json" in content_type:
                try:
                    body = await request.json()
                    config_section = body.get("prefer", {}).get("config", {})
                    for param_name, value in config_section.items():
                        if param_name in _OVERRIDE_PARAM_MAP:
                            overrides[_OVERRIDE_PARAM_MAP[param_name]] = bool(value)
                except Exception:
                    pass  # Let handler deal with malformed JSON

        # Set overrides (only does work if there are valid overrides)
        if overrides:
            set_config_overrides(overrides)

        try:
            return await handler(request)
        finally:
            # Always reset to static config after request
            reset_config()

    return middleware


async def init_app(app):
    """Initialize conversation storage on startup."""
    from nlweb_core.config import get_config
    import sys

    config = get_config()

    # Validate that Cosmos DB (object storage) is enabled - REQUIRED
    if not config.object_storage or not config.object_storage.enabled:
        print("\n" + "=" * 60)
        print("FATAL ERROR: Cosmos DB (object_storage) is not enabled")
        print("=" * 60)
        print("Object storage is now mandatory for NLWeb to function.")
        print("Vector DB no longer stores full content - only Cosmos DB does.")
        print("\nPlease configure object_storage in your config.yaml:")
        print("  object_storage:")
        print("    enabled: true")
        print("    endpoint: https://your-cosmos.documents.azure.com:443/")
        print("    database_name_env: your-database")
        print("    container_name_env: your-container")
        print("=" * 60 + "\n")
        sys.exit(1)

    # Initialize conversation storage on startup if enabled
    if config.conversation_storage and config.conversation_storage.enabled:
        try:
            from nlweb_core.conversation.storage import ConversationStorageClient
            from nlweb_core.conversation_saver import set_conversation_storage_client

            storage = ConversationStorageClient(config.conversation_storage)
            # Initialize pool and schema on startup to avoid first-request latency
            await storage.backend.initialize()
            app["conversation_storage"] = storage
            # Store in module-level cache so handlers can access it
            set_conversation_storage_client(storage)
            print("Conversation storage initialized on startup")
        except Exception as e:
            print(f"Failed to initialize conversation storage: {e}")
            import traceback

            traceback.print_exc()

    # Initialize site config and elicitation handler if enabled
    if config.site_config and config.site_config.enabled:
        try:
            from nlweb_core.site_config import initialize_site_config

            elicitation_handler = initialize_site_config(config)
            if elicitation_handler:
                print("Site config and elicitation handler initialized on startup")
            else:
                print("Site config enabled but initialization failed (check logs)")
        except Exception as e:
            print(f"Failed to initialize site config: {e}")
            import traceback

            traceback.print_exc()


async def cleanup_app(app):
    """Cleanup conversation storage on shutdown."""
    if "conversation_storage" in app:
        try:
            await app["conversation_storage"].backend.close()
            print("Conversation storage closed")
        except Exception as e:
            print(f"Error closing conversation storage: {e}")


def create_app():
    """Create and configure the aiohttp application."""
    app = web.Application(
        middlewares=[config_override_middleware, require_admin_api_key, profile_request]
    )

    # Add startup and cleanup hooks
    app.on_startup.append(init_app)
    app.on_cleanup.append(cleanup_app)

    # Add HTTP routes
    app.router.add_get("/ask", ask_handler)
    app.router.add_post("/ask", ask_handler)
    app.router.add_post("/await", await_handler)
    app.router.add_get("/health", health_handler)
    app.router.add_get("/config", config_handler)

    # Add MCP routes
    app.router.add_post("/mcp", mcp_handler)  # MCP StreamableHTTP (JSON-RPC over HTTP)
    app.router.add_get("/mcp-sse", mcp_sse_handler)  # MCP over SSE (streaming)
    app.router.add_post("/mcp-sse", mcp_sse_handler)  # MCP over SSE (streaming)

    # Add A2A routes
    app.router.add_post("/a2a", a2a_handler)  # A2A StreamableHTTP (JSON-RPC over HTTP)
    app.router.add_get("/a2a-sse", a2a_sse_handler)  # A2A over SSE (streaming)
    app.router.add_post("/a2a-sse", a2a_sse_handler)  # A2A over SSE (streaming)

    # Add Site Config Management routes
    app.router.add_get("/site-configs/{domain}", get_site_config_handler)
    app.router.add_get("/site-configs/{domain}/{config_type}", get_config_type_handler)
    app.router.add_put(
        "/site-configs/{domain}/{config_type}", update_config_type_handler
    )
    app.router.add_delete(
        "/site-configs/{domain}/{config_type}", delete_config_type_handler
    )
    app.router.add_delete("/site-configs/{domain}", delete_site_config_handler)

    # Enable CORS if configured
    if get_config().server.enable_cors:
        from aiohttp_cors import setup as cors_setup, ResourceOptions

        cors = cors_setup(
            app,
            defaults={
                "*": ResourceOptions(
                    allow_credentials=True,
                    expose_headers="*",
                    allow_headers="*",
                    allow_methods="*",
                )
            },
        )

        # Configure CORS for all routes
        for route in list(app.router.routes()):
            cors.add(route)

    return app


def main():
    """Main entry point to run the server."""
    # Initialize configuration from files (must be called before using get_config())
    initialize_config()

    app = create_app()

    # Get host and port from config
    config = get_config()
    host = config.server.host
    port = config.port

    # Run the server
    web.run_app(app, host=host, port=port)


if __name__ == "__main__":
    main()
