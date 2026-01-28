# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Simple aiohttp server for NLWeb /ask queries.

WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.
"""

import json
import asyncio
import logging
from aiohttp import web
from nlweb_core.handler import NLWebHandler
from nlweb_core.config import get_config
from pydantic import ValidationError
from nlweb_core.protocol import AskRequest, ResponseMeta
from nlweb_core.protocol.conversation_models import (
    ListConversationsRequest,
    GetConversationRequest,
    DeleteConversationRequest,
    ListConversationsResponse,
    GetConversationResponse,
    DeleteConversationResponse,
    ConversationSummary,
    ConversationPreview,
    ConversationInfo,
    PaginationResponse,
    ErrorResponse,
)
from nlweb_core.conversation.auth import (
    get_authenticated_user_id,
    validate_conversation_access,
    validate_session,
)
from nlweb_core.rate_limiter import get_rate_limiter, shutdown_rate_limiter

logger = logging.getLogger(__name__)


async def ask_handler(request):
    """
    Handle /ask requests (both GET and POST).

    For GET requests:
    - All parameters come from query string

    For POST requests:
    - Parameters can come from JSON body or query string
    - JSON body takes precedence over query string

    Expected parameters:
    - query: The natural language query (required)
    - site: Site to search (optional, defaults to "all")
    - num_results: Number of results to return (optional, defaults to 10)
    - db: Database endpoint to use (optional)
    - streaming: Whether to use SSE streaming (optional, defaults to true)

    Returns:
    - If streaming=false: JSON response with the complete NLWeb answer
    - Otherwise: Server-Sent Events stream
    """
    # Get request timeout from config (default 120 seconds)
    config = get_config()
    timeout_seconds = getattr(config.server, "timeout", 120) if config.server else 120

    # Rate limiting
    rate_limiter = get_rate_limiter(requests_per_minute=60, burst_size=10)
    client_ip = (
        request.headers.get("X-Forwarded-For", request.remote).split(",")[0].strip()
    )
    allowed, rate_headers = await rate_limiter.check_rate_limit(client_ip)

    if not allowed:
        return web.json_response(
            {
                "error": "Rate limit exceeded. Please try again later.",
                "_meta": {"version": "0.54", "response_type": "Error"},
            },
            status=429,
            headers=rate_headers,
        )

    try:
        # Get query parameters from URL
        query_params = dict(request.query)

        # For POST requests, merge JSON body params (body takes precedence)
        if request.method == "POST":
            try:
                body = await request.json()
                # Merge body params into query_params, with body taking precedence
                query_params = {**query_params, **body}
            except Exception as e:
                # If body parsing fails, just use query params
                logger.debug(
                    f"No JSON body in POST request (using query params only): {e}"
                )

        # Build AskRequest from query_params
        try:
            ask_request = AskRequest.from_query_params(query_params)
        except ValidationError as e:
            return web.json_response(
                {
                    "error": "Invalid request parameters",
                    "details": e.errors(),
                    "_meta": {"version": "0.5"},
                },
                status=400,
            )

        # Check streaming parameter from prefer
        streaming = (
            ask_request.prefer.streaming
            if ask_request.prefer and ask_request.prefer.streaming is not None
            else True
        )

        # Wrap execution with timeout
        try:
            async with asyncio.timeout(timeout_seconds):
                if not streaming:
                    # Non-streaming mode: collect all responses and return JSON
                    return await handle_non_streaming(ask_request)
                else:
                    # Streaming mode: use SSE
                    return await handle_streaming(request, ask_request)
        except asyncio.TimeoutError:
            logger.error(f"Request timeout after {timeout_seconds}s")
            if streaming:
                # For streaming, try to send error event
                response = web.StreamResponse(
                    status=504,
                    reason="Gateway Timeout",
                    headers={"Content-Type": "text/event-stream"},
                )
                await response.prepare(request)
                error_data = {
                    "_meta": {
                        "version": "0.54",
                        "nlweb/streaming_status": "error",
                        "error": f"Request timeout after {timeout_seconds}s",
                    }
                }
                await response.write(
                    f"data: {json.dumps(error_data)}\n\n".encode("utf-8")
                )
                await response.write_eof()
                return response
            else:
                # For non-streaming, return JSON error
                return web.json_response(
                    {
                        "error": "Request timeout",
                        "_meta": {"version": "0.54", "response_type": "Error"},
                    },
                    status=504,
                )

    except Exception as e:
        return web.json_response({"error": str(e), "_meta": {}}, status=500)


async def handle_non_streaming(ask_request: AskRequest):
    """
    Handle non-streaming request, return complete JSON response.

    Args:
        ask_request: Validated AskRequest model from protocol
    """
    responses = []

    async def output_method(data):
        """Callback to collect output from handler."""
        responses.append(data)

    # Create and run the handler
    handler = NLWebHandler(ask_request, output_method)
    await handler.runQuery()

    # Build the response with _meta
    response = {"_meta": {"version": "0.5"}}

    # Combine all responses
    for resp in responses:
        if "_meta" in resp:
            response["_meta"].update(resp["_meta"])
        if "content" in resp:
            if "content" not in response:
                response["content"] = []
            response["content"].extend(resp["content"])

    # Ensure content exists
    if "content" not in response:
        response["content"] = []

    return web.json_response(response)


async def handle_streaming(request, ask_request: AskRequest):
    """
    Handle streaming request using Server-Sent Events.

    Args:
        request: aiohttp request object
        ask_request: Validated AskRequest model from protocol
    """
    response = web.StreamResponse()
    response.headers["Content-Type"] = "text/event-stream"
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Connection"] = "keep-alive"

    await response.prepare(request)

    async def output_method(data):
        """Callback to stream output via SSE."""
        try:
            # Format as SSE
            event_data = f"data: {json.dumps(data)}\n\n"
            await response.write(event_data.encode("utf-8"))
        except Exception as e:
            print(f"Error writing to stream: {e}")

    try:
        # Create and run the handler
        handler = NLWebHandler(ask_request, output_method)
        await handler.runQuery()

        # Send completion event
        completion = {"_meta": {"version": "0.5", "nlweb/streaming_status": "finished"}}
        event_data = f"data: {json.dumps(completion)}\n\n"
        await response.write(event_data.encode("utf-8"))

    except Exception as e:
        # Send error event
        error_data = {
            "_meta": {
                "version": "0.5",
                "nlweb/streaming_status": "error",
                "error": str(e),
            }
        }
        event_data = f"data: {json.dumps(error_data)}\n\n"
        await response.write(event_data.encode("utf-8"))

    await response.write_eof()
    return response


async def health_handler(request):
    """Simple health check endpoint."""
    return web.json_response({"status": "ok"})


async def config_handler(request):
    """Expose client configuration."""
    return web.json_response({"test_user": get_config().test_user})


async def mcp_handler(request):
    """
    MCP protocol endpoint - handles JSON-RPC 2.0 requests for MCP.

    Supports StreamableHttp transport (recommended) via POST requests.
    """
    # Handle POST request for StreamableHttp/JSON-RPC
    try:
        body = await request.json()

        # MCP uses JSON-RPC 2.0 format
        method = body.get("method")
        params = body.get("params", {})
        request_id = body.get("id")

        # Handle initialize request
        if method == "initialize":
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "nlweb-mcp-server", "version": "0.5.0"},
                },
            }
            return web.json_response(response)

        # Handle tools/list request
        elif method == "tools/list":
            # Generate schema from AskRequest protocol model
            ask_schema = AskRequest.model_json_schema()

            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": "ask",
                            "description": "Search and answer natural language queries using NLWeb's vector database and LLM ranking",
                            "inputSchema": ask_schema,
                        }
                    ]
                },
            }
            return web.json_response(response)

        # Handle tools/call request
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            if tool_name != "ask":
                return web.json_response(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32602,
                            "message": f"Unknown tool: {tool_name}",
                        },
                    }
                )

            # MCP calls should default to non-streaming
            if "streaming" not in arguments:
                arguments["streaming"] = False

            try:
                ask_request = AskRequest.from_query_params(arguments)
            except ValidationError as e:
                return web.json_response(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32602,
                            "message": "Invalid parameters",
                            "data": e.errors(),
                        },
                    }
                )

            # Execute the query
            result_response = await handle_non_streaming(ask_request)

            # Extract the JSON from the response
            result_json = json.loads(result_response.body)

            # Return MCP response
            mcp_response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {"type": "text", "text": json.dumps(result_json, indent=2)}
                    ]
                },
            }
            return web.json_response(mcp_response)

        else:
            return web.json_response(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
            )

    except json.JSONDecodeError:
        return web.json_response(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            },
            status=400,
        )
    except Exception as e:
        return web.json_response(
            {
                "jsonrpc": "2.0",
                "id": request_id if "request_id" in locals() else None,
                "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
            },
            status=500,
        )


async def list_conversations_handler(request):
    """
    Handle GET /conversations - List conversations for authenticated user.
    Uses JSON body with meta.user for authentication.
    """
    try:
        from nlweb_core.conversation.storage import ConversationStorageClient

        # Check if conversation storage is enabled
        config = get_config()
        if not config.conversation_storage or not config.conversation_storage.enabled:
            return web.json_response(
                {
                    "_meta": {"version": "0.54", "response_type": "Error"},
                    "error": {
                        "code": "SERVICE_UNAVAILABLE",
                        "message": "Conversation storage is not enabled",
                    },
                },
                status=503,
            )

        # Parse JSON body
        try:
            body = await request.json()
            list_request = ListConversationsRequest(**body)
        except Exception as e:
            logger.debug(f"Invalid request body: {e}")
            return web.json_response(
                {
                    "_meta": {"version": "0.54", "response_type": "Error"},
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": f"Invalid request body: {str(e)}",
                    },
                },
                status=400,
            )

        # Extract and validate user ID
        user_id = get_authenticated_user_id(list_request.meta)
        if not user_id:
            return web.json_response(
                {
                    "_meta": {"version": "0.54", "response_type": "Error"},
                    "error": {
                        "code": "AUTH_REQUIRED",
                        "message": "User authentication required",
                    },
                },
                status=401,
            )

        # TODO: Validate user_id matches authenticated session
        # if not validate_session(request, user_id):
        #     return web.json_response({
        #         "_meta": {"version": "0.54", "response_type": "Error"},
        #         "error": {"code": "FORBIDDEN", "message": "User not authenticated"}
        #     }, status=403)

        # Get conversations for this user
        storage = ConversationStorageClient()
        conversation_ids = await storage.get_user_conversations(
            user_id, limit=list_request.pagination.limit
        )

        # Build conversation summaries
        conversations = []
        for conv_id in conversation_ids:
            try:
                # Get first message for preview
                messages = await storage.get_messages(conv_id, limit=1)
                if messages:
                    msg = messages[0]
                    conversations.append(
                        ConversationSummary(
                            conversation_id=conv_id,
                            message_count=1,  # TODO: Get actual count
                            first_message_timestamp=msg.timestamp,
                            last_message_timestamp=msg.timestamp,
                            site=msg.metadata.get("site") if msg.metadata else None,
                            preview=ConversationPreview(
                                query=msg.request.query.text,
                                result_count=len(msg.results) if msg.results else 0,
                            ),
                        )
                    )
            except Exception as e:
                logger.warning(f"Failed to load conversation {conv_id}: {e}")
                continue

        # Build response
        response = ListConversationsResponse(
            _meta={"version": "0.54", "response_type": "ConversationList"},
            conversations=conversations,
            pagination=PaginationResponse(
                total=len(conversations),
                limit=list_request.pagination.limit,
                offset=list_request.pagination.offset,
                has_more=False,  # TODO: Implement proper pagination
            ),
        )

        return web.json_response(response.model_dump(by_alias=True, mode="json"))

    except Exception as e:
        logger.error(f"Failed to list conversations: {e}", exc_info=True)
        return web.json_response(
            {
                "_meta": {"version": "0.54", "response_type": "Error"},
                "error": {"code": "INTERNAL_ERROR", "message": "Internal server error"},
            },
            status=500,
        )


async def get_conversation_handler(request):
    """
    Handle GET /conversations/{id} - Get messages for a specific conversation.
    Uses JSON body with meta.user for authentication.
    """
    try:
        from nlweb_core.conversation.storage import ConversationStorageClient

        # Check if conversation storage is enabled
        config = get_config()
        if not config.conversation_storage or not config.conversation_storage.enabled:
            return web.json_response(
                {
                    "_meta": {"version": "0.54", "response_type": "Error"},
                    "error": {
                        "code": "SERVICE_UNAVAILABLE",
                        "message": "Conversation storage is not enabled",
                    },
                },
                status=503,
            )

        # Get conversation ID from path
        conversation_id = request.match_info.get("id")
        if not conversation_id:
            return web.json_response(
                {
                    "_meta": {"version": "0.54", "response_type": "Error"},
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": "Conversation ID required",
                    },
                },
                status=400,
            )

        # Parse JSON body
        try:
            body = await request.json()
            get_request = GetConversationRequest(**body)
        except Exception as e:
            logger.debug(f"Invalid request body: {e}")
            return web.json_response(
                {
                    "_meta": {"version": "0.54", "response_type": "Error"},
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": f"Invalid request body: {str(e)}",
                    },
                },
                status=400,
            )

        # Extract and validate user ID
        user_id = get_authenticated_user_id(get_request.meta)
        if not user_id:
            return web.json_response(
                {
                    "_meta": {"version": "0.54", "response_type": "Error"},
                    "error": {
                        "code": "AUTH_REQUIRED",
                        "message": "User authentication required",
                    },
                },
                status=401,
            )

        # Initialize storage and validate access
        storage = ConversationStorageClient()

        # Validate user owns this conversation
        has_access = await validate_conversation_access(
            conversation_id, user_id, storage
        )
        if not has_access:
            # Return 404 instead of 403 to avoid information disclosure
            return web.json_response(
                {
                    "_meta": {"version": "0.54", "response_type": "Error"},
                    "error": {"code": "NOT_FOUND", "message": "Conversation not found"},
                },
                status=404,
            )

        # Get messages
        messages = await storage.get_messages(
            conversation_id, limit=get_request.pagination.limit
        )

        if not messages:
            return web.json_response(
                {
                    "_meta": {"version": "0.54", "response_type": "Error"},
                    "error": {"code": "NOT_FOUND", "message": "Conversation not found"},
                },
                status=404,
            )

        # Build conversation info
        first_msg = messages[0]
        last_msg = messages[-1]

        conversation_info = ConversationInfo(
            conversation_id=conversation_id,
            user_id=user_id,
            created_at=first_msg.timestamp,
            updated_at=last_msg.timestamp,
        )

        # Build response
        response = GetConversationResponse(
            _meta={"version": "0.54", "response_type": "ConversationMessages"},
            conversation=conversation_info,
            messages=messages,
            pagination=PaginationResponse(
                total=len(messages),
                limit=get_request.pagination.limit,
                offset=get_request.pagination.offset,
                has_more=False,  # TODO: Implement proper pagination
            ),
        )

        return web.json_response(response.model_dump(by_alias=True, mode="json"))

    except Exception as e:
        logger.error(f"Failed to get conversation: {e}", exc_info=True)
        return web.json_response(
            {
                "_meta": {"version": "0.54", "response_type": "Error"},
                "error": {"code": "INTERNAL_ERROR", "message": "Internal server error"},
            },
            status=500,
        )


async def delete_conversation_handler(request):
    """
    Handle DELETE /conversations/{id} - Delete a conversation.
    Uses JSON body with meta.user for authentication.
    """
    try:
        from nlweb_core.conversation.storage import ConversationStorageClient

        # Check if conversation storage is enabled
        config = get_config()
        if not config.conversation_storage or not config.conversation_storage.enabled:
            return web.json_response(
                {
                    "_meta": {"version": "0.54", "response_type": "Error"},
                    "error": {
                        "code": "SERVICE_UNAVAILABLE",
                        "message": "Conversation storage is not enabled",
                    },
                },
                status=503,
            )

        # Get conversation ID from path
        conversation_id = request.match_info.get("id")
        if not conversation_id:
            return web.json_response(
                {
                    "_meta": {"version": "0.54", "response_type": "Error"},
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": "Conversation ID required",
                    },
                },
                status=400,
            )

        # Parse JSON body
        try:
            body = await request.json()
            delete_request = DeleteConversationRequest(**body)
        except Exception as e:
            logger.debug(f"Invalid request body: {e}")
            return web.json_response(
                {
                    "_meta": {"version": "0.54", "response_type": "Error"},
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": f"Invalid request body: {str(e)}",
                    },
                },
                status=400,
            )

        # Extract and validate user ID
        user_id = get_authenticated_user_id(delete_request.meta)
        if not user_id:
            return web.json_response(
                {
                    "_meta": {"version": "0.54", "response_type": "Error"},
                    "error": {
                        "code": "AUTH_REQUIRED",
                        "message": "User authentication required",
                    },
                },
                status=401,
            )

        # Initialize storage and validate access
        storage = ConversationStorageClient()

        # Validate user owns this conversation
        has_access = await validate_conversation_access(
            conversation_id, user_id, storage
        )
        if not has_access:
            # Return 404 instead of 403 to avoid information disclosure
            return web.json_response(
                {
                    "_meta": {"version": "0.54", "response_type": "Error"},
                    "error": {"code": "NOT_FOUND", "message": "Conversation not found"},
                },
                status=404,
            )

        # Count messages before deletion
        messages = await storage.get_messages(conversation_id)
        messages_count = len(messages)

        # Delete conversation
        await storage.delete_conversation(conversation_id)

        # Build response
        response = DeleteConversationResponse(
            _meta={"version": "0.54", "response_type": "ConversationDeleted"},
            conversation_id=conversation_id,
            status="deleted",
            messages_deleted=messages_count,
        )

        return web.json_response(response.model_dump(by_alias=True, mode="json"))

    except Exception as e:
        logger.error(f"Failed to delete conversation: {e}", exc_info=True)
        return web.json_response(
            {
                "_meta": {"version": "0.54", "response_type": "Error"},
                "error": {"code": "INTERNAL_ERROR", "message": "Internal server error"},
            },
            status=500,
        )


async def conversations_handler(request):
    """
    Route conversation requests to appropriate handler.

    Backward compatibility wrapper that routes to new JSON-based handlers.
    """
    conversation_id = request.match_info.get("id")

    if request.method == "DELETE" and conversation_id:
        return await delete_conversation_handler(request)
    elif request.method == "GET" and conversation_id:
        return await get_conversation_handler(request)
    elif request.method == "GET":
        return await list_conversations_handler(request)
    else:
        return web.json_response(
            {
                "_meta": {"version": "0.54", "response_type": "Error"},
                "error": {
                    "code": "METHOD_NOT_ALLOWED",
                    "message": "Method not allowed",
                },
            },
            status=405,
        )


async def legacy_conversations_handler(request):
    """
    DEPRECATED: Old query-string based conversation handler.
    Kept for backward compatibility during transition.
    """
    try:
        from nlweb_core.conversation.storage import ConversationStorageClient

        # Check if conversation storage is enabled
        config = get_config()
        if not config.conversation_storage or not config.conversation_storage.enabled:
            return web.json_response(
                {"error": "Conversation storage is not enabled"}, status=503
            )

        storage = ConversationStorageClient()

        # Extract conversation ID from path if present
        conversation_id = request.match_info.get("id")

        if request.method == "DELETE" and conversation_id:
            # Delete conversation
            await storage.delete_conversation(conversation_id)
            return web.json_response(
                {"status": "deleted", "conversation_id": conversation_id}
            )

        elif request.method == "GET" and conversation_id:
            # Get messages for a conversation
            limit = int(request.query.get("limit", "100"))
            messages = await storage.get_messages(conversation_id, limit=limit)

            # Convert to JSON-serializable format
            messages_json = [msg.model_dump(mode="json") for msg in messages]

            return web.json_response(
                {
                    "conversation_id": conversation_id,
                    "messages": messages_json,
                    "count": len(messages_json),
                }
            )

        elif request.method == "GET":
            # List conversations for a user
            user_id = request.query.get("user_id")
            if not user_id:
                return web.json_response(
                    {"error": "user_id parameter is required"}, status=400
                )

            limit = int(request.query.get("limit", "20"))
            conversation_ids = await storage.get_user_conversations(
                user_id, limit=limit
            )

            return web.json_response(
                {
                    "user_id": user_id,
                    "conversations": conversation_ids,
                    "count": len(conversation_ids),
                }
            )

        else:
            return web.json_response({"error": "Method not allowed"}, status=405)

    except Exception as e:
        logger.error(f"Legacy conversation handler error: {e}", exc_info=True)
        return web.json_response({"error": str(e)}, status=500)


async def init_app(app):
    """Initialize resources on startup."""
    # Configure logging with request ID tracking
    from nlweb_core.request_context import configure_logging_with_request_id

    configure_logging_with_request_id()
    logger.info("Request ID tracking configured for logging")

    # Initialize conversation storage on startup if enabled
    config = get_config()
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
            logger.info("Conversation storage initialized on startup")
        except Exception as e:
            logger.warning(f"Failed to initialize conversation storage: {e}")


async def cleanup_app(app):
    """Cleanup resources on shutdown."""
    # Close conversation storage connections
    if "conversation_storage" in app:
        try:
            await app["conversation_storage"].backend.close()
            logger.info("Conversation storage closed")
        except Exception as e:
            logger.error(f"Error closing conversation storage: {e}")

    # Shutdown rate limiter
    try:
        await shutdown_rate_limiter()
        logger.info("Rate limiter shutdown")
    except Exception as e:
        logger.error(f"Error shutting down rate limiter: {e}")


def create_app():
    """Create and configure the aiohttp application."""
    app = web.Application()

    # Add startup and cleanup hooks
    app.on_startup.append(init_app)
    app.on_cleanup.append(cleanup_app)

    # Add routes - support both GET and POST for /ask
    app.router.add_get("/ask", ask_handler)
    app.router.add_post("/ask", ask_handler)
    app.router.add_get("/health", health_handler)
    app.router.add_get("/config", config_handler)

    # Conversation management endpoints
    app.router.add_get("/conversations", conversations_handler)
    app.router.add_get("/conversations/{id}", conversations_handler)
    app.router.add_delete("/conversations/{id}", conversations_handler)

    # MCP endpoint (JSON-RPC 2.0) - support both POST and GET (for SSE)
    app.router.add_get("/mcp", mcp_handler)
    app.router.add_post("/mcp", mcp_handler)
    return app


def main():
    """Main entry point to run the server."""
    app = create_app()

    # Get host and port from config
    config = get_config()
    host = config.server.host
    port = config.port

    print(f"Starting NLWeb server on http://{host}:{port}")
    print(f" Using protocol validation from nlweb_core.protocol")

    # Print LLM configuration for debugging
    print(f"\n=== LLM Configuration ===")
    if config.scoring_llm_model:
        print(f"Scoring LLM Model:")
        print(f"  model: {config.scoring_llm_model.model}")
        print(f"  endpoint: {config.scoring_llm_model.endpoint}")
        print(f"  api_version: {config.scoring_llm_model.api_version}")
        print(f"  api_key: {'SET' if config.scoring_llm_model.api_key else 'NOT SET'}")
    if config.high_llm_model:
        print(f"High LLM Model:")
        print(f"  model: {config.high_llm_model.model}")
        print(f"  endpoint: {config.high_llm_model.endpoint}")
        print(f"  api_version: {config.high_llm_model.api_version}")
        print(f"  api_key: {'SET' if config.high_llm_model.api_key else 'NOT SET'}")
    if config.low_llm_model:
        print(f"Low LLM Model:")
        print(f"  model: {config.low_llm_model.model}")
        print(f"  endpoint: {config.low_llm_model.endpoint}")
        print(f"  api_version: {config.low_llm_model.api_version}")
        print(f"  api_key: {'SET' if config.low_llm_model.api_key else 'NOT SET'}")
    print(f"========================\n")

    print(f"\nEndpoints:")
    print(f"  - GET/POST /ask")
    print(f"    Protocol parameters (validated):")
    print(f"      - query=<your query> (required)")
    print(f"      - mode=list|summary (optional)")
    print(f"      - site=<site_name> (optional)")
    print(f"      - streaming=<true|false> (optional)")
    print(f"      - prev=<previous queries as array> (optional)")
    print(f"      - context=<additional context> (optional)")
    print(f"      - response_format=<format preferences> (optional)")
    print(f"    Additional parameters (passed through):")
    print(f"      - num_results=<number> (optional)")
    print(f"      - num_start=<starting index> (optional)")
    print(f"      - db=<endpoint_name> (optional)")
    print(f"  - GET /health")
    print(f"  - POST /mcp - MCP protocol endpoint (JSON-RPC 2.0)")
    print(f"\nExamples:")
    print(f"  GET  - http://{host}:{port}/ask?query=best+pizza+restaurants&mode=list")
    print(
        f'  POST - curl -X POST http://{host}:{port}/ask -H \'Content-Type: application/json\' -d \'{{"query": "best pizza", "mode": "summary"}}\''
    )
    print(f"\nMCP Inspector:")
    print(f"  npx @modelcontextprotocol/inspector http://{host}:{port}/mcp")

    # Run the server
    web.run_app(app, host=host, port=port)


if __name__ == "__main__":
    main()
