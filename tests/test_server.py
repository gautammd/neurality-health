"""Tests for FastAPI webhook server."""
import pytest
from fastapi.testclient import TestClient

from server import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_returns_healthy(self, client):
        """Test health endpoint returns healthy status."""
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestVoiceWebhook:
    """Tests for Twilio voice webhook."""

    def test_returns_twiml(self, client):
        """Test voice webhook returns valid TwiML."""
        response = client.post(
            "/voice",
            data={
                "From": "+14085551234",
                "To": "+18005551234",
                "CallSid": "CA12345",
            },
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/xml"
        assert "<?xml version" in response.text
        assert "<Response>" in response.text

    def test_includes_sip_dial(self, client):
        """Test TwiML includes SIP dial."""
        response = client.post(
            "/voice",
            data={
                "From": "+14085551234",
                "To": "+18005551234",
                "CallSid": "CA67890",
            },
        )

        assert "<Dial>" in response.text
        assert "<Sip>" in response.text
        assert "call-CA67890" in response.text

    def test_includes_welcome_message(self, client):
        """Test TwiML includes welcome message."""
        response = client.post("/voice", data={})

        assert "<Say>" in response.text
        assert "connect" in response.text.lower()


class TestVoiceStatusWebhook:
    """Tests for Twilio call status webhook."""

    def test_returns_success(self, client):
        """Test status webhook returns success."""
        response = client.post(
            "/voice/status",
            data={
                "CallSid": "CA12345",
                "CallStatus": "completed",
            },
        )

        assert response.status_code == 200
        assert response.json() == {"received": True}


class TestVoiceFallback:
    """Tests for fallback webhook."""

    def test_returns_error_twiml(self, client):
        """Test fallback returns error TwiML."""
        response = client.post("/voice/fallback")

        assert response.status_code == 200
        assert "<Say>" in response.text
        assert "technical difficulties" in response.text.lower()
        assert "<Hangup/>" in response.text


class TestVoiceStreamWebhook:
    """Tests for Media Streams webhook."""

    def test_returns_stream_twiml(self, client):
        """Test stream webhook returns Stream TwiML."""
        response = client.post(
            "/voice/stream",
            data={
                "From": "+14085551234",
                "CallSid": "CA99999",
            },
        )

        assert response.status_code == 200
        assert "<Connect>" in response.text
        assert "<Stream" in response.text
        assert "CA99999" in response.text
