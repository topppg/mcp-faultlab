"""Optional integration fixture using the official MCP Python SDK 1.30.0."""

from mcp.server.fastmcp import FastMCP

server = FastMCP("faultlab-sdk-fixture")


@server.tool()
def echo(message: str) -> dict[str, str]:
    """Return synthetic input unchanged."""
    return {"echo": message}


if __name__ == "__main__":
    server.run(transport="stdio")
