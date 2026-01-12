"""MCP Client for calling tools via MCP server."""
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import structlog
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

log = structlog.get_logger()

# Get the directory where this file is located
MCP_SERVER_PATH = str(Path(__file__).parent / "mcp_server.py")

# Metrics tracking
_metrics = {
    "tool_calls": 0,
    "tool_errors": 0,
    "tool_retries": 0,
    "latencies_ms": [],
}


def get_metrics() -> dict:
    """Get current metrics."""
    latencies = _metrics["latencies_ms"]
    return {
        "tool_calls": _metrics["tool_calls"],
        "tool_errors": _metrics["tool_errors"],
        "tool_retries": _metrics["tool_retries"],
        "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0,
        "p95_latency_ms": sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) >= 20 else None,
    }


def reset_metrics() -> None:
    """Reset metrics (for testing)."""
    _metrics["tool_calls"] = 0
    _metrics["tool_errors"] = 0
    _metrics["tool_retries"] = 0
    _metrics["latencies_ms"] = []


class MCPToolClient:
    """Client for calling MCP tools with retry logic."""

    def __init__(self, max_retries: int = 3, retry_delay: float = 0.5):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._session: ClientSession | None = None
        self._client_ctx = None
        self._connected = False

    async def connect(self) -> None:
        """Connect to MCP server."""
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[MCP_SERVER_PATH],
            cwd=str(Path(__file__).parent),
        )
        self._client_ctx = stdio_client(server_params)
        read, write = await self._client_ctx.__aenter__()
        self._session = ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()
        self._connected = True
        log.info("mcp_client_connected")

    async def disconnect(self) -> None:
        """Disconnect from MCP server."""
        if self._session:
            await self._session.__aexit__(None, None, None)
        if self._client_ctx:
            await self._client_ctx.__aexit__(None, None, None)
        self._connected = False
        log.info("mcp_client_disconnected")

    async def ensure_connected(self) -> None:
        """Ensure client is connected, reconnect if needed."""
        if not self._connected:
            await self.connect()

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict:
        """Call a tool with retry logic."""
        _metrics["tool_calls"] += 1
        last_error = None

        for attempt in range(self.max_retries):
            start_time = time.time()
            try:
                await self.ensure_connected()

                if not self._session:
                    raise RuntimeError("MCP client not connected")

                result = await self._session.call_tool(name, arguments)

                # Track latency
                latency_ms = (time.time() - start_time) * 1000
                _metrics["latencies_ms"].append(latency_ms)

                # Parse result
                if result.content and len(result.content) > 0:
                    text = result.content[0].text
                    return json.loads(text)

                return {"error": "Empty response from MCP server"}

            except Exception as e:
                last_error = e
                self._connected = False  # Mark as disconnected for retry
                log.warning(
                    "mcp_tool_retry",
                    tool=name,
                    attempt=attempt + 1,
                    error=str(e),
                )
                if attempt < self.max_retries - 1:
                    _metrics["tool_retries"] += 1
                    await asyncio.sleep(self.retry_delay * (attempt + 1))  # Exponential backoff

        _metrics["tool_errors"] += 1
        log.error("mcp_tool_failed", tool=name, error=str(last_error))
        return {"error": f"Tool call failed after {self.max_retries} attempts: {last_error}"}


# Singleton client instance
_client: MCPToolClient | None = None


async def get_mcp_client() -> MCPToolClient:
    """Get or create MCP client singleton."""
    global _client
    if _client is None:
        _client = MCPToolClient()
        await _client.connect()
    return _client


async def call_mcp_tool(name: str, arguments: dict[str, Any]) -> dict:
    """Convenience function to call MCP tool."""
    client = await get_mcp_client()
    return await client.call_tool(name, arguments)
