"""MCP-compatible tools with Pydantic validation."""
import logging
import re
import sys
import uuid
from datetime import datetime, timedelta
from typing import Annotated

import structlog
from pydantic import BaseModel, Field, field_validator

from fixtures import (
    check_coverage,
    create_booking,
    get_availability_slots,
    get_procedure_code,
    PROVIDERS,
    LOCATIONS,
)

# Configure structlog to output to stderr (MCP uses stdout for JSON-RPC)
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
)
log = structlog.get_logger()

# ============================================
# Tool Schemas (Pydantic models)
# ============================================


class DateRange(BaseModel):
    start: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="Start date YYYY-MM-DD")]
    end: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="End date YYYY-MM-DD")]


class GetProviderAvailabilityInput(BaseModel):
    location_id: Annotated[str, Field(min_length=1, description="Location ID (e.g., loc-sj)")]
    provider_id: Annotated[str, Field(min_length=1, description="Provider ID (e.g., prov-001)")]
    date_range: DateRange
    appointment_type: Annotated[str, Field(min_length=1, description="e.g., cleaning, checkup")]


class GetProviderAvailabilityOutput(BaseModel):
    slots: list[dict]


class PatientInfo(BaseModel):
    first: Annotated[str, Field(min_length=1)]
    last: Annotated[str, Field(min_length=1)]
    phone: Annotated[str, Field(pattern=r"^\+1\d{10}$", description="E.164 format")]


class SlotInfo(BaseModel):
    start: str
    end: str


class BookAppointmentInput(BaseModel):
    patient: PatientInfo
    provider_id: str
    slot: SlotInfo
    appointment_type: str
    location_id: str
    idempotency_key: Annotated[str, Field(min_length=1)]


class BookAppointmentOutput(BaseModel):
    confirmation_id: str
    status: str
    reason: str | None = None


class CheckInsuranceCoverageInput(BaseModel):
    payer: Annotated[str, Field(min_length=1, description="Insurance company name")]
    plan: Annotated[str, Field(min_length=1, description="Plan type (PPO, HMO, etc.)")]
    procedure_code: Annotated[str, Field(min_length=1, description="Procedure code (e.g., D1110)")]
    dob: str | None = None


class CheckInsuranceCoverageOutput(BaseModel):
    covered: bool
    copay_estimate: float
    notes: str | None = None


class SendSmsInput(BaseModel):
    to: Annotated[str, Field(pattern=r"^\+1\d{10}$")]
    message: Annotated[str, Field(min_length=1, max_length=1600)]


class SendSmsOutput(BaseModel):
    queued: bool
    message_id: str | None = None


# ============================================
# Tool Implementations
# ============================================

_sms_log: list[dict] = []


def check_insurance_coverage(input: CheckInsuranceCoverageInput) -> CheckInsuranceCoverageOutput:
    """Check if insurance covers a procedure."""
    result = check_coverage(input.payer, input.plan, input.procedure_code)
    log.info(
        "check_insurance_coverage",
        payer=input.payer,
        plan=input.plan,
        procedure_code=input.procedure_code,
        covered=result["covered"],
    )
    return CheckInsuranceCoverageOutput(
        covered=result["covered"],
        copay_estimate=result["copay_estimate"],
        notes=result.get("notes"),
    )


def get_provider_availability(input: GetProviderAvailabilityInput) -> GetProviderAvailabilityOutput:
    """Get available appointment slots."""
    # Validate provider exists
    provider = next((p for p in PROVIDERS if p.id == input.provider_id), None)
    if not provider:
        log.warning("provider_not_found", provider_id=input.provider_id)
        return GetProviderAvailabilityOutput(slots=[])

    # Validate location exists
    location = next((l for l in LOCATIONS if l.id == input.location_id), None)
    if not location:
        log.warning("location_not_found", location_id=input.location_id)
        return GetProviderAvailabilityOutput(slots=[])

    slots = get_availability_slots(
        input.location_id,
        input.provider_id,
        input.date_range.start,
        input.date_range.end,
        input.appointment_type,
    )
    log.info(
        "get_provider_availability",
        provider_id=input.provider_id,
        location_id=input.location_id,
        slots_found=len(slots),
    )
    return GetProviderAvailabilityOutput(slots=slots)


def book_appointment(input: BookAppointmentInput) -> BookAppointmentOutput:
    """Book an appointment (idempotent)."""
    result = create_booking(
        patient_first=input.patient.first,
        patient_last=input.patient.last,
        patient_phone=input.patient.phone,
        provider_id=input.provider_id,
        slot_start=input.slot.start,
        slot_end=input.slot.end,
        appointment_type=input.appointment_type,
        location_id=input.location_id,
        idempotency_key=input.idempotency_key,
    )
    log.info(
        "book_appointment",
        confirmation_id=result.confirmation_id,
        status=result.status,
        patient_phone_last4=input.patient.phone[-4:],
    )
    return BookAppointmentOutput(
        confirmation_id=result.confirmation_id,
        status=result.status,
        reason=result.reason,
    )


def send_sms(input: SendSmsInput) -> SendSmsOutput:
    """Send an SMS (mock)."""
    message_id = f"sms_{uuid.uuid4()}"
    _sms_log.append({
        "id": message_id,
        "to": input.to,
        "message": input.message,
        "sent_at": datetime.now().isoformat(),
    })
    log.info("send_sms", message_id=message_id, to_last4=input.to[-4:])
    return SendSmsOutput(queued=True, message_id=message_id)


def get_sms_log() -> list[dict]:
    """Get SMS log (for testing)."""
    return _sms_log.copy()


def clear_sms_log() -> None:
    """Clear SMS log (for testing)."""
    _sms_log.clear()


# ============================================
# Tool Definitions for LLM Function Calling
# ============================================

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "check_insurance_coverage",
            "description": "Check if a patient's insurance covers a dental procedure and get the copay estimate",
            "parameters": {
                "type": "object",
                "properties": {
                    "payer": {"type": "string", "description": "Insurance company (e.g., Delta Dental, Cigna, Aetna)"},
                    "plan": {"type": "string", "description": "Plan type (e.g., PPO, HMO, DMO)"},
                    "procedure_code": {"type": "string", "description": "Dental procedure code (e.g., D1110 for cleaning)"},
                },
                "required": ["payer", "plan", "procedure_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_provider_availability",
            "description": "Get available appointment slots for a provider at a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location_id": {"type": "string", "description": "Location ID (loc-sj for San Jose, loc-sf for San Francisco, loc-oak for Oakland)"},
                    "provider_id": {"type": "string", "description": "Provider ID (default: prov-001)"},
                    "date_range": {
                        "type": "object",
                        "properties": {
                            "start": {"type": "string", "description": "Start date YYYY-MM-DD"},
                            "end": {"type": "string", "description": "End date YYYY-MM-DD"},
                        },
                        "required": ["start", "end"],
                    },
                    "appointment_type": {"type": "string", "description": "Type of appointment (cleaning, checkup, etc.)"},
                },
                "required": ["location_id", "provider_id", "date_range", "appointment_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Book an appointment for a patient. Requires patient info, slot, and idempotency key.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient": {
                        "type": "object",
                        "properties": {
                            "first": {"type": "string"},
                            "last": {"type": "string"},
                            "phone": {"type": "string", "description": "Phone in E.164 format (+1XXXXXXXXXX)"},
                        },
                        "required": ["first", "last", "phone"],
                    },
                    "provider_id": {"type": "string"},
                    "slot": {
                        "type": "object",
                        "properties": {
                            "start": {"type": "string", "description": "ISO datetime"},
                            "end": {"type": "string", "description": "ISO datetime"},
                        },
                        "required": ["start", "end"],
                    },
                    "appointment_type": {"type": "string"},
                    "location_id": {"type": "string"},
                    "idempotency_key": {"type": "string", "description": "Unique key to prevent duplicate bookings"},
                },
                "required": ["patient", "provider_id", "slot", "appointment_type", "location_id", "idempotency_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_sms",
            "description": "Send an SMS confirmation to the patient",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Phone number in E.164 format (+1XXXXXXXXXX)"},
                    "message": {"type": "string", "description": "SMS message content"},
                },
                "required": ["to", "message"],
            },
        },
    },
]


# ============================================
# Tool Executor
# ============================================

def execute_tool(name: str, arguments: dict) -> dict:
    """Execute a tool by name with validation."""
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
            return {"error": f"Unknown tool: {name}"}

        return result.model_dump()
    except Exception as e:
        log.error("tool_execution_error", tool=name, error=str(e))
        return {"error": str(e)}
