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

from fastmcp import Server
from mangum import Mangum

# Configure logging for production
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Initialize MCP server for Discovery and Instruction service
server = Server("mcp-discovery-instruction-service")

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


@server.call_tool()
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


@server.call_tool()
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
    # Validate endpoint_name input
    if not endpoint_name or len(endpoint_name) > MAX_ENDPOINT_NAME_LENGTH:
        logger.warning("Invalid endpoint_name length: %s", len(endpoint_name or 0))
        return json.dumps(
            {
                "error": "invalid_endpoint_name",
                "message": f"Endpoint name must be 1-{MAX_ENDPOINT_NAME_LENGTH} characters",
            }
        )

    if not re.match(ENDPOINT_NAME_PATTERN, endpoint_name):
        logger.warning("Invalid endpoint_name format: %s", endpoint_name)
        return json.dumps(
            {
                "error": "invalid_endpoint_name",
                "message": "Endpoint name must start with a letter or underscore, contain only lowercase alphanumerics and underscores",
            }
        )

    if endpoint_name not in ENDPOINTS:
        logger.warning("Unknown endpoint requested: %s", endpoint_name)
        return json.dumps(
            {
                "error": "endpoint_not_found",
                "message": f"Endpoint '{endpoint_name}' is not available. Available endpoints: {list(ENDPOINTS.keys())}",
            }
        )

    blueprint = ENDPOINTS[endpoint_name]
    logger.info("Serving API instructions for endpoint: %s", endpoint_name)

    return json.dumps(blueprint, indent=2)


# Lambda handler using Mangum for ASGI-to-Lambda translation
handler = Mangum(server.app, lifespan="off")
