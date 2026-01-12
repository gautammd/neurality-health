"""MCP Server exposing dental office tools."""
import asyncio
import json
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from tools import (
    CheckInsuranceCoverageInput,
    CheckInsuranceCoverageOutput,
    GetProviderAvailabilityInput,
    GetProviderAvailabilityOutput,
    BookAppointmentInput,
    BookAppointmentOutput,
    SendSmsInput,
    SendSmsOutput,
    check_insurance_coverage,
    get_provider_availability,
    book_appointment,
    send_sms,
)

# MCP uses stdout for JSON-RPC, so redirect all logging to stderr
logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

# Create MCP server
server = Server("neurality-health-tools")

# Tool JSON schemas
TOOL_SCHEMAS = {
    "check_insurance_coverage": {
        "type": "object",
        "properties": {
            "payer": {"type": "string", "description": "Insurance company name"},
            "plan": {"type": "string", "description": "Plan type (PPO, HMO, etc.)"},
            "procedure_code": {"type": "string", "description": "Procedure code (e.g., D1110)"},
            "dob": {"type": "string", "description": "Date of birth (optional)"},
        },
        "required": ["payer", "plan", "procedure_code"],
    },
    "get_provider_availability": {
        "type": "object",
        "properties": {
            "location_id": {"type": "string", "description": "Location ID"},
            "provider_id": {"type": "string", "description": "Provider ID"},
            "date_range": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "Start date YYYY-MM-DD"},
                    "end": {"type": "string", "description": "End date YYYY-MM-DD"},
                },
                "required": ["start", "end"],
            },
            "appointment_type": {"type": "string", "description": "Type of appointment"},
        },
        "required": ["location_id", "provider_id", "date_range", "appointment_type"],
    },
    "book_appointment": {
        "type": "object",
        "properties": {
            "patient": {
                "type": "object",
                "properties": {
                    "first": {"type": "string"},
                    "last": {"type": "string"},
                    "phone": {"type": "string", "description": "E.164 format"},
                },
                "required": ["first", "last", "phone"],
            },
            "provider_id": {"type": "string"},
            "slot": {
                "type": "object",
                "properties": {
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                },
                "required": ["start", "end"],
            },
            "appointment_type": {"type": "string"},
            "location_id": {"type": "string"},
            "idempotency_key": {"type": "string"},
        },
        "required": ["patient", "provider_id", "slot", "appointment_type", "location_id", "idempotency_key"],
    },
    "send_sms": {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Phone in E.164 format"},
            "message": {"type": "string", "description": "SMS content"},
        },
        "required": ["to", "message"],
    },
}


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="check_insurance_coverage",
            description="Check if insurance covers a dental procedure and get copay estimate",
            inputSchema=TOOL_SCHEMAS["check_insurance_coverage"],
        ),
        Tool(
            name="get_provider_availability",
            description="Get available appointment slots for a provider",
            inputSchema=TOOL_SCHEMAS["get_provider_availability"],
        ),
        Tool(
            name="book_appointment",
            description="Book an appointment (idempotent with idempotency_key)",
            inputSchema=TOOL_SCHEMAS["book_appointment"],
        ),
        Tool(
            name="send_sms",
            description="Send SMS confirmation to patient",
            inputSchema=TOOL_SCHEMAS["send_sms"],
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a tool and return result."""
    try:
        if name == "check_insurance_coverage":
            input_model = CheckInsuranceCoverageInput(**arguments)
            result = check_insurance_coverage(input_model)
        elif name == "get_provider_availability":
            input_model = GetProviderAvailabilityInput(**arguments)
            result = get_provider_availability(input_model)
        elif name == "book_appointment":
            input_model = BookAppointmentInput(**arguments)
            result = book_appointment(input_model)
        elif name == "send_sms":
            input_model = SendSmsInput(**arguments)
            result = send_sms(input_model)
        else:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

        return [TextContent(type="text", text=json.dumps(result.model_dump()))]

    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
