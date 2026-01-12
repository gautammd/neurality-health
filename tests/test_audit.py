"""Tests for audit logging."""
import asyncio
import json
import pytest
from pathlib import Path

from audit import AuditLogger, AUDIT_DIR


class TestAuditLogger:
    """Tests for AuditLogger."""

    def test_creates_unique_call_id(self):
        """Test each audit has unique call ID."""
        audit1 = AuditLogger(prompt_version="1.0.0")
        audit2 = AuditLogger(prompt_version="1.0.0")

        assert audit1.call_id != audit2.call_id

    def test_add_transcript(self):
        """Test adding transcript entries."""
        audit = AuditLogger(prompt_version="1.0.0")

        audit.add_transcript("user", "Hello, I need to schedule an appointment")
        audit.add_transcript("agent", "Of course! May I have your name please?")

        assert len(audit.transcript) == 2
        assert audit.transcript[0]["role"] == "user"
        assert audit.transcript[0]["text"] == "Hello, I need to schedule an appointment"
        assert audit.transcript[1]["role"] == "agent"

    def test_add_intent_deduplicates(self):
        """Test intents are deduplicated."""
        audit = AuditLogger(prompt_version="1.0.0")

        audit.add_intent("coverage_check")
        audit.add_intent("book_appointment")
        audit.add_intent("coverage_check")  # Duplicate

        assert audit.intents == ["coverage_check", "book_appointment"]

    def test_set_slot(self):
        """Test setting validated slots."""
        audit = AuditLogger(prompt_version="1.0.0")

        audit.set_slot("patient_first", "John", confidence=0.95)
        audit.set_slot("phone", "+14085551234", confidence=1.0)

        assert audit.slots["patient_first"]["value"] == "John"
        assert audit.slots["patient_first"]["confidence"] == 0.95
        assert audit.slots["phone"]["value"] == "+14085551234"

    def test_add_tool_trace(self):
        """Test adding tool execution traces."""
        audit = AuditLogger(prompt_version="1.0.0")

        audit.add_tool_trace(
            tool="check_insurance_coverage",
            input={"payer": "Delta Dental", "plan": "PPO"},
            output={"covered": True, "copay_estimate": 25},
            ok=True,
            duration_ms=150.5,
        )

        assert len(audit.tool_trace) == 1
        assert audit.tool_trace[0]["tool"] == "check_insurance_coverage"
        assert audit.tool_trace[0]["ok"] is True
        assert audit.tool_trace[0]["duration_ms"] == 150.5

    def test_set_outcome(self):
        """Test setting call outcome."""
        audit = AuditLogger(prompt_version="1.0.0")

        audit.set_outcome(
            booked=True,
            confirmation_id="ABC123",
            next_steps="SMS confirmation sent",
        )

        assert audit.outcome["booked"] is True
        assert audit.outcome["confirmation_id"] == "ABC123"
        assert audit.outcome["next_steps"] == "SMS confirmation sent"

    def test_to_dict(self):
        """Test converting audit to dictionary."""
        audit = AuditLogger(prompt_version="1.0.0")
        audit.add_transcript("user", "Hello")
        audit.add_intent("greeting")
        audit.finalize()

        result = audit.to_dict()

        assert "call_id" in result
        assert "prompt_version" in result
        assert result["prompt_version"] == "1.0.0"
        assert "transcript" in result
        assert "intents" in result
        assert "slots" in result
        assert "tool_trace" in result
        assert "outcome" in result
        assert result["ended_at"] is not None

    @pytest.mark.asyncio
    async def test_save_creates_file(self, tmp_path, monkeypatch):
        """Test saving audit creates JSON file."""
        # Use temp directory for tests
        monkeypatch.setattr("audit.AUDIT_DIR", tmp_path)

        audit = AuditLogger(prompt_version="1.0.0")
        audit.add_transcript("user", "Test message")
        audit.set_outcome(booked=False)

        filepath = await audit.save()

        assert filepath.exists()
        with open(filepath) as f:
            data = json.load(f)
        assert data["call_id"] == audit.call_id
        assert data["transcript"][0]["text"] == "Test message"

    def test_finalize_sets_ended_at(self):
        """Test finalize sets ended_at timestamp."""
        audit = AuditLogger(prompt_version="1.0.0")
        assert audit.ended_at is None

        audit.finalize()

        assert audit.ended_at is not None
        assert audit._finalized is True
