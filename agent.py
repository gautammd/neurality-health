"""LiveKit Voice Agent for Neurality Health."""
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

from livekit import agents, rtc, api
from livekit.agents import Agent, AgentSession, AgentServer, RoomInputOptions, get_job_context
from livekit.plugins import deepgram, openai, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

import structlog
from mcp_client import call_mcp_tool, get_metrics as get_mcp_metrics
from audit import AuditLogger

load_dotenv()
log = structlog.get_logger()

# Load prompts
PROMPTS_PATH = Path(__file__).parent / "prompts" / "manifest.json"
with open(PROMPTS_PATH) as f:
    PROMPTS = json.load(f)

SYSTEM_PROMPT = PROMPTS["prompts"]["system"]["content"]
PROMPT_VERSION = PROMPTS["prompts"]["system"]["version"]


class HealthAssistant(Agent):
    """Voice assistant for Neurality Health."""

    def __init__(self, audit: AuditLogger) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)
        self.audit = audit

    @agents.function_tool()
    async def check_insurance_coverage(
        self,
        payer: str,
        plan: str,
        procedure_code: str,
    ) -> str:
        """Check if insurance covers a dental procedure.

        Args:
            payer: Insurance company name (e.g., Delta Dental, Cigna, Aetna)
            plan: Plan type (e.g., PPO, HMO, DMO)
            procedure_code: Dental procedure code (e.g., D1110 for cleaning)
        """
        start_time = datetime.now()
        result = await call_mcp_tool("check_insurance_coverage", {
            "payer": payer,
            "plan": plan,
            "procedure_code": procedure_code,
        })
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000

        self.audit.add_tool_trace(
            tool="check_insurance_coverage",
            input={"payer": payer, "plan": plan, "procedure_code": procedure_code},
            output=result,
            ok="error" not in result,
            duration_ms=duration_ms,
        )
        self.audit.add_intent("coverage_check")

        if result.get("covered"):
            return f"Yes, {payer} {plan} covers this procedure. The copay is ${result['copay_estimate']}. {result.get('notes', '')}"
        else:
            return f"Unfortunately, this procedure is not covered. {result.get('notes', '')}"

    @agents.function_tool()
    async def get_provider_availability(
        self,
        location_id: str,
        appointment_type: str,
        start_date: str = "",
        end_date: str = "",
    ) -> str:
        """Get available appointment slots.

        Args:
            location_id: Location ID (loc-sj for San Jose, loc-sf for San Francisco, loc-oak for Oakland)
            appointment_type: Type of appointment (cleaning, checkup, consultation)
            start_date: Start date YYYY-MM-DD (optional, defaults to today)
            end_date: End date YYYY-MM-DD (optional, defaults to 7 days from now)
        """
        if not start_date:
            start_date = datetime.now().strftime("%Y-%m-%d")
        if not end_date:
            end_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

        start_time = datetime.now()
        result = await call_mcp_tool("get_provider_availability", {
            "location_id": location_id,
            "provider_id": "prov-001",
            "date_range": {"start": start_date, "end": end_date},
            "appointment_type": appointment_type,
        })
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000

        self.audit.add_tool_trace(
            tool="get_provider_availability",
            input={"location_id": location_id, "appointment_type": appointment_type},
            output=result,
            ok="error" not in result,
            duration_ms=duration_ms,
        )
        self.audit.add_intent("check_availability")

        slots = result.get("slots", [])
        if not slots:
            return "I couldn't find any available slots for that time period."

        slot_descriptions = []
        for slot in slots[:5]:
            dt = datetime.fromisoformat(slot["start"].replace("Z", ""))
            slot_descriptions.append(dt.strftime("%A %B %d at %I:%M %p"))

        return f"I found these available times: {', '.join(slot_descriptions)}. Which works best for you?"

    @agents.function_tool()
    async def book_appointment(
        self,
        patient_first: str,
        patient_last: str,
        patient_phone: str,
        slot_start: str,
        slot_end: str,
        appointment_type: str,
        location_id: str,
    ) -> str:
        """Book an appointment.

        Args:
            patient_first: Patient's first name
            patient_last: Patient's last name
            patient_phone: Patient's phone number in E.164 format (+1XXXXXXXXXX)
            slot_start: Appointment start time (ISO format)
            slot_end: Appointment end time (ISO format)
            appointment_type: Type of appointment
            location_id: Location ID
        """
        idempotency_key = f"{self.audit.call_id}-{datetime.now().timestamp()}"

        start_time = datetime.now()
        result = await call_mcp_tool("book_appointment", {
            "patient": {
                "first": patient_first,
                "last": patient_last,
                "phone": patient_phone,
            },
            "provider_id": "prov-001",
            "slot": {"start": slot_start, "end": slot_end},
            "appointment_type": appointment_type,
            "location_id": location_id,
            "idempotency_key": idempotency_key,
        })
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000

        self.audit.add_tool_trace(
            tool="book_appointment",
            input={"patient_first": patient_first, "location_id": location_id},
            output=result,
            ok=result.get("status") == "booked",
            duration_ms=duration_ms,
        )
        self.audit.add_intent("book_appointment")

        if result.get("status") == "booked":
            self.audit.set_outcome(
                booked=True,
                confirmation_id=result["confirmation_id"],
                next_steps="SMS confirmation pending",
            )
            return f"Your appointment is confirmed! Confirmation number: {result['confirmation_id']}. Would you like me to send a confirmation text?"
        else:
            return f"I'm sorry, I couldn't book that appointment. {result.get('reason', 'Please try a different time.')}"

    @agents.function_tool()
    async def send_sms(self, to: str, message: str) -> str:
        """Send SMS confirmation.

        Args:
            to: Phone number in E.164 format (+1XXXXXXXXXX)
            message: SMS message content
        """
        start_time = datetime.now()
        result = await call_mcp_tool("send_sms", {"to": to, "message": message})
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000

        self.audit.add_tool_trace(
            tool="send_sms",
            input={"to": to[-4:], "message_length": len(message)},
            output=result,
            ok=result.get("queued", False),
            duration_ms=duration_ms,
        )
        self.audit.add_intent("send_sms")

        if result.get("queued"):
            self.audit.outcome["next_steps"] = "SMS sent"
            return "I've sent the confirmation text to your phone."
        else:
            return "I wasn't able to send the text message, but your appointment is still confirmed."

    @agents.function_tool()
    async def end_call(self) -> str:
        """End the call. Use this when the conversation is complete and the user says goodbye."""
        ctx = get_job_context()
        if ctx is None:
            return "Unable to end call"

        log.info("ending_call", call_id=self.audit.call_id)
        self.audit.add_intent("end_call")

        # Delete the room to end the call
        try:
            await ctx.api.room.delete_room(
                api.DeleteRoomRequest(room=ctx.room.name)
            )
            return "Call ended"
        except Exception as e:
            log.error("end_call_failed", error=str(e))
            return "Unable to end call"


# Create server
server = AgentServer()


@server.rtc_session(agent_name="health-agent")
async def entrypoint(ctx: agents.JobContext):
    """Main entrypoint for the voice agent."""
    log.info("agent_starting", room=ctx.room.name)

    # Create audit logger
    audit = AuditLogger(prompt_version=PROMPT_VERSION)
    log.info("call_started", call_id=audit.call_id)

    # Create agent with tools
    assistant = HealthAssistant(audit=audit)

    # Create session with Deepgram STT/TTS and OpenAI LLM
    session = AgentSession(
        stt=deepgram.STT(),
        llm=openai.LLM(model="gpt-4o"),
        tts=deepgram.TTS(),
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
    )

    # Track transcripts
    @session.on("user_input_transcribed")
    def on_user_speech(event):
        # Event is UserInputTranscribedEvent, extract transcript text
        text = event.transcript if hasattr(event, 'transcript') else str(event)
        if event.is_final if hasattr(event, 'is_final') else True:
            audit.add_transcript("user", text)
            log.debug("user_speech", text=text)

    @session.on("agent_speech_committed")
    def on_agent_speech(message):
        # Message may be AgentSpeechEvent or string
        text = message.content if hasattr(message, 'content') else str(message)
        audit.add_transcript("agent", text)
        log.debug("agent_speech", text=text)

    # Save audit when session closes
    @session.on("close")
    def on_session_close():
        audit.finalize()
        audit.save_sync()
        log.info("call_ended", call_id=audit.call_id)

    # Start session
    await session.start(
        room=ctx.room,
        agent=assistant,
    )

    # Initial greeting
    await session.generate_reply(
        instructions="Greet the user warmly. Say: Hello! Thank you for calling Neurality Health. I can help you check insurance coverage and schedule an appointment. May I have your name please?"
    )


if __name__ == "__main__":
    agents.cli.run_app(server)
