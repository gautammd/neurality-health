"""Tests for fixture data."""
import pytest

from fixtures import (
    PROVIDERS,
    LOCATIONS,
    get_availability_slots,
    find_location_by_city,
    find_provider_for_location,
    check_coverage,
    get_procedure_code,
    create_booking,
    get_booking,
    reset_bookings,
)


@pytest.fixture(autouse=True)
def reset_state():
    """Reset state before each test."""
    reset_bookings()
    yield


class TestProviders:
    """Tests for provider data."""

    def test_providers_exist(self):
        """Test providers are defined."""
        assert len(PROVIDERS) >= 3

    def test_provider_has_required_fields(self):
        """Test provider has all required fields."""
        provider = PROVIDERS[0]
        assert provider.id
        assert provider.name
        assert provider.specialty
        assert len(provider.location_ids) > 0

    def test_find_provider_for_location(self):
        """Test finding provider by location."""
        provider = find_provider_for_location("loc-sj")
        assert provider is not None
        assert "loc-sj" in provider.location_ids

    def test_find_provider_for_invalid_location(self):
        """Test finding provider for invalid location."""
        provider = find_provider_for_location("loc-invalid")
        assert provider is None


class TestLocations:
    """Tests for location data."""

    def test_locations_exist(self):
        """Test locations are defined."""
        assert len(LOCATIONS) >= 3

    def test_location_has_required_fields(self):
        """Test location has all required fields."""
        location = LOCATIONS[0]
        assert location.id
        assert location.name
        assert location.address
        assert location.city
        assert location.state

    def test_find_location_by_city(self):
        """Test finding location by city."""
        location = find_location_by_city("San Jose")
        assert location is not None
        assert location.id == "loc-sj"

    def test_find_location_by_city_case_insensitive(self):
        """Test city search is case insensitive."""
        location = find_location_by_city("san francisco")
        assert location is not None
        assert location.id == "loc-sf"

    def test_find_location_invalid_city(self):
        """Test finding invalid city returns None."""
        location = find_location_by_city("New York")
        assert location is None


class TestAvailabilitySlots:
    """Tests for availability slot generation."""

    def test_generates_slots_for_weekdays(self):
        """Test generates slots for weekdays."""
        # Monday to Tuesday (2 weekdays)
        slots = get_availability_slots(
            "loc-sj", "prov-001", "2025-01-13", "2025-01-14", "cleaning"
        )
        # 6 slots per day (9, 10, 11, 14, 15, 16)
        assert len(slots) == 12

    def test_skips_weekends(self):
        """Test skips weekend days."""
        # Saturday and Sunday
        slots = get_availability_slots(
            "loc-sj", "prov-001", "2025-01-11", "2025-01-12", "cleaning"
        )
        assert len(slots) == 0

    def test_returns_empty_for_invalid_provider(self):
        """Test returns empty for non-existent provider."""
        slots = get_availability_slots(
            "loc-sj", "prov-999", "2025-01-13", "2025-01-14", "cleaning"
        )
        assert len(slots) == 0

    def test_returns_empty_for_provider_not_at_location(self):
        """Test returns empty when provider not at location."""
        # prov-002 only works at loc-sj
        slots = get_availability_slots(
            "loc-sf", "prov-002", "2025-01-13", "2025-01-14", "cleaning"
        )
        assert len(slots) == 0

    def test_slots_have_start_and_end(self):
        """Test each slot has start and end times."""
        slots = get_availability_slots(
            "loc-sj", "prov-001", "2025-01-13", "2025-01-13", "cleaning"
        )
        for slot in slots:
            assert "start" in slot
            assert "end" in slot


class TestInsurance:
    """Tests for insurance coverage data."""

    def test_check_coverage_known_plan(self):
        """Test checking coverage for known plan."""
        result = check_coverage("Delta Dental", "PPO", "D1110")
        assert result["covered"] is True
        assert result["copay_estimate"] == 25

    def test_check_coverage_unknown_plan(self):
        """Test checking coverage for unknown plan."""
        result = check_coverage("Unknown", "Plan", "D1110")
        assert result["covered"] is False
        assert "cash-pay" in result["notes"].lower()

    def test_get_procedure_code_cleaning(self):
        """Test getting procedure code for cleaning."""
        code = get_procedure_code("cleaning")
        assert code == "D1110"

    def test_get_procedure_code_case_insensitive(self):
        """Test procedure code lookup is case insensitive."""
        code = get_procedure_code("CLEANING")
        assert code == "D1110"

    def test_get_procedure_code_unknown(self):
        """Test unknown procedure returns default code."""
        code = get_procedure_code("unknown procedure")
        assert code == "D9310"  # Consultation code as default


class TestBookings:
    """Tests for booking management."""

    def test_create_booking(self):
        """Test creating a booking."""
        result = create_booking(
            patient_first="John",
            patient_last="Doe",
            patient_phone="+14085551234",
            provider_id="prov-001",
            slot_start="2025-01-13T09:00:00",
            slot_end="2025-01-13T10:00:00",
            appointment_type="cleaning",
            location_id="loc-sj",
            idempotency_key="test-key-1",
        )

        assert result.status == "booked"
        assert len(result.confirmation_id) == 6

    def test_get_booking(self):
        """Test retrieving a booking."""
        result = create_booking(
            patient_first="Jane",
            patient_last="Smith",
            patient_phone="+14085555678",
            provider_id="prov-001",
            slot_start="2025-01-14T10:00:00",
            slot_end="2025-01-14T11:00:00",
            appointment_type="checkup",
            location_id="loc-sj",
            idempotency_key="test-key-2",
        )

        booking = get_booking(result.confirmation_id)
        assert booking is not None
        assert booking.patient_first == "Jane"
        assert booking.patient_last == "Smith"

    def test_get_booking_not_found(self):
        """Test retrieving non-existent booking."""
        booking = get_booking("NOTFOUND")
        assert booking is None

    def test_idempotent_booking(self):
        """Test idempotent booking returns same result."""
        result1 = create_booking(
            patient_first="Bob",
            patient_last="Wilson",
            patient_phone="+14085559999",
            provider_id="prov-001",
            slot_start="2025-01-15T09:00:00",
            slot_end="2025-01-15T10:00:00",
            appointment_type="cleaning",
            location_id="loc-sj",
            idempotency_key="idempotent-key",
        )

        result2 = create_booking(
            patient_first="Bob",
            patient_last="Wilson",
            patient_phone="+14085559999",
            provider_id="prov-001",
            slot_start="2025-01-15T09:00:00",
            slot_end="2025-01-15T10:00:00",
            appointment_type="cleaning",
            location_id="loc-sj",
            idempotency_key="idempotent-key",
        )

        assert result1.confirmation_id == result2.confirmation_id

    def test_double_booking_fails(self):
        """Test booking same slot with different key fails."""
        create_booking(
            patient_first="First",
            patient_last="Patient",
            patient_phone="+14085551111",
            provider_id="prov-001",
            slot_start="2025-01-16T09:00:00",
            slot_end="2025-01-16T10:00:00",
            appointment_type="cleaning",
            location_id="loc-sj",
            idempotency_key="first-key",
        )

        result2 = create_booking(
            patient_first="Second",
            patient_last="Patient",
            patient_phone="+14085552222",
            provider_id="prov-001",
            slot_start="2025-01-16T09:00:00",
            slot_end="2025-01-16T10:00:00",
            appointment_type="cleaning",
            location_id="loc-sj",
            idempotency_key="second-key",
        )

        assert result2.status == "failed"
        assert "no longer available" in result2.reason.lower()
