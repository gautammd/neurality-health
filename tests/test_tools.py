"""Tests for MCP tools."""
import pytest
from pydantic import ValidationError

from tools import (
    CheckInsuranceCoverageInput,
    CheckInsuranceCoverageOutput,
    GetProviderAvailabilityInput,
    BookAppointmentInput,
    SendSmsInput,
    check_insurance_coverage,
    get_provider_availability,
    book_appointment,
    send_sms,
    execute_tool,
    clear_sms_log,
    get_sms_log,
)
from fixtures import reset_bookings


@pytest.fixture(autouse=True)
def reset_state():
    """Reset state before each test."""
    reset_bookings()
    clear_sms_log()
    yield


class TestCheckInsuranceCoverage:
    """Tests for check_insurance_coverage tool."""

    def test_delta_dental_ppo_cleaning_covered(self):
        """Test Delta Dental PPO covers cleaning."""
        input_data = CheckInsuranceCoverageInput(
            payer="Delta Dental",
            plan="PPO",
            procedure_code="D1110",
        )
        result = check_insurance_coverage(input_data)

        assert result.covered is True
        assert result.copay_estimate == 25
        assert "twice per year" in (result.notes or "").lower()

    def test_aetna_dmo_crown_not_covered(self):
        """Test Aetna DMO doesn't cover crowns."""
        input_data = CheckInsuranceCoverageInput(
            payer="Aetna",
            plan="DMO",
            procedure_code="D2740",
        )
        result = check_insurance_coverage(input_data)

        assert result.covered is False
        assert "not covered" in (result.notes or "").lower()

    def test_unknown_payer_returns_cash_estimate(self):
        """Test unknown payer returns cash estimate."""
        input_data = CheckInsuranceCoverageInput(
            payer="Unknown Insurance",
            plan="Gold",
            procedure_code="D1110",
        )
        result = check_insurance_coverage(input_data)

        assert result.covered is False
        assert "cash-pay" in (result.notes or "").lower()

    def test_validation_requires_payer(self):
        """Test validation requires payer."""
        with pytest.raises(ValidationError):
            CheckInsuranceCoverageInput(
                payer="",
                plan="PPO",
                procedure_code="D1110",
            )


class TestGetProviderAvailability:
    """Tests for get_provider_availability tool."""

    def test_returns_slots_for_valid_provider_location(self):
        """Test returns slots for valid provider/location combo."""
        input_data = GetProviderAvailabilityInput(
            location_id="loc-sj",
            provider_id="prov-001",
            date_range={"start": "2025-01-13", "end": "2025-01-14"},
            appointment_type="cleaning",
        )
        result = get_provider_availability(input_data)

        assert len(result.slots) > 0
        # Each day has 6 slots (9, 10, 11, 14, 15, 16)
        assert len(result.slots) == 12  # 2 days * 6 slots

    def test_returns_empty_for_invalid_provider(self):
        """Test returns empty for non-existent provider."""
        input_data = GetProviderAvailabilityInput(
            location_id="loc-sj",
            provider_id="prov-999",
            date_range={"start": "2025-01-13", "end": "2025-01-14"},
            appointment_type="cleaning",
        )
        result = get_provider_availability(input_data)

        assert len(result.slots) == 0

    def test_returns_empty_for_provider_not_at_location(self):
        """Test returns empty when provider not at location."""
        # prov-002 only works at loc-sj, not loc-sf
        input_data = GetProviderAvailabilityInput(
            location_id="loc-sf",
            provider_id="prov-002",
            date_range={"start": "2025-01-13", "end": "2025-01-14"},
            appointment_type="cleaning",
        )
        result = get_provider_availability(input_data)

        assert len(result.slots) == 0


class TestBookAppointment:
    """Tests for book_appointment tool."""

    def test_successful_booking(self):
        """Test successful appointment booking."""
        input_data = BookAppointmentInput(
            patient={"first": "John", "last": "Doe", "phone": "+14085551234"},
            provider_id="prov-001",
            slot={"start": "2025-01-13T09:00:00", "end": "2025-01-13T10:00:00"},
            appointment_type="cleaning",
            location_id="loc-sj",
            idempotency_key="test-key-001",
        )
        result = book_appointment(input_data)

        assert result.status == "booked"
        assert len(result.confirmation_id) == 6
        assert result.reason is None

    def test_idempotent_booking(self):
        """Test idempotent booking returns same confirmation."""
        input_data = BookAppointmentInput(
            patient={"first": "Jane", "last": "Smith", "phone": "+14085555678"},
            provider_id="prov-001",
            slot={"start": "2025-01-14T10:00:00", "end": "2025-01-14T11:00:00"},
            appointment_type="checkup",
            location_id="loc-sj",
            idempotency_key="idempotent-key-001",
        )

        result1 = book_appointment(input_data)
        result2 = book_appointment(input_data)

        assert result1.confirmation_id == result2.confirmation_id
        assert result2.status == "booked"

    def test_double_booking_fails(self):
        """Test booking same slot with different key fails."""
        input_data1 = BookAppointmentInput(
            patient={"first": "First", "last": "Patient", "phone": "+14085551111"},
            provider_id="prov-001",
            slot={"start": "2025-01-15T09:00:00", "end": "2025-01-15T10:00:00"},
            appointment_type="cleaning",
            location_id="loc-sj",
            idempotency_key="first-booking",
        )
        input_data2 = BookAppointmentInput(
            patient={"first": "Second", "last": "Patient", "phone": "+14085552222"},
            provider_id="prov-001",
            slot={"start": "2025-01-15T09:00:00", "end": "2025-01-15T10:00:00"},
            appointment_type="cleaning",
            location_id="loc-sj",
            idempotency_key="second-booking",
        )

        result1 = book_appointment(input_data1)
        result2 = book_appointment(input_data2)

        assert result1.status == "booked"
        assert result2.status == "failed"
        assert "no longer available" in (result2.reason or "").lower()

    def test_phone_validation(self):
        """Test phone number validation."""
        with pytest.raises(ValidationError):
            BookAppointmentInput(
                patient={"first": "Test", "last": "User", "phone": "4085551234"},  # Missing +1
                provider_id="prov-001",
                slot={"start": "2025-01-13T09:00:00", "end": "2025-01-13T10:00:00"},
                appointment_type="cleaning",
                location_id="loc-sj",
                idempotency_key="test-key",
            )


class TestSendSms:
    """Tests for send_sms tool."""

    def test_sends_sms(self):
        """Test SMS is queued."""
        input_data = SendSmsInput(
            to="+14085551234",
            message="Your appointment is confirmed!",
        )
        result = send_sms(input_data)

        assert result.queued is True
        assert result.message_id is not None
        assert result.message_id.startswith("sms_")

    def test_sms_log_contains_message(self):
        """Test SMS log contains sent message."""
        input_data = SendSmsInput(
            to="+14085559999",
            message="Test message content",
        )
        send_sms(input_data)

        log = get_sms_log()
        assert len(log) == 1
        assert log[0]["to"] == "+14085559999"
        assert log[0]["message"] == "Test message content"

    def test_phone_validation(self):
        """Test phone validation for SMS."""
        with pytest.raises(ValidationError):
            SendSmsInput(to="invalid", message="Test")

    def test_message_length_validation(self):
        """Test message length validation."""
        with pytest.raises(ValidationError):
            SendSmsInput(to="+14085551234", message="")  # Empty message


class TestExecuteTool:
    """Tests for execute_tool function."""

    def test_execute_unknown_tool(self):
        """Test executing unknown tool returns error."""
        result = execute_tool("unknown_tool", {})
        assert "error" in result
        assert "Unknown tool" in result["error"]

    def test_execute_with_invalid_input(self):
        """Test executing with invalid input returns error."""
        result = execute_tool("check_insurance_coverage", {"payer": ""})
        assert "error" in result

    def test_execute_check_insurance_coverage(self):
        """Test execute_tool for check_insurance_coverage."""
        result = execute_tool(
            "check_insurance_coverage",
            {"payer": "Delta Dental", "plan": "PPO", "procedure_code": "D1110"},
        )
        assert result["covered"] is True
        assert result["copay_estimate"] == 25

    def test_execute_send_sms(self):
        """Test execute_tool for send_sms."""
        result = execute_tool(
            "send_sms",
            {"to": "+14085551234", "message": "Test message"},
        )
        assert result["queued"] is True
