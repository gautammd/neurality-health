"""Booking storage (in-memory)."""
import random
import string
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Booking:
    confirmation_id: str
    patient_first: str
    patient_last: str
    patient_phone: str
    provider_id: str
    slot_start: str
    slot_end: str
    appointment_type: str
    location_id: str
    idempotency_key: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = "booked"


@dataclass
class BookingResult:
    confirmation_id: str
    status: str  # "booked" or "failed"
    reason: str | None = None


# In-memory storage
_bookings: dict[str, Booking] = {}
_idempotency_keys: dict[str, str] = {}  # key -> confirmation_id
_booked_slots: set[str] = set()  # "provider_id:slot_start"


def _generate_confirmation_id() -> str:
    chars = string.ascii_uppercase.replace("O", "").replace("I", "") + "23456789"
    return "".join(random.choices(chars, k=6))


def create_booking(
    patient_first: str,
    patient_last: str,
    patient_phone: str,
    provider_id: str,
    slot_start: str,
    slot_end: str,
    appointment_type: str,
    location_id: str,
    idempotency_key: str,
) -> BookingResult:
    """Create a booking (idempotent)."""
    # Check idempotency
    if idempotency_key in _idempotency_keys:
        existing_id = _idempotency_keys[idempotency_key]
        return BookingResult(
            confirmation_id=existing_id,
            status="booked",
            reason="Idempotent request - returning existing booking",
        )

    # Check slot availability
    slot_key = f"{provider_id}:{slot_start}"
    if slot_key in _booked_slots:
        return BookingResult(
            confirmation_id="",
            status="failed",
            reason="This time slot is no longer available",
        )

    # Create booking
    confirmation_id = _generate_confirmation_id()
    booking = Booking(
        confirmation_id=confirmation_id,
        patient_first=patient_first,
        patient_last=patient_last,
        patient_phone=patient_phone,
        provider_id=provider_id,
        slot_start=slot_start,
        slot_end=slot_end,
        appointment_type=appointment_type,
        location_id=location_id,
        idempotency_key=idempotency_key,
    )

    _bookings[confirmation_id] = booking
    _idempotency_keys[idempotency_key] = confirmation_id
    _booked_slots.add(slot_key)

    return BookingResult(confirmation_id=confirmation_id, status="booked")


def get_booking(confirmation_id: str) -> Booking | None:
    return _bookings.get(confirmation_id)


def reset_bookings() -> None:
    """Reset all bookings (for testing)."""
    _bookings.clear()
    _idempotency_keys.clear()
    _booked_slots.clear()
