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
- **Region**: us-east-2, deployed via AWS CDK
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
  "method": "POST",
  "headers": {
    "Content-Type": "application/json"
  },
  "curl_example": "curl -X POST https://api.lukach.io/geo -H \"Content-Type: application/json\" -d '{\"ips\":[\"8.8.8.8\",\"2001:4860:4860::888\"]}'",
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
    "required": ["ips"],
    "additionalProperties": false
  },
  "agent_instructions": "You are an AI agent with network capabilities. Use the endpoint, method, headers, and payload_schema provided to construct and execute an HTTP request directly from your environment..."
}
```

For the geo endpoint, ips can contain any combination of IPv4 and IPv6 addresses, with a total count from 1 to 300.

## Deployment

### Prerequisites
- AWS CDK v2.260+
- Python 3.12+
- fastmcp and mangum packages in `packages-use2-lukach-io` S3 bucket as layer zips
- SSM parameter `/account/api` containing cross-account API Gateway account ID

### Deploy
```bash
cdk deploy
```

### Outputs
- `ServiceLambdaName`: Lambda function name (`mcp-service`)
- `ServiceLambdaArn`: Full Lambda ARN

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