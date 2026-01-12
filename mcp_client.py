"""MCP Client for calling tools via MCP server."""
import json
import sys
import time
from pathlib import Path
from typing import Any

import structlog
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

log = structlog.get_logger()

MCP_SERVER_PATH = str(Path(__file__).parent / "mcp_server.py")

# Metrics
_metrics = {"tool_calls": 0, "tool_errors": 0, "latencies_ms": []}

# Circuit breaker
_circuit = {"failures": 0, "threshold": 5, "reset_after": 30, "opened_at": None, "state": "closed"}


def get_metrics() -> dict:
    latencies = _metrics["latencies_ms"]
    return {
        "tool_calls": _metrics["tool_calls"],
        "tool_errors": _metrics["tool_errors"],
        "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0,
    }


async def call_mcp_tool(name: str, arguments: dict[str, Any]) -> dict:
    """Call MCP tool with fresh connection per call."""
    _metrics["tool_calls"] += 1

    # Circuit breaker check
    if _circuit["state"] == "open":
        if time.time() - (_circuit["opened_at"] or 0) < _circuit["reset_after"]:
            return {"error": "Circuit breaker open"}
        _circuit["state"] = "half-open"

    start_time = time.time()

    try:
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[MCP_SERVER_PATH],
            cwd=str(Path(__file__).parent),
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments)

                _metrics["latencies_ms"].append((time.time() - start_time) * 1000)
                _circuit["failures"] = 0
                _circuit["state"] = "closed"

                if result.content and len(result.content) > 0:
                    return json.loads(result.content[0].text)
                return {"error": "Empty response"}

    except Exception as e:
        _metrics["tool_errors"] += 1
        _circuit["failures"] += 1

        if _circuit["failures"] >= _circuit["threshold"]:
            _circuit["state"] = "open"
            _circuit["opened_at"] = time.time()

        log.error("mcp_tool_failed", tool=name, error=str(e))
        return {"error": str(e)}
