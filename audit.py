"""Audit logging for voice agent calls."""
import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

import structlog

log = structlog.get_logger()

# Audit output directory
AUDIT_DIR = Path(__file__).parent / "sample_outputs"
AUDIT_DIR.mkdir(exist_ok=True)


class AuditLogger:
    """Collects and persists audit data for a single call."""

    def __init__(self, prompt_version: str):
        self.call_id = str(uuid.uuid4())
        self.prompt_version = prompt_version
        self.started_at = datetime.now().isoformat()
        self.ended_at: str | None = None

        self.transcript: list[dict] = []
        self.intents: list[str] = []
        self.slots: dict = {}
        self.tool_trace: list[dict] = []
        self.turns: list[dict] = []  # Turn-level latency tracking
        self.outcome: dict = {
            "booked": False,
            "confirmation_id": None,
            "next_steps": None,
        }
        self._finalized = False
        self._current_turn_start: float | None = None

    def add_transcript(
        self,
        role: Literal["user", "agent"],
        text: str,
    ) -> None:
        """Add a transcript entry."""
        self.transcript.append({
            "role": role,
            "text": text,
            "timestamp": datetime.now().isoformat(),
        })

    def add_intent(self, intent: str) -> None:
        """Add a detected intent (deduplicated)."""
        if intent not in self.intents:
            self.intents.append(intent)

    def start_turn(self) -> None:
        """Mark start of a turn (when user finishes speaking)."""
        self._current_turn_start = time.time()

    def end_turn(self, ttfb_ms: float | None = None) -> None:
        """Mark end of a turn (when agent finishes speaking)."""
        if self._current_turn_start is None:
            return
        turn_latency_ms = (time.time() - self._current_turn_start) * 1000
        self.turns.append({
            "ttfb_ms": round(ttfb_ms, 2) if ttfb_ms else None,
            "turn_latency_ms": round(turn_latency_ms, 2),
        })
        self._current_turn_start = None

    def set_slot(self, name: str, value: str, confidence: float = 1.0) -> None:
        """Set a validated slot value."""
        self.slots[name] = {
            "value": value,
            "confidence": confidence,
            "extracted_at": datetime.now().isoformat(),
        }

    def add_tool_trace(
        self,
        tool: str,
        input: dict,
        output: dict,
        ok: bool,
        duration_ms: float,
    ) -> None:
        """Add a tool execution trace."""
        self.tool_trace.append({
            "tool": tool,
            "input": input,
            "output": output,
            "ok": ok,
            "duration_ms": round(duration_ms, 2),
            "timestamp": datetime.now().isoformat(),
        })

    def set_outcome(
        self,
        booked: bool,
        confirmation_id: str | None = None,
        next_steps: str | None = None,
    ) -> None:
        """Set the call outcome."""
        self.outcome = {
            "booked": booked,
            "confirmation_id": confirmation_id,
            "next_steps": next_steps,
        }

    def finalize(self) -> None:
        """Mark the audit as finalized."""
        self.ended_at = datetime.now().isoformat()
        self._finalized = True

    def to_dict(self) -> dict:
        """Convert audit to dictionary."""
        return {
            "call_id": self.call_id,
            "prompt_version": self.prompt_version,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "transcript": self.transcript,
            "intents": self.intents,
            "slots": self.slots,
            "tool_trace": self.tool_trace,
            "turns": self.turns,
            "outcome": self.outcome,
        }

    def save_sync(self) -> Path:
        """Save audit to JSON file."""
        if not self._finalized:
            self.finalize()

        filename = f"call-{self.call_id[:8]}.json"
        filepath = AUDIT_DIR / filename

        filepath.write_text(json.dumps(self.to_dict(), indent=2))
        log.info("audit_saved", path=str(filepath), call_id=self.call_id)
        return filepath
