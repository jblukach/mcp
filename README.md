# MCP Discovery and Instruction Service

A serverless Model Context Protocol (MCP) server that acts as a **Discovery and Instruction Service** for AI agents. This service teaches external AI agents how to invoke APIs directly from their own execution environment, without executing API calls itself.

## Purpose

This MCP server is designed to be called by AI agents (via HTTP API Gateway integration) to:
1. **Discover available API endpoints** - Agents call `list_available_endpoints()` to see what's available
2. **Retrieve endpoint instructions** - Agents call `get_api_instructions("endpoint_name")` to get the full specification
3. **Make direct API calls** - Agents use the returned metadata (endpoint, method, headers, schema, curl example, agent instructions) to invoke APIs from their own environment

The service provides structured, production-ready guidance to AI agents on request/response formats, authentication, and direct invocation patterns.

## Architecture

- **Framework**: FastMCP with Mangum ASGI-to-Lambda adapter
- **Runtime**: Python 3.13 on ARM64 (cost-optimized)
- **Memory**: 256 MB, 30s timeout
- **Layers**: fastmcp and mangum from shared S3 layer package bucket
- **Regions**: us-east-1, us-east-2, and us-west-2, deployed via AWS CDK
- **Cross-Account**: Callable from API Gateway in a different AWS account via SSM-backed permission

## Available Tools

### `list_available_endpoints()`
Returns a JSON array of available endpoint names.

**Response:**
```json
{
  "available_endpoints": ["geo"]
}
```

### `get_api_instructions(endpoint_name: str)`
Returns the full API blueprint for a specific endpoint, including:
- Endpoint URL
- HTTP method
- Required headers
- Payload JSON Schema
- curl example
- Agent instructions for direct invocation

**Parameters:**
- `endpoint_name` (string): Name of the endpoint (e.g., "geo")

**Response (example for "geo"):**
```json
{
  "endpoint": "https://api.lukach.io/geo",
  "endpoints": {
    "failover": {
      "url": "https://api.lukach.io/geo",
      "primary_region": "us-east-1",
      "secondary_region": "us-west-2"
    },
    "regional": {
      "us-east-1": "https://use1.api.lukach.io/geo",
      "us-east-2": "https://use2.api.lukach.io/geo",
      "us-west-2": "https://usw2.api.lukach.io/geo"
    }
  },
  "method": "POST",
  "headers": {
    "Content-Type": "application/json"
  },
  "curl_examples": [
    "curl 'https://api.lukach.io/geo?ip=1.1.1.1'",
    "curl 'https://api.lukach.io/geo/1.1.1.1'",
    "curl -X POST https://api.lukach.io/geo -H \"Content-Type: application/json\" -d '{\"ips\":[\"8.8.8.8\",\"2001:4860:4860::888\"]}'"
  ],
  "payload_schema": {
    "type": "object",
    "properties": {
      "ips": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Array of IP addresses to geolocate. Supports any mix of IPv4 and IPv6 addresses.",
        "minItems": 1,
        "maxItems": 300
      }
    },
    "anyOf": [{"required": ["ip"]}, {"required": ["ips"]}],
    "additionalProperties": false
  },
  "agent_instructions": "You are an AI agent with network capabilities. Use the endpoint, method, headers, and payload_schema provided to construct and execute an HTTP request directly from your environment..."
}
```

For the geo endpoint, use `GET /geo` without an IP to look up the request source, `GET /geo?ip=...` or `GET /geo/{ip}` for explicit lookups, or `POST /geo` with either `ip` (one address) or `ips` (1 to 300 mixed IPv4 and IPv6 addresses). Query values may be repeated or comma-separated.

Use `https://api.lukach.io/geo` for normal public traffic. Route53 failover serves `api.lukach.io` from `us-east-1` as primary and `us-west-2` as secondary. Use the regional endpoints when testing a specific region or intentionally bypassing failover DNS:

- `https://use1.api.lukach.io/geo` for `us-east-1`
- `https://use2.api.lukach.io/geo` for `us-east-2`
- `https://usw2.api.lukach.io/geo` for `us-west-2`

The geo service also exposes its own MCP JSON-RPC surface at `https://api.lukach.io/mcp?endpoint=geo`, with regional equivalents at `https://use1.api.lukach.io/mcp?endpoint=geo`, `https://use2.api.lukach.io/mcp?endpoint=geo`, and `https://usw2.api.lukach.io/mcp?endpoint=geo`. The MCP tool is named `geo_lookup`, supports protocol version `2025-03-26`, and accepts the same `ip` or `ips` arguments. Authorized AWS workloads can invoke the `search` Lambda directly in `us-east-1`, `us-east-2`, or `us-west-2` with the same JSON keys.

Geo responses include ordered `results`; each successful entry can contain `asn.id`, `asn.org`, `asn.net`, `geo.country`, `geo.state`, `geo.city`, and `geo.cidr`. Top-level responses include `requested_count`, MaxMind attribution, `timestamp_utc`, serving `region`, and `geolite2-asn.mmdb` / `geolite2-city.mmdb` metadata when available. Invalid addresses are returned in order with entry-level `error` values.

## Direct HTTP Access

The Lambda now supports plain HTTP GET requests to `/mcp` for browser, curl, and non-MCP AI callers.

- `GET /mcp`: Returns discovery JSON and available endpoint names
- `GET /mcp?endpoint=geo`: Returns the same JSON blueprint as `get_api_instructions("geo")`
- `GET /mcp?endpoint_name=geo`: Alias for the same behavior

Examples:

```bash
curl https://api.lukach.io/mcp
curl "https://api.lukach.io/mcp?endpoint=geo"
curl "https://use1.api.lukach.io/mcp?endpoint=geo"
curl "https://use2.api.lukach.io/mcp?endpoint=geo"
curl "https://usw2.api.lukach.io/mcp?endpoint=geo"
```

## MCP Client Access

For MCP protocol requests (for example `initialize`), clients must include an `Accept` header that contains both `application/json` and `text/event-stream`.

- If this header is missing, the service returns `406 Not Acceptable`.
- With the correct header, `initialize` succeeds and returns an SSE response with `content-type: text/event-stream` and an `mcp-session-id` header.

Example initialize probe:

```bash
curl -i -X POST https://api.lukach.io/mcp \
  -H "content-type: application/json" \
  -H "accept: application/json, text/event-stream" \
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl-probe","version":"1.0.0"}}}'
```

### Short natural-language example

If your chat client has this MCP server configured, a concise prompt can be as simple as:

```text
Use api-lukach-io to geolocate 8.8.8.8.
```

You can also ask for a slightly richer result:

```text
Use api-lukach-io to geolocate 8.8.8.8 and return the city, state, country, and ASN owner.
```

## Deployment

### Prerequisites
- AWS CDK v2.260+
- Python 3.12+
- fastmcp and mangum packages in `packages-use1-lukach-io`, `packages-use2-lukach-io`, and `packages-usw2-lukach-io` S3 buckets as layer zips
- SSM parameter `/account/api` containing cross-account API Gateway account ID

### Deploy
```bash
cdk deploy --all
```

This synthesizes and deploys `McpStackUSE1`, `McpStack`, and `McpStackUSW2` for `us-east-1`, `us-east-2`, and `us-west-2` respectively. `McpStack` remains the `us-east-2` stack name so existing deployments update in place instead of attempting to recreate the named `mcp-service` Lambda.

### Outputs
- `ServiceLambdaName`: Lambda function name (`mcp-service`) for each regional stack
- `ServiceLambdaArn`: Full regional Lambda ARN for each regional stack

## Cross-Account API Gateway Integration

The service is automatically configured to accept invocations from:
1. The account ID specified in `/account/api` SSM parameter
2. API Gateway service principal

To integrate from another AWS account, ensure the SSM parameter `/account/api` in this account contains your calling account ID.

## Customization

Add new endpoints by extending the `ENDPOINTS` dict in `service/service.py`:

```python
ENDPOINTS = {
    "your_endpoint": {
        "endpoint": "https://api.example.com/endpoint",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "curl_example": "...",
        "payload_schema": {...},
        "agent_instructions": "..."
    }
}
```

## Logging

Logs are stored in CloudWatch with 7-day retention in `/aws/lambda/mcp-service`.