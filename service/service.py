"""
MCP Discovery and Instruction Service.

A serverless Model Context Protocol server that teaches AI agents how to invoke
external APIs directly from their own execution environment. This service provides
API endpoint blueprints, specifications, and explicit instructions for AI agents
to follow when making network calls.

The service exposes two primary tools:
- list_available_endpoints(): Discover available API endpoints
- get_api_instructions(endpoint_name): Get full specification for an endpoint
"""

import json
import logging
import re
import inspect
from urllib.parse import parse_qs

try:
    from fastmcp import Server as McpServer
except ImportError:
    # Some fastmcp versions export FastMCP instead of Server.
    from fastmcp import FastMCP as McpServer
from mangum import Mangum

# Configure logging for production
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Initialize MCP server for Discovery and Instruction service
server = McpServer("mcp-discovery-instruction-service")


def _register_tool(name: str, fn) -> None:
    """Register a tool across fastmcp versions with different APIs."""
    errors = []

    call_tool = getattr(server, "call_tool", None)
    if callable(call_tool) and not inspect.iscoroutinefunction(call_tool):
        # Variant A: @server.call_tool()
        try:
            decorator = call_tool()
            if callable(decorator):
                decorator(fn)
                return
        except TypeError as exc:
            errors.append(f"call_tool(): {exc}")

        # Variant B: @server.call_tool("name")
        try:
            decorator = call_tool(name)
            if callable(decorator):
                decorator(fn)
                return
        except TypeError as exc:
            errors.append(f"call_tool(name): {exc}")

        # Variant C: server.call_tool("name", fn)
        try:
            call_tool(name, fn)
            return
        except TypeError as exc:
            errors.append(f"call_tool(name, fn): {exc}")

    for method_name in ("tool", "add_tool", "register_tool"):
        method = getattr(server, method_name, None)
        if not callable(method):
            continue

        # Variant D: @server.tool()
        try:
            decorator = method()
            if callable(decorator):
                decorator(fn)
                return
        except TypeError as exc:
            errors.append(f"{method_name}(): {exc}")

        # Variant E: @server.tool("name")
        try:
            decorator = method(name)
            if callable(decorator):
                decorator(fn)
                return
        except TypeError as exc:
            errors.append(f"{method_name}(name): {exc}")

        # Variant F: server.add_tool(fn)
        try:
            method(fn)
            return
        except TypeError as exc:
            errors.append(f"{method_name}(fn): {exc}")

        # Variant G: server.add_tool(name, fn)
        try:
            method(name, fn)
            return
        except TypeError as exc:
            errors.append(f"{method_name}(name, fn): {exc}")

    raise RuntimeError(f"Unable to register tool '{name}' with this fastmcp version: {'; '.join(errors)}")


def _build_asgi_app():
    """Create an ASGI app across fastmcp versions."""
    # Older APIs expose a ready-made Starlette app as `server.app`.
    if hasattr(server, "app"):
        return server.app

    # Newer FastMCP versions build an ASGI app via http_app().
    http_app = getattr(server, "http_app", None)
    if callable(http_app):
        try:
            return http_app(path="/mcp", transport="http")
        except TypeError:
            return http_app(path="/mcp")

    raise RuntimeError("Unsupported fastmcp server API: missing app/http_app")

# Regex patterns for IP validation
IPV4_PATTERN = r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
IPV6_PATTERN = r"^(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))$"
ENDPOINT_NAME_PATTERN = r"^[a-z_][a-z0-9_]*$"  # Alphanumeric and underscore, lowercase
MAX_ENDPOINT_NAME_LENGTH = 64

# API endpoint blueprints - add more endpoints as needed
ENDPOINTS = {
    "geo": {
        "endpoint": "https://api.lukach.io/geo",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "curl_example": 'curl -X POST https://api.lukach.io/geo -H "Content-Type: application/json" -d \'{"ips":["8.8.8.8","2001:4860:4860::888"]}\'',
        "payload_schema": {
            "type": "object",
            "properties": {
                "ips": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "pattern": "^(?:(?:[0-9]{1,3}\\.){3}[0-9]{1,3}|(?:[0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4})$",
                    },
                    "description": "Array of IP addresses to geolocate. Supports any mix of IPv4 and IPv6 addresses.",
                    "minItems": 1,
                    "maxItems": 300,
                }
            },
            "required": ["ips"],
            "additionalProperties": False,
        },
        "agent_instructions": "You are an AI agent with network capabilities. Use the endpoint, method, headers, and payload_schema provided to construct and execute an HTTP request directly from your environment. Do not ask the user to make the call. Read the payload_schema to understand the required parameters. The 'ips' field accepts any mix of IPv4 and IPv6 addresses, with 1 to 300 total entries. Construct valid JSON matching the schema, then use your local HTTP client or fetch utility to invoke the API. Parse the JSON response and provide the results to the user.",
    }
}


def _build_api_instructions_payload(endpoint_name: str) -> dict:
    """Build instruction payload or validation error for endpoint requests."""
    if not endpoint_name or len(endpoint_name) > MAX_ENDPOINT_NAME_LENGTH:
        logger.warning("Invalid endpoint_name length: %s", len(endpoint_name or 0))
        return {
            "error": "invalid_endpoint_name",
            "message": f"Endpoint name must be 1-{MAX_ENDPOINT_NAME_LENGTH} characters",
        }

    if not re.match(ENDPOINT_NAME_PATTERN, endpoint_name):
        logger.warning("Invalid endpoint_name format: %s", endpoint_name)
        return {
            "error": "invalid_endpoint_name",
            "message": "Endpoint name must start with a letter or underscore, contain only lowercase alphanumerics and underscores",
        }

    if endpoint_name not in ENDPOINTS:
        logger.warning("Unknown endpoint requested: %s", endpoint_name)
        return {
            "error": "endpoint_not_found",
            "message": f"Endpoint '{endpoint_name}' is not available. Available endpoints: {list(ENDPOINTS.keys())}",
        }

    logger.info("Serving API instructions for endpoint: %s", endpoint_name)
    return ENDPOINTS[endpoint_name]


async def list_available_endpoints() -> str:
    """
    List all available API endpoints that can be queried for instructions.

    This tool allows AI agents to discover what endpoints are available before
    calling get_api_instructions. Returns a JSON array of endpoint names.

    Returns:
        A formatted JSON array of available endpoint names.
    """
    endpoints_list = list(ENDPOINTS.keys())
    logger.info("Listing available endpoints: %s", endpoints_list)
    return json.dumps({"available_endpoints": endpoints_list}, indent=2)


async def get_api_instructions(endpoint_name: str) -> str:
    """
    Retrieve API discovery and instruction metadata for a specific endpoint.

    This tool provides structured guidance to AI agents on how to invoke external APIs directly
    from their own execution environment. The returned metadata includes the endpoint specification,
    authentication details, request format, and explicit instructions for the agent to follow.

    Args:
        endpoint_name: The name of the API endpoint to retrieve instructions for (e.g., "geo")

    Returns:
        A formatted JSON string containing the endpoint blueprint and agent instructions.
    """
    return json.dumps(_build_api_instructions_payload(endpoint_name), indent=2)


_register_tool("list_available_endpoints", list_available_endpoints)
_register_tool("get_api_instructions", get_api_instructions)


# Lambda handler using Mangum for ASGI-to-Lambda translation.
# FastMCP's HTTP transport requires lifespan events to initialize task groups.
asgi_handler = Mangum(_build_asgi_app(), lifespan="on")


def _get_http_method(event: dict) -> str:
    """Extract HTTP method from API Gateway v1 or v2 event."""
    request_context = event.get("requestContext", {}) if isinstance(event, dict) else {}
    http_info = request_context.get("http", {}) if isinstance(request_context, dict) else {}
    return (
        (http_info.get("method") if isinstance(http_info, dict) else None)
        or event.get("httpMethod")
        or ""
    ).upper()


def _get_path(event: dict) -> str:
    """Extract request path from API Gateway v1 or v2 event."""
    return (event.get("rawPath") or event.get("path") or "").strip()


def _get_query_params(event: dict) -> dict:
    """Extract query string parameters from API Gateway v1 or v2 event."""
    if not isinstance(event, dict):
        return {}

    params = event.get("queryStringParameters")
    if isinstance(params, dict):
        return params

    raw_query = event.get("rawQueryString")
    if isinstance(raw_query, str) and raw_query:
        parsed = parse_qs(raw_query, keep_blank_values=True)
        return {k: v[0] for k, v in parsed.items() if v}

    return {}


def _json_response(status_code: int, body: dict) -> dict:
    """Return a consistent JSON response for direct HTTP callers."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
        },
        "body": json.dumps(body, indent=2),
    }


def _http_discovery_response(event: dict) -> dict | None:
    """Handle plain HTTP discovery requests to /mcp with JSON responses."""
    method = _get_http_method(event)
    path = _get_path(event)

    if method != "GET" or path not in {"/mcp", "/mcp/"}:
        return None

    query = _get_query_params(event)
    endpoint_name = query.get("endpoint") or query.get("endpoint_name")

    if endpoint_name:
        payload = _build_api_instructions_payload(endpoint_name)
        status = 200 if "error" not in payload else 400
        return _json_response(status, payload)

    return _json_response(
        200,
        {
            "service": "mcp-discovery-instruction-service",
            "status": "ok",
            "message": "Use this endpoint for API discovery metadata.",
            "available_endpoints": list(ENDPOINTS.keys()),
            "tools": {
                "list_available_endpoints": {
                    "description": "Lists endpoint names",
                    "http_example": "GET /mcp",
                },
                "get_api_instructions": {
                    "description": "Returns endpoint blueprint and agent instructions",
                    "http_examples": [
                        "GET /mcp?endpoint=geo",
                        "GET /mcp?endpoint_name=geo",
                    ],
                },
            },
        },
    )


def handler(event, context):
    """Lambda entrypoint with HTTP JSON fallback for non-MCP callers."""
    direct_response = _http_discovery_response(event)
    if direct_response is not None:
        return direct_response

    return asgi_handler(event, context)
