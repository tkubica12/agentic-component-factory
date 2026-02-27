"""Run the MCP server with StreamableHTTP transport."""
import uvicorn
from mcp_api_mock_gen.server import mcp

app = mcp.http_app(transport="streamable-http")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
