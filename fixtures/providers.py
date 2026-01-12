"""Provider and location fixtures."""
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class Provider:
    id: str
    name: str
    specialty: str
    location_ids: list[str]


@dataclass
class Location:
    id: str
    name: str
    address: str
    city: str
    state: str


PROVIDERS = [
    Provider(
        id="prov-001",
        name="Dr. Sarah Chen",
        specialty="General Dentistry",
        location_ids=["loc-sj", "loc-sf"],
    ),
    Provider(
        id="prov-002",
        name="Dr. Michael Rodriguez",
        specialty="Orthodontics",
        location_ids=["loc-sj"],
    ),
    Provider(
        id="prov-003",
        name="Dr. Emily Thompson",
        specialty="General Dentistry",
        location_ids=["loc-sf", "loc-oak"],
    ),
]

LOCATIONS = [
    Location(
        id="loc-sj",
        name="San Jose Clinic",
        address="123 Main Street",
        city="San Jose",
        state="CA",
    ),
    Location(
        id="loc-sf",
        name="San Francisco Office",
        address="456 Market Street",
        city="San Francisco",
        state="CA",
    ),
    Location(
        id="loc-oak",
        name="Oakland Center",
        address="789 Broadway",
        city="Oakland",
        state="CA",
    ),
]


def get_availability_slots(
    location_id: str,
    provider_id: str,
    start_date: str,
    end_date: str,
    appointment_type: str,
) -> list[dict]:
    """Generate mock availability slots."""
    provider = next((p for p in PROVIDERS if p.id == provider_id), None)
    if not provider or location_id not in provider.location_ids:
        return []

    slots = []
    duration_minutes = 60 if "cleaning" in appointment_type.lower() else 30

    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)

    current = start
    while current <= end:
        # Skip weekends
        if current.weekday() < 5:
            # Morning slots: 9am, 10am, 11am
            for hour in [9, 10, 11]:
                slot_start = current.replace(hour=hour, minute=0, second=0, microsecond=0)
                slot_end = slot_start + timedelta(minutes=duration_minutes)
                slots.append({
                    "start": slot_start.isoformat(),
                    "end": slot_end.isoformat(),
                })
            # Afternoon slots: 2pm, 3pm, 4pm
            for hour in [14, 15, 16]:
                slot_start = current.replace(hour=hour, minute=0, second=0, microsecond=0)
                slot_end = slot_start + timedelta(minutes=duration_minutes)
                slots.append({
                    "start": slot_start.isoformat(),
                    "end": slot_end.isoformat(),
                })
        current += timedelta(days=1)

    return slots


def find_location_by_city(city: str) -> Location | None:
    """Find location by city name."""
    city_lower = city.lower().replace(" ", "")
    for loc in LOCATIONS:
        if city_lower in loc.city.lower().replace(" ", ""):
            return loc
    return None


def find_provider_for_location(location_id: str) -> Provider | None:
    """Find a provider for a given location."""
    for provider in PROVIDERS:
        if location_id in provider.location_ids:
            return provider
    return None
